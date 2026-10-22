import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings

try:
    from curl_cffi import requests as cffi_requests
except ImportError:
    cffi_requests = None

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
logger = logging.getLogger("external_monitors")

KL_TZ = timezone(timedelta(hours=8))  # Kuala Lumpur / Malaysia Time (UTC+08:00)

STEAMRIP_BASE_URL = "https://steamrip.com/"
STEAMRIP_UPDATED_URL = "https://steamrip.com/updated-games/"
SUO_BASE_URL = "https://steamunlockonennabe.click/"
SUO_API_URL = "https://steamunlockonennabe.duckdns.org/api/onennabe"
SUO_DIRECT_IP_URL = "https://34.158.47.50/api/onennabe"
FITGIRL_FEED_URL = "https://fitgirl-repacks.site/feed/"
DODI_FEED_URL = "https://dodi-repacks.site/feed/"
CRACKWATCH_RSS_URL = "https://www.reddit.com/r/CrackWatch/new/.rss"
ONLINEFIX_RSS_URL = "https://online-fix.me/rss.xml"

# Brand Colors (Distinct spectrum - zero similar colors)
COLOR_STEAMRIP = 0x8B5CF6    # Vivid Royal Violet / Purple
COLOR_SUO = 0xF59E0B         # Cyber Amber Gold / Key Yellow
COLOR_FITGIRL = 0xFF1493     # Neon Magenta / Deep Pink
COLOR_DODI = 0x10B981        # Emerald / Forest Green
COLOR_CRACKWATCH = 0xFF5722  # Reddit Vibrant Flame Orange
COLOR_STEAM_DEAL = 0xE11D48  # Steam Sale Crimson / Discount Red
COLOR_ONLINEFIX = 0x00E5FF   # Neon Electric Aqua / Cyan

STEAMRIP_ICON = "https://steamrip.com/wp-content/uploads/2021/06/cropped-favicon1-192x192.png"
SUO_ICON = "https://raw.githubusercontent.com/ZackTheGrumpy/Website/refs/heads/main/logo.ico"
FITGIRL_ICON = "https://fitgirl-repacks.site/wp-content/uploads/2016/08/cropped-icon-192x192.jpg"
DODI_ICON = "https://dodi-repacks.site/wp-content/uploads/2021/04/cropped-cropped-DODI-Repacks-Site-Icon-192x192.png"
REDDIT_ICON = "https://www.redditstatic.com/desktop2x/img/favicon/android-icon-192x192.png"
STEAM_DEAL_ICON = "https://store.cloudflare.steamstatic.com/public/shared/images/responsive/share_steam_logo.png"
ONLINEFIX_ICON = "https://online-fix.me/favicon.ico"

SUO_GENRE_MAP = {
    0: "Unknown Genre",
    1: "Action",
    2: "Strategy",
    3: "RPG",
    4: "Casual",
    5: "Strategy",
    9: "Racing",
    10: "MMO",
    11: "FPS",
    12: "Puzzle",
    18: "Sports",
    23: "Indie",
    25: "Adventure",
    28: "Simulation",
    29: "Massively Multiplayer",
    33: "Indie",
    34: "Indie",
    37: "Free To Play",
    50: "Indie",
    51: "Animation & Modeling",
    52: "Music",
    53: "Software & Tools",
    54: "Education",
    55: "Software & Tools",
    70: "Early Access",
    71: "Sexual Content",
    72: "Sexual Content",
    73: "Adventure",
    74: "Gore"
}

REDDIT_HEADERS = {
    "User-Agent": "python:suga.nexus.crackwatch.monitor:v1.1 (by /u/suga_nexus contact: admin@suganexus.com)"
}
STANDARD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def parse_pubdate_to_kl(date_str: str) -> str:
    """Converts RSS pubDate or ISO date to Kuala Lumpur Time (GMT+8) with original time."""
    if not date_str:
        return f"`{datetime.now(KL_TZ).strftime('%a, %b %d, %Y %I:%M %p GMT+8')}`"
    
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
            kl_str = dt_kl.strftime("%a, %b %d, %Y %I:%M %p GMT+8")
            orig_time = dt.strftime("%I:%M %p").lstrip("0")
            orig_tz = dt.strftime("UTC%z")
            if len(orig_tz) == 8:
                orig_tz = f"{orig_tz[:6]}:{orig_tz[6:]}"
            return f"`{kl_str}`\n*(Original: {orig_time} {orig_tz})*"
        except Exception:
            continue

    # Try ISO
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        dt_kl = dt.astimezone(KL_TZ)
        kl_str = dt_kl.strftime("%a, %b %d, %Y %I:%M %p GMT+8")
        orig_time = dt.strftime("%I:%M %p").lstrip("0")
        orig_tz = dt.strftime("UTC%z")
        if len(orig_tz) == 8:
            orig_tz = f"{orig_tz[:6]}:{orig_tz[6:]}"
        return f"`{kl_str}`\n*(Original: {orig_time} {orig_tz})*"
    except Exception:
        pass

    return f"`{date_str} GMT+8`"


def fetch_web_content(url: str, headers: dict = None, timeout: int = 8) -> Optional[str]:
    """Fetches web content using curl_cffi (impersonating Chrome) with fallback to requests."""
    req_headers = headers or STANDARD_HEADERS
    if cffi_requests:
        try:
            r = cffi_requests.get(url, impersonate="chrome120", timeout=timeout)
            if r.status_code == 200:
                return r.text
            logger.warning(f"curl_cffi fetch {url} returned HTTP {r.status_code}")
        except Exception as e:
            logger.debug(f"curl_cffi failed for {url}: {e}, falling back to requests")

    try:
        r = requests.get(url, headers=req_headers, timeout=timeout)
        if r.status_code == 200:
            return r.text
        logger.warning(f"requests fetch {url} returned HTTP {r.status_code}")
        return None
    except Exception as e:
        logger.warning(f"Notice: Could not reach {url} (cloud datacenter filtered): {e}")
        return None


def update_seen_list(existing: List[Any], new_items: List[Any], max_len: int = 800) -> List[str]:
    """
    Maintains seen IDs in strictly chronological (FIFO) order.
    Preserves existing order, appends new items, and safely trims
    from the beginning so recently seen items are NEVER evicted.
    """
    seen_dict = {str(x): None for x in (existing or []) if x}
    for item in new_items:
        if item:
            seen_dict[str(item)] = None
    return list(seen_dict.keys())[-max_len:]


def check_fitgirl_feed(state: dict) -> List[Dict[str, Any]]:
    """Fetches new releases from FitGirl Repacks official feed."""
    fg_state = state.setdefault("fitgirl", {})
    seen_links = set(str(x) for x in fg_state.get("seen_links", []))

    try:
        content = fetch_web_content(FITGIRL_FEED_URL, timeout=6)
        if not content:
            return []

        soup = BeautifulSoup(content, "html.parser")
        items = soup.find_all("item")
        if not items:
            return []

        # First run initialization
        if not seen_links:
            logger.info("Initializing FitGirl tracker with current items...")
            init_links = []
            for it in items:
                link_tag = it.find("link")
                link = link_tag.next_sibling.strip() if (link_tag and link_tag.next_sibling) else ""
                if not link and link_tag:
                    link = link_tag.get_text(strip=True)
                if link:
                    init_links.append(link)
            fg_state["seen_links"] = update_seen_list([], init_links, max_len=500)
            return []

        new_releases = []
        newly_seen = []
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
                newly_seen.append(link)
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
            newly_seen.append(link)

        if newly_seen:
            fg_state["seen_links"] = update_seen_list(fg_state.get("seen_links", []), newly_seen, max_len=500)
        return list(reversed(new_releases))
    except Exception as e:
        logger.error(f"Error checking FitGirl feed: {e}")
        return []


def check_dodi_feed(state: dict) -> List[Dict[str, Any]]:
    """Fetches new releases from DODI Repacks official feed."""
    dodi_state = state.setdefault("dodi", {})
    seen_links = set(str(x) for x in dodi_state.get("seen_links", []))

    try:
        content = fetch_web_content(DODI_FEED_URL, timeout=15)
        if not content:
            return []

        soup = BeautifulSoup(content, "html.parser")
        items = soup.find_all("item")
        if not items:
            return []

        # First run initialization
        if not seen_links:
            logger.info("Initializing DODI tracker with current items...")
            init_links = []
            for it in items:
                link_tag = it.find("link")
                link = link_tag.next_sibling.strip() if (link_tag and link_tag.next_sibling) else ""
                if not link and link_tag:
                    link = link_tag.get_text(strip=True)
                if link:
                    init_links.append(link)
            dodi_state["seen_links"] = update_seen_list([], init_links, max_len=500)
            return []

        new_releases = []
        newly_seen = []
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
            newly_seen.append(link)

        if newly_seen:
            dodi_state["seen_links"] = update_seen_list(dodi_state.get("seen_links", []), newly_seen, max_len=500)
        return list(reversed(new_releases))
    except Exception as e:
        logger.error(f"Error checking DODI feed: {e}")
        return []


def check_crackwatch_reddit(state: dict) -> List[Dict[str, Any]]:
    """Fetches new releases and scene crack announcements from r/CrackWatch."""
    cw_state = state.setdefault("crackwatch", {})
    seen_ids = set(str(x) for x in cw_state.get("seen_ids", []))

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
            init_ids = []
            for e in entries:
                id_m = re.search(r'<id>(.*?)</id>', e)
                if id_m:
                    init_ids.append(id_m.group(1).strip())
            cw_state["seen_ids"] = update_seen_list([], init_ids, max_len=500)
            return []

        new_items = []
        newly_seen = []
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
                newly_seen.append(entry_id)
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
            newly_seen.append(entry_id)

        if newly_seen:
            cw_state["seen_ids"] = update_seen_list(cw_state.get("seen_ids", []), newly_seen, max_len=500)
        return list(reversed(new_items))
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
    embed.add_field(name="🕒 Release Time (GMT+8)", value=item["time_kl"], inline=True)
    embed.add_field(
        name="🌐 Official Download Page",
        value=f"👉 **[Open FitGirl-Repacks Post]({item['link']})**",
        inline=False
    )
    embed.set_footer(text="FitGirl Repacks Monitor • GMT+8")
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
    embed.add_field(name="🕒 Release Time (GMT+8)", value=item["time_kl"], inline=True)
    embed.add_field(
        name="🌐 Official Download Page",
        value=f"👉 **[Open DODI-Repacks Post]({item['link']})**",
        inline=False
    )
    embed.set_footer(text="DODI Repacks Monitor • GMT+8")
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
    embed.add_field(name="🕒 Posted Time (GMT+8)", value=item["time_kl"], inline=True)
    embed.add_field(
        name="🌐 Reddit Thread",
        value=f"👉 **[View Thread on r/CrackWatch]({item['link']})**",
        inline=False
    )
    embed.set_footer(text="Reddit r/CrackWatch Monitor • GMT+8")
    return embed


def clean_and_translate_onlinefix(title: str, category: str, desc_html: str):
    """
    Cleans and translates Online-Fix.me Russian templates into crisp English.
    """
    # 1. Title translation & cleaning
    clean_title = re.sub(r'(?i)\s*по\s+сети\b', ' [Online / Co-op Fix]', title).strip()
    clean_title = re.sub(r'(?i)обновлено\s+до\s+версии', 'Updated to v', clean_title)
    clean_title = re.sub(r'(?i)обновлен[оа]?\b', 'Updated', clean_title)
    clean_title = re.sub(r'(?i)фикс\s+обновлен', 'Fix Updated', clean_title)

    # 2. Category translation
    cat_map = {
        'Приключения': 'Adventure', 'Экшен': 'Action', 'Гонки': 'Racing',
        'Симуляторы': 'Simulator', 'Стратегии': 'Strategy', 'Ужасы': 'Horror',
        'Выживание': 'Survival', 'Шутеры': 'Shooter', 'Ролевые': 'RPG',
        'Руководства запуска': 'Multiplayer Launch Guide'
    }
    cats = [c.strip() for c in category.split(',') if c.strip()]
    en_cats = [cat_map.get(c, c) for c in cats]
    category_str = ', '.join(en_cats) if en_cats else 'Multiplayer Game Fix'

    # 3. Platform / Network
    desc_lower = desc_html.lower()
    if 'steam' in desc_lower:
        play_via = 'Steam (Spacewar / Steamworks)'
    elif 'epic' in desc_lower:
        play_via = 'Epic Games'
    elif 'lan' in desc_lower:
        play_via = 'LAN / Emulators'
    else:
        play_via = 'Steam / Online-Fix Network'

    # 4. Modes supported
    has_coop = 'fa-check' in desc_html and ('Кооператив' in desc_html or 'Cooperative' in desc_html or 'кооп' in desc_lower)
    has_multi = 'fa-check' in desc_html and ('Мультиплеер' in desc_html or 'Multiplayer' in desc_html)

    modes = []
    if has_coop:
        modes.append('✅ Co-op Supported')
    if has_multi:
        modes.append('✅ Multiplayer PvP')
    if not modes:
        modes = ['✅ Online Co-op / Multiplayer']
    modes_str = ' • '.join(modes)

    return clean_title, category_str, play_via, modes_str


def check_onlinefix_feed(state: dict) -> List[Dict[str, Any]]:
    """
    Checks for newly published multiplayer & co-op fixes on Online-Fix.me.
    Translates Russian descriptions and tags into English.
    Uses strict FIFO ordered tracking to prevent duplicate postings.
    """
    of_state = state.setdefault("onlinefix", {})
    seen_links = set(str(x) for x in of_state.get("seen_links", []))

    try:
        import xml.etree.ElementTree as ET
        res = requests.get(
            ONLINEFIX_RSS_URL,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
            timeout=10
        )
        if res.status_code != 200:
            logger.warning(f"Failed to fetch Online-Fix.me RSS: HTTP {res.status_code}")
            return []

        root = ET.fromstring(res.content)
        channel = root.find("channel")
        if channel is None:
            return []
        items = channel.findall("item")
        if not items:
            return []

        # First run initialization: record current entries so we don't spam history
        if not seen_links:
            logger.info(f"Initializing Online-Fix.me tracker with {len(items)} current items...")
            init_links = []
            for it in items:
                link_el = it.find("link")
                if link_el is not None and link_el.text:
                    init_links.append(link_el.text.strip())
            of_state["seen_links"] = update_seen_list([], init_links, max_len=500)
            return []

        new_items = []
        newly_seen_links = []
        for it in items:
            link_el = it.find("link")
            link = link_el.text.strip() if (link_el is not None and link_el.text) else ""
            if not link or link in seen_links:
                continue

            raw_title = it.find("title").text if it.find("title") is not None else "Online-Fix Game"
            raw_category = it.find("category").text if it.find("category") is not None else ""
            raw_desc = it.find("description").text if it.find("description") is not None else ""
            pub_date = it.find("pubDate").text if it.find("pubDate") is not None else ""

            clean_title, category_en, play_via, modes_en = clean_and_translate_onlinefix(
                raw_title, raw_category, raw_desc
            )
            time_kl = parse_pubdate_to_kl(pub_date)

            new_items.append({
                "source": "Online-Fix.me",
                "title": clean_title,
                "raw_title": raw_title,
                "link": link,
                "category": category_en,
                "network": play_via,
                "modes": modes_en,
                "time_kl": time_kl
            })
            seen_links.add(link)
            newly_seen_links.append(link)

        if newly_seen_links:
            of_state["seen_links"] = update_seen_list(of_state.get("seen_links", []), newly_seen_links, max_len=500)

        return list(reversed(new_items))

    except Exception as e:
        logger.error(f"Error checking Online-Fix feed: {e}")
        return []


def create_onlinefix_embed(item: Dict[str, Any]):
    """Builds a Discord Embed for a new Online-Fix.me release with signature Teal/Cyan color."""
    import discord
    title = item["title"]

    embed = discord.Embed(
        title=f"🎮 [Online-Fix] {title}",
        url=item["link"],
        color=COLOR_ONLINEFIX
    )
    embed.set_thumbnail(url=ONLINEFIX_ICON)
    embed.add_field(name="📦 Game Release / Fix", value=f"**{title}**", inline=False)
    embed.add_field(name="🌐 Multiplayer Network", value=f"`{item.get('network', 'Steam (Spacewar)')}`", inline=True)
    embed.add_field(name="👥 Supported Modes", value=f"`{item.get('modes', 'Co-op')}`", inline=True)
    embed.add_field(name="📂 Category", value=f"**{item.get('category', 'Multiplayer Fix')}**", inline=True)
    embed.add_field(name="🕒 Release Time (GMT+8)", value=item["time_kl"], inline=True)
    embed.add_field(
        name="🔗 Fix & Installation Guide",
        value=f"👉 **[Open Online-Fix.me Page]({item['link']})**",
        inline=False
    )
    embed.set_footer(text="Online-Fix.me Monitor • Multiplayer & Co-op Fixes • GMT+8", icon_url=ONLINEFIX_ICON)
    return embed


def check_steamrip_updates(state: dict) -> List[Dict[str, Any]]:
    """
    Fetches newly added game releases and recently updated games from https://steamrip.com/.
    Bypasses Cloudflare protection using curl_cffi browser impersonation.
    Deduplicates across Home Page and Updated Games page so no release is double-posted.
    """
    sr_state = state.setdefault("steamrip", {})
    seen_ids = set(str(x) for x in sr_state.get("seen_ids", []))
    seen_slugs = set(str(x) for x in sr_state.get("seen_slugs", []))
    raw_items: List[Dict[str, Any]] = []

    get_html = fetch_web_content

    # 1. Fetch Updated Games Page first (has more specific patch/build information)
    upd_html = get_html(STEAMRIP_UPDATED_URL)
    if upd_html:
        try:
            soup2 = BeautifulSoup(upd_html, "html.parser")
            current_date = ""
            container = soup2.select_one(".entry-content > div") or soup2.select_one(".entry-content")
            if container:
                for child in container.children:
                    if not child.name:
                        continue
                    if "updated-list-date" in child.get("class", []):
                        current_date = child.get_text(strip=True)
                    elif "updated-list" in child.get("class", []):
                        for li in child.find_all("li"):
                            a = li.find("a")
                            if not a:
                                continue
                            href = a.get("href", "")
                            if not href:
                                continue
                            full_url = urljoin(STEAMRIP_BASE_URL, href)
                            slug = full_url.rstrip("/").split("/")[-1]
                            title_el = a.select_one(".updated-card-title")
                            raw_title = title_el.get_text(strip=True) if title_el else a.get_text(strip=True)
                            clean_title = re.sub(r'(?i)\s*free\s+download\b', '', raw_title).strip()
                            build_el = a.select_one(".updated-list-build")
                            build = build_el.get_text(strip=True) if build_el else ""

                            item_id = f"upd_{slug}_{build}" if build else f"upd_{slug}"
                            raw_items.append({
                                "id": item_id,
                                "slug": slug,
                                "title": clean_title,
                                "raw_title": raw_title,
                                "url": full_url,
                                "version": build,
                                "meta": f"Updated: {current_date}" if current_date else "Game Update",
                                "category": "Game Update",
                                "thumbnail": None,
                                "poster": None,
                                "type": "Game Update",
                                "time_kl": parse_pubdate_to_kl(current_date) if current_date else parse_pubdate_to_kl("")
                            })
        except Exception as e:
            logger.error(f"Error parsing SteamRIP updated games: {e}")

    # 2. Fetch Home Page (New Game Releases)
    home_html = get_html(STEAMRIP_BASE_URL)
    if home_html:
        try:
            soup = BeautifulSoup(home_html, "html.parser")
            cards = soup.select(".post-item")
            for c in cards:
                post_id = None
                for cls in c.get("class", []):
                    if cls.startswith("post-") and cls != "post-item":
                        post_id = cls.replace("post-", "")
                        break

                link_el = c.select_one("a.post-thumb") or c.select_one("h2.post-title a")
                href = link_el.get("href") if link_el else ""
                if not href:
                    continue
                full_url = urljoin(STEAMRIP_BASE_URL, href)
                slug = full_url.rstrip("/").split("/")[-1]

                title_el = c.select_one(".post-title a") or c.select_one(".the-post-title")
                raw_title = title_el.get_text(strip=True) if title_el else ""
                clean_title = re.sub(r'(?i)\s*free\s+download\b', '', raw_title).strip()

                cat_el = c.select_one(".post-cat")
                category = cat_el.get_text(strip=True) if cat_el else "Game"

                tag_el = c.select_one(".tagmetafield")
                version = tag_el.get_text(strip=True) if tag_el else ""

                meta_el = c.select_one(".game-meta-line")
                meta_text = meta_el.get_text(strip=True) if meta_el else ""

                img_el = c.select_one("img.thumbnail-image")
                img_src = ""
                if img_el:
                    img_src = img_el.get("data-src") or img_el.get("src")
                    if img_src and img_src.startswith("data:"):
                        noscript = c.select_one("noscript img")
                        if noscript and noscript.get("src"):
                            img_src = noscript.get("src")
                    if img_src and not img_src.startswith("data:"):
                        img_src = urljoin(STEAMRIP_BASE_URL, img_src)

                item_id = f"post_{post_id}" if post_id else f"url_{slug}"
                poster_src = (
                    img_src.replace("_thumbnail_", "_featured_").replace("_thumbnail.", "_featured.")
                    if img_src else None
                )
                raw_items.append({
                    "id": item_id,
                    "slug": slug,
                    "title": clean_title,
                    "raw_title": raw_title,
                    "url": full_url,
                    "version": version,
                    "meta": meta_text,
                    "category": category,
                    "thumbnail": img_src or None,
                    "poster": poster_src,
                    "type": "New Release",
                    "time_kl": parse_pubdate_to_kl("")
                })
        except Exception as e:
            logger.error(f"Error parsing SteamRIP home page: {e}")

    if not raw_items:
        return []

    # First run initialization: record current items to state so we don't spam history
    if not seen_ids and not seen_slugs:
        logger.info(f"Initializing SteamRIP tracker with {len(raw_items)} current items...")
        init_ids = [it["id"] for it in raw_items]
        init_slugs = [it["slug"] for it in raw_items if it.get("slug")]
        sr_state["seen_ids"] = update_seen_list([], init_ids, max_len=600)
        sr_state["seen_slugs"] = update_seen_list([], init_slugs, max_len=600)
        return []

    def fetch_steamrip_poster(game_url: str) -> Optional[str]:
        page_html = get_html(game_url)
        if page_html:
            try:
                page_soup = BeautifulSoup(page_html, "html.parser")
                og_img = page_soup.find("meta", property="og:image")
                if og_img and og_img.get("content"):
                    return og_img.get("content")
                feat = page_soup.select_one(".featured-image img, .single-post-thumb img, .entry-content img")
                if feat:
                    src = feat.get("src") or feat.get("data-src")
                    if src and not src.startswith("data:"):
                        return urljoin(STEAMRIP_BASE_URL, src)
            except Exception as ex:
                logger.debug(f"Could not extract poster from {game_url}: {ex}")
        return None

    # Deduplicate items in current batch (e.g. if a game is both in Updated and Home)
    deduped_items: List[Dict[str, Any]] = []
    seen_in_batch = set()
    for it in raw_items:
        slug = it.get("slug", "")
        ver = it.get("version", "").strip()
        sig = f"{slug}:{ver}" if ver else slug
        if sig in seen_in_batch or slug in seen_in_batch:
            continue
        seen_in_batch.add(sig)
        if it.get("type") == "Game Update":
            seen_in_batch.add(slug)
        deduped_items.append(it)

    new_releases: List[Dict[str, Any]] = []
    newly_seen_ids = []
    newly_seen_slugs = []

    for it in deduped_items:
        slug = it.get("slug", "")
        ver = it.get("version", "").strip()
        sig = f"{slug}:{ver}" if ver else slug
        item_id = it["id"]

        # Check if already seen by ID or slug signature
        if item_id in seen_ids or sig in seen_slugs:
            continue

        if not it.get("poster"):
            it["poster"] = fetch_steamrip_poster(it["url"])

        new_releases.append(it)
        seen_ids.add(item_id)
        seen_slugs.add(sig)
        newly_seen_ids.append(item_id)
        newly_seen_slugs.append(sig)

    if newly_seen_ids:
        sr_state["seen_ids"] = update_seen_list(sr_state.get("seen_ids", []), newly_seen_ids, max_len=600)
        sr_state["seen_slugs"] = update_seen_list(sr_state.get("seen_slugs", []), newly_seen_slugs, max_len=600)

    return list(reversed(new_releases))


def create_steamrip_embed(item: Dict[str, Any]):
    """Builds a Discord Embed for a new SteamRIP game release or update with signature Royal Indigo color and full game poster banner."""
    import discord
    title = item["title"]
    is_update = item.get("type") == "Game Update"
    prefix = "🔄 [SteamRIP Update]" if is_update else "👑 [SteamRIP Release]"

    embed = discord.Embed(
        title=f"{prefix} {title}",
        url=item["url"],
        color=COLOR_STEAMRIP
    )
    # SteamRIP brand icon in top-right thumbnail
    embed.set_thumbnail(url=STEAMRIP_ICON)

    # Full-width high-resolution game poster banner
    poster_url = item.get("poster") or item.get("thumbnail")
    if poster_url:
        embed.set_image(url=poster_url)

    embed.add_field(name="🎮 Game Title", value=f"**{title}**", inline=False)
    if item.get("version"):
        embed.add_field(name="🏷️ Version / Build", value=f"`{item['version']}`", inline=True)
    if item.get("meta"):
        embed.add_field(name="📊 Release Info", value=f"`{item['meta']}`", inline=True)
    embed.add_field(name="📂 Category", value=f"**{item.get('category', 'Pre-installed Game')}**", inline=True)
    embed.add_field(name="🕒 Release Time (GMT+8)", value=item.get("time_kl", parse_pubdate_to_kl("")), inline=False)
    embed.add_field(
        name="🌐 Official SteamRIP Download",
        value=f"👉 **[Open SteamRIP Game Page]({item['url']})**",
        inline=False
    )
    embed.set_footer(text="SteamRIP Monitor • Pre-installed Steam Games • GMT+8", icon_url=STEAMRIP_ICON)
    return embed


_last_working_proxy: Optional[str] = None
_cached_proxies: List[str] = []
_proxies_fetched_at: float = 0.0


def fetch_suo_catalog(limit: int = 150, timeout: int = 4) -> List[Dict[str, Any]]:
    """
    Fetches the newest games from SUO Wannabe using streaming chunk reading
    to avoid downloading the massive 10.6MB full archive.
    Tries direct connections first; if blocked by cloud datacenter firewalls,
    automatically routes through a fast relay proxy to bypass the block completely.
    """
    global _last_working_proxy, _cached_proxies, _proxies_fetched_at
    import json
    import time
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    target_bytes = limit * 450  # ~300-350 bytes per game JSON object

    def parse_stream_response(response) -> Optional[List[Dict[str, Any]]]:
        try:
            chunks = []
            total_read = 0
            for chunk in response.iter_content(chunk_size=4096, decode_unicode=True):
                if chunk:
                    chunks.append(chunk)
                    total_read += len(chunk)
                    if total_read >= target_bytes:
                        break
            raw_text = "".join(chunks).strip()
            if not raw_text.startswith("["):
                return None
            last_brace = raw_text.rfind("}")
            if last_brace == -1:
                return None
            valid_json_text = raw_text[:last_brace + 1] + "]"
            parsed = json.loads(valid_json_text)
            if isinstance(parsed, list) and len(parsed) > 0:
                return parsed
        except Exception:
            return None
        return None

    # 1. Try Direct endpoints first
    endpoints = [
        (SUO_API_URL, {"User-Agent": STANDARD_HEADERS["User-Agent"], "Accept": "application/json"}, True),
        (SUO_DIRECT_IP_URL, {"Host": "steamunlockonennabe.duckdns.org", "User-Agent": STANDARD_HEADERS["User-Agent"], "Accept": "application/json"}, False)
    ]

    for url, headers, verify_ssl in endpoints:
        try:
            with requests.get(url, headers=headers, stream=True, verify=verify_ssl, timeout=timeout) as r:
                if r.status_code == 200:
                    data = parse_stream_response(r)
                    if data:
                        return data
        except Exception:
            continue

    # 2. Try Last Known Working Relay Proxy (instant bypass without re-fetching list)
    if _last_working_proxy:
        try:
            p_dict = {"http": f"http://{_last_working_proxy}", "https": f"http://{_last_working_proxy}"}
            with requests.get(SUO_API_URL, headers=STANDARD_HEADERS, proxies=p_dict, stream=True, timeout=5) as r:
                if r.status_code == 200:
                    data = parse_stream_response(r)
                    if data:
                        return data
        except Exception:
            _last_working_proxy = None

    # 3. Fetch fresh elite proxies and find an active relay to bypass datacenter firewall
    now = time.time()
    if now - _proxies_fetched_at > 300 or not _cached_proxies:
        try:
            p_res = requests.get(
                "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=2500&country=all&ssl=yes&anonymity=elite",
                timeout=4
            )
            if p_res.status_code == 200:
                _cached_proxies = [p.strip() for p in p_res.text.splitlines() if p.strip()]
                _proxies_fetched_at = now
        except Exception:
            pass

    for candidate in _cached_proxies[:8]:
        try:
            p_dict = {"http": f"http://{candidate}", "https": f"http://{candidate}"}
            with requests.get(SUO_API_URL, headers=STANDARD_HEADERS, proxies=p_dict, stream=True, timeout=4) as r:
                if r.status_code == 200:
                    data = parse_stream_response(r)
                    if data:
                        _last_working_proxy = candidate
                        logger.info(f"Bypassed SUO firewall block via relay proxy ({candidate})")
                        return data
        except Exception:
            continue

    logger.debug("SUO Wannabe endpoints unreachable")
    return []


def check_suo_updates(state: dict) -> List[Dict[str, Any]]:
    """
    Checks for newly published games on SteamUnlock Wannabe (https://steamunlockonennabe.click/).
    Uses streaming chunk extraction to get the latest additions in fractions of a second.
    Uses strict FIFO ordered tracking to prevent duplicate postings.
    """
    suo_state = state.setdefault("suo", {})
    seen_appids = set(str(x) for x in suo_state.get("seen_appids", []))

    req_limit = 250 if not seen_appids else 80
    data = fetch_suo_catalog(limit=req_limit, timeout=4)
    if not data:
        return []

    # First run initialization: record top catalog items to prevent spam
    if not seen_appids:
        logger.info(f"Initializing SUO Wannabe tracker with {len(data)} current catalog items...")
        init_appids = []
        for g in data:
            appid = str(g.get("appid") or "").strip()
            if appid:
                init_appids.append(appid)
        suo_state["seen_appids"] = update_seen_list([], init_appids, max_len=1500)
        return []

    new_items: List[Dict[str, Any]] = []
    newly_seen_appids = []
    # Inspect top 60 items for new additions
    for g in data[:60]:
        appid = str(g.get("appid") or "").strip()
        if not appid or appid in seen_appids:
            continue

        name = g.get("name") or f"AppID {appid}"
        size_gb = g.get("size_gb") or "N/A"
        added_on = g.get("added_on") or ""
        genre_id = int(g.get("primary_genre") or 0)
        genre_name = SUO_GENRE_MAP.get(genre_id, "Game")
        online_supp = g.get("online_supported") or "No"
        bypass_supp = g.get("bypass_supported") or "No"
        steam_store_url = f"https://store.steampowered.com/app/{appid}/"

        # Fetch real header image URL from Steam API (handles hash-path CDN URLs for new games)
        header_url = None
        try:
            api_resp = requests.get(
                f"https://store.steampowered.com/api/appdetails?appids={appid}&filters=basic",
                timeout=6
            )
            if api_resp.status_code == 200:
                app_data = api_resp.json().get(appid, {}).get("data", {})
                header_url = app_data.get("header_image")
        except Exception:
            pass

        # Format added time to GMT+8
        time_kl = parse_pubdate_to_kl(added_on)

        new_items.append({
            "source": "SUO Wannabe",
            "appid": appid,
            "title": name,
            "url": SUO_BASE_URL,
            "steam_url": steam_store_url,
            "header": header_url,  # Real URL from Steam API, or None
            "size_gb": size_gb,
            "genre": genre_name,
            "online_supported": online_supp,
            "bypass_supported": bypass_supp,
            "time_kl": time_kl
        })
        seen_appids.add(appid)
        newly_seen_appids.append(appid)

    if newly_seen_appids:
        suo_state["seen_appids"] = update_seen_list(suo_state.get("seen_appids", []), newly_seen_appids, max_len=1500)

    return list(reversed(new_items))


def create_suo_embed(item: Dict[str, Any]):
    """Builds a Discord Embed for a new SteamUnlock Wannabe game release.
    Embed URL points to Steam Store so Discord renders a web preview (webview).
    Image uses Steam's header JPG (460x215) which is the most reliably available asset.
    """
    import discord
    name = item["title"]
    appid = item["appid"]

    steam_url = item.get("steam_url") or f"https://store.steampowered.com/app/{appid}/"

    embed = discord.Embed(
        title=f"🔓 [SUO Wannabe] {name}",
        # URL = Steam Store page → Discord will render store page web preview on click
        url=steam_url,
        color=COLOR_SUO
    )

    # Use the real header URL from Steam appdetails API (if available)
    header_url = item.get("header")
    if header_url:
        embed.set_image(url=header_url)

    embed.add_field(name="🎮 Game Title", value=f"**[{name}]({steam_url})**", inline=False)
    embed.add_field(name="🆔 Steam AppID", value=f"`{appid}`", inline=True)
    embed.add_field(name="📦 Download Size", value=f"`{item.get('size_gb', 'N/A')}`", inline=True)
    embed.add_field(name="🏷️ Primary Genre", value=f"**{item.get('genre', 'Game')}**", inline=True)
    embed.add_field(name="🌐 Online Play", value=f"**{item.get('online_supported', 'No')}**", inline=True)
    embed.add_field(name="⚡ Bypass Support", value=f"**{item.get('bypass_supported', 'No')}**", inline=True)
    embed.add_field(name="🕒 Added Time (GMT+8)", value=item.get("time_kl", parse_pubdate_to_kl("")), inline=False)
    embed.add_field(
        name="🔗 Links",
        value=f"🛒 **[Steam Store Page]({steam_url})**\n👉 **[SUO Wannabe Catalog]({item['url']})**",
        inline=False
    )
    embed.set_footer(text="SteamUnlock Wannabe Monitor • Steam Akamai CDN • GMT+8", icon_url=SUO_ICON)
    return embed


def check_steam_deals(state: dict) -> List[Dict[str, Any]]:
    """
    Checks for newly featured Steam specials and discounts with pricing in MYR (RM).
    Monitors Steam's official featured categories endpoint (cc=my, l=en).
    Uses strictly ordered FIFO deduplication to prevent reposting active deals.
    """
    steam_deals_state = state.setdefault("steam_deals", {})
    seen_deal_keys = set(str(x) for x in steam_deals_state.get("seen_deal_keys", []))

    url = "https://store.steampowered.com/api/featuredcategories/?cc=my&l=en"
    headers = {
        "User-Agent": STANDARD_HEADERS["User-Agent"],
        "Accept": "application/json"
    }

    try:
        res = requests.get(url, headers=headers, timeout=12)
        if res.status_code != 200:
            logger.warning(f"Failed to fetch Steam promotions: HTTP {res.status_code}")
            return []

        data = res.json()
        specials = data.get("specials", {}).get("items", [])
        if not specials:
            return []

        # First run initialization: record current special keys so we don't spam on initial startup
        if not seen_deal_keys:
            logger.info(f"Initializing Steam Specials tracker with {len(specials)} current featured deals...")
            init_keys = []
            for item in specials:
                app_id = item.get("id")
                disc = item.get("discount_percent", 0)
                if app_id:
                    init_keys.append(f"{app_id}_{disc}")
            steam_deals_state["seen_deal_keys"] = update_seen_list([], init_keys, max_len=1000)
            return []

        new_deals = []
        newly_seen_keys = []
        for item in specials:
            app_id = item.get("id")
            name = item.get("name")
            discount_pct = item.get("discount_percent", 0)
            orig_price_raw = item.get("original_price")
            final_price_raw = item.get("final_price")
            currency = item.get("currency", "MYR")

            # Must have discount and valid id/prices
            if not app_id or not name or discount_pct <= 0:
                continue

            deal_key = f"{app_id}_{discount_pct}"
            if deal_key in seen_deal_keys:
                continue

            orig_rm = (orig_price_raw / 100.0) if orig_price_raw is not None else 0.0
            final_rm = (final_price_raw / 100.0) if final_price_raw is not None else 0.0
            savings_rm = max(0.0, orig_rm - final_rm)

            # Expiration
            exp_ts = item.get("discount_expiration")
            expiry_str = "Limited Time Deal"
            if exp_ts:
                try:
                    exp_dt = datetime.fromtimestamp(exp_ts, tz=timezone.utc).astimezone(KL_TZ)
                    expiry_str = exp_dt.strftime("%Y-%m-%d %I:%M %p GMT+8")
                except Exception:
                    pass

            now_kl = datetime.now(KL_TZ).strftime("%Y-%m-%d %I:%M %p GMT+8")

            deal_obj = {
                "id": app_id,
                "name": name,
                "discount_percent": discount_pct,
                "original_price": orig_rm,
                "final_price": final_rm,
                "savings": savings_rm,
                "currency": currency,
                "header_image": item.get("header_image") or item.get("large_capsule_image"),
                "store_url": f"https://store.steampowered.com/app/{app_id}/",
                "discount_expiration": expiry_str,
                "windows": item.get("windows_available", True),
                "mac": item.get("mac_available", False),
                "linux": item.get("linux_available", False),
                "time_kl": now_kl
            }

            new_deals.append(deal_obj)
            seen_deal_keys.add(deal_key)
            newly_seen_keys.append(deal_key)

        if newly_seen_keys:
            steam_deals_state["seen_deal_keys"] = update_seen_list(steam_deals_state.get("seen_deal_keys", []), newly_seen_keys, max_len=1000)

        return new_deals

    except Exception as e:
        logger.error(f"Error checking Steam promotions: {e}")
        return []


def create_steam_deal_embed(item: Dict[str, Any]):
    """Builds a Discord Embed for Steam game promotions formatted with Malaysian Ringgit (MYR/RM)."""
    import discord
    name = item["name"]
    app_id = item["id"]
    disc_pct = item["discount_percent"]
    orig_rm = item["original_price"]
    final_rm = item["final_price"]
    savings_rm = item["savings"]

    platforms = []
    if item.get("windows"):
        platforms.append("🪟 Windows")
    if item.get("mac"):
        platforms.append("🍎 macOS")
    if item.get("linux"):
        platforms.append("🐧 Linux / Steam Deck")
    platform_str = " • ".join(platforms) if platforms else "PC"

    # Color tiering based on discount depth: > 70% gets gold/legendary color, otherwise Steam blue
    embed_color = 0xF1C40F if disc_pct >= 70 else COLOR_STEAM_DEAL

    embed = discord.Embed(
        title=f"🔥 [Steam Deal • -{disc_pct}%] {name}",
        url=item["store_url"],
        color=embed_color
    )

    if item.get("header_image"):
        embed.set_image(url=item["header_image"])
    embed.set_thumbnail(url=STEAM_DEAL_ICON)

    embed.add_field(name="🎮 Game Title", value=f"**[{name}]({item['store_url']})**", inline=False)
    embed.add_field(name="🏷️ Discount", value=f"**🔥 -{disc_pct}% OFF**", inline=True)
    embed.add_field(name="💵 Normal Price", value=f"~~RM {orig_rm:.2f}~~", inline=True)
    embed.add_field(name="💰 Promo Price (MYR)", value=f"**`RM {final_rm:.2f}`**", inline=True)
    embed.add_field(name="💸 You Save", value=f"**RM {savings_rm:.2f}**", inline=True)
    embed.add_field(name="💻 Platforms", value=platform_str, inline=True)
    embed.add_field(name="⏳ Deal Ends", value=f"`{item['discount_expiration']}`", inline=True)

    embed.add_field(
        name="🛒 Steam Store Link",
        value=f"👉 **[Purchase {name} on Steam Store (RM {final_rm:.2f})]({item['store_url']})**",
        inline=False
    )

    embed.set_footer(text="Steam Promotion Monitor • Prices in Malaysian Ringgit (MYR/RM) • GMT+8", icon_url=STEAM_DEAL_ICON)
    return embed
