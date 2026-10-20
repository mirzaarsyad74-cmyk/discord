"""
Single-run script designed for GitHub Actions cron workflows or scheduled tasks.
Executes one monitoring cycle across CS.RIN.RU, Steam, FitGirl, DODI, and Reddit r/CrackWatch,
posts new releases with distinct signature colors to Discord Webhook, and exits cleanly.
"""
import os
import sys
import json
import logging
from dotenv import load_dotenv
from discord import SyncWebhook

from scraper import CsRinScraper, FORUM_URL
from monitor import ForumMonitor
from release_filter import classify_release
from discord_poster import (
    create_post_embed,
    create_title_change_embed,
    create_op_update_embed,
    create_new_thread_embed,
    safe_webhook_send,
    extract_metadata
)
from steam_client_watcher import create_steam_monitor_embed
from external_monitors import (
    create_fitgirl_embed,
    create_dodi_embed,
    create_crackwatch_embed,
    create_steamrip_embed,
    create_suo_embed,
    create_steam_deal_embed
)

# UTF-8 encoding support
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("run_once")

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
        "releases_only": True,
        "topics": [],
        "subforums": []
    }



def main():
    config = load_config()
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    csrin_cookie = os.getenv("CSRIN_COOKIE", "").strip() or config.get("csrin_cookie", "")

    if not webhook_url or not webhook_url.startswith("http"):
        logger.error("DISCORD_WEBHOOK_URL environment variable is missing or invalid!")
        sys.exit(1)

    try:
        webhook = SyncWebhook.from_url(webhook_url)
    except Exception as e:
        logger.error(f"Failed to connect to Discord Webhook: {e}")
        sys.exit(1)

    scraper = CsRinScraper(session_cookie=csrin_cookie)
    monitor = ForumMonitor(scraper=scraper)

    topics = config.get("topics", [])
    subforums = config.get("subforums", [])
    releases_only = config.get("releases_only", True)

    logger.info(f"Checking {len(topics)} topic(s)... (Releases Only: {releases_only})")

    # 1. Process Monitored Game Topics (CS.RIN.RU)
    if config.get("watch_csrin", False) and topics:
        for topic_raw in topics:
            t_id = scraper.extract_topic_id(topic_raw)
            logger.info(f"Processing topic ID: {t_id}")

            if t_id not in monitor.state.get("topics", {}):
                logger.info(f"First-time initialization for topic {t_id}...")
                monitor.check_topic(t_id, is_first_run_init=True)
                continue

            events = monitor.check_topic(t_id)

            # Title change
            if events.title_change and config.get("alert_on_title_change", True):
                old_t, new_t = events.title_change
                url = f"{FORUM_URL}/viewtopic.php?t={t_id}"
                embed = create_title_change_embed(t_id, old_t, new_t, url)
                safe_webhook_send(webhook, embed, username="CS.RIN.RU Monitor")
                logger.info(f"Sent title change alert for {t_id}: '{new_t}'")

            # OP update
            if events.op_update and config.get("alert_on_op_update", True):
                embed = create_op_update_embed(events.op_update)
                safe_webhook_send(webhook, embed, username="CS.RIN.RU Monitor")
                logger.info(f"Sent OP update for {t_id}")

            # New posts in topic
            for post in events.new_posts:
                if monitor.is_post_seen(t_id, post):
                    continue

                release_label = None
                if releases_only:
                    is_rel, release_label = classify_release(post)
                    if not is_rel:
                        monitor.mark_post_seen(t_id, post)
                        continue

                # Release signature deduplication
                meta = extract_metadata(post.clean_markdown, post.topic_title)
                rel_name = meta.get("release_name")
                if rel_name and monitor.is_release_duplicate(t_id, rel_name):
                    logger.info(f"Skipping duplicate release signature: {rel_name}")
                    monitor.mark_post_seen(t_id, post)
                    continue

                embed = create_post_embed(post, release_label=release_label)
                safe_webhook_send(webhook, embed, username="CS.RIN.RU Monitor")
                logger.info(f"Posted {release_label or 'post'} #{post.post_id} by {post.author}")
                monitor.mark_post_seen(t_id, post)
                if rel_name:
                    monitor.mark_release_seen(t_id, rel_name)

    # 2. Process Subforums (CS.RIN.RU)
    if config.get("watch_csrin", False) and subforums:
        for f_raw in subforums:
            f_id = scraper.extract_forum_id(f_raw)
            if f_id not in monitor.state.get("subforums", {}):
                monitor.check_subforum(f_id, is_first_run_init=True)
                continue

            new_threads = monitor.check_subforum(f_id)
            for th in new_threads:
                embed = create_new_thread_embed(th, f_id)
                safe_webhook_send(webhook, embed, username="CS.RIN.RU Monitor")

    # 3. Global Live Feeds (CS.RIN.RU)
    if config.get("watch_csrin", False) and config.get("enable_global_feed", False):
        feed_ids = config.get("subforum_feeds", ["10"])
        for fid in feed_ids:
            logger.info(f"Checking CS.RIN.RU Global Live Feed (f={fid})...")
            feed_posts = monitor.check_live_feed(forum_id=fid)
            for post in feed_posts:
                is_rel, release_label = classify_release(post)
                if not is_rel:
                    continue

                meta = extract_metadata(post.clean_markdown, post.topic_title)
                rel_name = meta.get("release_name")
                if rel_name and monitor.is_release_duplicate(post.topic_id, rel_name):
                    logger.info(f"Skipping duplicate release signature: {rel_name}")
                    continue

                embed = create_post_embed(post, release_label=release_label)
                safe_webhook_send(webhook, embed, username="CS.RIN.RU Monitor")
                logger.info(f"Posted Global Feed [{release_label}] for {post.topic_title} #{post.post_id}")
                if rel_name:
                    monitor.mark_release_seen(post.topic_id, rel_name)

    # 4. SteamRIP Watcher (Signature Royal Indigo Color - https://steamrip.com/)
    if config.get("watch_steamrip", False):
        logger.info("Checking SteamRIP (https://steamrip.com/)...")
        sr_updates = monitor.check_steamrip_updates()
        if sr_updates:
            for upd in sr_updates:
                embed = create_steamrip_embed(upd)
                safe_webhook_send(webhook, embed, username="SteamRIP Monitor")
                logger.info(f"Posted SteamRIP [{upd.get('type')}]: {upd['title']}")

    # 5. SteamUnlock Wannabe Watcher (https://steamunlockonennabe.click/)
    if config.get("watch_steamunlockonennabe", True):
        import time
        suo_cd = monitor.state.get("suo", {}).get("cooldown_until", 0)
        if time.time() >= suo_cd:
            logger.info("Checking SUO Wannabe (https://steamunlockonennabe.click/)...")
            suo_updates = monitor.check_suo_updates()
            if suo_updates:
                for upd in suo_updates:
                    embed = create_suo_embed(upd)
                    safe_webhook_send(webhook, embed, username="SUO Wannabe Monitor")
                    logger.info(f"Posted SUO Wannabe release: {upd['title']}")

    # 6. Steam Deals & Promotions (Prices in MYR / RM)
    if config.get("watch_steam_deals", True):
        logger.info("Checking Steam Specials & Promotions (MYR/RM)...")
        deal_updates = monitor.check_steam_deals()
        if deal_updates:
            for upd in deal_updates:
                embed = create_steam_deal_embed(upd)
                safe_webhook_send(webhook, embed, username="Steam Specials")
                logger.info(f"Posted Steam Deal: {upd['name']} (-{upd['discount_percent']}%)")

    # 7. Steam Client Version Watch (OpenSteam001/steam-monitor protobuf)
    if config.get("watch_steam_versions", True):
        logger.info("Checking OpenSteam001/steam-monitor protobuf branch for Steam Client updates...")
        steam_updates = monitor.check_steam_client_version()
        if steam_updates:
            for upd in steam_updates:
                embed = create_steam_monitor_embed(
                    channel_name=upd["channel_name"],
                    version=upd["version"],
                    build_kl_time=upd["build_kl"],
                    commit_info=upd.get("commit_info")
                )
                safe_webhook_send(webhook, embed, username="Steam Client Watch")
                logger.info(f"Posted Steam Client Version Update: {upd['channel_name']} v{upd['version']}")

    # 8. FitGirl Repacks Watcher (Signature Magenta Color)
    if config.get("watch_fitgirl", False):
        logger.info("Checking FitGirl Repacks official feed...")
        fg_updates = monitor.check_fitgirl_updates()
        if fg_updates:
            for upd in fg_updates:
                embed = create_fitgirl_embed(upd)
                safe_webhook_send(webhook, embed, username="FitGirl Repacks")
                logger.info(f"Posted FitGirl Repack: {upd['title']}")

    # 9. DODI Repacks Watcher (Signature Emerald Green Color)
    if config.get("watch_dodi", False):
        logger.info("Checking DODI Repacks official feed...")
        dodi_updates = monitor.check_dodi_updates()
        if dodi_updates:
            for upd in dodi_updates:
                embed = create_dodi_embed(upd)
                safe_webhook_send(webhook, embed, username="DODI Repacks")
                logger.info(f"Posted DODI Repack: {upd['title']}")

    # 7. Reddit r/CrackWatch Watcher (Signature Orange-Red Color)
    if config.get("watch_crackwatch_reddit", True):
        logger.info("Checking Reddit r/CrackWatch feed...")
        cw_updates = monitor.check_crackwatch_updates()
        if cw_updates:
            for upd in cw_updates:
                embed = create_crackwatch_embed(upd)
                safe_webhook_send(webhook, embed, username="Reddit CrackWatch")
                logger.info(f"Posted r/CrackWatch: {upd['title']}")

    logger.info("Single-run execution finished successfully!")


if __name__ == "__main__":
    main()
