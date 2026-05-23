import logging
from telegram import Update
from telegram.ext import Application, CommandHandler
from app.config import settings
from app.database.models import init_db
from app.bot.handlers import start_command, help_command, track_command, untrack_command, list_command, status_command
from app.scheduler.manager import SchedulerManager
from app.services.sync_service import SyncService

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=settings.LOG_LEVEL
)
logger = logging.getLogger(__name__)

async def post_init(application: Application):
    sync_service = SyncService(application.bot)
    application.bot_data["sync_service"] = sync_service
    scheduler_manager = SchedulerManager(application.bot, sync_service=sync_service)
    application.bot_data["scheduler_manager"] = scheduler_manager
    scheduler_manager.start()

def main():
    # Initialize database
    init_db()
    logger.info("Database initialized.")

    # Create the Application and pass your bot's token.
    application = Application.builder().token(settings.BOT_TOKEN).post_init(post_init).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("track", track_command))
    application.add_handler(CommandHandler("untrack", untrack_command))
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CommandHandler("status", status_command))

    # Run the bot until the user presses Ctrl-C
    logger.info("Bot started. Press Ctrl-C to stop.")
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
