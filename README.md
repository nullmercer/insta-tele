# Instagram Archive Bot

A production-grade Telegram bot that archives Instagram posts from public accounts directly into Telegram cloud storage with persistent state management and automated synchronization.

## Features

- **Full Automation**: Handles initial historical archive sync and continuous new-post tracking
- **Cloud Storage**: Utilizes Telegram as the sole permanent storage backend, eliminating the need for local media persistence
- **Duplicate Prevention**: Skips already archived posts to prevent redundant uploads
- **Zero Local Storage**: Streams media directly through memory (BytesIO) without saving files to disk
- **Comprehensive Media Support**: Archives reels, videos, carousel posts, and single images
- **State Persistence**: Uses SQLite for robust state management, allowing safe resumption of interrupted syncs
- **Asynchronous Operations**: Built with async/await architecture for non-blocking operations and scalability
- **Error Handling**: Includes retry logic, timeout handling, rate-limit management, and graceful failure recovery
- **Session Management**: Supports Instagram session authentication using instagrapi for improved reliability

## Architecture Overview

The bot's architecture is designed for efficiency and minimal resource usage:

```
Instagram
    ↓
instagrapi Metadata Fetch
    ↓
requests.get() (Media Download)
    ↓
BytesIO Memory Stream
    ↓
Telegram Upload
    ↓
Telegram Cloud Storage
    ↓
SQLite Persistence
```

**Key Architectural Principles:**
- **No Permanent Local Media Files**: Media is downloaded directly into memory and streamed to Telegram
- **Telegram as Storage Backend**: All archived media resides in a private Telegram channel
- **In-Memory Processing**: Media exists only temporarily in RAM during transfer

## Setup Instructions

### Prerequisites

- Python 3.11+
- Telegram account with BotFather access
- Instagram account (for session creation)
- Git

### 1. Telegram Bot Configuration

#### Create a Telegram Bot

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` command
3. Follow instructions to choose a bot name and username (username must end with `bot`)
4. Save the API token provided

#### Create a Private Telegram Channel

1. Create a new private channel in Telegram
2. Name it appropriately (e.g., "Instagram Archive")
3. Open channel info → Administrators → Add Admin
4. Search for your bot's username and add it
5. Ensure it has `Post Messages` and `Send Media` permissions

#### Get Your Telegram Channel ID

1. Forward any message from your private channel to `@RawDataBot`
2. Look for the `chat` object's `id` field in the response
3. This negative number is your `TELEGRAM_CHANNEL_ID`

### 2. Instagram Session Setup

The bot supports authenticated Instagram sessions for better reliability and rate-limit avoidance.

#### Option A: Using instagrapi Session ID

1. Set `INSTAGRAM_USERNAME` and `INSTAGRAM_SESSION_ID` in your `.env` file
2. Run: `python login_session.py`
3. Follow any verification prompts
4. Session will be saved automatically

#### Option B: Manual Session Creation

1. Install instaloader: `pip install instaloader`
2. Run: `instaloader --login=YOUR_USERNAME`
3. Enter your password and 2FA code if needed
4. A session file will be created in your home directory

### 3. Environment Configuration

Create a `.env` file in the root directory:

```ini
BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
TELEGRAM_CHANNEL_ID=YOUR_TELEGRAM_CHANNEL_ID
INSTAGRAM_USERNAME=YOUR_INSTAGRAM_USERNAME
INSTAGRAM_SESSION_ID=YOUR_SESSION_ID
CHECK_INTERVAL_MINUTES=10
LOG_LEVEL=INFO
```

**Environment Variables:**
- `BOT_TOKEN`: API token from BotFather
- `TELEGRAM_CHANNEL_ID`: Your private channel ID
- `INSTAGRAM_USERNAME`: Your Instagram username
- `INSTAGRAM_SESSION_ID`: Session ID for authentication (optional)
- `CHECK_INTERVAL_MINUTES`: Interval between sync checks (default: 10)
- `LOG_LEVEL`: Logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL)

### 4. Local Installation

```bash
# Clone repository
git clone https://github.com/nullmercer/insta-tele.git
cd insta-tele

# Create and activate virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the bot
python main.py
```

### 5. Docker Deployment

```bash
# Build image
docker build -t insta-archive-bot .

# Run with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the bot
docker-compose down
```

## Bot Commands

- `/start` - Initialize the bot
- `/help` - Show available commands
- `/track <username>` - Add Instagram account to tracking
- `/untrack <username>` - Stop tracking an account
- `/list` - Show all tracked accounts
- `/status` - Check bot and sync status

## Database Schema

The bot uses SQLite (`data/archive.db`) with three main tables:

```sql
CREATE TABLE tracked_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE archived_posts (
    shortcode TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    telegram_file_id TEXT,
    media_type TEXT,
    caption TEXT,
    timestamp TIMESTAMP,
    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (username) REFERENCES tracked_accounts (username)
);

CREATE TABLE subscribers (
    telegram_user_id INTEGER PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Incremental Sync Mechanism

The bot uses an efficient incremental sync process:

1. **Check Tracked Accounts**: Iterates through all tracked accounts in the database
2. **Fetch Latest Posts**: Retrieves recent posts using instagrapi
3. **Compare Shortcodes**: Checks against the `archived_posts` table
4. **Archive New Posts**: Only processes posts with unseen shortcodes
5. **Save Metadata**: Stores post metadata and Telegram file ID
6. **Efficient Skipping**: Stops processing when encountering already-archived posts

## Security Best Practices

- **Protect Your Bot Token**: Never commit `.env` to version control or share publicly
- **Session Files**: Treat session files with the same security as passwords
- **Private Channel**: Always use a private Telegram channel for archiving
- **Least Privilege**: Grant only necessary permissions to your bot
- **Keep Dependencies Updated**: Regularly update Python packages for security patches

## Troubleshooting

### Bot Not Responding
- Verify `BOT_TOKEN` is correct in `.env`
- Ensure the bot process is running
- Check that the bot is added to your channel/group

### Posts Not Archiving
- Review bot logs for errors: `docker-compose logs -f`
- Verify `TELEGRAM_CHANNEL_ID` is correct
- Confirm bot has admin permissions in the channel
- Check that Instagram authentication is working
- Instagram may be rate-limiting; try again after some time

### Instagram Authentication Issues
- Ensure `INSTAGRAM_USERNAME` and `INSTAGRAM_SESSION_ID` are set
- Run `python login_session.py` to refresh the session
- Check for Instagram security challenges in the logs

### Database Errors
- Verify the `data` directory has write permissions
- In Docker, check volume mounts in `docker-compose.yml`
- Delete `data/archive.db` and restart to reinitialize

## Deployment

The bot is ready for deployment on various platforms:

- **Railway**: Connect your GitHub repository and configure environment variables
- **Render**: Similar setup to Railway with worker dyno configuration
- **VPS**: Use Docker Compose on any VPS with Docker installed
- **Cloud Providers**: Compatible with AWS, GCP, Azure using containerized deployment

## Dependencies

See `requirements.txt`:
- `python-telegram-bot`: Telegram bot framework
- `instaloader`: Instagram metadata fetching
- `instagrapi`: Alternative Instagram API with session support
- `requests`: HTTP library
- `APScheduler`: Task scheduling
- `python-dotenv`: Environment variable management

## Project Structure

```
insta-tele/
├── app/
│   ├── bot/
│   ├── database/
│   ├── scheduler/
│   ├── services/
│   └── config.py
├── data/
│   └── archive.db
├── docs/
├── main.py
├── login_session.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## License

This project is open source and available under the MIT License.

## Support

For issues, questions, or contributions, please open an issue on GitHub.
