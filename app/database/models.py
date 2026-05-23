import sqlite3

from ..config import settings


def get_db_connection():
    conn = sqlite3.connect(settings.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(conn, table, column, definition):
    columns = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tracked_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                instagram_user_id TEXT,
                initial_sync_completed INTEGER NOT NULL DEFAULT 0,
                last_synced_at TIMESTAMP,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migrate existing SQLite files without dropping local extension columns.
        _ensure_column(conn, "tracked_accounts", "instagram_user_id", "TEXT")
        _ensure_column(
            conn,
            "tracked_accounts",
            "initial_sync_completed",
            "INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(conn, "tracked_accounts", "last_synced_at", "TIMESTAMP")
        _ensure_column(conn, "tracked_accounts", "thread_id", "INTEGER")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS archived_posts (
                shortcode TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                telegram_file_id TEXT,
                media_type TEXT,
                caption TEXT,
                timestamp TIMESTAMP,
                archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (username) REFERENCES tracked_accounts (username)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                telegram_user_id INTEGER PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_archived_posts_username_timestamp "
            "ON archived_posts (username, timestamp)"
        )
        conn.commit()


def add_tracked_account(username):
    with get_db_connection() as conn:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO tracked_accounts (username) VALUES (?)",
            (username,),
        )
        conn.commit()
        return cursor.rowcount > 0


def remove_tracked_account(username):
    with get_db_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM tracked_accounts WHERE username = ?",
            (username,),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_tracked_accounts():
    with get_db_connection() as conn:
        rows = conn.execute("SELECT username FROM tracked_accounts").fetchall()
        return [row["username"] for row in rows]


def get_tracked_account(username):
    with get_db_connection() as conn:
        return conn.execute(
            "SELECT * FROM tracked_accounts WHERE username = ?",
            (username,),
        ).fetchone()


def is_post_archived(shortcode):
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM archived_posts WHERE shortcode = ?",
            (shortcode,),
        ).fetchone()
        return row is not None


def has_telegram_file_id(shortcode):
    with get_db_connection() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM archived_posts
            WHERE shortcode = ?
              AND telegram_file_id IS NOT NULL
              AND telegram_file_id <> ''
            """,
            (shortcode,),
        ).fetchone()
        return row is not None


def has_archived_posts(username):
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM archived_posts WHERE username = ? LIMIT 1",
            (username,),
        ).fetchone()
        return row is not None


def get_instagram_user_id(username):
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT instagram_user_id FROM tracked_accounts WHERE username = ?",
            (username,),
        ).fetchone()
        return row["instagram_user_id"] if row else None


def save_instagram_user_id(username, instagram_user_id):
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE tracked_accounts SET instagram_user_id = ? WHERE username = ?",
            (str(instagram_user_id), username),
        )
        conn.commit()


def get_thread_id(username):
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT thread_id FROM tracked_accounts WHERE username = ?",
            (username,),
        ).fetchone()
        return row["thread_id"] if row else None


def save_thread_id(username, thread_id):
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE tracked_accounts SET thread_id = ? WHERE username = ?",
            (thread_id, username),
        )
        conn.commit()


def is_initial_sync_completed(username):
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT initial_sync_completed FROM tracked_accounts WHERE username = ?",
            (username,),
        ).fetchone()
        return bool(row and row["initial_sync_completed"])


def mark_initial_sync_completed(username):
    with get_db_connection() as conn:
        conn.execute(
            """
            UPDATE tracked_accounts
            SET initial_sync_completed = 1,
                last_synced_at = CURRENT_TIMESTAMP
            WHERE username = ?
            """,
            (username,),
        )
        conn.commit()


def mark_account_synced(username):
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE tracked_accounts SET last_synced_at = CURRENT_TIMESTAMP "
            "WHERE username = ?",
            (username,),
        )
        conn.commit()


def save_archived_post(
    shortcode,
    username,
    telegram_file_id,
    media_type,
    caption,
    timestamp,
):
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO archived_posts
                (shortcode, username, telegram_file_id, media_type, caption, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(shortcode) DO UPDATE SET
                telegram_file_id = COALESCE(
                    excluded.telegram_file_id,
                    archived_posts.telegram_file_id
                ),
                media_type = excluded.media_type,
                caption = excluded.caption,
                timestamp = excluded.timestamp
            """,
            (shortcode, username, telegram_file_id, media_type, caption, timestamp),
        )
        conn.commit()


def get_stats():
    with get_db_connection() as conn:
        accounts_count = conn.execute(
            "SELECT COUNT(*) FROM tracked_accounts"
        ).fetchone()[0]
        posts_count = conn.execute("SELECT COUNT(*) FROM archived_posts").fetchone()[0]
        last_sync = conn.execute(
            "SELECT MAX(last_synced_at) FROM tracked_accounts"
        ).fetchone()[0]

        return {
            "accounts_count": accounts_count,
            "posts_count": posts_count,
            "last_sync": last_sync,
        }
