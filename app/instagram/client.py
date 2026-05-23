import io
import logging
import os
import requests
from types import SimpleNamespace
from ..config import settings

logger = logging.getLogger(__name__)

SESSION_DIR = os.path.expanduser("~/.config/instagrapi")
SESSION_FILE = os.path.join(SESSION_DIR, f"session-{settings.INSTAGRAM_USERNAME or 'default'}.json")


class InstagramSessionError(Exception):
    """Raised when the session is completely dead (e.g. login required)."""
    pass


class InstagramChallengeError(InstagramSessionError):
    """Raised when Instagram triggers a challenge (verification)."""
    pass


class InstagramClient:
    def __init__(self):
        self._cl = None
        self._is_challenged = False
        self._load_client()

    def _load_client(self):
        from instagrapi import Client
        
        ig_user = settings.INSTAGRAM_USERNAME
        if not ig_user:
            logger.warning("INSTAGRAM_USERNAME not configured")
            return

        if not os.path.exists(SESSION_FILE):
            logger.error(f"Instagrapi session not found: {SESSION_FILE}. Run: python login_session.py")
            return

        cl = Client()
        # Same device config as login_session.py to avoid device mismatch flags
        cl.set_device({
            "app_version": "316.0.0.38.109",
            "android_version": 33,
            "android_release": "13",
            "dpi": "420dpi",
            "resolution": "1080x2340",
            "manufacturer": "Google",
            "device": "cheetah",
            "model": "Pixel 7 Pro",
            "cpu": "tensor",
            "version_code": "563503248"
        })
        cl.delay_range = [1, 3]

        try:
            cl.load_settings(SESSION_FILE)
            cl.login_by_sessionid(cl.settings.get("authorization_data", {}).get("sessionid", ""))
            self._cl = cl
            self._is_challenged = False
            logger.info(f"instagrapi client ready: {ig_user}")
        except Exception as e:
            logger.error(f"Session load failed: {e}\nRun: python login_session.py", exc_info=True)

    def _relogin(self):
        """Attempt to reload the session file (may have been refreshed externally)."""
        logger.info("Attempting session reload...")
        old_cl = self._cl
        self._cl = None
        self._load_client()
        if self._cl is None:
            self._cl = old_cl
            return False
        return True

    def _handle_exception(self, e, username=None):
        err_msg = str(e).lower()
        if "challenge" in err_msg or "checkpoint" in err_msg:
            self._is_challenged = True
            raise InstagramChallengeError(
                f"Instagram challenged the bot account. "
                f"Please log in manually in a browser or re-run login_session.py. "
                f"Original error: {e}"
            ) from e
        if "login_required" in err_msg:
            raise InstagramSessionError(f"Login required: {e}") from e
        
        context = f" for {username}" if username else ""
        raise RuntimeError(f"Instagram request failed{context}: {e}") from e

    # -- public API -------------------------------------------------------
    def get_instagram_user_id(self, username: str) -> str:
        if self._is_challenged:
            raise InstagramChallengeError("Bot session is in a challenged state. Manual intervention required.")

        if not self._cl:
            raise RuntimeError("No instagrapi client; session not loaded")

        for attempt in range(2):
            try:
                return str(self._cl.user_id_from_username(username))
            except Exception as e:
                if "login_required" in str(e).lower() and attempt == 0:
                    logger.warning("Session expired; attempting reload")
                    if self._relogin():
                        continue
                self._handle_exception(e, username)

        raise RuntimeError(f"user_id lookup failed for {username}")

    def _get_media_page(self, user_id: str, amount: int, end_cursor: str = ""):
        if self._is_challenged:
            raise InstagramChallengeError("Bot session is in a challenged state. Manual intervention required.")

        if not self._cl:
            raise RuntimeError("No instagrapi client; session not loaded")

        for attempt in range(2):
            try:
                return self._cl.user_medias_paginated(
                    user_id,
                    amount=amount,
                    end_cursor=end_cursor,
                )
            except Exception as e:
                if "login_required" in str(e).lower() and attempt == 0:
                    logger.warning("Session expired; attempting reload")
                    if self._relogin():
                        continue
                self._handle_exception(e, user_id)

        raise RuntimeError(f"media fetch failed for user id {user_id}")

    def _to_posts(self, medias) -> list:
        posts = []
        for m in medias:
            try:
                posts.append(self._media_to_post(m))
            except Exception as e:
                shortcode = getattr(m, "code", "?")
                raise RuntimeError(f"Failed to parse Instagram media {shortcode}: {e}") from e
        return posts

    def get_post_page(
        self,
        user_id: str,
        amount: int = 20,
        end_cursor: str = "",
    ):
        medias, next_cursor = self._get_media_page(
            user_id,
            amount=amount,
            end_cursor=end_cursor,
        )
        posts = self._to_posts(medias)
        logger.info(f"Fetched {len(posts)} posts for Instagram user id {user_id}")
        return posts, next_cursor

    def get_recent_posts(self, user_id: str, amount: int = 20) -> list:
        posts, _ = self.get_post_page(user_id, amount=amount)
        return posts

    def get_all_profile_posts(self, user_id: str, page_size: int = 33) -> list:
        posts = []
        seen_shortcodes = set()
        end_cursor = ""

        while True:
            medias, next_cursor = self._get_media_page(
                user_id,
                amount=page_size,
                end_cursor=end_cursor,
            )
            page = self._to_posts(medias)
            for post in page:
                if post.shortcode not in seen_shortcodes:
                    posts.append(post)
                    seen_shortcodes.add(post.shortcode)

            if not next_cursor or next_cursor == end_cursor or not medias:
                break
            end_cursor = next_cursor

        logger.info(f"Fetched {len(posts)} total posts for Instagram user id {user_id}")
        return posts

    def _media_to_post(self, m):
        class LightweightPost:
            def __init__(self, m):
                self.shortcode = m.code
                self.typename = {
                    1: "GraphImage",
                    2: "GraphVideo",
                    8: "GraphSidecar",
                }.get(m.media_type, "GraphImage")
                self.is_video = m.media_type == 2
                self.video_url = str(m.video_url) if m.video_url else None
                self.url = str(m.thumbnail_url) if m.thumbnail_url else None
                self.caption = m.caption_text or None
                self.date_utc = m.taken_at or None
                self._resources = m.resources or []

            def get_sidecar_nodes(self):
                return [
                    SimpleNamespace(
                        is_video=r.media_type == 2,
                        video_url=str(r.video_url) if r.video_url else None,
                        display_url=str(r.thumbnail_url) if r.thumbnail_url else None,
                    )
                    for r in self._resources
                ]

        return LightweightPost(m)

    def get_post_media_urls(self, post) -> list:
        if post.typename == "GraphSidecar":
            items = []
            for n in post.get_sidecar_nodes():
                url = n.video_url if n.is_video else n.display_url
                if url:
                    items.append({"url": url, "type": "video" if n.is_video else "image"})
            return items

        url = post.video_url if post.is_video else post.url
        if not url:
            return []
        return [{"url": url, "type": "video" if post.is_video else "image"}]

    def download_media(self, url: str):
        try:
            r = requests.get(url, timeout=30, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36"
            })
            r.raise_for_status()
            return io.BytesIO(r.content)
        except Exception as e:
            logger.error(f"Download failed {url}: {e}")
            return None
