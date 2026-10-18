# 🤖 CS.RIN.RU Discord Auto-Poster Bot

An automated Discord bot that monitors threads on **CS.RIN.RU** (specifically configured for [SHINOBI: Art of Vengeance](https://cs.rin.ru/forum/viewtopic.php?f=10&t=146233&start=60)) and automatically posts new replies, OP updates, and topic status changes into your Discord channel.

---

## ✨ Features

- **Automated Anti-Bot Challenge Handling**: Seamlessly bypasses CS.RIN.RU's lightweight JavaScript security token challenge without needing headless browsers.
- **New Reply Alerts**: Posts any new comment, release, repack, bypass, or save file with author, time, direct link, and formatted content.
- **Crack / Status Change Alerts**: Automatically triggers an alert if the topic title changes (e.g., from `[NOT CRACKED / HV PLAYABLE]` to `[CRACKED]`).
- **Main Post (OP) Edit Tracking**: Detects when the first post (OP) is edited with updated links or patch notes.
- **Clean Discord Embeds**:
  - Quote blocks converted to Discord `> quote` formatting
  - Code blocks preserved
  - Forum links resolved and hyperlinked
  - Attached screenshots and repack images displayed in the embed
  - Automatic character-length safety truncation with direct read links
- **Dual Running Modes**:
  - **Webhook Mode (Easiest)**: No bot registration or permissions required. Just paste your Discord Webhook URL.
  - **Bot Mode (Interactive)**: Connects as a bot with prefix and slash commands (`!status`, `!check`, `!latest`).
- **Persistent State**: Stores seen post IDs and last topic state in `data/state.json` to prevent duplicates across restarts.
- **Login Cookie Support (Optional)**: Provide your CS.RIN.RU `phpbb3_...` session cookie to reveal hidden download links (`[[Please login to see this link.]]`).

---

## 🚀 Quick Start (Choose Mode A or Mode B)

### Option A: Webhook Mode (Fastest — 1 Minute Setup)
1. Open Discord, right-click the text channel where you want updates posted.
2. Select **Edit Channel** ➔ **Integrations** ➔ **Webhooks** ➔ **New Webhook**.
3. Click **Copy Webhook URL**.
4. Open the `.env` file in this folder and paste your URL:
   ```env
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/1234567890/abcdef...
   ```
5. Double-click `run.bat` or run:
   ```powershell
   .\.venv\Scripts\python.exe main.py
   ```

---

### Option B: Discord Bot Mode (Interactive Commands)
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application**, give it a name (e.g., `CS.RIN Monitor`), and go to the **Bot** tab.
3. Click **Reset Token** and copy your bot token.
4. Under **Privileged Gateway Intents**, enable **Message Content Intent**.
5. Go to **OAuth2** ➔ **URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Permissions: `Send Messages`, `Embed Links`, `Read Message History`
   - Copy the generated URL and invite the bot to your server.
6. In Discord, right-click the channel you want it to post in and click **Copy Channel ID** (requires Developer Mode enabled in Discord User Settings ➔ Advanced).
7. Open `.env` and fill in:
   ```env
   DISCORD_BOT_TOKEN=your_bot_token_here
   DISCORD_CHANNEL_ID=your_channel_id_here
   ```
8. Double-click `run.bat` or run:
   ```powershell
   .\.venv\Scripts\python.exe main.py
   ```

#### Bot Commands:
- `!list` or `/list`: Displays all actively monitored game topics with their titles and URLs.
- `!add <url>` or `/add <url>`: Adds any new game topic URL or ID to monitoring on the fly.
- `!remove <url or id>` or `/remove <url>`: Stops monitoring a game topic.
- `!status` or `/status`: Displays current monitoring status, interval, and tracked post count.
- `!check` or `/check`: Triggers an immediate manual check of CS.RIN.RU.
- `!latest [url]`: Previews the most recent post for a game topic.

---

## ⚙️ Configuration (`config.json`)

You can customize topics and polling behavior in `config.json`:

```json
{
  "topics": [
    "https://cs.rin.ru/forum/viewtopic.php?f=10&t=146233&start=60",
    "https://cs.rin.ru/forum/viewtopic.php?t=123456"
  ],
  "subforums": [
    "https://cs.rin.ru/forum/viewforum.php?f=10"
  ],
  "check_interval_seconds": 120,
  "alert_on_title_change": true,
  "alert_on_op_update": true,
  "send_latest_post_on_startup": false,
  "csrin_cookie": ""
}
```

- **`topics`**: List of any game topic URLs or IDs you want to monitor (add as many games as you want!).
- **`subforums`**: (Optional) List of forum sections (e.g. `f=10` Main Forum). Alerts whenever someone creates a *brand new game thread*!
- **`check_interval_seconds`**: Polling frequency in seconds (default: `120` = 2 minutes).
- **`alert_on_title_change`**: Notifies Discord if any monitored topic title changes (crack status updates).
- **`alert_on_op_update`**: Notifies Discord if the first post of a game thread is modified.

---

## 🧪 Testing

To test the forum scraper and embed generator locally without needing live Discord credentials, run:

```powershell
.\.venv\Scripts\python.exe test_run.py
```

This verifies the connection to CS.RIN.RU, handles the security challenge, extracts the Shinobi Art of Vengeance thread, and prints mock Discord embeds to your terminal.
