import io
import os
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.config import settings
from app.database import models
from app.services.sync_service import SyncService


class FakePost:
    def __init__(self, shortcode):
        self.shortcode = shortcode
        self.typename = "GraphImage"
        self.caption = None
        self.date_utc = f"2026-05-0{shortcode[-1]} 00:00:00"


class FakeInstagramClient:
    def __init__(self, all_posts=None, pages=None):
        self.all_posts = all_posts or []
        self.pages = pages or {}
        self.user_id_lookups = 0
        self.page_calls = []

    def get_instagram_user_id(self, username):
        self.user_id_lookups += 1
        return "ig-123"

    def get_all_profile_posts(self, user_id, page_size):
        return self.all_posts

    def get_post_page(self, user_id, amount, end_cursor=""):
        self.page_calls.append((user_id, amount, end_cursor))
        return self.pages.get(end_cursor, ([], ""))

    def get_post_media_urls(self, post):
        return [{"url": post.shortcode, "type": "image"}]

    def download_media(self, url):
        return io.BytesIO(url.encode("ascii"))


class FakeBot:
    def __init__(self):
        self.sent = []
        self.topics_created = []

    async def create_forum_topic(self, chat_id, name, **kwargs):
        self.topics_created.append((chat_id, name))
        return SimpleNamespace(message_thread_id=999)

    async def send_photo(self, chat_id, photo, caption, **kwargs):
        shortcode = photo.getvalue().decode("ascii")
        self.sent.append({
            "shortcode": shortcode,
            "chat_id": chat_id,
            "message_thread_id": kwargs.get("message_thread_id")
        })
        return SimpleNamespace(photo=[SimpleNamespace(file_id=f"tg-{shortcode}")])


class FailingBot(FakeBot):
    def __init__(self, fail_shortcode):
        super().__init__()
        self.fail_shortcode = fail_shortcode

    async def send_photo(self, chat_id, photo, caption, **kwargs):
        shortcode = photo.getvalue().decode("ascii")
        if shortcode == self.fail_shortcode:
            raise RuntimeError("Telegram rejected upload")
        return await super().send_photo(chat_id, photo, caption, **kwargs)


class PersistentSyncTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_database_path = settings.DATABASE_PATH
        settings.DATABASE_PATH = os.path.join(self.temp_dir.name, "archive.db")

    def tearDown(self):
        settings.DATABASE_PATH = self.old_database_path
        self.temp_dir.cleanup()

    def test_init_db_migrates_existing_account_table(self):
        with sqlite3.connect(settings.DATABASE_PATH) as conn:
            conn.execute(
                """
                CREATE TABLE tracked_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    thread_id INTEGER
                )
                """
            )

        models.init_db()
        with models.get_db_connection() as conn:
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(tracked_accounts)").fetchall()
            }

        self.assertIn("thread_id", columns)
        self.assertIn("instagram_user_id", columns)
        self.assertIn("initial_sync_completed", columns)
        self.assertIn("last_synced_at", columns)

    async def test_initial_archive_and_restart_safe_incremental_sync(self):
        models.init_db()
        models.add_tracked_account("example")
        initial_client = FakeInstagramClient(
            all_posts=[FakePost("post3"), FakePost("post2"), FakePost("post1")]
        )
        bot = FakeBot()

        with patch("app.services.sync_service.asyncio.sleep", new=AsyncMock()):
            result = await SyncService(bot, initial_client).sync_account("example")

        self.assertTrue(result)
        self.assertEqual([s["shortcode"] for s in bot.sent], ["post1", "post2", "post3"])
        self.assertTrue(models.is_initial_sync_completed("example"))
        self.assertEqual(models.get_instagram_user_id("example"), "ig-123")
        self.assertEqual(initial_client.user_id_lookups, 1)

        restart_client = FakeInstagramClient(
            pages={"": ([FakePost("post4"), FakePost("post3")], "")}
        )
        with patch("app.services.sync_service.asyncio.sleep", new=AsyncMock()):
            result = await SyncService(bot, restart_client).sync_account("example")

        self.assertTrue(result)
        self.assertEqual([s["shortcode"] for s in bot.sent], ["post1", "post2", "post3", "post4"])
        self.assertEqual(restart_client.user_id_lookups, 0)
        self.assertEqual(restart_client.page_calls, [("ig-123", 20, "")])
        self.assertTrue(models.is_post_archived("post4"))

    async def test_incremental_sync_paginates_until_existing_shortcode(self):
        models.init_db()
        models.add_tracked_account("example")
        models.save_instagram_user_id("example", "ig-123")
        models.save_archived_post("old", "example", "tg-old", "GraphImage", None, None)
        models.mark_initial_sync_completed("example")
        client = FakeInstagramClient(
            pages={
                "": ([FakePost("post3"), FakePost("post2")], "cursor"),
                "cursor": ([FakePost("post1"), FakePost("old")], ""),
            }
        )
        bot = FakeBot()

        with patch("app.services.sync_service.asyncio.sleep", new=AsyncMock()):
            result = await SyncService(bot, client).sync_account("example")

        self.assertTrue(result)
        self.assertEqual([s["shortcode"] for s in bot.sent], ["post1", "post2", "post3"])
        self.assertEqual(len(client.page_calls), 2)

    async def test_initial_sync_is_not_completed_after_failed_upload(self):
        models.init_db()
        models.add_tracked_account("example")
        client = FakeInstagramClient(
            all_posts=[FakePost("post2"), FakePost("post1")]
        )

        with patch("app.services.sync_service.asyncio.sleep", new=AsyncMock()):
            result = await SyncService(FailingBot("post2"), client).sync_account("example")

        self.assertFalse(result)
        self.assertTrue(models.is_post_archived("post1"))
        self.assertFalse(models.is_post_archived("post2"))
        self.assertFalse(models.is_initial_sync_completed("example"))

    async def test_initial_sync_retries_legacy_row_without_telegram_file_id(self):
        models.init_db()
        models.add_tracked_account("example")
        models.save_archived_post("post1", "example", None, "GraphImage", None, None)
        client = FakeInstagramClient(all_posts=[FakePost("post1")])
        bot = FakeBot()

        with patch("app.services.sync_service.asyncio.sleep", new=AsyncMock()):
            result = await SyncService(bot, client).sync_account("example")

        self.assertTrue(result)
        self.assertEqual([s["shortcode"] for s in bot.sent], ["post1"])
        self.assertTrue(models.has_telegram_file_id("post1"))

    async def test_forum_topic_creation_and_reuse(self):
        models.init_db()
        models.add_tracked_account("user1")
        settings.TELEGRAM_GROUP_ID = "-100200300"
        settings.TELEGRAM_CHANNEL_ID = "-100100100"
        
        client = FakeInstagramClient(all_posts=[FakePost("p1"), FakePost("p2")])
        bot = FakeBot()
        
        service = SyncService(bot, client)
        
        with patch("app.services.sync_service.asyncio.sleep", new=AsyncMock()):
            await service.sync_account("user1")
            
        # Topic should be created once
        self.assertEqual(bot.topics_created, [("-100200300", "@user1")])
        # Both posts sent to the topic
        self.assertEqual(len(bot.sent), 2)
        for msg in bot.sent:
            self.assertEqual(msg["chat_id"], "-100200300")
            self.assertEqual(msg["message_thread_id"], 999)
            
        # Verify thread_id is saved in DB
        self.assertEqual(models.get_thread_id("user1"), 999)
        
        # New service instance should reuse thread_id without creating topic
        bot2 = FakeBot()
        client2 = FakeInstagramClient(pages={"": ([FakePost("p3")], "")})
        service2 = SyncService(bot2, client2)
        
        with patch("app.services.sync_service.asyncio.sleep", new=AsyncMock()):
            await service2.sync_account("user1")
            
        self.assertEqual(bot2.topics_created, []) # No new topic
        self.assertEqual(bot2.sent[0]["message_thread_id"], 999) # Reused

    async def test_fallback_to_channel_when_group_id_unset(self):
        models.init_db()
        models.add_tracked_account("user2")
        settings.TELEGRAM_GROUP_ID = None
        settings.TELEGRAM_CHANNEL_ID = "-100100100"
        
        client = FakeInstagramClient(all_posts=[FakePost("p1")])
        bot = FakeBot()
        
        service = SyncService(bot, client)
        with patch("app.services.sync_service.asyncio.sleep", new=AsyncMock()):
            await service.sync_account("user2")
            
        self.assertEqual(bot.topics_created, [])
        self.assertEqual(bot.sent[0]["chat_id"], "-100100100")
        self.assertIsNone(bot.sent[0]["message_thread_id"])


if __name__ == "__main__":
    unittest.main()
