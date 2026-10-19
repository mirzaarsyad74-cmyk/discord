# 🎮 Game Release & SteamRIP Discord Auto-Poster Bot

An automated Discord bot that monitors newly published pre-installed Steam games and updates from **[SteamRIP](https://steamrip.com/)**, along with **FitGirl Repacks**, **DODI Repacks**, **Reddit r/CrackWatch**, and **Steam Client Versions**, automatically posting new releases into your Discord channel.

[![Deploy to Koyeb](https://www.koyeb.com/static/images/deploy/button.svg)](https://app.koyeb.com/deploy?type=git&name=game-release-monitor&repository=https://github.com/mirzaarsyad74-cmyk/discord&ports=8000;http;/)

*(Note: CS.RIN.RU has been removed from active monitoring as requested).*

---

## 🚀 1-Click Deploy to Koyeb (Free 24/7 Cloud Hosting)

Koyeb runs the bot continuously 24/7 on their **Free Tier** with **no credit card required**!

1. Click the button above or open [Koyeb Deploy](https://app.koyeb.com/deploy?type=git&name=game-release-monitor&repository=https://github.com/mirzaarsyad74-cmyk/discord&ports=8000;http;/).
2. Sign up with GitHub (free, no credit card).
3. Under **Environment variables**, click **Add Variable**:
   - `DISCORD_WEBHOOK_URL` = paste your Discord Webhook URL (or `DISCORD_BOT_TOKEN` & `DISCORD_CHANNEL_ID` for bot mode).
4. Click **Deploy**!
   *(The bot includes a built-in HTTP health server on port 8000 so Koyeb's health checks pass automatically).*

---

## ⚡ Alternative Free Option: GitHub Actions (Cron Scheduled)


You can run this bot completely free in the cloud on GitHub Actions—**no server or PC running needed!**

### Step 1: Create a GitHub Repository & Push
1. Create a new repository on [GitHub](https://github.com/new) (e.g., `cs-rin-discord-bot`). Keep it **Private** or Public.
2. In your terminal, link and push the code:
   ```powershell
   git remote add origin https://github.com/mirzaarsyad74-cmyk/YOUR_REPO_NAME.git
   git push -u origin main
   ```

### Step 2: Add Your Discord Webhook to GitHub Secrets
1. In your GitHub repository, click **Settings** ➔ **Secrets and variables** ➔ **Actions**.
2. Click **New repository secret**.
3. Name: `DISCORD_WEBHOOK_URL`
4. Secret: Paste your Discord Webhook URL (`https://discord.com/api/webhooks/...`).
5. Click **Add secret**.

### Step 3: Enable Write Permissions (For State Persistence)
1. In your GitHub repository, click **Settings** ➔ **Actions** ➔ **General**.
2. Scroll to **Workflow permissions**.
3. Select **Read and write permissions** and click **Save**.
   *(This allows GitHub Actions to commit and update `data/state.json` so you never receive duplicate posts!)*

### Step 4: Run / Test
- Go to the **Actions** tab in GitHub ➔ click **CS.RIN.RU Release Notifier** on the left.
- Click **Run workflow** to test it immediately!
- The workflow will automatically run **every 30 minutes** in the cloud.

---

## 💻 Option 2: Run Locally on Your PC
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

You can customize enabled monitors and polling behavior in `config.json`:

```json
{
  "watch_steamrip": true,
  "watch_steam_versions": true,
  "watch_fitgirl": true,
  "watch_dodi": true,
  "watch_crackwatch_reddit": true,
  "watch_csrin": false,
  "enable_global_feed": false,
  "subforum_feeds": [],
  "topics": [],
  "subforums": [],
  "check_interval_seconds": 120
}
```

- **`watch_steamrip`**: Enable/disable SteamRIP release & update monitoring (`true` by default).
- **`watch_fitgirl`**: Enable/disable FitGirl Repacks monitor.
- **`watch_dodi`**: Enable/disable DODI Repacks monitor.
- **`watch_crackwatch_reddit`**: Enable/disable Reddit r/CrackWatch monitor.
- **`watch_steam_versions`**: Enable/disable Steam Client version monitoring.
- **`watch_csrin`**: Disabled (`false`). (CS.RIN.RU monitoring removed).
- **`check_interval_seconds`**: Polling frequency in seconds (default: `120` = 2 minutes).

---

## 🧪 Testing

To test the SteamRIP scraper and embed generator locally without needing live Discord credentials, run:

```powershell
.\.venv\Scripts\python.exe test_run.py
```

This verifies the connection to SteamRIP, bypasses Cloudflare, extracts the latest releases and updates, and prints mock Discord embeds to your terminal.

