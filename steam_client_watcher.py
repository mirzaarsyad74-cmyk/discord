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
STEAM_LOGO_URL = "https://raw.githubusercontent.com/mirzaarsyad74-cmyk/discord/main/assets/icons/steam_gameoverlay_icon.png"
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


def format_steam_changelog(raw_text: str) -> str:
    """
    Parses Steam's raw BBCode / HTML announcement into Discord-formatted markdown.
    Preserves section headers and bullet points cleanly.
    """
    if not raw_text:
        return "*(No release notes provided)*"

    # 1. BBCode bold -> Markdown bold header
    text = re.sub(r'\[b\](.*?)\[/b\]', r'\n**\1**\n', raw_text)
    # 2. List items -> bullets
    text = re.sub(r'\[\*\](?:\[p\])?(.*?)(?:\[/p\])?\[/\*\]', r'• \1\n', text, flags=re.DOTALL)
    # 3. Clean remaining BBCode tags
    text = re.sub(r'\[/?(?:p|list|olist)\]', '\n', text)
    text = re.sub(r'\[img\].*?\[/img\]', '', text)
    text = re.sub(r'\[url=(.*?)\](.*?)\[/url\]', r'[\2](\1)', text)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)

    lines = []
    is_first = True
    for l in text.splitlines():
        l_str = l.strip()
        if not l_str:
            continue
        if is_first and ("a new steam client update" in l_str.lower() or "steam client update has been released" in l_str.lower()):
            lines.append(f"*{l_str}*")
            is_first = False
        elif l_str.startswith("**") and l_str.endswith("**"):
            lines.append(f"\n{l_str}")
        elif l_str.startswith("•"):
            lines.append(l_str)
        else:
            lines.append(f"• {l_str}")

    changelog_text = "\n".join(lines).strip()
    if len(changelog_text) > 1000:
        changelog_text = changelog_text[:997] + "…"
    return changelog_text or "*(No release notes provided)*"


STEAM_MANIFEST_STABLE_URL = "https://client-update.fastly.steamstatic.com/steam_client_win64"
STEAM_MANIFEST_BETA_URL = "https://client-update.fastly.steamstatic.com/steam_client_publicbeta_win64"


def get_steam_manifest_version(channel: str = "stable") -> Optional[int]:
    """
    Fetches the exact Steam Version (binary build timestamp) directly from Valve's official CDN manifest.
    This matches the exact version number displayed in the 'About Steam' client window.
    """
    url = STEAM_MANIFEST_STABLE_URL if channel.lower() == "stable" else STEAM_MANIFEST_BETA_URL
    try:
        res = requests.get(url, headers={"User-Agent": "Valve/Steam HTTP Client 1.0"}, timeout=6)
        if res.status_code == 200:
            for line in res.text.splitlines():
                if "version" in line:
                    parts = line.split('"')
                    if len(parts) >= 4 and parts[3].isdigit():
                        return int(parts[3])
    except Exception as e:
        logger.debug(f"Could not read Steam client manifest version: {e}")
    return None


def check_steam_client_updates(
    last_seen_stable: int = 0,
    last_seen_beta: int = 0
) -> tuple:
    """
    Monitors official Steam Client updates from Valve's official sources:
    1. Stable channel: Valve ISteamNews API for AppID 593110 (Steam Client).
    2. Beta channel: Valve Steam Client Beta RSS announcements.
    Returns: (new_updates_list, new_latest_stable_date, new_latest_beta_date)
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    new_updates: List[Dict[str, Any]] = []
    new_stable_date: Optional[int] = None
    new_beta_date: Optional[int] = None

    # Fetch optional protobuf commit info if reachable (enhancement)
    latest_commit = None
    try:
        proto_data = check_steam_monitor_protobuf()
        latest_commit = proto_data.get("latest_commit")
    except Exception as e:
        logger.debug(f"Could not fetch protobuf info: {e}")

    # 1. Check Stable Steam Client Updates (Valve ISteamNews API)
    try:
        res = requests.get(STEAM_CLIENT_NEWS_URL, headers=headers, timeout=12)
        if res.status_code == 200:
            items = res.json().get("appnews", {}).get("newsitems", [])
            client_updates = [i for i in items if "client update" in i.get("title", "").lower()]
            if client_updates:
                client_updates.sort(key=lambda x: int(x.get("date", 0)), reverse=True)
                latest_stable_item = client_updates[0]
                latest_stable_ts = int(latest_stable_item.get("date", 0))

                if last_seen_stable == 0:
                    logger.info(f"Initializing Steam Client Stable tracker with date: {latest_stable_ts}")
                    new_stable_date = latest_stable_ts
                elif latest_stable_ts > last_seen_stable:
                    for item in client_updates[:1]:
                        ts = int(item.get("date", 0))
                        gid = item.get("gid", "")
                        store_url = f"https://store.steampowered.com/news/app/593110/view/{gid}" if gid else item.get("url", "https://store.steampowered.com/news/app/593110")
                        cl_text = format_steam_changelog(item.get("contents", ""))
                        
                        # Query official CDN manifest for exact client build version (matches 'About Steam')
                        manifest_ver = get_steam_manifest_version("stable")
                        build_ver = manifest_ver if manifest_ver else ts

                        new_updates.append({
                            "channel_name": "Stable",
                            "branch_display": "Stable Client",
                            "version": build_ver,
                            "title": item.get("title", "Steam Client Update"),
                            "url": store_url,
                            "date": ts,
                            "build_kl": to_kl_time_string(build_ver),
                            "changelog": cl_text,
                            "commit_info": latest_commit
                        })
                    new_stable_date = latest_stable_ts
    except Exception as e:
        logger.error(f"Error checking official Steam client news API: {e}")

    # 2. Check Beta Steam Client Updates (Valve SteamClientBeta RSS)
    STEAM_BETA_RSS_URL = "https://steamcommunity.com/groups/SteamClientBeta/rss/"
    try:
        res_beta = requests.get(STEAM_BETA_RSS_URL, headers=headers, timeout=12)
        if res_beta.status_code == 200:
            root = ET.fromstring(res_beta.text)
            channel = root.find("channel")
            if channel is not None:
                items = channel.findall("item")
                beta_items = []
                for it in items:
                    title_el = it.find("title")
                    title = title_el.text.strip() if title_el is not None and title_el.text else ""
                    if "steam client beta" in title.lower():
                        pubdate_el = it.find("pubDate")
                        pubdate_str = pubdate_el.text.strip() if pubdate_el is not None and pubdate_el.text else ""
                        link_el = it.find("link")
                        link = link_el.text.strip() if link_el is not None and link_el.text else ""
                        desc_el = it.find("description")
                        desc = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
                        guid_el = it.find("guid")
                        guid = guid_el.text.strip() if guid_el is not None and guid_el.text else link

                        # Parse pubDate to Unix timestamp
                        try:
                            dt = datetime.strptime(pubdate_str, "%a, %d %b %Y %H:%M:%S %z")
                            ts = int(dt.timestamp())
                        except Exception:
                            ts = 0

                        beta_items.append({
                            "title": title,
                            "link": link,
                            "date": ts,
                            "guid": guid,
                            "desc": desc
                        })

                if beta_items:
                    beta_items.sort(key=lambda x: x["date"], reverse=True)
                    latest_beta_ts = beta_items[0]["date"]

                    if last_seen_beta == 0:
                        new_beta_date = latest_beta_ts
                    elif latest_beta_ts > last_seen_beta:
                        for b_item in beta_items[:1]:
                            cl_text = format_steam_changelog(b_item["desc"])
                            manifest_ver_beta = get_steam_manifest_version("beta")
                            build_ver_beta = manifest_ver_beta if manifest_ver_beta else b_item["date"]

                            new_updates.append({
                                "channel_name": "Beta",
                                "branch_display": "Steam Beta Branch",
                                "version": build_ver_beta,
                                "title": b_item["title"],
                                "url": b_item["link"],
                                "date": b_item["date"],
                                "build_kl": to_kl_time_string(build_ver_beta),
                                "changelog": cl_text,
                                "commit_info": latest_commit
                            })
                        new_beta_date = latest_beta_ts
    except Exception as e:
        logger.error(f"Error checking Steam Client Beta RSS: {e}")

    return new_updates, new_stable_date, new_beta_date


def fetch_steam_client_changelog() -> Optional[Dict[str, Any]]:
    """
    Fetches the most recent Steam Client Update announcement from Valve's official API.
    Returns: {"title": str, "url": str, "changelog": str} or None.
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        res = requests.get(STEAM_CLIENT_NEWS_URL, headers=headers, timeout=12)
        if res.status_code != 200:
            return None
        items = res.json().get("appnews", {}).get("newsitems", [])
        entry = next((i for i in items if "client update" in i.get("title", "").lower()), None)
        if not entry:
            return None

        gid = entry.get("gid", "")
        url = f"https://store.steampowered.com/news/app/593110/view/{gid}" if gid else entry.get("url", "https://store.steampowered.com/news/app/593110")
        return {
            "title": entry.get("title", "Steam Client Update"),
            "url": url,
            "changelog": format_steam_changelog(entry.get("contents", ""))
        }
    except Exception as e:
        logger.error(f"Error fetching Steam client changelog: {e}")
        return None


def create_steam_client_embed(
    item: Optional[Dict[str, Any]] = None,
    channel_name: Optional[str] = None,
    version: Optional[Any] = None,
    build_kl_time: Optional[str] = None,
    commit_info: Optional[Dict[str, str]] = None,
    **kwargs
) -> discord.Embed:
    """
    Builds a Discord Embed for an official Steam Client update,
    matching the layout of the official Steam 'About Steam' client window.
    Supports both dict argument or individual keyword arguments.
    """
    if isinstance(item, dict):
        channel_name = item.get("channel_name", channel_name or "Stable")
        version = item.get("version", version)
        build_kl_time = item.get("build_kl", build_kl_time)
        commit_info = item.get("commit_info", commit_info)
        title = item.get("title")
        url = item.get("url")
        changelog = item.get("changelog")
    else:
        title = kwargs.get("title")
        url = kwargs.get("url")
        changelog = kwargs.get("changelog")

    chan = str(channel_name or "Stable")
    branch_display = "Stable Client" if chan.lower() == "stable" else f"Steam Beta Branch ({chan})"
    embed_title = title or f"🎮 Steam Client Update ({branch_display})"
    target_url = url or "https://store.steampowered.com/news/app/593110"

    embed = discord.Embed(
        title=embed_title,
        url=target_url,
        color=0x0078D4  # Valve Steam Sapphire Blue
    )
    embed.set_thumbnail(url=STEAM_LOGO_URL)

    embed.add_field(
        name="📌 Steam Beta Branch",
        value=f"**{branch_display}**",
        inline=True
    )
    if version:
        embed.add_field(
            name="🔢 Steam Version",
            value=f"`{version}`",
            inline=True
        )
    if build_kl_time:
        embed.add_field(
            name="🕒 Steam Client Build Date",
            value=f"**{build_kl_time}**",
            inline=False
        )

    # Changelog / Release notes
    if not changelog:
        cl_data = fetch_steam_client_changelog()
        if cl_data:
            changelog = cl_data.get("changelog")

    if changelog:
        embed.add_field(
            name="📋 Official Release Notes",
            value=changelog,
            inline=False
        )

    if commit_info and commit_info.get("title"):
        commit_title = commit_info.get("title")
        commit_link = commit_info.get("link")
        commit_val = f"[{commit_title}]({commit_link})" if commit_link else commit_title
        embed.add_field(name="📝 Protobuf Commit", value=commit_val, inline=False)

    embed.add_field(
        name="🌐 Official Steam Announcement",
        value=f"👉 **[View Full Patch Notes on Steam Store]({target_url})**",
        inline=False
    )

    embed.set_footer(text="Steam Client Watch • Official Valve Announcement • GMT+8", icon_url=STEAM_LOGO_URL)
    return embed


# Backwards compatibility alias
create_steam_monitor_embed = create_steam_client_embed
