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
FITGIRL_FEED_URL = "https://fitgirl-repacks.site/feed/"
DODI_FEED_URL = "https://dodi-repacks.site/feed/"
CRACKWATCH_RSS_URL = "https://old.reddit.com/r/CrackWatch/new/.rss"

# Brand Colors
COLOR_STEAMRIP = 0x6C5CE7    # Royal Indigo / Vivid Violet
COLOR_SUO = 0x1A9FFF         # Electric Steam Cyan / Blue
COLOR_FITGIRL = 0xFF1493     # Deep Pink / Magenta
COLOR_DODI = 0x10AC84        # Emerald / Mint Green
COLOR_CRACKWATCH = 0xFF4500  # Reddit Vibrant Orange-Red

STEAMRIP_ICON = "https://steamrip.com/wp-content/uploads/2021/06/cropped-favicon1-192x192.png"
SUO_ICON = "https://raw.githubusercontent.com/ZackTheGrumpy/Website/refs/heads/main/logo.ico"
FITGIRL_ICON = "https://fitgirl-repacks.site/wp-content/uploads/2016/08/cropped-icon-192x192.jpg"
DODI_ICON = "https://dodi-repacks.site/wp-content/uploads/2021/04/cropped-cropped-DODI-Repacks-Site-Icon-192x192.png"
REDDIT_ICON = "https://www.redditstatic.com/desktop2x/img/favicon/android-icon-192x192.png"

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


def check_fitgirl_feed(state: dict) -> List[Dict[str, Any]]:
    """Fetches new releases from FitGirl Repacks official feed."""
    fg_state = state.setdefault("fitgirl", {})
    seen_links = set(fg_state.setdefault("seen_links", []))

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


def check_steamrip_updates(state: dict) -> List[Dict[str, Any]]:
    """
    Fetches newly added game releases and recently updated games from https://steamrip.com/.
    Bypasses Cloudflare protection using curl_cffi browser impersonation.
    """
    sr_state = state.setdefault("steamrip", {})
    seen_ids = set(sr_state.setdefault("seen_ids", []))
    items: List[Dict[str, Any]] = []

    # Helper for fetching via curl_cffi or requests
    get_html = fetch_web_content

    # 1. Fetch Home Page (New Game Releases)
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

                item_id = f"post_{post_id}" if post_id else f"url_{full_url}"
                poster_src = (
                    img_src.replace("_thumbnail_", "_featured_").replace("_thumbnail.", "_featured.")
                    if img_src else None
                )
                items.append({
                    "id": item_id,
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

    # 2. Fetch Updated Games Page (Game Patches & Updates)
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
                            title_el = a.select_one(".updated-card-title")
                            raw_title = title_el.get_text(strip=True) if title_el else a.get_text(strip=True)
                            clean_title = re.sub(r'(?i)\s*free\s+download\b', '', raw_title).strip()
                            build_el = a.select_one(".updated-list-build")
                            build = build_el.get_text(strip=True) if build_el else ""

                            item_id = f"upd_{full_url}_{build}"
                            items.append({
                                "id": item_id,
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

    if not items:
        return []

    def fetch_steamrip_poster(game_url: str) -> Optional[str]:
        """Fetches high-res game poster (og:image) directly from the SteamRIP game page."""
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

    # First run initialization: record current items to state so we don't spam history
    if not seen_ids:
        logger.info(f"Initializing SteamRIP tracker with {len(items)} current items...")
        for it in items:
            seen_ids.add(it["id"])
        sr_state["seen_ids"] = list(seen_ids)[-300:]
        return []

    new_releases: List[Dict[str, Any]] = []
    for it in items:
        if it["id"] not in seen_ids:
            # If item does not have a poster yet (e.g. from updated list), fetch og:image
            if not it.get("poster"):
                it["poster"] = fetch_steamrip_poster(it["url"])
            new_releases.append(it)
            seen_ids.add(it["id"])

    sr_state["seen_ids"] = list(seen_ids)[-300:]
    return new_releases


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


def check_suo_updates(state: dict) -> List[Dict[str, Any]]:
    """
    Checks for newly published games on SteamUnlock Wannabe (https://steamunlockonennabe.click/).
    Directly queries the SUO API and fetches high-resolution box art posters from Steam Fastly CDN.
    """
    suo_state = state.setdefault("suo", {})
    seen_appids = set(suo_state.setdefault("seen_appids", []))

    content = fetch_web_content(SUO_API_URL, timeout=15)
    if not content:
        return []

    try:
        import json
        data = json.loads(content)
        if not isinstance(data, list):
            return []
    except Exception as e:
        logger.error(f"Error parsing SUO Wannabe JSON: {e}")
        return []

    # First run initialization: record top 300 existing appids to prevent spam
    if not seen_appids:
        logger.info(f"Initializing SUO Wannabe tracker with {len(data)} current catalog items...")
        for g in data[:300]:
            appid = str(g.get("appid") or "").strip()
            if appid:
                seen_appids.add(appid)
        suo_state["seen_appids"] = list(seen_appids)[-500:]
        return []

    new_items: List[Dict[str, Any]] = []
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

        # Steam cover art & header posters
        poster_url = f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/library_600x900_2x.jpg"
        header_url = f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"
        steam_store_url = f"https://store.steampowered.com/app/{appid}/"

        # Format added time to GMT+8
        time_kl = parse_pubdate_to_kl(added_on)

        new_items.append({
            "source": "SUO Wannabe",
            "appid": appid,
            "title": name,
            "url": SUO_BASE_URL,
            "steam_url": steam_store_url,
            "poster": poster_url,
            "header": header_url,
            "size_gb": size_gb,
            "genre": genre_name,
            "online_supported": online_supp,
            "bypass_supported": bypass_supp,
            "time_kl": time_kl
        })
        seen_appids.add(appid)

    suo_state["seen_appids"] = list(seen_appids)[-500:]
    return new_items


def create_suo_embed(item: Dict[str, Any]):
    """Builds a Discord Embed for a new SteamUnlock Wannabe game release with Steam cover art."""
    import discord
    name = item["title"]
    appid = item["appid"]

    embed = discord.Embed(
        title=f"🔓 [SUO Wannabe] {name}",
        url=item.get("steam_url") or item["url"],
        color=COLOR_SUO
    )
    # Thumbnail: Horizontal Steam header
    if item.get("header"):
        embed.set_thumbnail(url=item["header"])

    # Full-width game poster: Steam 600x900 box art
    if item.get("poster"):
        embed.set_image(url=item["poster"])

    embed.add_field(name="🎮 Game Title", value=f"**{name}**", inline=False)
    embed.add_field(name="🆔 Steam AppID", value=f"`{appid}`", inline=True)
    embed.add_field(name="📦 Download Size", value=f"`{item.get('size_gb', 'N/A')}`", inline=True)
    embed.add_field(name="🏷️ Primary Genre", value=f"**{item.get('genre', 'Game')}**", inline=True)
    embed.add_field(name="🌐 Online Play", value=f"**{item.get('online_supported', 'No')}**", inline=True)
    embed.add_field(name="⚡ Bypass Support", value=f"**{item.get('bypass_supported', 'No')}**", inline=True)
    embed.add_field(name="🕒 Added Time (GMT+8)", value=item.get("time_kl", parse_pubdate_to_kl("")), inline=False)
    embed.add_field(
        name="🔗 Game & Catalog Links",
        value=f"👉 **[Open SUO Wannabe Catalog]({item['url']})**\n🛒 **[View on Steam Store]({item['steam_url']})**",
        inline=False
    )
    embed.set_footer(text="SteamUnlock Wannabe Monitor • Steam Fastly CDN Posters • GMT+8", icon_url=SUO_ICON)
    return embed



