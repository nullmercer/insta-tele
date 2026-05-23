# Persistent Instagram Archive Sync

## Architecture

The durable sync boundary is SQLite, not process memory:

```text
/track or scheduler
        |
        v
tracked_accounts.initial_sync_completed
        |
        +-- 0: initial_full_sync(username)
        |      resolve/cache Instagram user id
        |      paginate entire profile
        |      reverse newest-first API results
        |      upload oldest -> newest
        |      persist each archived_posts.shortcode + Telegram file ids
        |      mark initial_sync_completed only after every upload succeeds
        |
        +-- 1: incremental_sync(username)
               read cached Instagram user id
               request recent page(s), 20 items per page
               stop at first archived_posts.shortcode
               upload unseen posts oldest -> newest
               update last_synced_at
```

`archived_posts.shortcode` is the durable deduplication key. A row is considered
fully archived when it also contains a Telegram file ID. This matters during
migration from older versions, which could insert a shortcode before Telegram
accepted its upload. A restarted bot or repeated `/track username` command
does not upload completed rows again and retries incomplete legacy rows.

The application creates one `SyncService` instance and shares it between
command handlers and the scheduler. Its per-account async lock prevents two
in-process sync triggers from uploading the same account concurrently.

## Database Migration

New installations create `tracked_accounts` with the state fields included.
For an existing database, the equivalent migration SQL is:

```sql
ALTER TABLE tracked_accounts ADD COLUMN instagram_user_id TEXT;
ALTER TABLE tracked_accounts
    ADD COLUMN initial_sync_completed INTEGER NOT NULL DEFAULT 0;
ALTER TABLE tracked_accounts ADD COLUMN last_synced_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_archived_posts_username_timestamp
    ON archived_posts (username, timestamp);
```

`init_db()` performs this migration conditionally with `PRAGMA table_info`, so
the bot can start against an already deployed SQLite file without dropping
columns added by local deployments.

Existing tracked accounts default to `initial_sync_completed = 0`. Their first
sync after migration walks the available history once, skips shortcodes
already present with Telegram file IDs in `archived_posts`, retries legacy rows
whose Telegram file IDs are blank, fills any historical gaps left by the old
50-post cap, and then stores completion state.

## Implemented Helpers

The database module provides:

```python
is_post_archived(shortcode)
has_archived_posts(username)
mark_initial_sync_completed(username)
get_instagram_user_id(username)
save_archived_post(...)
```

It also exposes `has_telegram_file_id()`, `save_instagram_user_id()`,
`is_initial_sync_completed()`, and `mark_account_synced()` for the sync
coordinator.

## Instagrapi Pagination

The initial sync uses the cursor returned by `instagrapi` until the profile is
exhausted:

```python
end_cursor = ""
posts = []

while True:
    medias, next_cursor = client.user_medias_paginated(
        user_id,
        amount=33,
        end_cursor=end_cursor,
    )
    posts.extend(medias)  # returned newest -> oldest
    if not next_cursor or next_cursor == end_cursor or not medias:
        break
    end_cursor = next_cursor

for media in reversed(posts):
    await archive(media)  # oldest -> newest
```

For an established account, incremental sync requests 20 posts first. If a
high-volume account produced more than 20 posts between polls, it continues in
20-item pages only until an existing shortcode is reached; this avoids missing
posts while keeping normal polling to one small request.

## Restart-Safe Workflow

1. `/track username` inserts the account if it is new and schedules
   `sync_account(username)`.
2. An incomplete account runs `initial_full_sync()`. Uploaded posts are stored
   immediately after Telegram returns their file IDs.
3. If an upload fails, completion is not set. A later invocation resumes by
   skipping already persisted shortcodes and retrying work that was not saved.
4. After success, `initial_sync_completed = 1` and `last_synced_at` is set.
5. Scheduler runs and repeated `/track` calls use `incremental_sync()` only.
6. A process restart reopens the same SQLite file and follows the same stored
   state; it does not initiate historical uploads for completed accounts.

## Efficient Polling

- Poll completed accounts every 10 to 30 minutes unless near-real-time archive
  delivery is required.
- Keep incremental pages at 20 items and paginate only when no known shortcode
  is present in the first page.
- Stagger large sets of tracked accounts or add jitter to reduce burst traffic
  against Instagram and Telegram.
- Run initial archives deliberately; a profile with years of media is expected
  to require more API calls and Telegram uploads than ordinary polling.

## Production Notes

- Preserve `data/archive.db` on a durable volume and back it up; it contains
  both deduplication history and Telegram file IDs.
- Protect the Instagram session file and bot token as credentials.
- Use only one bot process against a SQLite archive unless a database-backed
  work claim is added; the current async lock coordinates one running process.
- Telegram upload followed by database commit has an unavoidable narrow crash
  window: if the process dies after Telegram accepts media but before SQLite
  commits the shortcode, a retry can duplicate that upload. Eliminating this
  fully requires an external idempotency/reconciliation design, such as
  storing and matching Telegram channel message identifiers.
- Monitor authentication failures and Instagram throttling; increase poll
  intervals rather than aggressively retrying.
