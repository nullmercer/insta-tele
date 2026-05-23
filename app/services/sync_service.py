import asyncio
import logging

from telegram import InputMediaPhoto, InputMediaVideo
from telegram.error import RetryAfter

from ..config import settings
from ..database import models
from ..instagram.client import InstagramClient, InstagramSessionError, InstagramChallengeError

logger = logging.getLogger(__name__)

INITIAL_PAGE_SIZE = 33
INCREMENTAL_PAGE_SIZE = 20


class SyncService:
    def __init__(self, bot, insta_client=None):
        self.bot = bot
        self.insta_client = insta_client or InstagramClient()
        self._account_locks = {}
        self._stop_events = {}

    async def sync_all_accounts(self):
        accounts = models.get_tracked_accounts()
        logger.info(f"Starting sync for {len(accounts)} accounts")
        for username in accounts:
            try:
                await self.sync_account(username)
            except InstagramSessionError as exc:
                logger.error(f"Critical Instagram session error: {exc}. Stopping sync for all accounts.")
                break
            except Exception as exc:
                logger.error(f"Unexpected error syncing @{username}: {exc}")
                continue

    async def sync_account(self, username):
        lock = self._account_locks.setdefault(username, asyncio.Lock())
        async with lock:
            # Create a fresh stop event for this sync run
            stop_event = self._stop_events.setdefault(username, asyncio.Event())
            stop_event.clear()
            
            try:
                if models.is_initial_sync_completed(username):
                    return await self.incremental_sync(username)
                return await self.initial_full_sync(username)
            except InstagramSessionError:
                raise
            except Exception as exc:
                logger.exception(f"Sync failed for @{username}: {exc}")
                return False
            finally:
                # Cleanup stop event if no one else is waiting on it
                if username in self._stop_events and not stop_event.is_set():
                    del self._stop_events[username]

    def stop_sync(self, username):
        """Signal an active sync for a username to stop."""
        if username in self._stop_events:
            self._stop_events[username].set()
            logger.info(f"Signal sent to stop sync for @{username}")

    def _is_stopped(self, username):
        event = self._stop_events.get(username)
        return event.is_set() if event else False

    def _get_or_cache_user_id(self, username):
        user_id = models.get_instagram_user_id(username)
        if user_id:
            return user_id

        user_id = self.insta_client.get_instagram_user_id(username)
        models.save_instagram_user_id(username, user_id)
        return user_id

    async def get_or_create_forum_topic(self, username):
        if not settings.TELEGRAM_GROUP_ID:
            return settings.TELEGRAM_CHANNEL_ID, None
        
        thread_id = models.get_thread_id(username)
        if thread_id is not None:
            return settings.TELEGRAM_GROUP_ID, thread_id
            
        topic = await self.bot.create_forum_topic(
            chat_id=settings.TELEGRAM_GROUP_ID,
            name=f"@{username}"
        )
        models.save_thread_id(username, topic.message_thread_id)
        return settings.TELEGRAM_GROUP_ID, topic.message_thread_id

    async def initial_full_sync(self, username):
        logger.info(f"Starting initial full archive for @{username}")
        user_id = self._get_or_cache_user_id(username)
        posts = self.insta_client.get_all_profile_posts(
            user_id,
            page_size=INITIAL_PAGE_SIZE,
        )

        archived_count = 0
        failed_count = 0
        for post in reversed(posts):
            if self._is_stopped(username):
                logger.info(f"Stop signal received; aborting initial sync for @{username}")
                return False
                
            if models.has_telegram_file_id(post.shortcode):
                continue
            try:
                if await self.archive_post(post, username):
                    archived_count += 1
                    await asyncio.sleep(2)
            except Exception as exc:
                failed_count += 1
                logger.error(
                    f"Failed to archive initial post {post.shortcode} "
                    f"from @{username}: {exc}"
                )

        if failed_count:
            logger.warning(
                f"Initial archive for @{username} is incomplete: "
                f"{failed_count} posts failed"
            )
            return False

        models.mark_initial_sync_completed(username)
        logger.info(
            f"Initial archive completed for @{username}; "
            f"{archived_count} new posts stored"
        )
        return True

    async def incremental_sync(self, username):
        logger.info(f"Starting incremental sync for @{username}")
        user_id = self._get_or_cache_user_id(username)
        new_posts = []
        end_cursor = ""
        reached_archive_boundary = False

        while True:
            posts, next_cursor = self.insta_client.get_post_page(
                user_id,
                amount=INCREMENTAL_PAGE_SIZE,
                end_cursor=end_cursor,
            )
            for post in posts:
                if models.has_telegram_file_id(post.shortcode):
                    reached_archive_boundary = True
                    break
                new_posts.append(post)

            if reached_archive_boundary or not next_cursor or next_cursor == end_cursor:
                break
            end_cursor = next_cursor

        failed_count = 0
        archived_count = 0
        for post in reversed(new_posts):
            if self._is_stopped(username):
                logger.info(f"Stop signal received; aborting incremental sync for @{username}")
                return False

            try:
                if await self.archive_post(post, username):
                    archived_count += 1
                    await asyncio.sleep(2)
            except Exception as exc:
                failed_count += 1
                logger.error(
                    f"Failed to archive incremental post {post.shortcode} "
                    f"from @{username}: {exc}"
                )

        if failed_count:
            return False

        models.mark_account_synced(username)
        logger.info(f"Incremental sync completed for @{username}: {archived_count} new posts")
        return True

    async def _call_telegram(self, func, *args, **kwargs):
        """Helper to call Telegram methods with RetryAfter support."""
        while True:
            try:
                return await func(*args, **kwargs)
            except RetryAfter as exc:
                logger.warning(f"Flood control: sleeping for {exc.retry_after}s")
                await asyncio.sleep(exc.retry_after + 1)
            except Exception as exc:
                # If a thread/topic was deleted, we need to handle it in the caller
                # by catching 'Message thread not found'
                raise

    async def archive_post(self, post, username):
        if models.has_telegram_file_id(post.shortcode):
            logger.info(f"Skipping previously archived post {post.shortcode}")
            return False

        media_items = self.insta_client.get_post_media_urls(post)
        if not media_items:
            raise RuntimeError("No downloadable media URLs returned")

        chat_id, message_thread_id = await self.get_or_create_forum_topic(username)
        
        async def perform_upload():
            send_kwargs = {
                "chat_id": chat_id,
                "read_timeout": 120,
                "write_timeout": 120,
                "connect_timeout": 60
            }
            if message_thread_id is not None:
                send_kwargs["message_thread_id"] = message_thread_id

            caption = f"@{username}"
            file_ids = []

            if len(media_items) == 1:
                item = media_items[0]
                media_file = self.insta_client.download_media(item["url"])
                if not media_file:
                    raise RuntimeError("Failed to download media")

                if item["type"] == "video":
                    msg = await self._call_telegram(
                        self.bot.send_video,
                        video=media_file,
                        caption=caption,
                        **send_kwargs,
                    )
                    file_ids.append(msg.video.file_id)
                else:
                    msg = await self._call_telegram(
                        self.bot.send_photo,
                        photo=media_file,
                        caption=caption,
                        **send_kwargs,
                    )
                    file_ids.append(msg.photo[-1].file_id)
            else:
                chunk_size = 10
                for i in range(0, len(media_items), chunk_size):
                    chunk = media_items[i : i + chunk_size]
                    media_group = []
                    for index, item in enumerate(chunk):
                        media_file = self.insta_client.download_media(item["url"])
                        if not media_file:
                            raise RuntimeError(f"Failed to download carousel media in chunk {i//chunk_size}")

                        item_caption = caption if (i == 0 and index == 0) else None
                        if item["type"] == "video":
                            media_group.append(InputMediaVideo(media_file, caption=item_caption))
                        else:
                            media_group.append(InputMediaPhoto(media_file, caption=item_caption))

                    msgs = await self._call_telegram(
                        self.bot.send_media_group,
                        media=media_group,
                        **send_kwargs,
                    )
                    for msg in msgs:
                        if getattr(msg, "photo", None):
                            file_ids.append(msg.photo[-1].file_id)
                        elif getattr(msg, "video", None):
                            file_ids.append(msg.video.file_id)
            return file_ids

        try:
            file_ids = await perform_upload()
        except Exception as e:
            if "message thread not found" in str(e).lower() and message_thread_id is not None:
                logger.warning(f"Thread {message_thread_id} for @{username} not found (likely deleted). Recreating...")
                models.save_thread_id(username, None)
                # Refresh thread info and retry once
                new_chat_id, new_thread_id = await self.get_or_create_forum_topic(username)
                chat_id, message_thread_id = new_chat_id, new_thread_id
                file_ids = await perform_upload()
            else:
                raise

        models.save_archived_post(
            shortcode=post.shortcode,
            username=username,
            telegram_file_id=",".join(file_ids) if file_ids else None,
            media_type=post.typename,
            caption=post.caption,
            timestamp=post.date_utc,
        )
        logger.info(f"Archived post {post.shortcode} from @{username}")
        return True
