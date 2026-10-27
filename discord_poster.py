import re
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import discord
from scraper import ForumPost

logger = logging.getLogger("discord_poster")

KL_TZ = timezone(timedelta(hours=8))  # Kuala Lumpur / Malaysia Time (UTC+08:00)

COLOR_NEW_POST = 0x3498DB       # Vibrant Blue
COLOR_CRACK = 0xE74C3C          # Crimson Red for Scene Cracks
COLOR_REPACK = 0x9B59B6         # Royal Purple for Repacks
COLOR_BYPASS = 0xE67E22         # Vibrant Orange / Gold for Bypasses
COLOR_STEAM_VER = 0x1A9FFF      # Steam Cyan/Blue for Steam Updates
COLOR_TITLE_CHANGE = 0xE74C3C   # Alert Red
COLOR_OP_UPDATE = 0xF39C12      # Gold / Orange


def format_post_time(raw_time: str) -> str:
    """
    Parses original post creation time and formats it as:
    `Sun, Oct 18, 2026 06:21 PM GMT+8`
    *(Original: 11:21 AM UTC+01:00)*
    """
    if not raw_time:
        now_kl = datetime.now(KL_TZ).strftime("%a, %b %d, %Y %I:%M %p GMT+8")
        return f"`{now_kl}`"

    # Check relative time strings like '15 minutes ago'
    m_rel = re.search(r'(\d+)\s*(minute|hour|sec|day)s?\s*ago', raw_time, re.I)
    if m_rel:
        val = int(m_rel.group(1))
        unit = m_rel.group(2).lower()
        now_utc = datetime.now(timezone.utc)
        if 'min' in unit:
            dt = now_utc - timedelta(minutes=val)
        elif 'hour' in unit:
            dt = now_utc - timedelta(hours=val)
        elif 'day' in unit:
            dt = now_utc - timedelta(days=val)
        else:
            dt = now_utc
        kl_dt = dt.astimezone(KL_TZ)
        kl_str = kl_dt.strftime("%a, %b %d, %Y %I:%M %p GMT+8")
        return f"`{kl_str}`\n*(Original: {raw_time})*"

    # Try ISO-8601 (e.g. CS.RIN Atom feed '2026-10-18T11:21:43+01:00')
    try:
        dt = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        kl_dt = dt.astimezone(KL_TZ)
        kl_str = kl_dt.strftime("%a, %b %d, %Y %I:%M %p GMT+8")
        
        orig_tz = dt.strftime("UTC%z")
        if len(orig_tz) == 8:
            orig_tz = f"{orig_tz[:6]}:{orig_tz[6:]}"
        orig_time = dt.strftime("%I:%M %p").lstrip("0")
        orig_str = f"{orig_time} {orig_tz}"
        return f"`{kl_str}`\n*(Original: {orig_str})*"
    except Exception:
        pass

    # Try common RFC / phpBB formats
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%A, %d %b %Y, %H:%M",
        "%d %b %Y, %H:%M",
        "%Y-%m-%d %H:%M:%S"
    ):
        try:
            dt = datetime.strptime(raw_time.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            kl_dt = dt.astimezone(KL_TZ)
            kl_str = kl_dt.strftime("%a, %b %d, %Y %I:%M %p GMT+8")
            orig_time = dt.strftime("%I:%M %p").lstrip("0")
            orig_tz = dt.strftime("UTC%z")
            if len(orig_tz) == 8:
                orig_tz = f"{orig_tz[:6]}:{orig_tz[6:]}"
            return f"`{kl_str}`\n*(Original: {orig_time} {orig_tz})*"
        except Exception:
            continue

    return f"`{raw_time} GMT+8`"


def convert_time_to_kl(raw_time: str) -> str:
    """Legacy helper returning single line GMT+8 string."""
    res = format_post_time(raw_time)
    return res.splitlines()[0].strip("`")


def sanitize_game_title(raw_title: str) -> str:
    """
    Cleans messy forum thread titles:
    - Strips 'Main Forum • ' and 'Re: ' prefixes
    - Strips forum tags like '[NOT CRACKED / HV PLAYABLE]', '[Steam/Epic]', '[v1.0.8 / CSF + Crack]'
    Returns a clean, readable game title.
    """
    if not raw_title:
        return "Game Update"
    
    title = raw_title.strip()
    title = re.sub(r'^(?:Main Forum\s*[•\-]\s*)+', '', title, flags=re.IGNORECASE)
    title = re.sub(r'^Re:\s*', '', title, flags=re.IGNORECASE)
    # Strip status brackets
    title = re.sub(r'\[(?:NOT CRACKED|HV PLAYABLE|UNCRACKED|CRACKED|DENUVO|CSF|STEAM|EPIC|GOG|EARLY ACCESS)[^\]]*\]', '', title, flags=re.IGNORECASE)
    # Strip version / crack noise in brackets
    title = re.sub(r'\[(?:v?\d+\.\d+|CSF|Crack|Repack|Update|Clean Steam Files)[^\]]*\]', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\s{2,}', ' ', title).strip()
    return title or raw_title


def scrub_ugly_content(text: str) -> str:
    """
    Removes:
    1. Giant ASCII art, ANSI logos, and codebox banners.
    2. phpBB forum artifacts: 'Code:Select all|Line number On/Off|Expand/Contract'.
    3. Trailing or empty quote blocks.
    4. Extended symbol borders (------, =====, //////, etc.).
    Preserves actual readable text, changelog items, and install notes.
    """
    if not text:
        return ""

    # Strip phpBB control code headers
    text = re.sub(r'(?i)Code:\s*Select\s*all\s*\|\s*Line\s*number\s*On/Off\s*\|\s*Expand/Contract[^\n]*', '', text)
    text = re.sub(r'(?i)Code:\s*Select\s*all[^\n]*', '', text)
    text = re.sub(r'(?i)Line\s*number\s*On/Off\s*\|\s*Expand/Contract[^\n]*', '', text)
    text = re.sub(r'(?i)\bSelect\s+all\b', '', text)
    text = re.sub(r'\[\[Please login to see this link\.\]\]', '*(link protected on forum)*', text)
    # Strip phpBB Atom feed footer statistics
    text = re.sub(r'(?i)Statistics:\s*Posted\s*by[^\n]*', '', text)
    text = re.sub(r'(?i)\bPosted\s*by\s+[^\n—–-]+[—–-]\s*\d+\s*(?:minute|hour|sec|day)s?\s*ago[^\n]*', '', text)

    box_drawing_chars = set("░▒▓█▀▄▌▐■═║╔╗╚╝─│┌┐└┘▲▼►◄◆◇○●☺☻")
    cleaned_lines = []

    for line in text.splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue

        # Strip markdown quote / formatting markers to inspect core characters
        core = re.sub(r'^[>\s*#_`]+', '', trimmed).strip()
        if not core:
            continue

        # Skip lines containing box drawing characters (NFO ASCII art banners)
        if any(c in box_drawing_chars for c in core):
            continue

        # Skip lines with high density of punctuation / ASCII art drawing
        non_space = [c for c in core if not c.isspace()]
        if len(non_space) >= 5:
            symbols = sum(1 for c in non_space if not c.isalnum())
            if symbols / len(non_space) > 0.40:
                continue

        # Skip repetitive borders (e.g. ----- or ===== or ///// or \\\\\)
        if re.search(r'([=\-_./\\*#~+]){4,}', core):
            continue

        # Skip standalone "nFO" line if it was just introducing an ASCII logo
        if core.lower() in ("nfo", "**nfo**", "*nfo*"):
            continue

        cleaned_lines.append(trimmed)

    result = "\n".join(cleaned_lines)
    # Remove empty quote wrappers left behind by stripped ASCII
    result = re.sub(r'>\s*\*\*Quote:\*\*\s*(?:\n|$)', '', result)
    result = re.sub(r'>\s*\n', '\n', result)
    result = re.sub(r'\n{3,}', '\n\n', result).strip()
    return result


def extract_metadata(text: str, topic_title: str) -> Dict[str, Any]:
    """Extracts structured metadata and all multi-releases from release post text."""
    meta: Dict[str, Any] = {
        "release_name": None,
        "all_releases": [],
        "group": None,
        "version": None,
        "platform": None,
        "size": None
    }

    # 1. Scene release directory tags: Game_Name_v1.0-GROUP or Game.Name-GROUP
    scene_matches = re.findall(
        r'\b([A-Za-z0-9_.\-]+-(?:ElAmigos|RUNE|TENOKE|FLT|CODEX|SKIDROW|Razor1911|FitGirl|DODI|GOLDBERG|Fairlight|TinyRepack|Voices38))\b',
        text,
        re.IGNORECASE
    )
    if scene_matches:
        unique_matches = list(dict.fromkeys(scene_matches))
        meta["all_releases"] = unique_matches
        meta["release_name"] = unique_matches[0]
        group = unique_matches[0].split("-")[-1]
        meta["group"] = group

    if not meta["group"] and re.search(r'\bvoices38\b', text, re.IGNORECASE):
        meta["group"] = "Voices38"

    # 2. Extract version (v1.2.3 or 1.2.3 or Build 123456)
    v_match = re.search(r'(?:^|[_\s.\-])v?(\d+\.\d+(?:\.\d+)?(?:[a-z])?)(?:[_\s.\-]|$$)', text, re.IGNORECASE)
    if v_match:
        meta["version"] = f"v{v_match.group(1).lstrip('vV')}"
    else:
        build_match = re.search(r'(?i)\bbuild\s*(\d{5,})\b', text)
        if build_match:
            meta["version"] = f"Build {build_match.group(1)}"

    # 3. Extract platform
    if re.search(r'(?i)(?:[_\s.\-]|^)(?:mac|macos|osx)(?:[_\s.\-]|$)', text):
        meta["platform"] = "macOS"
    elif re.search(r'(?i)(?:[_\s.\-]|^)(?:linux)(?:[_\s.\-]|$)', text):
        meta["platform"] = "Linux"
    elif re.search(r'(?i)(?:[_\s.\-]|^)(?:win|windows|pc)(?:[_\s.\-]|$)', text):
        meta["platform"] = "Windows"

    # 4. Extract size if mentioned (e.g. [5.2 GB] or 10.8 GB)
    size_match = re.search(r'\[?\b(\d+(?:\.\d+)?\s*(?:MB|GB))\b\]?', text, re.IGNORECASE)
    if size_match:
        meta["size"] = size_match.group(1).upper()

    return meta


def create_post_embed(post: ForumPost, release_label: Optional[str] = None) -> discord.Embed:
    """
    Builds a Discord Embed for a new post or release notification.
    Cleans out all ASCII art, code artifacts, and formats clean metadata fields.
    Supports single releases and multi-release post manifests.
    """
    cleaned_body = scrub_ugly_content(post.clean_markdown)
    meta = extract_metadata(post.clean_markdown, post.topic_title)

    category_name = release_label or "Update"
    lbl_lower = category_name.lower()

    if "voices38" in lbl_lower or (post.author and post.author.lower() == "voices38") or "voices38" in (meta.get("group") or "").lower():
        icon = "⚡"
        embed_color = 0xFFD700  # Electric Gold for Voices38 Denuvo Bypasses
        badge_text = "Voices38 Denuvo Bypass"
    elif "steam version" in lbl_lower or "csf" in lbl_lower or "build" in lbl_lower:
        icon = "🔄"
        embed_color = COLOR_STEAM_VER
        badge_text = "Steam Version / CSF Update"
    elif "bypass" in lbl_lower or "hypervisor" in lbl_lower:
        icon = "⚡"
        embed_color = COLOR_BYPASS
        badge_text = "Bypass / Hypervisor"
    elif "repack" in lbl_lower or "fitgirl" in lbl_lower or "dodi" in lbl_lower:
        grp = (meta.get("group") or "").lower()
        if "fitgirl" in lbl_lower or "fitgirl" in grp:
            icon = "🎀"
            embed_color = 0xFF1493  # FitGirl Signature Magenta
            badge_text = "FitGirl Repack"
        elif "dodi" in lbl_lower or "dodi" in grp:
            icon = "⚡"
            embed_color = 0x10AC84  # DODI Signature Emerald Green
            badge_text = "DODI Repack"
        else:
            icon = "📦"
            embed_color = COLOR_REPACK  # Royal Purple for ElAmigos / other repacks
            badge_text = f"{meta['group'] or 'Repack'} Release"
    elif "crack" in lbl_lower or meta.get("group"):
        icon = "🚀"
        embed_color = COLOR_CRACK
        badge_text = f"{meta['group'] or 'Scene'} Crack Release"
    else:
        icon = "💬"
        embed_color = COLOR_NEW_POST
        badge_text = "Forum Post"

    clean_game_title = sanitize_game_title(post.topic_title)
    title = f"{icon} {clean_game_title}"
    if len(title) > 250:
        title = title[:247] + "..."

    post_link = post.post_url
    if post.topic_id and post.topic_id != "0" and "t=" not in post_link and "cs.rin.ru/forum/viewtopic.php" in post_link:
        post_link = f"https://cs.rin.ru/forum/viewtopic.php?t={post.topic_id}&p={post.post_id}#p{post.post_id}"

    embed = discord.Embed(
        title=title,
        url=post_link,
        color=embed_color
    )

    # Top Author / Category Badge
    embed.set_author(name=f"👤 {post.author} • {badge_text}")

    # Structured Fields Grid
    all_rel = meta.get("all_releases", [])
    if len(all_rel) > 1:
        rel_list_str = "\n".join([f"• `{r}`" for r in all_rel[:8]])
        if len(all_rel) > 8:
            rel_list_str += f"\n• *...and {len(all_rel) - 8} more*"
        embed.add_field(name=f"📦 Multi-Release Detected ({len(all_rel)} Releases)", value=rel_list_str, inline=False)
    elif meta.get("release_name"):
        embed.add_field(name="📦 Release Name", value=f"`{meta['release_name']}`", inline=False)
    
    embed.add_field(name="🏷️ Category", value=f"**{badge_text}**", inline=True)

    if meta.get("group"):
        embed.add_field(name="👑 Group / Repacker", value=f"**{meta['group']}**", inline=True)

    if meta.get("version"):
        embed.add_field(name="🔢 Version", value=f"**{meta['version']}**", inline=True)

    if meta.get("platform"):
        embed.add_field(name="💻 Platform", value=f"**{meta['platform']}**", inline=True)

    if meta.get("size"):
        embed.add_field(name="💾 File Size", value=f"**{meta['size']}**", inline=True)

    post_time_field = format_post_time(post.posted_time)
    embed.add_field(name="🕒 Posted Time (GMT+8)", value=post_time_field, inline=True)

    # Details / Notes (Clean description, omitting duplicate release name)
    notes_lines = []
    rel_names_set = set(all_rel) if all_rel else ({meta["release_name"]} if meta.get("release_name") else set())
    for line in cleaned_body.splitlines():
        trimmed = line.strip()
        # Skip line if it's identical to any release name already displayed in field
        if any(r and r in trimmed and len(trimmed) <= len(r) + 5 for r in rel_names_set):
            continue
        notes_lines.append(trimmed)

    clean_notes = "\n".join(notes_lines).strip()
    if clean_notes and len(clean_notes) > 10:
        if len(clean_notes) > 1000:
            clean_notes = clean_notes[:990] + "..."
        embed.add_field(name="📝 Details / Notes", value=clean_notes, inline=False)
    elif meta.get("release_name") or all_rel:
        embed.add_field(
            name="📝 Details",
            value="ℹ️ *Scene release registered. Check the forum thread for direct discussions and files.*",
            inline=False
        )

    # Direct Forum Source Link Field (NO repo links)
    embed.add_field(
        name="🌐 Forum Link",
        value=f"👉 **[Open Thread on CS.RIN.RU]({post_link})**",
        inline=False
    )

    if post.images:
        embed.set_image(url=post.images[0])

    embed.set_footer(text=f"CS.RIN.RU Forum Monitor • Post #{post.post_id} • GMT+8")
    return embed


DEFAULT_MONITOR_AVATARS: Dict[str, str] = {
    "WeMod / Wand": "https://www.wemod.com/static/images/device-icons/favicon-192-ce0bc030f3.png",
    "SteamRIP Monitor": "https://steamrip.com/wp-content/uploads/2021/06/cropped-favicon1-192x192.png",
    "SUO Wannabe Monitor": "https://steamunlockonennabe.click/logo.ico",
    "Steam Specials": "https://store.cloudflare.steamstatic.com/public/shared/images/responsive/share_steam_logo.png",
    "Steam Client Watch": "https://store.cloudflare.steamstatic.com/public/shared/images/responsive/share_steam_logo.png",
    "FitGirl Repacks": "https://fitgirl-repacks.site/wp-content/uploads/2016/08/cropped-icon-192x192.jpg",
    "DODI Repacks": "https://dodi-repacks.site/wp-content/uploads/2019/02/cropped-ICON-192x192.png",
    "Reddit CrackWatch": "https://www.redditstatic.com/desktop2x/img/favicon/android-icon-192x192.png",
    "Online-Fix.me": "https://online-fix.me/apple-touch-icon.png",
    "CS.RIN.RU Monitor": "https://cs.rin.ru/favicon.ico",
    "Release Monitor Bot": "https://store.cloudflare.steamstatic.com/public/shared/images/responsive/share_steam_logo.png",
}


def safe_webhook_send(
    webhook: Any,
    embed: discord.Embed,
    username: str = "CS.RIN.RU Monitor",
    avatar_url: Optional[str] = None,
    max_retries: int = 3,
    delay: float = 1.2
) -> bool:
    """
    Sends a Discord webhook with rate-limit shielding and HTTP 429 exponential backoff.
    Guarantees reliable delivery even when multiple releases burst in a single check.
    Automatically assigns high-res monitor avatars for each monitor username.
    """
    resolved_avatar = avatar_url or DEFAULT_MONITOR_AVATARS.get(username)

    for attempt in range(1, max_retries + 1):
        try:
            send_kwargs: Dict[str, Any] = {"embed": embed, "username": username}
            if resolved_avatar:
                send_kwargs["avatar_url"] = resolved_avatar
            webhook.send(**send_kwargs)
            time.sleep(delay)
            return True
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate limit" in err_str:
                wait_time = 3.0 * attempt
                logger.warning(f"Discord 429 rate limit hit. Waiting {wait_time}s before retry ({attempt}/{max_retries})...")
                time.sleep(wait_time)
            else:
                logger.error(f"Error sending webhook: {e}")
                time.sleep(1.0)
    return False


def create_title_change_embed(topic_id: str, old_title: str, new_title: str, url: str) -> discord.Embed:
    """Builds an alert embed when the thread title changes (e.g. crack status updated)."""
    kl_now = datetime.now(KL_TZ).strftime("%a, %b %d, %Y %I:%M %p GMT+8")
    embed = discord.Embed(
        title="🚨 Topic Status / Title Updated!",
        url=url,
        description=(
            f"**Previous Title:**\n`{old_title}`\n\n"
            f"**New Title:**\n`{new_title}`\n\n"
            f"👉 [Click here to view thread]({url})"
        ),
        color=COLOR_TITLE_CHANGE
    )
    embed.add_field(name="🌐 Forum Link", value=f"👉 **[Open Thread on CS.RIN.RU]({url})**", inline=False)
    embed.set_footer(text=f"CS.RIN.RU • Topic ID: {topic_id} • {kl_now}")
    return embed


def create_op_update_embed(post: ForumPost) -> discord.Embed:
    """Builds an embed when the main thread (first post) was edited."""
    post_time_field = format_post_time(post.posted_time)
    cleaned_body = scrub_ugly_content(post.clean_markdown)
    if len(cleaned_body) > 1200:
        cleaned_body = cleaned_body[:1190] + "..."

    clean_title = sanitize_game_title(post.topic_title)
    post_link = post.post_url
    if post.topic_id and post.topic_id != "0" and "t=" not in post_link and "cs.rin.ru/forum/viewtopic.php" in post_link:
        post_link = f"https://cs.rin.ru/forum/viewtopic.php?t={post.topic_id}&p={post.post_id}#p{post.post_id}"

    embed = discord.Embed(
        title=f"📝 Main Post (OP) Updated: {clean_title}",
        url=post_link,
        description=cleaned_body or "*[Main post edited]*",
        color=COLOR_OP_UPDATE
    )
    embed.set_author(name=f"Author: {post.author}", url=post.author_profile_url or "")
    embed.add_field(name="🕒 Updated Time (GMT+8)", value=post_time_field, inline=True)
    embed.add_field(
        name="🌐 Forum Link",
        value=f"👉 **[Open Thread on CS.RIN.RU]({post_link})**",
        inline=False
    )
    if post.images:
        embed.set_image(url=post.images[0])
    embed.set_footer(text=f"CS.RIN.RU • OP Post #{post.post_id} Edited • GMT+8")
    return embed


def create_new_thread_embed(thread_info: dict, forum_id: str) -> discord.Embed:
    """Builds an embed when a brand new game topic is posted to a monitored subforum."""
    kl_now = datetime.now(KL_TZ).strftime("%a, %b %d, %Y %I:%M %p GMT+8")
    clean_title = sanitize_game_title(thread_info.get("title", "Untitled"))
    embed = discord.Embed(
        title=f"🆕 New Topic: {clean_title}",
        url=thread_info.get("url", ""),
        description=f"A new game topic was started in forum section #{forum_id}.",
        color=COLOR_NEW_POST
    )
    embed.add_field(
        name="🌐 Forum Link",
        value=f"👉 **[View Topic on CS.RIN.RU]({thread_info.get('url', '')})**",
        inline=False
    )
    embed.set_footer(text=f"CS.RIN.RU • Forum #{forum_id} • {kl_now}")
    return embed
