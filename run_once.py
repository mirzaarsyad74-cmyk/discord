"""
Single-run script designed for GitHub Actions cron workflows or scheduled tasks.
Executes one monitoring cycle, posts any new releases to Discord Webhook,
and exits cleanly.
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
    create_new_thread_embed
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
        "topics": ["https://cs.rin.ru/forum/viewtopic.php?f=10&t=146233&start=60"],
        "subforums": [],
        "releases_only": True,
        "alert_on_title_change": True,
        "alert_on_op_update": True
    }


def main():
    config = load_config()
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    csrin_cookie = os.getenv("CSRIN_COOKIE", "").strip() or config.get("csrin_cookie", "")

    if not webhook_url or not webhook_url.startswith("http"):
        logger.error("DISCORD_WEBHOOK_URL environment variable is missing or invalid!")
        logger.error("In GitHub Actions, make sure to add DISCORD_WEBHOOK_URL to Repository Secrets.")
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

    # 1. Process Topics
    for topic_raw in topics:
        t_id = scraper.extract_topic_id(topic_raw)
        logger.info(f"Processing topic ID: {t_id}")

        # If state doesn't exist yet for this topic, initialize it without spamming old posts
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
            try:
                webhook.send(embed=embed, username="CS.RIN.RU Monitor")
                logger.info(f"Sent title change alert for {t_id}: '{new_t}'")
            except Exception as e:
                logger.error(f"Error sending title change: {e}")

        # OP update
        if events.op_update and config.get("alert_on_op_update", True):
            embed = create_op_update_embed(events.op_update)
            try:
                webhook.send(embed=embed, username="CS.RIN.RU Monitor")
                logger.info(f"Sent OP update for {t_id}")
            except Exception as e:
                logger.error(f"Error sending OP update: {e}")

        # New posts
        for post in events.new_posts:
            release_label = None
            if releases_only:
                is_rel, release_label = classify_release(post)
                if not is_rel:
                    logger.info(f"Skipping non-release reply #{post.post_id} by {post.author}")
                    continue

            embed = create_post_embed(post, release_label=release_label)
            try:
                webhook.send(embed=embed, username="CS.RIN.RU Monitor")
                logger.info(f"Posted {release_label or 'post'} #{post.post_id} by {post.author}")
            except Exception as e:
                logger.error(f"Error sending post #{post.post_id}: {e}")

    # 2. Process Subforums
    for f_raw in subforums:
        f_id = scraper.extract_forum_id(f_raw)
        logger.info(f"Processing subforum f={f_id}")
        if f_id not in monitor.state.get("subforums", {}):
            monitor.check_subforum(f_id, is_first_run_init=True)
            continue

        new_threads = monitor.check_subforum(f_id)
        for th in new_threads:
            embed = create_new_thread_embed(th, f_id)
            try:
                webhook.send(embed=embed, username="CS.RIN.RU Monitor")
                logger.info(f"Posted new thread alert: {th.get('title')}")
            except Exception as e:
                logger.error(f"Error sending thread alert: {e}")

    logger.info("Single-run execution finished successfully!")


if __name__ == "__main__":
    main()
