import os
import sys
import json
import asyncio
import logging
from typing import Optional, List
from dotenv import load_dotenv

import discord
from discord.ext import commands, tasks

from scraper import CsRinScraper, FORUM_URL
from monitor import ForumMonitor, TopicUpdateEvents
from release_filter import classify_release
from discord_poster import (
    create_post_embed,
    create_title_change_embed,
    create_op_update_embed,
    create_new_thread_embed
)

# Set up UTF-8 for Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("cs_rin_bot")

# Load environment & config
load_dotenv()

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading config.json: {e}")
    return {
        "topics": ["https://cs.rin.ru/forum/viewtopic.php?f=10&t=146233&start=60"],
        "subforums": [],
        "check_interval_seconds": 120,
        "alert_on_title_change": True,
        "alert_on_op_update": True,
        "send_latest_post_on_startup": False
    }

def save_config(cfg: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving config.json: {e}")

config = load_config()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID", "").strip()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
CSRIN_COOKIE = os.getenv("CSRIN_COOKIE", "").strip() or config.get("csrin_cookie", "")
CHECK_INTERVAL = int(config.get("check_interval_seconds", 120))

# Initialize scraper and monitor
scraper = CsRinScraper(session_cookie=CSRIN_COOKIE)
monitor = ForumMonitor(scraper=scraper)


async def send_updates_to_target(target, events: TopicUpdateEvents, is_webhook: bool = False):
    """Dispatches topic update embeds to Discord channel or Webhook."""
    # 1. Title change alert (crack status, version update, etc.)
    if events.title_change and config.get("alert_on_title_change", True):
        old_t, new_t = events.title_change
        url = f"{FORUM_URL}/viewtopic.php?t={events.topic_id}"
        embed = create_title_change_embed(events.topic_id, old_t, new_t, url)
        try:
            if is_webhook:
                target.send(embed=embed, username="CS.RIN.RU Monitor")
            else:
                await target.send(embed=embed)
            logger.info(f"Sent title change alert for topic {events.topic_id}")
        except Exception as e:
            logger.error(f"Failed to send title change alert: {e}")

    # 2. Main post (OP) update
    if events.op_update and config.get("alert_on_op_update", True):
        embed = create_op_update_embed(events.op_update)
        try:
            if is_webhook:
                target.send(embed=embed, username="CS.RIN.RU Monitor")
            else:
                await target.send(embed=embed)
            logger.info(f"Sent OP update embed for topic {events.topic_id}")
        except Exception as e:
            logger.error(f"Failed to send OP update embed: {e}")

    # 3. New posts (filtered by releases_only)
    releases_only = config.get("releases_only", True)

    for post in events.new_posts:
        if monitor.is_post_seen(events.topic_id, post):
            logger.debug(f"Post #{post.post_id} already marked seen, skipping.")
            continue

        release_label = None
        if releases_only:
            is_rel, release_label = classify_release(post)
            if not is_rel:
                logger.info(f"Skipping non-release reply #{post.post_id} by {post.author} (releases_only is enabled)")
                monitor.mark_post_seen(events.topic_id, post)
                continue

        embed = create_post_embed(post, release_label=release_label)
        try:
            if is_webhook:
                target.send(embed=embed, username="CS.RIN.RU Monitor")
            else:
                await target.send(embed=embed)
            logger.info(f"Posted {'RELEASE: ' + release_label if release_label else 'post'} #{post.post_id} by {post.author} to Discord")
            await asyncio.sleep(1)  # pause to prevent rate limits
        except Exception as e:
            logger.error(f"Failed to send post #{post.post_id}: {e}")
        finally:
            monitor.mark_post_seen(events.topic_id, post)


async def send_new_thread_to_target(target, thread_info: dict, forum_id: str, is_webhook: bool = False):
    """Dispatches brand new game thread alerts to Discord."""
    embed = create_new_thread_embed(thread_info, forum_id)
    try:
        if is_webhook:
            target.send(embed=embed, username="CS.RIN.RU Monitor")
        else:
            await target.send(embed=embed)
        logger.info(f"Posted new thread alert: {thread_info.get('title')}")
    except Exception as e:
        logger.error(f"Failed to send new thread alert: {e}")


# ==============================================================================
# MODE A: Discord Bot (Token)
# ==============================================================================

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


@tasks.loop(seconds=CHECK_INTERVAL)
async def bot_monitor_task():
    """Background task running every interval to check for updates."""
    if not DISCORD_CHANNEL_ID:
        return
    channel = bot.get_channel(int(DISCORD_CHANNEL_ID))
    if not channel:
        logger.warning(f"Could not find Discord channel ID: {DISCORD_CHANNEL_ID}")
        return

    # Check monitored game topics
    topics = config.get("topics", [])
    for topic_raw in topics:
        t_id = scraper.extract_topic_id(topic_raw)
        try:
            events = monitor.check_topic(t_id)
            await send_updates_to_target(channel, events, is_webhook=False)
        except Exception as e:
            logger.error(f"Error checking topic {t_id}: {e}")

    # Check monitored subforums (if any)
    subforums = config.get("subforums", [])
    for f_raw in subforums:
        f_id = scraper.extract_forum_id(f_raw)
        try:
            new_threads = monitor.check_subforum(f_id)
            for th in new_threads:
                await send_new_thread_to_target(channel, th, f_id, is_webhook=False)
        except Exception as e:
            logger.error(f"Error checking subforum {f_id}: {e}")

    # Check Global Live Feed (all new games & Steam updates)
    if config.get("enable_global_feed", True):
        try:
            feed_posts = monitor.check_live_feed(forum_id="10")
            for post in feed_posts:
                is_rel, release_label = classify_release(post)
                if not is_rel:
                    continue
                embed = create_post_embed(post, release_label=release_label)
                await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Error checking global live feed: {e}")


@bot.event
async def on_ready():
    topics = config.get("topics", [])
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    logger.info(f"Actively monitoring {len(topics)} game topic(s) every {CHECK_INTERVAL}s.")
    
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} application commands.")
    except Exception as e:
        logger.warning(f"Failed to sync slash commands: {e}")

    if not bot_monitor_task.is_running():
        bot_monitor_task.start()


# Bot Commands
@bot.command(name="check")
async def cmd_check(ctx: commands.Context):
    """Forces an immediate check of all monitored topics."""
    msg = await ctx.send("🔍 Checking CS.RIN.RU for new posts...")
    total_new = 0
    topics = config.get("topics", [])
    for topic_raw in topics:
        t_id = scraper.extract_topic_id(topic_raw)
        events = monitor.check_topic(t_id)
        total_new += len(events.new_posts)
        await send_updates_to_target(ctx.channel, events, is_webhook=False)
    
    await msg.edit(content=f"✅ Check complete! Found {total_new} new post(s) across {len(topics)} topic(s).")


@bot.command(name="add")
async def cmd_add(ctx: commands.Context, url_or_id: str):
    """Adds a new game topic URL or ID to monitoring list."""
    t_id = scraper.extract_topic_id(url_or_id)
    if not t_id or not t_id.isdigit():
        await ctx.send("❌ Please provide a valid CS.RIN.RU topic URL or ID (e.g., `!add https://cs.rin.ru/forum/viewtopic.php?t=12345`).")
        return

    topics = config.setdefault("topics", [])
    # Check if already added
    for existing in topics:
        if scraper.extract_topic_id(existing) == t_id:
            await ctx.send(f"⚠️ Topic `{t_id}` is already in the monitor list!")
            return

    msg = await ctx.send(f"⏳ Inspecting topic `{t_id}` on CS.RIN.RU...")
    meta = scraper.get_topic_metadata(t_id)
    title = meta.title or f"Topic {t_id}"

    # Add and save
    full_url = f"{FORUM_URL}/viewtopic.php?t={t_id}"
    topics.append(full_url)
    save_config(config)

    # Initialize tracking so we don't backfill old posts
    monitor.check_topic(t_id, is_first_run_init=True)

    await msg.edit(content=f"✅ **Added to monitor!**\n🎮 **Game/Topic:** `{title}`\n🔗 **Link:** {full_url}\nWill now auto-post new updates!")


@bot.command(name="remove")
async def cmd_remove(ctx: commands.Context, url_or_id: str):
    """Removes a game topic from monitoring list."""
    t_id = scraper.extract_topic_id(url_or_id)
    topics = config.get("topics", [])
    found_idx = -1
    for i, t in enumerate(topics):
        if scraper.extract_topic_id(t) == t_id:
            found_idx = i
            break

    if found_idx == -1:
        await ctx.send(f"❌ Topic `{t_id}` not found in the monitor list.")
        return

    removed_url = topics.pop(found_idx)
    save_config(config)
    monitor.remove_topic(t_id)
    await ctx.send(f"🗑️ Removed topic `{t_id}` from monitor list.")


@bot.command(name="list")
async def cmd_list(ctx: commands.Context):
    """Lists all actively monitored games and topics."""
    topics = config.get("topics", [])
    if not topics:
        await ctx.send("No topics currently monitored. Use `!add <url>` to add one!")
        return

    embed = discord.Embed(
        title=f"📋 Monitored Game Topics ({len(topics)})",
        color=0x3498DB
    )
    lines = []
    state_topics = monitor.state.get("topics", {})
    for t in topics:
        t_id = scraper.extract_topic_id(t)
        t_data = state_topics.get(t_id, {})
        title = t_data.get("title", f"Topic {t_id}")
        seen_count = len(t_data.get("seen_post_ids", []))
        lines.append(f"• **[{title}]({FORUM_URL}/viewtopic.php?t={t_id})** (ID: `{t_id}`, `{seen_count}` posts seen)")

    embed.description = "\n\n".join(lines)
    embed.set_footer(text="Use !add <url> or !remove <url> to manage topics")
    await ctx.send(embed=embed)


@bot.command(name="status")
async def cmd_status(ctx: commands.Context):
    """Displays monitor status and active settings."""
    topics = config.get("topics", [])
    releases_only = config.get("releases_only", True)
    embed = discord.Embed(
        title="🤖 CS.RIN.RU Auto-Poster Status",
        color=0x3498DB
    )
    embed.add_field(name="Monitored Games", value=f"`{len(topics)}` topics active", inline=True)
    embed.add_field(name="Check Interval", value=f"`{CHECK_INTERVAL}` seconds", inline=True)
    embed.add_field(name="Releases Only (No Chat)", value=f"**{'✅ YES' if releases_only else '❌ NO'}**", inline=True)
    embed.add_field(name="Crack / Title Alerts", value=str(config.get("alert_on_title_change", True)), inline=True)
    embed.set_footer(text=f"Serving channel: #{ctx.channel.name}")
    await ctx.send(embed=embed)


@bot.command(name="latest")
async def cmd_latest(ctx: commands.Context, url_or_id: Optional[str] = None):
    """Previews the latest post in a monitored topic right now."""
    topics = config.get("topics", [])
    if not topics:
        await ctx.send("No topics configured.")
        return
    target_id = scraper.extract_topic_id(url_or_id) if url_or_id else scraper.extract_topic_id(topics[0])
    msg = await ctx.send(f"⏳ Fetching latest post for topic `{target_id}`...")
    
    meta = scraper.get_topic_metadata(target_id)
    posts = scraper.get_posts_page(target_id, start=meta.max_start, topic_title=meta.title)
    if not posts:
        await msg.edit(content=f"Could not retrieve posts for topic `{target_id}`.")
        return
    
    latest_post = posts[-1]
    embed = create_post_embed(latest_post)
    await msg.edit(content="Here is the latest post on CS.RIN.RU:", embed=embed)


# Slash command equivalents
@bot.tree.command(name="list", description="List all monitored games and topics")
async def slash_list(interaction: discord.Interaction):
    ctx = await commands.Context.from_interaction(interaction)
    await cmd_list(ctx)

@bot.tree.command(name="add", description="Add a game forum topic URL or ID to monitor")
async def slash_add(interaction: discord.Interaction, url: str):
    ctx = await commands.Context.from_interaction(interaction)
    await cmd_add(ctx, url)

@bot.tree.command(name="remove", description="Remove a game forum topic from monitoring")
async def slash_remove(interaction: discord.Interaction, url_or_id: str):
    ctx = await commands.Context.from_interaction(interaction)
    await cmd_remove(ctx, url_or_id)

@bot.tree.command(name="check", description="Force an immediate check for new forum posts")
async def slash_check(interaction: discord.Interaction):
    ctx = await commands.Context.from_interaction(interaction)
    await cmd_check(ctx)


# ==============================================================================
# MODE B: Standalone Webhook Runner
# ==============================================================================

async def run_webhook_daemon(webhook_url: str):
    """Lightweight runner when only DISCORD_WEBHOOK_URL is configured."""
    from discord import SyncWebhook
    topics = config.get("topics", [])
    subforums = config.get("subforums", [])
    logger.info("=" * 60)
    logger.info("🚀 Starting in DISCORD WEBHOOK mode!")
    logger.info(f"Target Webhook: {webhook_url[:35]}...")
    logger.info(f"Monitoring {len(topics)} topic(s), {len(subforums)} subforum(s)")
    logger.info(f"Polling interval: {CHECK_INTERVAL} seconds")
    logger.info("=" * 60)

    try:
        webhook = SyncWebhook.from_url(webhook_url)
    except Exception as e:
        logger.error(f"Invalid DISCORD_WEBHOOK_URL: {e}")
        return

    # Initial check on startup
    for topic_raw in topics:
        t_id = scraper.extract_topic_id(topic_raw)
        if t_id not in monitor.state.get("topics", {}):
            logger.info(f"Initializing topic {t_id} state...")
            monitor.check_topic(t_id, is_first_run_init=True)

    for f_raw in subforums:
        f_id = scraper.extract_forum_id(f_raw)
        if f_id not in monitor.state.get("subforums", {}):
            logger.info(f"Initializing subforum {f_id} state...")
            monitor.check_subforum(f_id, is_first_run_init=True)

    while True:
        try:
            # Re-read topics from config each loop so user edits in config.json apply dynamically!
            current_cfg = load_config()
            active_topics = current_cfg.get("topics", [])
            active_subforums = current_cfg.get("subforums", [])

            for topic_raw in active_topics:
                t_id = scraper.extract_topic_id(topic_raw)
                logger.info(f"Checking CS.RIN.RU topic {t_id}...")
                events = monitor.check_topic(t_id)
                await send_updates_to_target(webhook, events, is_webhook=True)

            for f_raw in active_subforums:
                f_id = scraper.extract_forum_id(f_raw)
                logger.info(f"Checking subforum {f_id} for new threads...")
                new_threads = monitor.check_subforum(f_id)
                for th in new_threads:
                    await send_new_thread_to_target(webhook, th, f_id, is_webhook=True)

            # Check Global Live Feed (all new games & Steam updates)
            if current_cfg.get("enable_global_feed", True):
                logger.info("Checking CS.RIN.RU Global Live Feed (f=10 Main Forum)...")
                feed_posts = monitor.check_live_feed(forum_id="10")
                for post in feed_posts:
                    is_rel, release_label = classify_release(post)
                    if not is_rel:
                        continue
                    embed = create_post_embed(post, release_label=release_label)
                    webhook.send(embed=embed, username="CS.RIN.RU Monitor")
                    logger.info(f"Posted Global Feed [{release_label}] for {post.topic_title} #{post.post_id}")

        except Exception as e:
            logger.error(f"Error during webhook poll: {e}", exc_info=True)

        logger.info(f"Sleeping for {CHECK_INTERVAL} seconds...")
        await asyncio.sleep(CHECK_INTERVAL)


# ==============================================================================
# Application Entry Point
# ==============================================================================

def main():
    has_bot_token = bool(DISCORD_BOT_TOKEN and DISCORD_BOT_TOKEN != "your_discord_bot_token_here")
    has_webhook = bool(DISCORD_WEBHOOK_URL and DISCORD_WEBHOOK_URL.startswith("http"))

    if has_bot_token:
        if not DISCORD_CHANNEL_ID or DISCORD_CHANNEL_ID == "your_discord_channel_id_here":
            logger.error(
                "DISCORD_BOT_TOKEN is set, but DISCORD_CHANNEL_ID is missing!\n"
                "Please open .env and set DISCORD_CHANNEL_ID to your target channel ID."
            )
            sys.exit(1)
        logger.info("Starting Discord Bot client...")
        bot.run(DISCORD_BOT_TOKEN)
    elif has_webhook:
        asyncio.run(run_webhook_daemon(DISCORD_WEBHOOK_URL))
    else:
        print("\n" + "=" * 65)
        print("⚠️  CONFIGURATION REQUIRED")
        print("=" * 65)
        print("No valid Discord Bot Token or Webhook URL found in .env!\n")
        print("Choose ONE of the following two quick options to start:\n")
        print("Option 1: Webhook Mode (Easiest - 1 minute setup)")
        print("  1. In Discord, right click your channel -> Edit Channel -> Integrations -> Webhooks.")
        print("  2. Click 'New Webhook', click 'Copy Webhook URL'.")
        print("  3. Open '.env' in this folder and paste it into DISCORD_WEBHOOK_URL=...\n")
        print("Option 2: Bot Mode (Interactive with !commands & /slash commands)")
        print("  1. Create a bot at https://discord.com/developers/applications")
        print("  2. Copy Bot Token into DISCORD_BOT_TOKEN=...")
        print("  3. Copy your Channel ID into DISCORD_CHANNEL_ID=...")
        print("=" * 65 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
