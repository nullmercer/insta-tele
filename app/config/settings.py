import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    def __init__(self):
        self.BOT_TOKEN = os.getenv("BOT_TOKEN")
        self.TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
        self.TELEGRAM_GROUP_ID = os.getenv("TELEGRAM_GROUP_ID")
        self.INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
        self.CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "10"))

        self.DATABASE_PATH = os.getenv("DATABASE_PATH", "data/archive.db")
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.SESSION_FILE_PATH = os.getenv("SESSION_FILE_PATH", "")

        self.USE_CLI_FALLBACK = os.getenv("USE_CLI_FALLBACK", "false").lower() in ("1", "true", "yes")
        self.INSTALOADER_CLI_PATH = os.getenv("INSTALOADER_CLI_PATH", "instaloader")
        self.PROFILE_FETCH_TIMEOUT_SECS = int(os.getenv("PROFILE_FETCH_TIMEOUT_SECS", "15"))

        os.makedirs(os.path.dirname(self.DATABASE_PATH) or "data", exist_ok=True)
        os.makedirs("logs", exist_ok=True)

settings = Settings()
