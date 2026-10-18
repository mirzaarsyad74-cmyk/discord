import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
import requests
import discord

logger = logging.getLogger("steam_client_watcher")

KL_TZ = timezone(timedelta(hours=8))  # Kuala Lumpur / Malaysia Time (UTC+08:00)

STEAM_NEWS_URL = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=593110&count=6"
STEAM_LOGO_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/8/83/Steam_icon_logo.svg/512px-Steam_icon_logo.svg.png"


def to_kl_time_string(unix_timestamp: int) -> str:
    """Converts a Unix timestamp to formatted Kuala Lumpur Time (UTC+08:00)."""
    try:
        dt = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)
        dt_kl = dt.astimezone(KL_TZ)
        return dt_kl.strftime("%a, %b %d, %Y %I:%M %p UTC+08:00")
    except Exception as e:
        logger.error(f"Error converting timestamp {unix_timestamp}: {e}")
        return str(unix_timestamp)


def clean_steam_bbcode(text: str) -> str:
    """Cleans Steam news BBCode tags into clean Discord Markdown."""
    if not text:
        return ""
    # Convert BBCode tags
    text = re.sub(r'\[b\](.*?)\[/b\]', r'**\1**', text, flags=re.DOTALL)
    text = re.sub(r'\[i\](.*?)\[/i\]', r'*\1*', text, flags=re.DOTALL)
    text = re.sub(r'\[u\](.*?)\[/u\]', r'__\1__', text, flags=re.DOTALL)
    text = re.sub(r'\[url=(.*?)\](.*?)\[/url\]', r'[\2](\1)', text, flags=re.DOTALL)
    text = re.sub(r'\[list\]', '', text)
    text = re.sub(r'\[/list\]', '', text)
    text = re.sub(r'\[\*\]\s*\[p\](.*?)\[/p\]', r'• \1', text, flags=re.DOTALL)
    text = re.sub(r'\[\*\]', '• ', text)
    text = re.sub(r'\[p\]', '', text)
    text = re.sub(r'\[/p\]', '\n', text)
    text = re.sub(r'\[img\].*?\[/img\]', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def check_steam_client_updates() -> List[Dict[str, Any]]:
    """
    Fetches the latest official Steam Client updates from Valve's ISteamNews API.
    Returns list of update items.
    """
    try:
        res = requests.get(STEAM_NEWS_URL, timeout=10)
        if res.status_code != 200:
            logger.error(f"Failed to fetch Steam news: HTTP {res.status_code}")
            return []
        
        data = res.json()
        newsitems = data.get("appnews", {}).get("newsitems", [])
        
        client_updates = []
        for item in newsitems:
            title = item.get("title", "")
            # Only pick up actual Steam Client updates
            if "Steam Client Update" in title:
                client_updates.append(item)
                
        return client_updates
    except Exception as e:
        logger.error(f"Error checking Steam Client updates: {e}")
        return []


def create_steam_client_embed(item: Dict[str, Any]) -> discord.Embed:
    """Builds a Discord Embed for an official Steam Client update."""
    title = item.get("title", "Steam Client Update")
    timestamp = int(item.get("date", 0))
    kl_time = to_kl_time_string(timestamp)
    url = item.get("url", "https://store.steampowered.com/news/collection/steam/")
    raw_content = clean_steam_bbcode(item.get("contents", ""))

    # Format description
    desc_preview = raw_content[:2500] if len(raw_content) > 2500 else raw_content
    if len(raw_content) > 2500:
        desc_preview += f"...\n\n👉 **[Read Full Changelog on Steam]({url})**"

    embed = discord.Embed(
        title=f"📢 {title}",
        url=url,
        description=desc_preview or "A new Steam Client update has been released by Valve.",
        color=0x1A9FFF  # Official Steam Accent Blue
    )
    embed.set_thumbnail(url=STEAM_LOGO_URL)

    # Steam Version & Kuala Lumpur Build Time Fields
    embed.add_field(name="🔢 Steam Version (Build ID)", value=f"`{timestamp}`", inline=True)
    embed.add_field(name="🕒 Build Date (Kuala Lumpur Time)", value=f"**{kl_time}**", inline=True)
    embed.add_field(name="🌐 Official Steam Link", value=f"👉 **[Open Steam Announcement]({url})**", inline=False)

    embed.set_footer(text=f"Valve Corporation • Steam Client Watch • {kl_time}")
    return embed
