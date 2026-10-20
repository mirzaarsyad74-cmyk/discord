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
STEAM_CLIENT_NEWS_URL = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=593110&count=10&maxlength=2000&format=json&feeds=steam_community_announcements"


def to_kl_time_string(unix_timestamp: int) -> str:
    """
    Converts a Unix timestamp into Kuala Lumpur Time (GMT+8),
    displaying both GMT+8 and original UTC time:
    e.g. '`Wed, Oct 14, 2026 3:46 AM GMT+8`\n*(Original: 7:46 PM UTC)*'
    """
    try:
        dt_utc = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)
        dt_kl = dt_utc.astimezone(KL_TZ)
        time_part = dt_kl.strftime("%I:%M %p").lstrip("0")
        date_part = dt_kl.strftime("%a, %b %d, %Y")
        orig_part = dt_utc.strftime("%I:%M %p UTC").lstrip("0")
        return f"`{date_part} {time_part} GMT+8`\n*(Original: {orig_part})*"
    except Exception as e:
        logger.error(f"Error converting timestamp {unix_timestamp}: {e}")
        return str(unix_timestamp)


def iso_to_kl_time_string(iso_str: str) -> str:
    """Converts an ISO-8601 timestamp string to Kuala Lumpur Time (GMT+8)."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        dt_kl = dt.astimezone(KL_TZ)
        time_part = dt_kl.strftime("%I:%M %p").lstrip("0")
        date_part = dt_kl.strftime("%a, %b %d, %Y")
        orig_tz = dt.strftime("UTC%z")
        if len(orig_tz) == 8:
            orig_tz = f"{orig_tz[:6]}:{orig_tz[6:]}"
        orig_time = dt.strftime("%I:%M %p").lstrip("0")
        return f"`{date_part} {time_part} GMT+8`\n*(Original: {orig_time} {orig_tz})*"
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


def fetch_steam_client_changelog() -> Optional[Dict[str, Any]]:
    """
    Fetches the most recent Steam Client Update announcement from the ISteamNews API.
    Parses the plain-text content into Discord-formatted bullet sections.
    Returns: {"title": str, "url": str, "changelog": str} or None.
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        res = requests.get(STEAM_CLIENT_NEWS_URL, headers=headers, timeout=12)
        if res.status_code != 200:
            logger.warning(f"Steam client news API returned HTTP {res.status_code}")
            return None

        items = res.json().get("appnews", {}).get("newsitems", [])
        # Find the latest entry whose title contains 'client update'
        entry = next(
            (i for i in items if "client update" in i.get("title", "").lower()),
            None
        )
        if not entry:
            return None

        raw_content = entry.get("contents", "")
        title = entry.get("title", "Steam Client Update")
        url = entry.get("url", "https://store.steampowered.com/news/app/593110")

        # Steam client update content is a raw blob with no line breaks.
        # We insert newlines before recognizable section headers by looking for
        # capitalized words that appear after a period without a space (direct concatenation).
        # Pattern: lowercase/punctuation immediately followed by an uppercase word group = section header boundary.
        normalized = re.sub(
            r'([a-z.)])([A-Z][a-z])',   # e.g. "downloaded.Homescreen" → "downloaded.\nHomescreen"
            r'\1\n\2',
            raw_content
        )

        lines = [l.strip() for l in normalized.splitlines() if l.strip()]

        changelog_lines = []
        # Known Steam section header patterns
        section_re = re.compile(
            r'^(General|Downloads?|Storage|Library|Family(?: Sharing)?|Chat|Overlay|VR|'
            r'Remote Play|Broadcast|Screenshot|Controller|Steam Input|Achievement|'
            r'Mobile App|Settings|Homescreen?|Screensaver|Client|Linux|macOS|Windows|'
            r'Notifications?|Customization|Friends?|Community|Store)\b',
            re.IGNORECASE
        )

        is_first = True
        for line in lines:
            if is_first:
                # Skip or italicize the "A new Steam Client update has been released" preamble
                changelog_lines.append(f"*{line}*")
                is_first = False
                continue

            if section_re.match(line):
                # Section header — bold it
                changelog_lines.append(f"\n**{line}**")
            else:
                # Regular change item — add as bullet
                # Break long lines at sentence boundaries
                for sentence in re.split(r'(?<=[.!?])\s+', line):
                    sentence = sentence.strip()
                    if sentence and len(sentence) < 220:
                        changelog_lines.append(f"• {sentence}")

        changelog_text = "\n".join(changelog_lines).strip()
        # Discord embed field value cap = 1024 chars
        if len(changelog_text) > 1000:
            changelog_text = changelog_text[:997] + "…"

        return {
            "title": title,
            "url": url,
            "changelog": changelog_text or "*(No changelog content parsed)*"
        }
    except Exception as e:
        logger.error(f"Error fetching Steam client changelog: {e}")
        return None


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
        commit_val = f"[{commit_title}]({commit_link})" if commit_link else commit_title
        embed.add_field(name="📝 Protobuf Commit", value=commit_val, inline=False)

    # Fetch and embed latest Steam Client changelog
    changelog_data = fetch_steam_client_changelog()
    if changelog_data:
        cl_title = changelog_data["title"]
        cl_url = changelog_data["url"]
        cl_text = changelog_data["changelog"]
        embed.add_field(
            name=f"📋 Latest Release Notes: [{cl_title}]({cl_url})",
            value=cl_text,
            inline=False
        )

    embed.add_field(
        name="🌐 Monitor Source",
        value=f"👉 **[OpenSteam001/steam-monitor (protobuf)]({STEAM_MONITOR_REPO_URL})**",
        inline=False
    )

    embed.set_footer(text="Steam Version Monitor • GMT+8")
    return embed
