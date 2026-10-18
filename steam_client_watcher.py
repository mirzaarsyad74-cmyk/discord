import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
import requests
import xml.etree.ElementTree as ET
import discord

logger = logging.getLogger("steam_client_watcher")

KL_TZ = timezone(timedelta(hours=8))  # Kuala Lumpur / Malaysia Time (UTC+08:00)

STEAM_MONITOR_RAW_README = "https://raw.githubusercontent.com/OpenSteam001/steam-monitor/protobuf/README.md"
STEAM_MONITOR_COMMITS_ATOM = "https://github.com/OpenSteam001/steam-monitor/commits/protobuf.atom"
STEAM_MONITOR_REPO_URL = "https://github.com/OpenSteam001/steam-monitor/tree/protobuf"
STEAM_LOGO_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/8/83/Steam_icon_logo.svg/512px-Steam_icon_logo.svg.png"


def to_kl_time_string(unix_timestamp: int) -> str:
    """
    Converts a Unix timestamp into Kuala Lumpur Time (UTC+08:00),
    formatted to match the Steam 'About Steam' window:
    e.g. 'Wed, Oct 14, 2026 3:46 AM UTC +08:00'
    """
    try:
        dt = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)
        dt_kl = dt.astimezone(KL_TZ)
        time_part = dt_kl.strftime("%I:%M %p").lstrip("0")
        date_part = dt_kl.strftime("%a, %b %d, %Y")
        return f"{date_part} {time_part} UTC +08:00"
    except Exception as e:
        logger.error(f"Error converting timestamp {unix_timestamp}: {e}")
        return str(unix_timestamp)


def iso_to_kl_time_string(iso_str: str) -> str:
    """Converts an ISO-8601 timestamp string to Kuala Lumpur Time (UTC+08:00)."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        dt_kl = dt.astimezone(KL_TZ)
        time_part = dt_kl.strftime("%I:%M %p").lstrip("0")
        date_part = dt_kl.strftime("%a, %b %d, %Y")
        return f"{date_part} {time_part} UTC +08:00"
    except Exception as e:
        logger.error(f"Error converting ISO time {iso_str}: {e}")
        return iso_str


def check_steam_monitor_protobuf() -> Dict[str, Any]:
    """
    Monitors https://github.com/OpenSteam001/steam-monitor/tree/protobuf.
    Parses both README.md table and recent commits Atom feed.
    Returns:
    {
        "channels": {
            "stable": {"version": 1788652215, "updated_utc": "...", "build_kl": "..."},
            "beta": {"version": 1790380355, "updated_utc": "...", "build_kl": "..."}
        },
        "latest_commit": {
            "title": "Update Steam protobuf definitions (beta 1790380355)",
            "link": "https://github.com/...",
            "commit_id": "...",
            "updated_iso": "...",
            "updated_kl": "..."
        }
    }
    """
    result: Dict[str, Any] = {
        "channels": {},
        "latest_commit": None
    }

    # 1. Fetch README.md table
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        res = requests.get(STEAM_MONITOR_RAW_README, headers=headers, timeout=12)
        if res.status_code == 200:
            # Pattern matches markdown table rows: | Stable | 1788652215 | 2026-09-05 23:50:15 UTC |
            matches = re.findall(r'\|\s*([a-zA-Z]+)\s*\|\s*(\d+)\s*\|\s*([^|\n]+)\s*\|', res.text)
            for channel_raw, version_str, updated_utc in matches:
                chan_key = channel_raw.strip().lower()
                if chan_key in ("channel", "---"):
                    continue
                v_int = int(version_str)
                result["channels"][chan_key] = {
                    "channel_name": channel_raw.strip(),
                    "version": v_int,
                    "updated_utc": updated_utc.strip(),
                    "build_kl": to_kl_time_string(v_int)
                }
    except Exception as e:
        logger.error(f"Error fetching steam-monitor README: {e}")

    # 2. Fetch commits Atom feed
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        res_feed = requests.get(STEAM_MONITOR_COMMITS_ATOM, headers=headers, timeout=12)
        if res_feed.status_code == 200:
            root = ET.fromstring(res_feed.text)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            first_entry = root.find('atom:entry', ns)
            if first_entry is not None:
                title = first_entry.find('atom:title', ns).text.strip() if first_entry.find('atom:title', ns) is not None else ""
                link = first_entry.find('atom:link', ns).attrib.get('href', '') if first_entry.find('atom:link', ns) is not None else ""
                updated = first_entry.find('atom:updated', ns).text.strip() if first_entry.find('atom:updated', ns) is not None else ""
                id_tag = first_entry.find('atom:id', ns).text.strip() if first_entry.find('atom:id', ns) is not None else link
                commit_id = id_tag.split('/')[-1] if '/' in id_tag else id_tag

                result["latest_commit"] = {
                    "title": title,
                    "link": link,
                    "commit_id": commit_id,
                    "updated_iso": updated,
                    "updated_kl": iso_to_kl_time_string(updated) if updated else ""
                }
    except Exception as e:
        logger.error(f"Error fetching steam-monitor commits feed: {e}")

    return result


def create_steam_monitor_embed(
    channel_name: str,
    version: int,
    build_kl_time: str,
    commit_info: Optional[Dict[str, str]] = None
) -> discord.Embed:
    """
    Builds a Discord Embed for a new Steam Client version update,
    matching the layout of the official Steam 'About Steam' client window.
    """
    branch_display = f"{channel_name} Client" if channel_name.lower() == "stable" else f"Steam Beta Branch ({channel_name})"
    
    embed = discord.Embed(
        title=f"🎮 Steam Client Update ({branch_display})",
        url=STEAM_MONITOR_REPO_URL,
        color=0x1A9FFF  # Official Steam Accent Blue
    )
    embed.set_thumbnail(url=STEAM_LOGO_URL)

    embed.add_field(
        name="📌 Steam Beta Branch",
        value=f"**{branch_display}**",
        inline=True
    )
    embed.add_field(
        name="🔢 Steam Version",
        value=f"`{version}`",
        inline=True
    )
    embed.add_field(
        name="🕒 Steam Client Build Date",
        value=f"**{build_kl_time}**",
        inline=False
    )

    if commit_info and commit_info.get("title"):
        commit_title = commit_info.get("title")
        commit_link = commit_info.get("link")
        if commit_link:
            embed.add_field(
                name="📝 Monitor Commit",
                value=f"[{commit_title}]({commit_link})",
                inline=False
            )
        else:
            embed.add_field(
                name="📝 Monitor Commit",
                value=commit_title,
                inline=False
            )

    embed.add_field(
        name="🌐 Monitor Source",
        value=f"👉 **[OpenSteam001/steam-monitor (protobuf)]({STEAM_MONITOR_REPO_URL})**",
        inline=False
    )

    embed.set_footer(text=f"Steam Version Monitor • Kuala Lumpur Time (UTC+08:00)")
    return embed
