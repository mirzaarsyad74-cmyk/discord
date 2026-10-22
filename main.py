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
    create_new_thread_embed,
    safe_webhook_send
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
logger = logging.getLogger("release_monitor_bot")

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
        "watch_steamrip": False,
        "watch_steamunlockonennabe": True,
        "watch_steam_deals": True,
        "watch_steam_versions": True,
        "watch_fitgirl": False,
        "watch_dodi": False,
        "watch_crackwatch_reddit": True,
        "watch_csrin": False,
        "enable_global_feed": False,
        "subforum_feeds": [],
        "topics": [],
        "subforums": [],
        "releases_only": True,
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


def create_startup_test_embed():
    """Builds a test embed sent once upon boot to confirm to Discord that the monitor is alive."""
    from datetime import datetime
    embed = discord.Embed(
        title="🟢 Game Release Monitor Online & Active",
        description="Bot has booted successfully on Koyeb (24/7 cloud) and is actively scanning for new releases!",
        color=0x2ECC71,
        timestamp=datetime.now()
    )
    embed.add_field(name="👑 SteamRIP", value="`✅ Scanning every 60s`", inline=True)
    embed.add_field(name="🔓 SUO Wannabe", value="`✅ Scanning every 60s`", inline=True)
    embed.add_field(name="🎀 FitGirl Repacks", value="`✅ Scanning every 60s`", inline=True)
    embed.add_field(name="🌿 DODI Repacks", value="`✅ Scanning every 60s`", inline=True)
    embed.add_field(name="🔥 Reddit r/CrackWatch", value="`✅ Scanning every 60s`", inline=True)
    embed.add_field(name="⚙️ Steam Client Updates", value="`✅ Scanning every 60s`", inline=True)
    embed.add_field(name="⚡ 24/7 Keep-Alive", value="`✅ Armed & Running`", inline=True)
    embed.set_footer(text="Game Release Monitor • Live Startup Test • GMT+8")
    return embed


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

    # Check SteamRIP (https://steamrip.com/ - Pre-installed Steam Games)
    if config.get("watch_steamrip", True):
        try:
            from external_monitors import create_steamrip_embed
            logger.info("Checking SteamRIP (https://steamrip.com/)...")
            updates = await asyncio.to_thread(monitor.check_steamrip_updates)
            for upd in updates:
                await channel.send(embed=create_steamrip_embed(upd))
        except Exception as e:
            logger.error(f"Error checking SteamRIP feed: {e}")

    # Check SteamUnlock Wannabe (https://steamunlockonennabe.click/)
    if config.get("watch_steamunlockonennabe", True):
        try:
            from external_monitors import create_suo_embed
            logger.info("Checking SUO Wannabe (https://steamunlockonennabe.click/)...")
            updates = await asyncio.to_thread(monitor.check_suo_updates)
            for upd in updates:
                await channel.send(embed=create_suo_embed(upd))
        except Exception as e:
            logger.error(f"Error checking SUO Wannabe feed: {e}")

    # Check Steam Deals & Promotions (Prices in MYR/RM)
    if config.get("watch_steam_deals", True):
        try:
            from external_monitors import create_steam_deal_embed
            logger.info("Checking Steam Specials & Promotions (MYR/RM)...")
            updates = await asyncio.to_thread(monitor.check_steam_deals)
            for upd in updates:
                await channel.send(embed=create_steam_deal_embed(upd))
        except Exception as e:
            logger.error(f"Error checking Steam deals: {e}")

    # Check monitored game topics (CS.RIN.RU)
    if config.get("watch_csrin", False):
        topics = config.get("topics", [])
        for topic_raw in topics:
            t_id = scraper.extract_topic_id(topic_raw)
            try:
                events = await asyncio.to_thread(monitor.check_topic, t_id)
                await send_updates_to_target(channel, events, is_webhook=False)
            except Exception as e:
                logger.error(f"Error checking topic {t_id}: {e}")

        # Check monitored subforums (if any)
        subforums = config.get("subforums", [])
        for f_raw in subforums:
            f_id = scraper.extract_forum_id(f_raw)
            try:
                new_threads = await asyncio.to_thread(monitor.check_subforum, f_id)
                for th in new_threads:
                    await send_new_thread_to_target(channel, th, f_id, is_webhook=False)
            except Exception as e:
                logger.error(f"Error checking subforum {f_id}: {e}")

        # Check Global Live Feed (all new games & Steam updates)
        if config.get("enable_global_feed", False):
            try:
                feed_posts = await asyncio.to_thread(monitor.check_live_feed, "10")
                for post in feed_posts:
                    is_rel, release_label = classify_release(post)
                    if not is_rel:
                        continue
                    embed = create_post_embed(post, release_label=release_label)
                    await channel.send(embed=embed)
            except Exception as e:
                logger.error(f"Error checking global live feed: {e}")

    # Check Steam Client Version Updates (OpenSteam001/steam-monitor)
    if config.get("watch_steam_versions", True):
        try:
            steam_updates = await asyncio.to_thread(monitor.check_steam_client_version)
            if steam_updates:
                from steam_client_watcher import create_steam_monitor_embed
                for upd in steam_updates:
                    embed = create_steam_monitor_embed(upd)
                    await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Error checking Steam Client updates: {e}")

    # Check FitGirl Repacks (Signature Magenta Color)
    if config.get("watch_fitgirl", True):
        try:
            from external_monitors import create_fitgirl_embed
            logger.info("Checking FitGirl Repacks (https://fitgirl-repacks.site/)...")
            updates = await asyncio.to_thread(monitor.check_fitgirl_updates)
            for upd in updates:
                await channel.send(embed=create_fitgirl_embed(upd))
        except Exception as e:
            logger.error(f"Error checking FitGirl feed: {e}")

    # Check DODI Repacks (Signature Emerald Green Color)
    if config.get("watch_dodi", True):
        try:
            from external_monitors import create_dodi_embed
            logger.info("Checking DODI Repacks (https://dodi-repacks.site/)...")
            updates = await asyncio.to_thread(monitor.check_dodi_updates)
            for upd in updates:
                await channel.send(embed=create_dodi_embed(upd))
        except Exception as e:
            logger.error(f"Error checking DODI feed: {e}")

    # Check Reddit r/CrackWatch (Signature Orange-Red Color)
    if config.get("watch_crackwatch_reddit", True):
        try:
            from external_monitors import create_crackwatch_embed
            logger.info("Checking Reddit r/CrackWatch (r/CrackWatch)...")
            updates = await asyncio.to_thread(monitor.check_crackwatch_updates)
            for upd in updates:
                await channel.send(embed=create_crackwatch_embed(upd))
        except Exception as e:
            logger.error(f"Error checking r/CrackWatch feed: {e}")


@bot.event
async def on_ready():
    active_monitors = []
    if config.get("watch_steamrip", False):
        active_monitors.append("SteamRIP")
    if config.get("watch_steamunlockonennabe", True):
        active_monitors.append("SUO Wannabe")
    if config.get("watch_steam_deals", True):
        active_monitors.append("Steam Deals (MYR)")
    if config.get("watch_fitgirl", False):
        active_monitors.append("FitGirl")
    if config.get("watch_dodi", False):
        active_monitors.append("DODI")
    if config.get("watch_crackwatch_reddit", True):
        active_monitors.append("r/CrackWatch")
    if config.get("watch_steam_versions", True):
        active_monitors.append("Steam Client")
    if config.get("watch_csrin", False):
        active_monitors.append(f"CS.RIN.RU ({len(config.get('topics', []))} topics)")

    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    logger.info(f"Actively monitoring: {', '.join(active_monitors)} every {CHECK_INTERVAL}s.")
    
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} application commands.")
    except Exception as e:
        logger.warning(f"Failed to sync slash commands: {e}")

    if not bot_monitor_task.is_running():
        bot_monitor_task.start()

    if DISCORD_CHANNEL_ID:
        try:
            channel = bot.get_channel(int(DISCORD_CHANNEL_ID))
            if channel:
                await channel.send(embed=create_startup_test_embed())
                logger.info("🚀 Sent startup test embed to Discord channel!")
        except Exception as ex:
            logger.warning(f"Could not send startup test embed: {ex}")


# Bot Commands
@bot.command(name="check")
async def cmd_check(ctx: commands.Context):
    """Forces an immediate check of all active monitors."""
    msg = await ctx.send("🔍 Checking monitors for new game releases & updates...")
    total_new = 0

    if config.get("watch_steamrip", True):
        from external_monitors import create_steamrip_embed
        for upd in await asyncio.to_thread(monitor.check_steamrip_updates):
            total_new += 1
            await ctx.send(embed=create_steamrip_embed(upd))

    if config.get("watch_steamunlockonennabe", True):
        from external_monitors import create_suo_embed
        for upd in await asyncio.to_thread(monitor.check_suo_updates):
            total_new += 1
            await ctx.send(embed=create_suo_embed(upd))

    if config.get("watch_fitgirl", True):
        from external_monitors import create_fitgirl_embed
        for upd in await asyncio.to_thread(monitor.check_fitgirl_updates):
            total_new += 1
            await ctx.send(embed=create_fitgirl_embed(upd))

    if config.get("watch_dodi", True):
        from external_monitors import create_dodi_embed
        for upd in await asyncio.to_thread(monitor.check_dodi_updates):
            total_new += 1
            await ctx.send(embed=create_dodi_embed(upd))

    if config.get("watch_crackwatch_reddit", True):
        from external_monitors import create_crackwatch_embed
        for upd in await asyncio.to_thread(monitor.check_crackwatch_updates):
            total_new += 1
            await ctx.send(embed=create_crackwatch_embed(upd))

    if config.get("watch_csrin", False):
        topics = config.get("topics", [])
        for topic_raw in topics:
            t_id = scraper.extract_topic_id(topic_raw)
            events = await asyncio.to_thread(monitor.check_topic, t_id)
            total_new += len(events.new_posts)
            await send_updates_to_target(ctx.channel, events, is_webhook=False)

    await msg.edit(content=f"✅ Check complete! Found {total_new} new update(s) across active monitors.")


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
    embed = discord.Embed(
        title="🤖 Game Release Monitor Status",
        color=0x6C5CE7
    )
    embed.add_field(name="SteamRIP Monitor", value="**✅ ACTIVE (steamrip.com)**" if config.get("watch_steamrip", False) else "❌ Disabled", inline=True)
    embed.add_field(name="SUO Wannabe", value="**✅ ACTIVE (steamunlockonennabe.click)**" if config.get("watch_steamunlockonennabe", True) else "❌ Disabled", inline=True)
    embed.add_field(name="Steam Specials (MYR)", value="**✅ ACTIVE (RM Pricing)**" if config.get("watch_steam_deals", True) else "❌ Disabled", inline=True)
    embed.add_field(name="FitGirl Repacks", value="**✅ ACTIVE**" if config.get("watch_fitgirl", False) else "❌ Disabled", inline=True)
    embed.add_field(name="DODI Repacks", value="**✅ ACTIVE**" if config.get("watch_dodi", False) else "❌ Disabled", inline=True)
    embed.add_field(name="r/CrackWatch", value="**✅ ACTIVE**" if config.get("watch_crackwatch_reddit", True) else "❌ Disabled", inline=True)
    embed.add_field(name="Steam Client Watch", value="**✅ ACTIVE**" if config.get("watch_steam_versions", True) else "❌ Disabled", inline=True)
    embed.add_field(name="CS.RIN.RU", value="❌ **REMOVED**" if not config.get("watch_csrin", False) else f"✅ Active ({len(config.get('topics', []))} topics)", inline=True)
    embed.add_field(name="Check Interval", value=f"`{CHECK_INTERVAL}` seconds", inline=True)
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

    # Send test post on boot only if explicitly enabled (prevents spam on container restarts)
    if os.getenv("SEND_STARTUP_TEST", "").lower() in ("true", "1") or config.get("send_startup_test", False):
        try:
            safe_webhook_send(webhook, create_startup_test_embed(), username="Release Monitor Bot")
            logger.info("🚀 Sent startup test embed to Discord webhook!")
        except Exception as ex:
            logger.warning(f"Could not send startup test embed: {ex}")

    while True:
        try:
            # Re-read topics from config each loop so user edits in config.json apply dynamically!
            current_cfg = load_config()
            active_topics = current_cfg.get("topics", [])
            active_subforums = current_cfg.get("subforums", [])

            # Check SteamRIP (https://steamrip.com/ - Pre-installed Steam Games)
            if current_cfg.get("watch_steamrip", True):
                from external_monitors import create_steamrip_embed
                logger.info("Checking SteamRIP (https://steamrip.com/)...")
                updates = await asyncio.to_thread(monitor.check_steamrip_updates)
                for upd in updates:
                    safe_webhook_send(webhook, create_steamrip_embed(upd), username="SteamRIP Monitor")
                    logger.info(f"Posted SteamRIP release: {upd['title']}")

            # Check SteamUnlock Wannabe (https://steamunlockonennabe.click/)
            if current_cfg.get("watch_steamunlockonennabe", True):
                from external_monitors import create_suo_embed
                logger.info("Checking SUO Wannabe (https://steamunlockonennabe.click/)...")
                updates = await asyncio.to_thread(monitor.check_suo_updates)
                for upd in updates:
                    safe_webhook_send(webhook, create_suo_embed(upd), username="SUO Wannabe Monitor")
                    logger.info(f"Posted SUO Wannabe release: {upd['title']}")

            # Check Steam Deals & Promotions (Prices in MYR/RM)
            if current_cfg.get("watch_steam_deals", True):
                from external_monitors import create_steam_deal_embed
                logger.info("Checking Steam Specials & Promotions (MYR/RM)...")
                updates = await asyncio.to_thread(monitor.check_steam_deals)
                for upd in updates:
                    safe_webhook_send(webhook, create_steam_deal_embed(upd), username="Steam Specials")
                    logger.info(f"Posted Steam Deal: {upd['name']} (-{upd['discount_percent']}%)")

            if current_cfg.get("watch_csrin", False):
                for topic_raw in active_topics:
                    t_id = scraper.extract_topic_id(topic_raw)
                    logger.info(f"Checking CS.RIN.RU topic {t_id}...")
                    events = await asyncio.to_thread(monitor.check_topic, t_id)
                    await send_updates_to_target(webhook, events, is_webhook=True)

                for f_raw in active_subforums:
                    f_id = scraper.extract_forum_id(f_raw)
                    logger.info(f"Checking subforum {f_id} for new threads...")
                    new_threads = await asyncio.to_thread(monitor.check_subforum, f_id)
                    for th in new_threads:
                        await send_new_thread_to_target(webhook, th, f_id, is_webhook=True)

                # Check Global Live Feed (all new games & Steam updates)
                if current_cfg.get("enable_global_feed", False):
                    logger.info("Checking CS.RIN.RU Global Live Feed (f=10 Main Forum)...")
                    feed_posts = await asyncio.to_thread(monitor.check_live_feed, "10")
                    for post in feed_posts:
                        is_rel, release_label = classify_release(post)
                        if not is_rel:
                            continue
                        embed = create_post_embed(post, release_label=release_label)
                        webhook.send(embed=embed, username="CS.RIN.RU Monitor")
                        logger.info(f"Posted Global Feed [{release_label}] for {post.topic_title} #{post.post_id}")

            # Check Steam Client Version Updates (OpenSteam001/steam-monitor)
            if current_cfg.get("watch_steam_versions", True):
                logger.info("Checking official Valve sources for Steam Client updates...")
                steam_updates = await asyncio.to_thread(monitor.check_steam_client_version)
                if steam_updates:
                    from steam_client_watcher import create_steam_monitor_embed
                    for upd in steam_updates:
                        embed = create_steam_monitor_embed(upd)
                        safe_webhook_send(webhook, embed, username="Steam Client Watch")
                        logger.info(f"Posted Steam Client Update: {upd.get('title')} ({upd.get('branch_display')})")

            # Check FitGirl Repacks (Signature Magenta Color)
            if current_cfg.get("watch_fitgirl", True):
                from external_monitors import create_fitgirl_embed
                logger.info("Checking FitGirl Repacks (https://fitgirl-repacks.site/)...")
                updates = await asyncio.to_thread(monitor.check_fitgirl_updates)
                for upd in updates:
                    safe_webhook_send(webhook, create_fitgirl_embed(upd), username="FitGirl Repacks")
                    logger.info(f"Posted FitGirl Repack: {upd['title']}")

            # Check DODI Repacks (Signature Emerald Green Color)
            if current_cfg.get("watch_dodi", True):
                from external_monitors import create_dodi_embed
                logger.info("Checking DODI Repacks (https://dodi-repacks.site/)...")
                updates = await asyncio.to_thread(monitor.check_dodi_updates)
                for upd in updates:
                    safe_webhook_send(webhook, create_dodi_embed(upd), username="DODI Repacks")
                    logger.info(f"Posted DODI Repack: {upd['title']}")

            # Check Reddit r/CrackWatch (Signature Orange-Red Color)
            if current_cfg.get("watch_crackwatch_reddit", True):
                from external_monitors import create_crackwatch_embed
                logger.info("Checking Reddit r/CrackWatch (r/CrackWatch)...")
                updates = await asyncio.to_thread(monitor.check_crackwatch_updates)
                for upd in updates:
                    safe_webhook_send(webhook, create_crackwatch_embed(upd), username="Reddit CrackWatch")
                    logger.info(f"Posted r/CrackWatch: {upd['title']}")

        except Exception as e:
            logger.error(f"Error during webhook poll: {e}", exc_info=True)

        logger.info(f"Sleeping for {CHECK_INTERVAL} seconds...")
        await asyncio.sleep(CHECK_INTERVAL)


# ==============================================================================
# Application Entry Point & Cloud Health Server
# ==============================================================================

def start_health_server():
    """
    Starts a background HTTP health-check server on port 8000 (or $PORT)
    and an automated keep-alive self-pinger to prevent Koyeb Free Tier from sleeping.
    """
    port_str = os.getenv("PORT", "8000")
    try:
        port = int(port_str)
    except ValueError:
        port = 8000

    from http.server import HTTPServer, BaseHTTPRequestHandler
    import threading

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/debug"):
                import socket
                import urllib3
                urllib3.disable_warnings()
                report = {}
                
                # 1. DNS
                try:
                    ip = socket.gethostbyname("steamunlockonennabe.duckdns.org")
                    report["dns"] = f"Resolved to {ip}"
                except Exception as ex:
                    report["dns"] = f"Failed: {type(ex).__name__}: {ex}"

                # 2. Direct TCP connect to 34.158.47.50:443
                try:
                    s = socket.create_connection(("34.158.47.50", 443), timeout=3)
                    s.close()
                    report["tcp_ip"] = "Success (port 443 open)"
                except Exception as ex:
                    report["tcp_ip"] = f"Failed: {type(ex).__name__}: {ex}"

                # 3. Direct TCP connect to domain:443
                try:
                    s = socket.create_connection(("steamunlockonennabe.duckdns.org", 443), timeout=3)
                    s.close()
                    report["tcp_domain"] = "Success (port 443 open)"
                except Exception as ex:
                    report["tcp_domain"] = f"Failed: {type(ex).__name__}: {ex}"

                import requests
                # 4. HTTP request
                for target, headers, verify in [
                    ("https://steamunlockonennabe.duckdns.org/api/onennabe", {"User-Agent": "Mozilla/5.0"}, True),
                    ("https://34.158.47.50/api/onennabe", {"Host": "steamunlockonennabe.duckdns.org", "User-Agent": "Mozilla/5.0"}, False)
                ]:
                    try:
                        r = requests.get(target, headers=headers, verify=verify, timeout=4, stream=True)
                        first_chunk = next(r.iter_content(chunk_size=512, decode_unicode=True))
                        report[target] = f"HTTP {r.status_code}, first_50={first_chunk[:50]!r}"
                        r.close()
                    except Exception as ex:
                        report[target] = f"Failed: {type(ex).__name__}: {ex}"

                # 5. Test fetch_suo_catalog
                try:
                    from external_monitors import fetch_suo_catalog
                    cat = fetch_suo_catalog(limit=50, timeout=4)
                    report["fetch_suo_catalog"] = f"Success: {len(cat)} games parsed, top: {cat[0].get('name') if cat else None}"
                except Exception as ex:
                    report["fetch_suo_catalog"] = f"Failed: {type(ex).__name__}: {ex}"

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(report, indent=2).encode("utf-8"))
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            active_srcs = [
                s for s, enabled in [
                    ("SteamRIP", config.get("watch_steamrip", False)),
                    ("SUO Wannabe", config.get("watch_steamunlockonennabe", True)),
                    ("Steam Deals (MYR)", config.get("watch_steam_deals", True)),
                    ("FitGirl", config.get("watch_fitgirl", False)),
                    ("DODI", config.get("watch_dodi", False)),
                    ("r/CrackWatch", config.get("watch_crackwatch_reddit", True)),
                    ("Steam Client", config.get("watch_steam_versions", True)),
                ] if enabled
            ]
            resp = json.dumps({
                "status": "healthy",
                "service": "game-release-monitor",
                "check_interval_seconds": CHECK_INTERVAL,
                "active_sources": active_srcs
            })
            self.wfile.write(resp.encode("utf-8"))

        def log_message(self, format, *args):
            pass  # Suppress probe spam in logs

    try:
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"Health check HTTP server listening on port {port} (Koyeb/Cloud ready)")
    except Exception as e:
        logger.warning(f"Could not start health check HTTP server on port {port}: {e}")

    # Automated 24/7 Keep-Alive Worker (prevents Koyeb Free Tier scale-to-zero)
    def keep_alive_worker():
        import time
        import urllib.request
        time.sleep(60)
        app_url = os.getenv("APP_URL", "").strip() or os.getenv("KOYEB_PUBLIC_URL", "").strip() or "https://increasing-saree-yuno74-2b5073cf.koyeb.app"
        while True:
            target_url = app_url or os.getenv("APP_URL", "").strip() or os.getenv("KOYEB_PUBLIC_URL", "").strip() or "https://increasing-saree-yuno74-2b5073cf.koyeb.app"
            if target_url:
                ping_endpoint = f"{target_url.rstrip('/')}/health"
                try:
                    req = urllib.request.Request(ping_endpoint, headers={"User-Agent": "GameReleaseMonitor-KeepAlive/1.0"})
                    with urllib.request.urlopen(req, timeout=10) as res:
                        logger.info(f"⚡ Keep-alive ping sent to {ping_endpoint} (HTTP {res.status}) - keeping Koyeb active!")
                except Exception as ex:
                    logger.debug(f"Keep-alive ping to {ping_endpoint} failed: {ex}")
            # Ping every 20 minutes (1200 seconds)
            time.sleep(1200)

    ka_thread = threading.Thread(target=keep_alive_worker, daemon=True)
    ka_thread.start()



def main():
    start_health_server()
    has_bot_token = bool(DISCORD_BOT_TOKEN and DISCORD_BOT_TOKEN != "your_discord_bot_token_here")
    has_webhook = bool(DISCORD_WEBHOOK_URL and DISCORD_WEBHOOK_URL.startswith("http"))

    if has_bot_token:
        if not DISCORD_CHANNEL_ID or DISCORD_CHANNEL_ID == "your_discord_channel_id_here":
            logger.error(
                "DISCORD_BOT_TOKEN is set, but DISCORD_CHANNEL_ID is missing!\n"
                "Please set DISCORD_CHANNEL_ID in your environment variables."
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
        print("No valid Discord Bot Token or Webhook URL found in environment!\n")
        print("Choose ONE of the following two quick options to start:\n")
        print("Option 1: Webhook Mode (Easiest - 1 minute setup)")
        print("  1. In Discord, right click your channel -> Edit Channel -> Integrations -> Webhooks.")
        print("  2. Click 'New Webhook', click 'Copy Webhook URL'.")
        print("  3. Set DISCORD_WEBHOOK_URL in .env (or Koyeb Environment variables)\n")
        print("Option 2: Bot Mode (Interactive with !commands & /slash commands)")
        print("  1. Create a bot at https://discord.com/developers/applications")
        print("  2. Set DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID\n")
        print("=" * 65 + "\n")
        if os.getenv("PORT") or os.getenv("KOYEB_APP_NAME"):
            import time
            while True:
                time.sleep(60)
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()

