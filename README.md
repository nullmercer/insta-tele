# Instagram Archive Bot

## Project Overview

This project implements a production-grade Telegram bot designed to archive Instagram posts from public accounts directly into Telegram cloud storage. It automates the entire archiving process, including initial historical synchronization and continuous tracking of new posts, ensuring no duplicates and zero permanent local media storage.

The restart-safe SQLite sync architecture, migration SQL, `instagrapi`
pagination flow, and polling guidance are documented in
[`docs/PERSISTENT_SYNC.md`](docs/PERSISTENT_SYNC.md).

## Features

- **Full Automation**: Handles initial historical archive sync and continuous new-post tracking.
- **Cloud Storage**: Utilizes Telegram as the sole permanent storage backend, eliminating the need for local media persistence.
- **Duplicate Prevention**: Skips already archived posts to prevent redundant uploads.
- **Zero Local Storage**: Streams media directly through memory (BytesIO) without saving files to disk.
- **Comprehensive Media Support**: Archives reels, videos, carousel posts, and single images.
- **State Persistence**: Uses SQLite for robust state management, allowing safe resumption of interrupted syncs.
- **Asynchronous Operations**: Built with an async architecture for Telegram handlers, scheduler, and non-blocking operations to ensure scalability.
- **Error Handling**: Includes retry logic, timeout handling, rate-limit management, graceful failure recovery, and a logging system to ensure bot stability.

## Architecture Explanation

The bot's architecture is designed for efficiency and minimal resource usage, particularly avoiding local media storage. The flow is as follows:

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
- **No Permanent Local Media Files**: Media is never stored on the local filesystem. It is downloaded directly into memory and streamed to Telegram.
- **Telegram as Storage Backend**: All archived media resides permanently in a private Telegram channel.
- **In-Memory Processing**: Media exists only temporarily in RAM during the transfer process.

## Telegram Bot Setup

To get your bot up and running, you'll need to interact with BotFather on Telegram to create a new bot and obtain its token, and then set up a private channel for archiving posts.

### BotFather Instructions

1. Open Telegram and search for `@BotFather`.
2. Start a chat with BotFather and send the `/newbot` command.
3. Follow the instructions to choose a name and a username for your bot. The username must end with `bot` (e.g., `MyArchiveBot`).
4. Upon successful creation, BotFather will provide you with an API token. Keep this token secure!

### How to Obtain BOT_TOKEN

After creating your bot with BotFather, the API token will be provided in the confirmation message. It will look something like `1234567890:ABCDEF1234567890abcdef1234567890`.

### How to Create a Private Telegram Channel

1. Open Telegram and create a new channel.
2. Set the channel type to `Private Channel`.
3. Give it a descriptive name (e.g., "Instagram Archive").
4. Add your newly created bot as an administrator to this channel. This is crucial for the bot to be able to post messages and media.

### How to Add Bot as Admin

1. In your private Telegram channel, tap on the channel name to open its info.
2. Go to `Administrators` -> `Add Admin`.
3. Search for your bot's username and add it as an administrator. Ensure it has permissions to `Post Messages` and `Send Media`.

### How to Obtain TELEGRAM_CHANNEL_ID

The `TELEGRAM_CHANNEL_ID` is a unique identifier for your private channel. To get it:

1. Forward any message from your private channel to `@RawDataBot` on Telegram.
2. The bot will respond with a JSON object. Look for the `chat` object and find the `id` field. It will be a negative number (e.g., `-1001234567890`). This is your `TELEGRAM_CHANNEL_ID`.

## Configuration

### Environment Variables

Create a `.env` file in the root directory of the project based on the provided `.env.example`.

```ini
BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
TELEGRAM_CHANNEL_ID=YOUR_TELEGRAM_CHANNEL_ID
INSTAGRAM_USERNAME=YOUR_INSTAGRAM_USERNAME_FOR_SESSION # Optional, but highly recommended
CHECK_INTERVAL_MINUTES=10 # How often to check for new posts (in minutes)
LOG_LEVEL=INFO # Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
```

- `BOT_TOKEN`: The API token obtained from BotFather.
- `TELEGRAM_CHANNEL_ID`: The ID of your private Telegram archive channel.
- `INSTAGRAM_USERNAME`: Your Instagram username. This is used to load an authenticated session, which helps in avoiding rate limits and scraping blocks. If not provided, Instaloader will run unauthenticated, which is prone to issues.
- `CHECK_INTERVAL_MINUTES`: The interval in minutes at which the bot will check for new posts on tracked accounts. Defaults to 10 minutes.
- `LOG_LEVEL`: The logging verbosity. Set to `DEBUG` for more detailed output during development or troubleshooting.

### How to Create Instagram Session

To avoid Instagram rate limits and improve stability, it is highly recommended to run Instaloader with an authenticated session. The bot will attempt to load a session file if `INSTAGRAM_USERNAME` is set in your `.env` file.

**Steps to create an Instagram session file:**

1. **Install Instaloader locally (if not already installed):**
   ```bash
   pip install instaloader
   ```

2. **Log in to Instagram via Instaloader:**
   Open your terminal and run the following command, replacing `YOUR_INSTAGRAM_USERNAME` with your actual Instagram username:
   ```bash
   instaloader --login=YOUR_INSTAGRAM_USERNAME
   ```
   You will be prompted to enter your Instagram password and potentially a 2FA code. Upon successful login, Instaloader will create a session file (e.g., `YOUR_INSTAGRAM_USERNAME.json`) in your current directory.

3. **Place the session file:**
   Move the generated session file (e.g., `YOUR_INSTAGRAM_USERNAME.json`) into the root directory of this bot project (e.g., `insta_archive_bot/`). The bot will automatically pick it up if `INSTAGRAM_USERNAME` is correctly set in your `.env` file.

## Local Setup Instructions

To run the bot locally, follow these steps:

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-repo/insta_archive_bot.git # Replace with your repository URL
    cd insta_archive_bot
    ```

2.  **Create a virtual environment and install dependencies:**
    ```bash
    python3.11 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Configure environment variables:**
    Create a `.env` file in the root directory as described in the [Environment Variables](#environment-variables) section.

4.  **Initialize the database:**
    The bot will automatically initialize the SQLite database (`data/archive.db`) on its first run. You can also manually trigger it by running `python -c "from app.database.models import init_db; init_db()"`.

5.  **Run the bot:**
    ```bash
    python main.py
    ```

    The bot will start polling for updates and the scheduler will begin checking for new Instagram posts at the configured interval.

## Docker Setup Instructions

For containerized deployment, Docker and Docker Compose files are provided.

1.  **Build the Docker image:**
    ```bash
    docker build -t insta-archive-bot .
    ```

2.  **Configure environment variables:**
    Create a `.env` file in the root directory as described in the [Environment Variables](#environment-variables) section.

3.  **Run with Docker Compose:**
    ```bash
    docker-compose up -d
    ```

    This will start the bot in a detached mode. The `data` and `logs` directories will be mounted as volumes to persist the database and logs outside the container.

4.  **View logs:**
    ```bash
    docker-compose logs -f
    ```

5.  **Stop the bot:**
    ```bash
    docker-compose down
    ```

## Deployment

The bot is designed to be deployment-ready for various platforms, including cloud providers and virtual private servers (VPS).

### Railway Deployment

Railway is a modern PAAS that makes it easy to deploy applications. You can deploy this bot to Railway by connecting your GitHub repository. Ensure your `.env` variables are configured in Railway's variables section.

### Render Deployment

Render is another excellent PAAS for deploying web services and background workers. Similar to Railway, you can connect your GitHub repository and configure environment variables in the Render dashboard. Set up a 'Background Worker' service type for the bot.

### VPS Deployment

For VPS deployments, you can use the provided Docker Compose setup. Ensure Docker and Docker Compose are installed on your VPS. Then, simply copy your project files, configure the `.env` file, and run `docker-compose up -d`.

## SQLite Explanation

SQLite is used as the lightweight, file-based database for persisting the bot's state. It stores information about tracked Instagram accounts and archived posts, ensuring data integrity and allowing the bot to resume operations seamlessly even after restarts.

**Database Schema:**

```sql
-- tracked_accounts table
CREATE TABLE IF NOT EXISTS tracked_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- archived_posts table
CREATE TABLE IF NOT EXISTS archived_posts (
    shortcode TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    telegram_file_id TEXT,
    media_type TEXT,
    caption TEXT,
    timestamp TIMESTAMP,
    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (username) REFERENCES tracked_accounts (username)
);

-- subscribers table (for future use or admin notifications)
CREATE TABLE IF NOT EXISTS subscribers (
    telegram_user_id INTEGER PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Incremental Sync Explanation

The bot employs an incremental synchronization mechanism to efficiently track and archive new posts without re-downloading or re-uploading existing content. This process runs periodically (configured by `CHECK_INTERVAL_MINUTES`).

**Logic:**
1.  **Check Tracked Accounts**: The scheduler wakes up and iterates through all Instagram accounts currently being tracked in the database.
2.  **Fetch Latest Posts**: For each tracked account, the bot fetches the most recent posts from Instagram using Instaloader.
3.  **Compare Shortcodes**: It then compares the shortcodes of these fetched posts against the `archived_posts` table in the SQLite database.
4.  **Archive ONLY Unseen Posts**: Only posts whose shortcodes are not found in the database (i.e., new posts) are processed for archiving.
5.  **Save Metadata**: After a new post is successfully uploaded to Telegram, its metadata (shortcode, Telegram file ID, etc.) is saved to the `archived_posts` table.
6.  **Efficient Skipping**: Once an already archived post is encountered during the fetch, the process for that account stops, as older posts would have already been processed during initial historical sync or previous incremental syncs. This ensures efficiency and prevents unnecessary API calls.

## Telegram Cloud Storage Explanation

This bot leverages Telegram itself as the primary and permanent cloud storage solution for all archived Instagram media. This strategy offers several benefits:

-   **Cost-Effective**: Telegram offers unlimited cloud storage for media, making it a highly economical solution compared to dedicated cloud storage providers.
-   **Accessibility**: Archived content is easily accessible directly within Telegram, either through the bot or by browsing the private channel.
-   **No Local Storage**: By uploading directly to Telegram, the bot avoids the need for any local disk storage, which is crucial for deployments on ephemeral environments or those with limited storage.
-   **File ID Reuse**: After a media file is uploaded to Telegram, a unique `file_id` is returned. This ID is stored in the SQLite database. For future access or sharing, this `file_id` can be reused to forward the media without re-uploading the actual file, saving bandwidth and speeding up operations.

## Security Best Practices

-   **Keep your `BOT_TOKEN` secure**: Never share your bot token publicly or commit it to version control. Use environment variables for sensitive information.
-   **Instagram Session File**: Treat your Instagram session file (`.json`) with the same care as your password. It grants access to your Instagram account. Do not share it and ensure it's not exposed in public repositories.
-   **Private Telegram Channel**: Always use a private Telegram channel for archiving to prevent unauthorized access to archived content.
-   **Least Privilege**: Ensure your Telegram bot only has the necessary permissions in your archive channel (e.g., `Post Messages`, `Send Media`).
-   **Regular Updates**: Keep your Python dependencies updated to patch any known security vulnerabilities.

## Troubleshooting

-   **Bot not responding to commands**: 
    -   Ensure your `BOT_TOKEN` is correct in the `.env` file.
    -   Verify that the bot is running and not encountering any errors in its logs.
    -   Check if the bot has been added to the Telegram group/channel where you are sending commands.

-   **Posts not archiving**: 
    -   Check the bot's logs for any error messages related to Instagram fetching or Telegram uploads.
    -   Ensure your `TELEGRAM_CHANNEL_ID` is correct and that the bot is an administrator in the channel with appropriate permissions.
    -   Verify that the Instagram session file is correctly placed and `INSTAGRAM_USERNAME` is set in `.env`.
    -   Instagram might be rate-limiting your account. Try again after some time or ensure your session is authenticated.

-   **`InstaloaderException: Login required` or `429 Too Many Requests`**: 
    -   This usually means your Instagram session is not authenticated or has expired. Follow the instructions in [How to Create Instagram Session](#how-to-create-instagram-session) to create or refresh your session file.
    -   Ensure `INSTAGRAM_USERNAME` is correctly set in your `.env` file.

-   **`sqlite3.OperationalError: unable to open database file`**: 
    -   This error indicates that the bot cannot access the SQLite database file. Ensure the `data` directory exists and has proper write permissions. If running in Docker, verify volume mounts are correct.
