import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
logger = logging.getLogger("external_monitors")

KL_TZ = timezone(timedelta(hours=8))  # Kuala Lumpur / Malaysia Time (UTC+08:00)

FITGIRL_FEED_URL = "https://fitgirl-repacks.site/feed/"
DODI_FEED_URL = "https://dodi-repacks.site/feed/"
CRACKWATCH_RSS_URL = "https://old.reddit.com/r/CrackWatch/new/.rss"

# Brand Colors
COLOR_FITGIRL = 0xFF1493     # Deep Pink / Magenta
COLOR_DODI = 0x10AC84        # Emerald / Mint Green
COLOR_CRACKWATCH = 0xFF4500  # Reddit Vibrant Orange-Red

FITGIRL_ICON = "https://fitgirl-repacks.site/wp-content/uploads/2016/08/cropped-icon-192x192.jpg"
DODI_ICON = "https://dodi-repacks.site/wp-content/uploads/2021/04/cropped-cropped-DODI-Repacks-Site-Icon-192x192.png"
REDDIT_ICON = "https://www.redditstatic.com/desktop2x/img/favicon/android-icon-192x192.png"

REDDIT_HEADERS = {
    "User-Agent": "python:suga.nexus.crackwatch.monitor:v1.1 (by /u/suga_nexus contact: admin@suganexus.com)"
}
STANDARD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def parse_pubdate_to_kl(date_str: str) -> str:
    """Converts RSS pubDate or ISO date to Kuala Lumpur Time (UTC+08:00)."""
    if not date_str:
        return datetime.now(KL_TZ).strftime("%a, %b %d, %Y %I:%M %p UTC+08:00")
    
    # Try RFC 822 format (standard RSS: Sun, 18 Oct 2026 04:39:01 +0000)
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%a, %d %b %Y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S"
    ):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt_kl = dt.astimezone(KL_TZ)
            time_str = dt_kl.strftime("%I:%M %p").lstrip("0")
            return f"{dt_kl.strftime('%a, %b %d, %Y')} {time_str} UTC +08:00"
        except Exception:
            continue

    # Try ISO
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        dt_kl = dt.astimezone(KL_TZ)
        time_str = dt_kl.strftime("%I:%M %p").lstrip("0")
        return f"{dt_kl.strftime('%a, %b %d, %Y')} {time_str} UTC +08:00"
    except Exception:
        pass

    return f"{date_str} (UTC+08:00)"


def check_fitgirl_feed(state: dict) -> List[Dict[str, Any]]:
    """Fetches new releases from FitGirl Repacks official feed."""
    fg_state = state.setdefault("fitgirl", {})
    seen_links = set(fg_state.setdefault("seen_links", []))

    try:
        res = requests.get(FITGIRL_FEED_URL, headers=STANDARD_HEADERS, timeout=12)
        if res.status_code != 200:
            logger.warning(f"Failed to fetch FitGirl feed: HTTP {res.status_code}")
            return []

        soup = BeautifulSoup(res.content, "html.parser")
        items = soup.find_all("item")
        if not items:
            return []

        # First run initialization
        if not seen_links:
            logger.info("Initializing FitGirl tracker with current items...")
            for it in items:
                link_tag = it.find("link")
                if link_tag and link_tag.next_sibling:
                    seen_links.add(link_tag.next_sibling.strip())
            fg_state["seen_links"] = list(seen_links)[-200:]
            return []

        new_releases = []
        for it in items:
            title_tag = it.find("title")
            title = title_tag.get_text(strip=True) if title_tag else ""
            link_tag = it.find("link")
            link = link_tag.next_sibling.strip() if (link_tag and link_tag.next_sibling) else ""
            if not link and link_tag:
                link = link_tag.get_text(strip=True)

            if not link or link in seen_links:
                continue

            # Skip general administrative / upcoming summary posts
            if title.lower() in ("upcoming repacks", "donation instructions", "troubleshooting"):
                seen_links.add(link)
                continue

            pubdate_tag = it.find("pubdate")
            pubdate = pubdate_tag.get_text(strip=True) if pubdate_tag else ""
            kl_time = parse_pubdate_to_kl(pubdate)

            new_releases.append({
                "source": "FitGirl",
                "title": title,
                "link": link,
                "time_kl": kl_time
            })
            seen_links.add(link)

        fg_state["seen_links"] = list(seen_links)[-200:]
        return new_releases
    except Exception as e:
        logger.error(f"Error checking FitGirl feed: {e}")
        return []


def check_dodi_feed(state: dict) -> List[Dict[str, Any]]:
    """Fetches new releases from DODI Repacks official feed."""
    dodi_state = state.setdefault("dodi", {})
    seen_links = set(dodi_state.setdefault("seen_links", []))

    try:
        res = requests.get(DODI_FEED_URL, headers=STANDARD_HEADERS, timeout=12)
        if res.status_code != 200:
            logger.warning(f"Failed to fetch DODI feed: HTTP {res.status_code}")
            return []

        soup = BeautifulSoup(res.content, "html.parser")
        items = soup.find_all("item")
        if not items:
            return []

        # First run initialization
        if not seen_links:
            logger.info("Initializing DODI tracker with current items...")
            for it in items:
                link_tag = it.find("link")
                if link_tag and link_tag.next_sibling:
                    seen_links.add(link_tag.next_sibling.strip())
            dodi_state["seen_links"] = list(seen_links)[-200:]
            return []

        new_releases = []
        for it in items:
            title_tag = it.find("title")
            title = title_tag.get_text(strip=True) if title_tag else ""
            link_tag = it.find("link")
            link = link_tag.next_sibling.strip() if (link_tag and link_tag.next_sibling) else ""
            if not link and link_tag:
                link = link_tag.get_text(strip=True)

            if not link or link in seen_links:
                continue

            # Strip leading numbers like '2358- ' from title
            clean_title = re.sub(r'^\d+\s*[-–]\s*', '', title)

            pubdate_tag = it.find("pubdate")
            pubdate = pubdate_tag.get_text(strip=True) if pubdate_tag else ""
            kl_time = parse_pubdate_to_kl(pubdate)

            new_releases.append({
                "source": "DODI",
                "title": clean_title,
                "link": link,
                "time_kl": kl_time
            })
            seen_links.add(link)

        dodi_state["seen_links"] = list(seen_links)[-200:]
        return new_releases
    except Exception as e:
        logger.error(f"Error checking DODI feed: {e}")
        return []


def check_crackwatch_reddit(state: dict) -> List[Dict[str, Any]]:
    """Fetches new releases and scene crack announcements from r/CrackWatch."""
    cw_state = state.setdefault("crackwatch", {})
    seen_ids = set(cw_state.setdefault("seen_ids", []))

    try:
        import html
        res = requests.get(CRACKWATCH_RSS_URL, headers=REDDIT_HEADERS, timeout=12)
        if res.status_code == 429:
            logger.info("Reddit rate-limited (HTTP 429); will retry on next cycle.")
            return []
        if res.status_code != 200:
            logger.warning(f"Failed to fetch r/CrackWatch: HTTP {res.status_code}")
            return []

        entries = re.findall(r'<entry>(.*?)</entry>', res.text, re.DOTALL)
        if not entries:
            return []

        # First run initialization
        if not seen_ids:
            logger.info("Initializing r/CrackWatch tracker with current entries...")
            for e in entries:
                id_m = re.search(r'<id>(.*?)</id>', e)
                if id_m:
                    seen_ids.add(id_m.group(1).strip())
            cw_state["seen_ids"] = list(seen_ids)[-250:]
            return []

        new_items = []
        for e in entries:
            id_m = re.search(r'<id>(.*?)</id>', e)
            entry_id = id_m.group(1).strip() if id_m else ""
            if not entry_id or entry_id in seen_ids:
                continue

            title_m = re.search(r'<title>(.*?)</title>', e)
            title = html.unescape(title_m.group(1).strip()) if title_m else ""

            link_m = re.search(r'<link\s+href="([^"]+)"', e)
            link = link_m.group(1).strip() if link_m else ""

            upd_m = re.search(r'<updated>(.*?)</updated>', e)
            updated = upd_m.group(1).strip() if upd_m else ""

            author_m = re.search(r'<author>\s*<name>(.*?)</name>', e)
            author = author_m.group(1).strip() if author_m else "CrackWatch"

            # Filter out non-release posts (questions, humor, drama)
            # Prioritize posts with scene tags, [Release], [Repack], [Crack], Daily Releases
            t_lower = title.lower()
            is_valid_release = any([
                re.search(r'\b(?:rune|tenoke|flt|skidrow|codex|razor1911|fitgirl|dodi|elamigos|goldberg)\b', t_lower),
                re.search(r'\b(?:repack|crack(?:ed|fix)?|bypass|hypervisor|denuvo)\b', t_lower),
                "daily releases" in t_lower,
                title.startswith("[Release]") or title.startswith("[Repack]") or title.startswith("[Crack]")
            ])

            if not is_valid_release:
                seen_ids.add(entry_id)
                continue

            kl_time = parse_pubdate_to_kl(updated)
            new_items.append({
                "source": "Reddit r/CrackWatch",
                "title": title,
                "link": link,
                "author": author,
                "time_kl": kl_time
            })
            seen_ids.add(entry_id)

        cw_state["seen_ids"] = list(seen_ids)[-250:]
        return new_items
    except Exception as e:
        logger.error(f"Error checking r/CrackWatch: {e}")
        return []


def create_fitgirl_embed(item: Dict[str, Any]):
    """Builds a Discord Embed for a new FitGirl Repack with signature Magenta color."""
    import discord
    title = item["title"]
    clean_title = re.sub(r'(?i)\s*\[?fitgirl\s*repack\]?', '', title).strip()

    embed = discord.Embed(
        title=f"🎀 [FitGirl Repack] {clean_title}",
        url=item["link"],
        color=COLOR_FITGIRL
    )
    embed.set_thumbnail(url=FITGIRL_ICON)
    embed.add_field(name="📦 Full Repack Title", value=f"`{title}`", inline=False)
    embed.add_field(name="👑 Repacker", value="**FitGirl**", inline=True)
    embed.add_field(name="🏷️ Category", value="**Game Repack**", inline=True)
    embed.add_field(name="🕒 Release Time", value=f"`{item['time_kl']}`", inline=True)
    embed.add_field(
        name="🌐 Official Download Page",
        value=f"👉 **[Open FitGirl-Repacks Post]({item['link']})**",
        inline=False
    )
    embed.set_footer(text=f"FitGirl Repacks Monitor • Kuala Lumpur Time (UTC+08:00)")
    return embed


def create_dodi_embed(item: Dict[str, Any]):
    """Builds a Discord Embed for a new DODI Repack with signature Emerald Green color."""
    import discord
    title = item["title"]
    clean_title = re.sub(r'(?i)\s*\[?dodi\s*repack\]?', '', title).strip()

    embed = discord.Embed(
        title=f"⚡ [DODI Repack] {clean_title}",
        url=item["link"],
        color=COLOR_DODI
    )
    embed.set_thumbnail(url=DODI_ICON)
    embed.add_field(name="📦 Full Repack Title", value=f"`{title}`", inline=False)
    embed.add_field(name="👑 Repacker", value="**DODI**", inline=True)
    embed.add_field(name="🏷️ Category", value="**Game Repack**", inline=True)
    embed.add_field(name="🕒 Release Time", value=f"`{item['time_kl']}`", inline=True)
    embed.add_field(
        name="🌐 Official Download Page",
        value=f"👉 **[Open DODI-Repacks Post]({item['link']})**",
        inline=False
    )
    embed.set_footer(text=f"DODI Repacks Monitor • Kuala Lumpur Time (UTC+08:00)")
    return embed


def create_crackwatch_embed(item: Dict[str, Any]):
    """Builds a Discord Embed for a new r/CrackWatch alert with signature Reddit Orange color."""
    import discord
    title = item["title"]
    is_voices38 = "voices38" in title.lower()
    embed_color = 0xFFD700 if is_voices38 else COLOR_CRACKWATCH
    prefix = "⚡ [r/CrackWatch • Voices38 Alert]" if is_voices38 else "👀 [r/CrackWatch]"

    embed = discord.Embed(
        title=f"{prefix} {title}",
        url=item["link"],
        color=embed_color
    )
    embed.set_thumbnail(url=REDDIT_ICON)
    if is_voices38:
        embed.add_field(name="⚡ Special Release Alert", value="**Voices38 Denuvo Bypass / Crack Detected!**", inline=False)
    embed.add_field(name="📢 Release Title", value=f"**{title}**", inline=False)
    embed.add_field(name="👤 Posted By", value=f"`{item.get('author', 'Redditor')}`", inline=True)
    embed.add_field(name="🕒 Posted Time", value=f"`{item['time_kl']}`", inline=True)
    embed.add_field(
        name="🌐 Reddit Thread",
        value=f"👉 **[View Thread on r/CrackWatch]({item['link']})**",
        inline=False
    )
    embed.set_footer(text=f"Reddit r/CrackWatch Monitor • Kuala Lumpur Time (UTC+08:00)")
    return embed
