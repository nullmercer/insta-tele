import logging
from telegram import Update
from telegram.ext import ContextTypes
from ..database import models
from ..services.sync_service import SyncService

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Instagram Archive Bot!\n\n"
        "I can archive Instagram posts to a Telegram channel.\n"
        "Use /help to see available commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 *Available Commands:*\n\n"
        "/track <username> - Start tracking an Instagram account\n"
        "/untrack <username> - Stop tracking an account\n"
        "/list - List all tracked accounts\n"
        "/status - Show bot statistics\n"
        "/help - Show this help message"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def track_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please provide an Instagram username: /track <username>")
        return

    username = context.args[0].strip().lower()
    is_new_account = models.add_tracked_account(username)
    sync_service = context.application.bot_data.get("sync_service")
    if sync_service is None:
        sync_service = SyncService(context.bot)
        context.application.bot_data["sync_service"] = sync_service

    if is_new_account:
        await update.message.reply_text(
            f"Started tracking @{username}. Initial full archive started."
        )
    elif models.is_initial_sync_completed(username):
        await update.message.reply_text(
            f"Already tracking @{username}. Checking for newly uploaded posts."
        )
    else:
        await update.message.reply_text(
            f"Tracking @{username} already exists. Resuming the incomplete initial archive."
        )

    context.application.create_task(sync_service.sync_account(username))

async def untrack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Please provide an Instagram username: /untrack <username>")
        return

    username = context.args[0].strip().lower()
    
    # Signal SyncService to stop if a sync is running
    sync_service = context.application.bot_data.get("sync_service")
    if sync_service:
        sync_service.stop_sync(username)

    if models.remove_tracked_account(username):
        await update.message.reply_text(f"❌ Stopped tracking @{username} and cancelled active archiving.")
    else:
        await update.message.reply_text(f"⚠️ Not tracking @{username}.")

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    accounts = models.get_tracked_accounts()
    if not accounts:
        await update.message.reply_text("No accounts are currently being tracked.")
        return

    text = "📋 *Tracked Accounts:*\n\n" + "\n".join([f"• @{acc}" for acc in accounts])
    await update.message.reply_text(text, parse_mode='Markdown')

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = models.get_stats()
    status_text = (
        "📊 *Bot Status:*\n\n"
        f"👥 Tracked Accounts: {stats['accounts_count']}\n"
        f"📦 Archived Posts: {stats['posts_count']}\n"
        f"🕒 Last Sync: {stats['last_sync'] or 'Never'}"
    )
    await update.message.reply_text(status_text, parse_mode='Markdown')
