import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from ..services.sync_service import SyncService
from ..config import settings

logger = logging.getLogger(__name__)

class SchedulerManager:
    def __init__(self, bot, sync_service=None):
        self.scheduler = AsyncIOScheduler()
        self.sync_service = sync_service or SyncService(bot)

    def start(self):
        self.scheduler.add_job(
            self.sync_service.sync_all_accounts,
            'interval',
            minutes=settings.CHECK_INTERVAL_MINUTES,
            id='instagram_sync',
            replace_existing=True
        )
        self.scheduler.start()
        logger.info(f"Scheduler started. Sync interval: {settings.CHECK_INTERVAL_MINUTES} minutes.")

    def stop(self):
        self.scheduler.shutdown()
        logger.info("Scheduler stopped.")
