import re
import time
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
ONLINEFIX_TG_URL = "https://t.me/s/onlinefix"
WEMOD_LATEST_URL = "https://www.wemod.com/cheats?sort=latest"
WEMOD_FEED_URL = WEMOD_LATEST_URL

# Brand Colors (Distinct spectrum - zero similar colors)
COLOR_STEAMRIP = 0x8B5CF6    # Vivid Royal Violet / Purple
COLOR_SUO = 0xF59E0B         # Cyber Amber Gold / Key Yellow
COLOR_FITGIRL = 0xFF1493     # Neon Magenta / Deep Pink
COLOR_DODI = 0x10B981        # Emerald / Forest Green
COLOR_CRACKWATCH = 0xFF5722  # Reddit Vibrant Flame Orange
COLOR_STEAM_DEAL = 0xE11D48  # Steam Sale Crimson / Discount Red
COLOR_ONLINEFIX = 0x00E5FF   # Neon Electric Aqua / Cyan
COLOR_WEMOD = 0x6366F1       # Electric Iris / Wand Indigo
COLOR_STEAM_FREE = 0x9333EA  # Aesthetic Purple / Steam Free Violet
COLOR_DENUVO_REMOVED = 0x10B981  # Emerald Green (Clean / Denuvo Removed)
COLOR_DENUVO_ADDED = 0xEF4444    # Danger Crimson (Denuvo Added)
COLOR_STEAM_PATCH = 0x38BDF8     # Steam Engine Sky Blue
COLOR_FREE_WEEKEND = 0x06B6D4    # Electric Cyan

STEAMRIP_ICON = "https://steamrip.com/wp-content/uploads/2021/06/cropped-favicon1-192x192.png"
SUO_ICON = "https://raw.githubusercontent.com/mirzaarsyad74-cmyk/discord/main/assets/icons/suo_icon.png"
FITGIRL_ICON = "https://fitgirl-repacks.site/wp-content/uploads/2016/08/cropped-icon-192x192.jpg"
DODI_ICON = "https://dodi-repacks.site/wp-content/uploads/2019/02/cropped-ICON-192x192.png"
REDDIT_ICON = "https://www.redditstatic.com/desktop2x/img/favicon/android-icon-192x192.png"
STEAM_DEAL_ICON = "https://raw.githubusercontent.com/mirzaarsyad74-cmyk/discord/main/assets/icons/steam_deals_icon.png"
STEAM_FREE_GAMES_ICON = "https://raw.githubusercontent.com/mirzaarsyad74-cmyk/discord/main/assets/icons/steam_free_games_icon.png"
DENUVO_ICON = "https://raw.githubusercontent.com/mirzaarsyad74-cmyk/discord/main/assets/icons/csrin_icon.png"
STEAM_PATCH_ICON = "https://raw.githubusercontent.com/mirzaarsyad74-cmyk/discord/main/assets/icons/steam_gameoverlay_icon.png"
ONLINEFIX_ICON = "https://online-fix.me/apple-touch-icon.png"
WEMOD_ICON = "https://www.wemod.com/static/images/device-icons/favicon-192-ce0bc030f3.png"

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
    "User-Agent": "Discordbot/2.0; (+https://discordapp.com)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9"
}
STANDARD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def fetch_reddit_feed(url: str) -> Optional[str]:
    """
    Fetches Reddit RSS feed with Discordbot User-Agent and curl_cffi browser TLS impersonation fallback.
    Prevents HTTP 429 and Cloudflare/Fastly blocks on cloud datacenter IPs (like Koyeb).
    """
    # 1. Primary attempt: Discordbot User-Agent (whitelisted by Reddit WAF)
    try:
        res = requests.get(url, headers=REDDIT_HEADERS, timeout=12)
        if res.status_code == 200 and ("<entry>" in res.text or "<item>" in res.text):
            return res.text
        if res.status_code == 429:
            logger.info(f"Reddit 429 received on {url}. Retrying via curl_cffi browser TLS impersonation...")
    except Exception as e:
        logger.debug(f"requests error fetching {url}: {e}")

    # 2. Fallback attempt: curl_cffi with Chrome 120 browser handshake
    try:
        from curl_cffi import requests as c_requests
        c_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"
        }
        res_c = c_requests.get(url, headers=c_headers, impersonate="chrome120", timeout=12)
        if res_c.status_code == 200 and ("<entry>" in res_c.text or "<item>" in res_c.text):
            return res_c.text
    except Exception as e:
        logger.debug(f"curl_cffi error fetching {url}: {e}")

    return None



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


def fetch_web_content(url: str, headers: dict = None, timeout: int = 8, silent_fail: bool = False) -> Optional[str]:
    """Fetches web content using curl_cffi (impersonating Chrome) with fallback to requests."""
    req_headers = headers or STANDARD_HEADERS
    if cffi_requests:
        try:
            r = cffi_requests.get(url, impersonate="chrome120", timeout=timeout)
            if r.status_code == 200:
                return r.text
            if not silent_fail:
                logger.warning(f"curl_cffi fetch {url} returned HTTP {r.status_code}")
        except Exception as e:
            logger.debug(f"curl_cffi failed for {url}: {e}, falling back to requests")

    try:
        r = requests.get(url, headers=req_headers, timeout=timeout)
        if r.status_code == 200:
            return r.text
        if not silent_fail:
            logger.warning(f"requests fetch {url} returned HTTP {r.status_code}")
        return None
    except Exception as e:
        if not silent_fail:
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

    # Rate-limit shield: throttle requests on shared container IPs to at most once every 90s
    now_ts = int(time.time())
    last_check = int(cw_state.get("last_check_ts", 0))
    if seen_ids and (now_ts - last_check < 90):
        return []

    try:
        import html
        feed_xml = fetch_reddit_feed(CRACKWATCH_RSS_URL)
        cw_state["last_check_ts"] = now_ts
        if not feed_xml:
            return []

        entries = re.findall(r'<entry>(.*?)</entry>', feed_xml, re.DOTALL)
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

            # Prevent posting old historical submissions (e.g. approved from mod queue weeks later)
            if updated:
                try:
                    dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    now = datetime.now(timezone.utc)
                    if (now - dt).total_seconds() > 48 * 3600:
                        seen_ids.add(entry_id)
                        newly_seen.append(entry_id)
                        continue
                except Exception:
                    pass

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
    # Strip CDATA tags if present
    title = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', title or '', flags=re.DOTALL).strip()
    category = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', category or '', flags=re.DOTALL).strip()
    desc_html = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', desc_html or '', flags=re.DOTALL).strip()

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
    Supports official RSS feed with automatic seamless fallback to official Telegram real-time broadcast mirror (https://t.me/s/onlinefix)
    to bypass Cloudflare 403 datacenter blocking on cloud hosts like Koyeb.
    Translates Russian descriptions and tags into English.
    Uses strict FIFO ordered tracking to prevent duplicate postings.
    """
    of_state = state.setdefault("onlinefix", {})
    seen_links = set(str(x) for x in of_state.get("seen_links", []))

    def parse_rss_items(xml_text: str) -> List[Dict[str, Any]]:
        import html
        raw_blocks = re.findall(r'<item>(.*?)</item>', xml_text, re.DOTALL)
        parsed_entries = []
        for it in raw_blocks:
            l_m = re.search(r'<link>(.*?)</link>', it)
            link = l_m.group(1).strip() if l_m else ""
            if not link:
                continue

            t_m = re.search(r'<title>(.*?)</title>', it)
            raw_title = html.unescape(t_m.group(1).strip()) if t_m else "Online-Fix Game"

            c_m = re.search(r'<category>(.*?)</category>', it)
            raw_category = html.unescape(c_m.group(1).strip()) if c_m else ""

            d_m = re.search(r'<description>(.*?)</description>', it, re.DOTALL)
            raw_desc = d_m.group(1) if d_m else ""

            p_m = re.search(r'<pubdate>(.*?)</pubdate>', it, re.IGNORECASE)
            pub_date = p_m.group(1).strip() if p_m else ""

            clean_title, category_en, play_via, modes_en = clean_and_translate_onlinefix(
                raw_title, raw_category, raw_desc
            )
            time_kl = parse_pubdate_to_kl(pub_date)

            parsed_entries.append({
                "source": "Online-Fix.me",
                "title": clean_title,
                "raw_title": raw_title,
                "link": link,
                "category": category_en,
                "network": play_via,
                "modes": modes_en,
                "time_kl": time_kl
            })
        return parsed_entries

    def parse_telegram_items(html_text: str) -> List[Dict[str, Any]]:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_text, "html.parser")
        msg_divs = soup.select(".tgme_widget_message")
        parsed_entries = []
        for div in msg_divs:
            text_el = div.select_one(".tgme_widget_message_text")
            time_el = div.select_one("time")
            link_el = div.select_one("a[href*='online-fix.me']")
            if not text_el or not link_el:
                continue

            link = link_el.get("href", "").strip()
            dt = time_el.get("datetime", "").strip() if time_el else ""
            raw_text = text_el.get_text(separator="\n", strip=True)

            first_line = raw_text.split("\n")[0].strip()
            clean_raw = re.sub(r'^(Обновлено|Новое|Добавлено)\s+руководство\s+на\s+сайте\s*-\s*', '', first_line)

            cat_m = re.search(r'/games/([^/]+)/', link)
            cat_slug = cat_m.group(1).capitalize() if cat_m else "Multiplayer"

            clean_title, category_en, play_via, modes_en = clean_and_translate_onlinefix(
                clean_raw, cat_slug, raw_text
            )
            time_kl = parse_pubdate_to_kl(dt)

            parsed_entries.append({
                "source": "Online-Fix.me",
                "title": clean_title,
                "raw_title": first_line,
                "link": link,
                "category": category_en,
                "network": play_via,
                "modes": modes_en,
                "time_kl": time_kl
            })
        return parsed_entries

    try:
        entries = []
        # Try direct RSS first with silent_fail=True if not flagged as datacenter blocked
        if not of_state.get("cf_blocked", False):
            xml_text = fetch_web_content(ONLINEFIX_RSS_URL, timeout=8, silent_fail=True)
            if xml_text:
                entries = parse_rss_items(xml_text)
            else:
                of_state["cf_blocked"] = True
                logger.info("Online-Fix.me RSS blocked by Cloudflare (HTTP 403 on cloud datacenter). Using official real-time Telegram mirror (https://t.me/s/onlinefix)...")

        # Fallback to official Telegram real-time broadcast mirror (unblocked globally)
        if not entries:
            tg_html = fetch_web_content(ONLINEFIX_TG_URL, timeout=10)
            if tg_html:
                entries = parse_telegram_items(tg_html)

        if not entries:
            return []

        # First run initialization: record current entries so we don't spam history
        if not seen_links:
            logger.info(f"Initializing Online-Fix.me tracker with {len(entries)} current items...")
            init_links = [e["link"] for e in entries if e.get("link")]
            of_state["seen_links"] = update_seen_list([], init_links, max_len=500)
            return []

        new_items = []
        newly_seen_links = []
        for it in entries:
            link = it.get("link")
            if not link or link in seen_links:
                continue

            new_items.append(it)
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


def fetch_wemod_trainer_detail(slug_url: str) -> dict:
    """Fetches cheats list, creator, build ID, and store/community links from individual trainer page."""
    detail = {}
    try:
        import json
        html = fetch_web_content(slug_url, timeout=6, silent_fail=True)
        if not html:
            return detail

        scripts = re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL)
        for scr in scripts:
            try:
                d = json.loads(scr)
                if d.get("@type") == "VideoGame":
                    detail["cheats"] = d.get("cheatCode", [])
                    creator = d.get("creator")
                    if isinstance(creator, dict):
                        detail["creator"] = creator.get("name")
                    elif isinstance(creator, str):
                        detail["creator"] = creator
                    img_url = d.get("image", "")
                    detail["screenshot"] = img_url
                    bm = re.search(r'/screenshots/trainers/\d+/[^/]+/(\d+)/', img_url)
                    if bm:
                        detail["build_id"] = bm.group(1)

                    same_as = d.get("sameAs", [])
                    if isinstance(same_as, list) and same_as:
                        detail["steam_url"] = same_as[0]
                    elif isinstance(same_as, str):
                        detail["steam_url"] = same_as
                    break
            except Exception:
                continue

        m_comm = re.search(r'href=["\'](https://community\.wemod\.com/t/[^"\']+)["\']', html)
        if m_comm:
            detail["community_url"] = m_comm.group(1)
    except Exception as ex:
        logger.debug(f"Failed to fetch trainer detail for {slug_url}: {ex}")

    return detail


def check_wemod_feed(state: dict) -> List[Dict[str, Any]]:
    """
    Checks for newly released game trainers and trainer cheat updates from WeMod / Wand.
    Monitors live catalog feed: https://www.wemod.com/cheats?sort=latest
    Extracts game title, gaming platforms (Steam, Xbox, Epic, GOG, EA, Ubisoft),
    cheat count, detailed cheats list, trainer creator, and game thumbnail image.
    Uses strict FIFO ordered tracking to prevent duplicate postings.
    """
    wemod_state = state.setdefault("wemod", {})
    known_trainers = wemod_state.setdefault("known_trainers", {})
    seen_keys = set(str(x) for x in wemod_state.get("seen_keys", []))

    try:
        html = fetch_web_content(WEMOD_LATEST_URL, timeout=12)
        if not html:
            return []

        idx_start = html.find('class="results-list"')
        if idx_start == -1:
            return []

        chunk = html[idx_start:idx_start + 350000]
        soup = BeautifulSoup(chunk, "html.parser")
        items = soup.select("a.game-result")
        if not items:
            return []

        # First-run initialization: populate initial games without sending historical notifications
        if not known_trainers and not seen_keys:
            logger.info(f"Initializing WeMod/Wand trainer tracker with {len(items[:30])} current games...")
            init_keys = []
            for a in items[:30]:
                href = a.get("href", "").strip()
                if not href.startswith("/cheats/"):
                    continue
                cheats_el = a.select_one(".col.cheats .desktop") or a.select_one(".col.cheats")
                cheats_cnt_str = cheats_el.get_text(strip=True) if cheats_el else "0"
                cheats_cnt = int(re.sub(r'\D', '', cheats_cnt_str) or 0)
                upd_el = a.select_one(".col.updated")
                upd_str = upd_el.get_text(strip=True) if upd_el else ""

                known_trainers[href] = {
                    "cheats_count": cheats_cnt,
                    "updated_text": upd_str,
                    "init_seen": True
                }
                init_keys.append(f"{href}:{cheats_cnt}")
            wemod_state["seen_keys"] = update_seen_list([], init_keys, max_len=600)
            return []

        new_items = []
        newly_seen_keys = []

        for a in items[:25]:
            href = a.get("href", "").strip()
            if not href.startswith("/cheats/"):
                continue

            name_el = a.select_one(".col.name div")
            name = name_el.get_text(strip=True) if name_el else a.get("aria-label", "")

            img = a.select_one(".col.thumbnail img")
            thumb = img.get("src") if img else None

            cheats_el = a.select_one(".col.cheats .desktop") or a.select_one(".col.cheats")
            cheats_cnt_str = cheats_el.get_text(strip=True) if cheats_el else "0"
            cheats_cnt = int(re.sub(r'\D', '', cheats_cnt_str) or 0)

            platforms = [p.get_text(strip=True) for p in a.select(".col.platforms .platform span") if p.get_text(strip=True)]
            if not platforms:
                platforms = [p.get("alt") for p in a.select(".col.platforms .platform img") if p.get("alt")]
            platform_str = ", ".join(platforms) if platforms else "PC"

            upd_el = a.select_one(".col.updated")
            updated_str = upd_el.get_text(strip=True) if upd_el else ""

            full_url = f"https://www.wemod.com{href}"

            is_new_game = href not in known_trainers
            known_info = known_trainers.get(href, {})
            old_cheats_cnt = known_info.get("cheats_count", 0)
            old_build_id = known_info.get("build_id")

            # Determine if this game has a fresh update
            is_recent = any(w in updated_str.lower() for w in ["minute", "hour", "just now", "today"])
            cheats_changed = (cheats_cnt != old_cheats_cnt) and (old_cheats_cnt > 0)

            action_type = None
            detail = {}

            if is_new_game:
                action_type = "✨ New Trainer Release"
                detail = fetch_wemod_trainer_detail(full_url)
            elif cheats_changed or (is_recent and not known_info.get("init_seen")):
                detail = fetch_wemod_trainer_detail(full_url)
                curr_build = detail.get("build_id")
                event_key = f"{href}:{cheats_cnt}:{curr_build or updated_str}"
                if event_key not in seen_keys and curr_build != old_build_id:
                    action_type = "🔄 Trainer Updated"
                    newly_seen_keys.append(event_key)
                    seen_keys.add(event_key)

            if not action_type:
                continue

            # Update known trainer info in state
            known_trainers[href] = {
                "name": name,
                "cheats_count": cheats_cnt,
                "build_id": detail.get("build_id") or old_build_id,
                "updated_text": updated_str,
                "last_notified": datetime.now(timezone.utc).isoformat()
            }
            item_key = f"{href}:{cheats_cnt}:{detail.get('build_id') or ''}"
            seen_keys.add(item_key)
            newly_seen_keys.append(item_key)

            now_kl = datetime.now(timezone.utc).astimezone(KL_TZ)
            kl_str = now_kl.strftime("%a, %b %d, %Y %I:%M %p GMT+8")
            rel_note = f"*(Updated: {updated_str})*" if updated_str else ""
            time_kl_str = f"`{kl_str}`\n{rel_note}".strip()

            new_items.append({
                "source": "WeMod / Wand",
                "game_name": name,
                "platform": platform_str,
                "action_type": action_type,
                "wemod_url": full_url,
                "thumbnail": thumb,
                "cheats_count": cheats_cnt,
                "updated_text": updated_str,
                "creator": detail.get("creator"),
                "cheats": detail.get("cheats", []),
                "steam_url": detail.get("steam_url"),
                "community_url": detail.get("community_url"),
                "time_kl": time_kl_str
            })

        if newly_seen_keys:
            wemod_state["seen_keys"] = update_seen_list(wemod_state.get("seen_keys", []), newly_seen_keys, max_len=600)

        # Prune known_trainers if it exceeds 800 entries
        if len(known_trainers) > 800:
            keys_to_remove = list(known_trainers.keys())[:-500]
            for k in keys_to_remove:
                del known_trainers[k]

        return list(reversed(new_items))

    except Exception as e:
        logger.error(f"Error checking WeMod feed: {e}")
        return []


def create_wemod_embed(item: Dict[str, Any]):
    """Builds a Discord Embed for a new WeMod trainer release or update with signature Wand Indigo/Electric Iris color."""
    import discord
    game_name = item.get("game_name") or item.get("name", "Unknown Game")
    platform = item.get("platform") or item.get("platforms", "PC")
    action_type = item.get("action_type", "✨ New Trainer Release")
    is_release = "Release" in action_type

    plat_lower = platform.lower()
    badges = []
    if re.search(r'\bsteam\b', plat_lower):
        badges.append("🪟 Steam")
    if re.search(r'\b(?:xbox|uwp|microsoft)\b', plat_lower):
        badges.append("🎮 Xbox")
    if re.search(r'\bepic\b', plat_lower):
        badges.append("⚡ Epic Games")
    if re.search(r'\bgog\b', plat_lower):
        badges.append("🔮 GOG")
    if re.search(r'\b(?:ea|origin)\b', plat_lower):
        badges.append("🟠 EA app")
    if re.search(r'\bubisoft\b', plat_lower):
        badges.append("🌀 Ubisoft")
    if not badges:
        badges.append(f"💻 {platform}")
    plat_str = " • ".join(badges)

    title_prefix = "✨ [WeMod Trainer Release]" if is_release else "🔄 [WeMod Trainer Updated]"
    embed_title = f"{title_prefix} {game_name}"

    wemod_url = item.get("wemod_url") or item.get("url") or item.get("topic_url", "https://www.wemod.com")
    community_url = item.get("community_url") or item.get("topic_url")
    steam_url = item.get("steam_url")

    embed = discord.Embed(
        title=embed_title,
        url=wemod_url,
        color=COLOR_WEMOD
    )

    if item.get("thumbnail"):
        embed.set_thumbnail(url=item["thumbnail"])
    else:
        embed.set_thumbnail(url=WEMOD_ICON)

    embed.add_field(name="🎮 Game Title", value=f"**[{game_name}]({wemod_url})**", inline=False)
    embed.add_field(name="💻 Platform", value=plat_str, inline=True)
    embed.add_field(name="🏷️ Event Type", value=f"**{action_type}**", inline=True)

    time_val = item.get("time_kl")
    if not time_val:
        now_kl = datetime.now(timezone.utc).astimezone(KL_TZ)
        kl_str = now_kl.strftime("%a, %b %d, %Y %I:%M %p GMT+8")
        rel_note = f"*(Updated: {item.get('updated_text', 'recently')})*"
        time_val = f"`{kl_str}`\n{rel_note}"
    embed.add_field(name="🕒 Time (GMT+8)", value=time_val, inline=True)

    if item.get("creator"):
        embed.add_field(name="👤 Trainer Creator", value=f"`{item['creator']}`", inline=True)

    cheats_cnt = item.get("cheats_count", 0)
    changes = item.get("changes") or item.get("cheats", [])
    if changes:
        display_bullets = []
        for c in changes[:6]:
            clean_c = " ".join(str(c).split())
            display_bullets.append(f"• {clean_c}")
        if len(changes) > 6:
            display_bullets.append(f"• *... and {len(changes) - 6} more cheat options*")
        bullets_text = "\n".join(display_bullets)
        field_name = f"📋 Cheats Included ({len(changes)} Cheats)" if len(changes) > 1 else "📋 Cheats & Changes Included"
        embed.add_field(name=field_name, value=bullets_text, inline=False)
    elif cheats_cnt > 0:
        embed.add_field(name="📋 Cheats & Changes Included", value=f"• Released trainer with **{cheats_cnt} cheats** for {plat_str}", inline=False)
    else:
        fallback_desc = f"Cheats and trainer ready for {plat_str} on WeMod / Wand."
        embed.add_field(name="📋 Trainer Details", value=fallback_desc, inline=False)

    links = [f"👉 **[Launch / Get Cheats on WeMod]({wemod_url})**"]
    if community_url:
        links.append(f"💬 **[Discussion & Community]({community_url})**")
    if steam_url:
        links.append(f"🛒 **[Steam Store]({steam_url})**")
    embed.add_field(
        name="🔗 Links",
        value=" • ".join(links),
        inline=False
    )

    embed.set_footer(text="WeMod / Wand Monitor • Game Trainers & Cheats • GMT+8", icon_url=WEMOD_ICON)
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


def check_steam_free_games(state: dict) -> List[Dict[str, Any]]:
    """
    Checks for 100% Free Steam Games (Free to Keep, Normally Paid):
    1. Direct Steam Store search specials with maxprice=free and specials=1 (100% discount promotions).
    2. Reddit r/FreeGamesOnSteam RSS feed for community-reported giveaways and free claims.
    Deduplicates strictly using seen keys stored in state['steam_free_games'].
    """
    free_state = state.setdefault("steam_free_games", {})
    seen_keys = set(str(x) for x in free_state.get("seen_keys", []))

    new_items = []
    newly_seen_keys = []

    # 1. Check Steam Official 100% Off Specials (Free to Keep)
    steam_search_url = "https://store.steampowered.com/search/results/?query=&start=0&count=50&maxprice=free&specials=1&cc=my&l=en&infinite=1"
    headers = {
        "User-Agent": STANDARD_HEADERS["User-Agent"],
        "Accept": "application/json"
    }

    try:
        res = requests.get(steam_search_url, headers=headers, timeout=12)
        if res.status_code == 200:
            data = res.json()
            html_text = data.get("results_html", "")
            if html_text:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html_text, "html.parser")
                rows = soup.select("a.search_result_row")

                for row in rows:
                    app_id = row.get("data-ds-appid")
                    if not app_id:
                        pkg_id = row.get("data-ds-packageid")
                        app_id = f"sub_{pkg_id}" if pkg_id else None

                    title_el = row.select_one(".title")
                    title = title_el.text.strip() if title_el else ""
                    disc_el = row.select_one(".discount_pct")
                    disc = disc_el.text.strip() if disc_el else ""
                    orig_el = row.select_one(".discount_original_price")
                    orig = orig_el.text.strip() if orig_el else "Free Promotion"
                    final_el = row.select_one(".discount_final_price")
                    final = final_el.text.strip() if final_el else "FREE"
                    raw_link = row.get("href", "")
                    clean_link = raw_link.split("?")[0] if raw_link else f"https://store.steampowered.com/app/{app_id}/"

                    if not app_id or not title:
                        continue

                    deal_key = f"steam_{app_id}"
                    if deal_key in seen_keys:
                        continue

                    # Header image
                    header_img = f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{app_id}/header.jpg" if not str(app_id).startswith("sub_") else None
                    if not header_img:
                        img_el = row.select_one(".search_capsule img")
                        header_img = img_el.get("src") if img_el else None

                    item_obj = {
                        "id": app_id,
                        "title": title,
                        "discount": disc or "100%",
                        "original_price": orig,
                        "final_price": final,
                        "store_url": clean_link,
                        "header_image": header_img,
                        "source": "Steam Store (100% Off)",
                        "time_kl": datetime.now(KL_TZ).strftime("%a, %b %d, %Y %I:%M %p GMT+8")
                    }

                    new_items.append(item_obj)
                    seen_keys.add(deal_key)
                    newly_seen_keys.append(deal_key)
    except Exception as e:
        logger.error(f"Error checking Steam store 100% specials: {e}")

    # 2. Check Reddit r/FreeGamesOnSteam RSS Feed
    FREEGAMES_RSS_URL = "https://www.reddit.com/r/FreeGamesOnSteam/new/.rss"
    try:
        import html
        feed_r = fetch_reddit_feed(FREEGAMES_RSS_URL)
        if feed_r:
            entries = re.findall(r'<entry>(.*?)</entry>', feed_r, re.DOTALL)
            for e in entries:
                id_m = re.search(r'<id>(.*?)</id>', e)
                entry_id = id_m.group(1).strip() if id_m else ""
                if not entry_id:
                    continue

                title_m = re.search(r'<title>(.*?)</title>', e)
                title = html.unescape(title_m.group(1).strip()) if title_m else ""

                # Ignore non-game discussion / sticky threads
                if not title or "discussion thread" in title.lower():
                    continue

                content_m = re.search(r'<content[^>]*>(.*?)</content>', e, re.DOTALL)
                content = html.unescape(content_m.group(1)) if content_m else ""

                # Find steam store links inside content
                steam_links = re.findall(r'https?://store\.steampowered\.com/(?:app|sub)/(\d+)/?', content)
                app_id = steam_links[0] if steam_links else None

                dedup_key = f"steam_{app_id}" if app_id else f"reddit_{entry_id}"
                if dedup_key in seen_keys:
                    continue

                link_m = re.search(r'<link\s+href="([^"]+)"', e)
                reddit_link = link_m.group(1).strip() if link_m else ""
                store_url = f"https://store.steampowered.com/app/{app_id}/" if app_id else reddit_link

                header_img = f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{app_id}/header.jpg" if app_id else None

                item_obj = {
                    "id": app_id or entry_id,
                    "title": title,
                    "discount": "100%",
                    "original_price": "Free Giveaway",
                    "final_price": "FREE (100% OFF)",
                    "store_url": store_url,
                    "header_image": header_img,
                    "source": "r/FreeGamesOnSteam Giveaway",
                    "time_kl": datetime.now(KL_TZ).strftime("%a, %b %d, %Y %I:%M %p GMT+8")
                }

                new_items.append(item_obj)
                seen_keys.add(dedup_key)
                newly_seen_keys.append(dedup_key)
    except Exception as e:
        logger.error(f"Error checking r/FreeGamesOnSteam: {e}")

    # First run initialization (seed seen keys so we don't spam everything on first boot)
    if "seen_keys" not in free_state and newly_seen_keys:
        logger.info(f"Initializing Steam Free Games tracker with {len(newly_seen_keys)} existing promotions...")
        free_state["seen_keys"] = update_seen_list([], newly_seen_keys, max_len=1000)
        return []

    if newly_seen_keys:
        free_state["seen_keys"] = update_seen_list(free_state.get("seen_keys", []), newly_seen_keys, max_len=1000)

    return new_items


def create_steam_free_game_embed(item: Dict[str, Any]):
    """Builds a rich Discord Embed for 100% Free Steam Games with Aesthetic Purple branding."""
    import discord
    name = item["title"]
    store_url = item["store_url"]
    disc = item.get("discount", "100%")
    orig = item.get("original_price", "Paid Game")
    final = item.get("final_price", "FREE")

    embed = discord.Embed(
        title=f"🎁 [100% FREE ON STEAM] {name}",
        url=store_url,
        color=COLOR_STEAM_FREE
    )

    if item.get("header_image"):
        embed.set_image(url=item["header_image"])
    embed.set_thumbnail(url=STEAM_FREE_GAMES_ICON)

    embed.add_field(name="🎮 Game Title", value=f"**[{name}]({store_url})**", inline=False)
    embed.add_field(name="🏷️ Promotion", value="**🔥 100% FREE TO KEEP**", inline=True)
    embed.add_field(name="💵 Original Price", value=f"~~{orig}~~" if orig != "Free Giveaway" else f"*{orig}*", inline=True)
    embed.add_field(name="💰 Promo Price", value="**`FREE / RM 0.00`**", inline=True)
    embed.add_field(name="📡 Source", value=f"`{item.get('source', 'Steam Store')}`", inline=True)
    embed.add_field(name="⏰ Discovered", value=f"`{item.get('time_kl', 'Now')}`", inline=True)

    embed.add_field(
        name="🛒 Steam Store Claim Link",
        value=f"👉 **[Claim {name} for Free on Steam Store]({store_url})**",
        inline=False
    )

    embed.set_footer(text="Steam Free Games Monitor • Free to Keep Forever • GMT+8", icon_url=STEAM_FREE_GAMES_ICON)
    return embed


# ==============================================================================
# 9. DENUVO REMOVAL & ADDITION TRACKER
# ==============================================================================

DEFAULT_DENUVO_WATCHLIST = [
    {"appid": "2358720", "name": "Black Myth: Wukong"},
    {"appid": "2161700", "name": "Persona 3 Reload"},
    {"appid": "1237320", "name": "Sonic Frontiers"},
    {"appid": "1693980", "name": "Dead Space"},
    {"appid": "2072450", "name": "Like a Dragon: Infinite Wealth"},
    {"appid": "2054970", "name": "Dragon's Dogma 2"},
    {"appid": "1774580", "name": "Star Wars Jedi: Survivor"},
    {"appid": "1888930", "name": "Suicide Squad: Kill the Justice League"},
    {"appid": "2246340", "name": "Shin Megami Tensei V: Vengeance"},
    {"appid": "2124490", "name": "Silent Hill 2 Remake"},
    {"appid": "1627720", "name": "Lies of P"}
]


def check_denuvo_status(state: dict, watchlist: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, Any]]:
    """
    Tracks Denuvo Anti-Tamper removals and stealth additions across PC games:
    1. Real-time Reddit r/CrackWatch verified Denuvo removal announcements.
    2. Direct Steam Store API drm_notice monitoring against the curated Denuvo watchlist.
    """
    denuvo_state = state.setdefault("denuvo_status", {})
    known_drm = denuvo_state.setdefault("known_drm", {})
    seen_keys = set(str(k) for k in denuvo_state.get("seen_keys", []))

    new_items: List[Dict[str, Any]] = []
    newly_seen_keys: List[str] = []

    # 1. Check Reddit r/CrackWatch for verified Denuvo Removal announcements
    try:
        xml_data = fetch_reddit_feed("https://www.reddit.com/r/CrackWatch/search.rss?q=%22Denuvo+Removed%22&restrict_sr=on&sort=new")
        if xml_data:
            soup = BeautifulSoup(xml_data, "html.parser")
            for entry in soup.find_all("entry"):
                title_tag = entry.find("title")
                id_tag = entry.find("id")
                link_tag = entry.find("link")
                content_tag = entry.find("content")

                if not title_tag or not id_tag:
                    continue

                raw_title = title_tag.get_text(strip=True)
                entry_id = id_tag.get_text(strip=True)
                url = link_tag.get("href", "") if link_tag else ""
                content_html = content_tag.get_text() if content_tag else ""

                # Check if title indicates a Denuvo removal
                m = re.search(r'(?i)(?:denuvo\s+(?:has\s+been\s+)?removed\s+(?:from|in)\s+|\[denuvo\s+removed\]\s*)(.+)', raw_title)
                if not m:
                    continue

                game_raw = m.group(1).strip()
                clean_name = re.sub(r'(?i)(?:steam\s+version\s+of\s+|gog\s+version\s+of\s+|pc\s+version\s+of\s+)', '', game_raw).strip()
                clean_name = re.sub(r'[\(\[].*?[\)\]]', '', clean_name).strip()

                dedup_key = f"cw_denuvo_{clean_name.lower()}"
                if dedup_key in seen_keys:
                    continue

                app_id = None
                app_m = re.search(r'store\.steampowered\.com/app/(\d+)', content_html)
                if app_m:
                    app_id = app_m.group(1)

                header_img = f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{app_id}/header.jpg" if app_id else None
                store_url = f"https://store.steampowered.com/app/{app_id}/" if app_id else url

                new_items.append({
                    "event_type": "removed",
                    "title": clean_name,
                    "app_id": app_id,
                    "status_desc": "🔓 Denuvo Anti-Tamper Removed (Now DRM-Free)",
                    "source": "Reddit r/CrackWatch Verified Announcement",
                    "store_url": store_url,
                    "header_image": header_img,
                    "time_kl": datetime.now(KL_TZ).strftime("%a, %b %d, %Y %I:%M %p GMT+8")
                })
                seen_keys.add(dedup_key)
                newly_seen_keys.append(dedup_key)
    except Exception as e:
        logger.error(f"Error checking r/CrackWatch Denuvo removals: {e}")

    # 2. Check Steam Store API for watchlist games
    active_watchlist = watchlist if watchlist else DEFAULT_DENUVO_WATCHLIST
    is_first_init = not bool(known_drm)

    for game in active_watchlist:
        aid = str(game.get("appid", "")).strip()
        gname = game.get("name", f"App {aid}")
        if not aid:
            continue

        try:
            res = requests.get(f"https://store.steampowered.com/api/appdetails?appids={aid}&l=en", timeout=8)
            if res.status_code != 200:
                continue
            data = res.json().get(aid, {}).get("data", {})
            if not data:
                continue

            drm_notice = data.get("drm_notice", "") or ""
            has_denuvo = "denuvo" in drm_notice.lower()
            current_status = "Denuvo" if has_denuvo else "Clean"
            header_img = data.get("header_image")

            # First run: seed state
            if is_first_init or aid not in known_drm:
                known_drm[aid] = current_status
                continue

            last_status = known_drm.get(aid)
            if last_status == "Denuvo" and current_status == "Clean":
                dedup_key = f"steam_denuvo_removed_{aid}"
                if dedup_key not in seen_keys:
                    new_items.append({
                        "event_type": "removed",
                        "title": data.get("name", gname),
                        "app_id": aid,
                        "status_desc": "🔓 Denuvo Anti-Tamper Removed from Steam Executable!",
                        "source": "Steam Store Official API",
                        "store_url": f"https://store.steampowered.com/app/{aid}/",
                        "header_image": header_img,
                        "time_kl": datetime.now(KL_TZ).strftime("%a, %b %d, %Y %I:%M %p GMT+8")
                    })
                    seen_keys.add(dedup_key)
                    newly_seen_keys.append(dedup_key)
                known_drm[aid] = "Clean"

            elif last_status == "Clean" and current_status == "Denuvo":
                dedup_key = f"steam_denuvo_added_{aid}"
                if dedup_key not in seen_keys:
                    new_items.append({
                        "event_type": "added",
                        "title": data.get("name", gname),
                        "app_id": aid,
                        "status_desc": "🔒 Denuvo Anti-Tamper Added to Game Store Page!",
                        "source": "Steam Store Official API",
                        "store_url": f"https://store.steampowered.com/app/{aid}/",
                        "header_image": header_img,
                        "time_kl": datetime.now(KL_TZ).strftime("%a, %b %d, %Y %I:%M %p GMT+8")
                    })
                    seen_keys.add(dedup_key)
                    newly_seen_keys.append(dedup_key)
                known_drm[aid] = "Denuvo"

        except Exception as e:
            logger.debug(f"Error checking Steam DRM for app {aid}: {e}")

    # Seed on first boot to prevent spamming historical announcements
    if "seen_keys" not in denuvo_state and newly_seen_keys:
        logger.info(f"Initializing Denuvo Tracker with {len(newly_seen_keys)} historical items...")
        denuvo_state["seen_keys"] = update_seen_list([], newly_seen_keys, max_len=600)
        return []

    if newly_seen_keys:
        denuvo_state["seen_keys"] = update_seen_list(denuvo_state.get("seen_keys", []), newly_seen_keys, max_len=600)

    return new_items


def create_denuvo_embed(item: Dict[str, Any]):
    """Builds an alert embed when Denuvo is removed or added to a game."""
    import discord
    name = item["title"]
    store_url = item["store_url"]
    event_type = item.get("event_type", "removed")
    is_removed = event_type == "removed"

    embed = discord.Embed(
        title=f"{'🔓' if is_removed else '🔒'} [DENUVO {'REMOVED' if is_removed else 'ADDED'}] {name}",
        url=store_url,
        color=COLOR_DENUVO_REMOVED if is_removed else COLOR_DENUVO_ADDED
    )

    if item.get("header_image"):
        embed.set_image(url=item["header_image"])
    embed.set_thumbnail(url=DENUVO_ICON)

    embed.add_field(name="🎮 Game Title", value=f"**[{name}]({store_url})**", inline=False)
    embed.add_field(name="🛡️ DRM Status", value=f"**{item.get('status_desc')}**", inline=False)
    embed.add_field(name="📡 Verified Source", value=f"`{item.get('source')}`", inline=True)
    if item.get("app_id"):
        embed.add_field(name="🆔 Steam AppID", value=f"`{item['app_id']}`", inline=True)
    embed.add_field(name="⏰ Discovered", value=f"`{item.get('time_kl', 'Now')}`", inline=True)

    embed.set_footer(text="Denuvo Watch • Game DRM & Crack Status • GMT+8", icon_url=DENUVO_ICON)
    return embed


# ==============================================================================
# 10. STEAM APP DEPOTS & PATCH WATCHER
# ==============================================================================

DEFAULT_STEAM_PATCH_APPS = [
    {"appid": "2358720", "name": "Black Myth: Wukong"},
    {"appid": "1627720", "name": "Lies of P"},
    {"appid": "2161700", "name": "Persona 3 Reload"},
    {"appid": "1237320", "name": "Sonic Frontiers"},
    {"appid": "2054970", "name": "Dragon's Dogma 2"}
]


def check_steam_app_patches(state: dict, monitored_apps: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, Any]]:
    """
    Monitors high-profile Steam apps for major patch notes, version updates, and depot changes
    using the official Steam Community Announcements API.
    """
    patch_state = state.setdefault("steam_app_patches", {})
    last_dates = patch_state.setdefault("last_dates", {})
    apps_to_check = monitored_apps if monitored_apps else DEFAULT_STEAM_PATCH_APPS

    new_patches: List[Dict[str, Any]] = []

    for app in apps_to_check:
        aid = str(app.get("appid", "")).strip()
        gname = app.get("name", f"App {aid}")
        if not aid:
            continue

        last_date = int(last_dates.get(aid, 0))
        url = f"https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid={aid}&count=4&feeds=steam_community_announcements"

        try:
            res = requests.get(url, timeout=8)
            if res.status_code != 200:
                continue
            data = res.json()
            items = data.get("appnews", {}).get("newsitems", [])

            if last_date == 0 and items:
                last_dates[aid] = max(int(it.get("date", 0)) for it in items)
                continue

            max_date = last_date
            for it in items:
                p_date = int(it.get("date", 0))
                if p_date <= last_date:
                    continue

                title = it.get("title", "Game Update")
                if not re.search(r'(?i)\b(?:patch|update|hotfix|version|v\d|build|notes|maintenance|changelog)\b', title):
                    continue

                if p_date > max_date:
                    max_date = p_date

                raw_contents = it.get("contents", "")
                clean_contents = re.sub(r'\[/?(?:h1|h2|h3|b|i|u|list|\*|p|img|url)[^\]]*\]', '', raw_contents)
                clean_contents = re.sub(r'\{STEAM_CLAN_IMAGE\}/[^\s)]+', '', clean_contents)
                clean_contents = re.sub(r'\s+', ' ', clean_contents).strip()
                snippet = clean_contents[:250] + "..." if len(clean_contents) > 250 else clean_contents

                dt_kl = datetime.fromtimestamp(p_date, tz=timezone.utc).astimezone(KL_TZ)
                time_kl = dt_kl.strftime("%a, %b %d, %Y %I:%M %p GMT+8")

                new_patches.append({
                    "appid": aid,
                    "game_name": gname,
                    "patch_title": title,
                    "title": f"{gname} - {title}",
                    "snippet": snippet,
                    "url": it.get("url", f"https://store.steampowered.com/news/app/{aid}"),
                    "header_image": f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/header.jpg",
                    "time_kl": time_kl
                })

            last_dates[aid] = max_date

        except Exception as e:
            logger.debug(f"Error checking Steam patches for app {aid}: {e}")

    return new_patches


def create_steam_patch_embed(item: Dict[str, Any]):
    """Builds a rich Discord Embed for Steam App Patch & Depot updates."""
    import discord
    gname = item.get("game_name", "Game")
    title = item.get("patch_title") or item.get("title", "Game Update")
    patch_url = item.get("url", "")
    aid = item.get("appid")

    embed = discord.Embed(
        title=f"⚙️ [{gname}] {title}",
        url=patch_url,
        color=COLOR_STEAM_PATCH
    )

    if item.get("header_image"):
        embed.set_image(url=item["header_image"])
    embed.set_thumbnail(url=STEAM_PATCH_ICON)

    embed.add_field(name="🎮 Game", value=f"**[{gname}](https://store.steampowered.com/app/{aid}/)**", inline=True)
    embed.add_field(name="🆔 AppID", value=f"`{aid}`", inline=True)
    embed.add_field(name="⏰ Released", value=f"`{item.get('time_kl')}`", inline=True)

    if item.get("snippet"):
        embed.add_field(name="📋 Update Summary / Notes", value=item["snippet"], inline=False)

    embed.add_field(
        name="🔗 Read Full Patch Notes",
        value=f"👉 **[Open Patch Notes on Steam]({patch_url})**",
        inline=False
    )

    embed.set_footer(text="Steam App Patch & Depot Watcher • GMT+8", icon_url=STEAM_PATCH_ICON)
    return embed


# ==============================================================================
# 11. STEAM FREE WEEKEND ALERTS
# ==============================================================================

def check_steam_free_weekends(state: dict) -> List[Dict[str, Any]]:
    """
    Monitors Steam Free Weekend promotions:
    1. Reddit r/FreeGameFindings & r/FreeGamesOnSteam for verified Free Weekend announcements.
    """
    fw_state = state.setdefault("steam_free_weekends", {})
    seen_keys = set(str(k) for k in fw_state.get("seen_keys", []))

    new_items: List[Dict[str, Any]] = []
    newly_seen_keys: List[str] = []

    try:
        xml_data = fetch_reddit_feed("https://www.reddit.com/r/FreeGameFindings/search.rss?q=Steam+Free+Weekend&restrict_sr=on&sort=new")
        if xml_data:
            soup = BeautifulSoup(xml_data, "html.parser")
            for entry in soup.find_all("entry"):
                title_tag = entry.find("title")
                id_tag = entry.find("id")
                link_tag = entry.find("link")
                content_tag = entry.find("content")

                if not title_tag or not id_tag:
                    continue

                raw_title = title_tag.get_text(strip=True)
                entry_id = id_tag.get_text(strip=True)
                post_url = link_tag.get("href", "") if link_tag else ""
                content_html = content_tag.get_text() if content_tag else ""

                if "free weekend" not in raw_title.lower() or "steam" not in raw_title.lower():
                    continue

                dedup_key = f"fw_{entry_id}"
                if dedup_key in seen_keys:
                    continue

                clean_name = re.sub(r'\[.*?\]|\(.*?\)', '', raw_title)
                clean_name = re.sub(r'(?i)\bfree\s+weekend\b', '', clean_name).strip()

                app_id = None
                app_m = re.search(r'store\.steampowered\.com/app/(\d+)', content_html)
                if app_m:
                    app_id = app_m.group(1)

                store_url = f"https://store.steampowered.com/app/{app_id}/" if app_id else post_url
                header_img = f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{app_id}/header.jpg" if app_id else None

                new_items.append({
                    "title": clean_name or raw_title,
                    "app_id": app_id,
                    "store_url": store_url,
                    "header_image": header_img,
                    "time_kl": datetime.now(KL_TZ).strftime("%a, %b %d, %Y %I:%M %p GMT+8")
                })
                seen_keys.add(dedup_key)
                newly_seen_keys.append(dedup_key)
    except Exception as e:
        logger.error(f"Error checking Steam Free Weekends: {e}")

    # Seed on first boot
    if "seen_keys" not in fw_state and newly_seen_keys:
        logger.info(f"Initializing Steam Free Weekends with {len(newly_seen_keys)} existing promotions...")
        fw_state["seen_keys"] = update_seen_list([], newly_seen_keys, max_len=600)
        return []

    if newly_seen_keys:
        fw_state["seen_keys"] = update_seen_list(fw_state.get("seen_keys", []), newly_seen_keys, max_len=600)

    return new_items


def create_steam_free_weekend_embed(item: Dict[str, Any]):
    """Builds a rich Discord Embed for Steam Free Weekend events."""
    import discord
    name = item["title"]
    store_url = item["store_url"]

    embed = discord.Embed(
        title=f"🎉 [STEAM FREE WEEKEND] {name}",
        url=store_url,
        color=COLOR_FREE_WEEKEND
    )

    if item.get("header_image"):
        embed.set_image(url=item["header_image"])
    embed.set_thumbnail(url=STEAM_FREE_GAMES_ICON)

    embed.add_field(name="🎮 Game Title", value=f"**[{name}]({store_url})**", inline=False)
    embed.add_field(name="🏷️ Event", value="**🆓 Free to Play This Weekend**", inline=True)
    embed.add_field(name="💻 Platform", value="**`Steam (PC)`**", inline=True)
    embed.add_field(name="⏰ Discovered", value=f"`{item.get('time_kl', 'Now')}`", inline=True)

    embed.add_field(
        name="🚀 Play Now on Steam",
        value=f"👉 **[Download & Play {name} on Steam]({store_url})**",
        inline=False
    )

    embed.set_footer(text="Steam Free Weekend Monitor • Temporary Full Game Trial • GMT+8", icon_url=STEAM_FREE_GAMES_ICON)
    return embed


