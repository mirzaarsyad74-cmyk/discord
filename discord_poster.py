import re
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


def convert_time_to_kl(raw_time: str) -> str:
    """Converts ISO or forum timestamp strings into Kuala Lumpur Time (UTC+08:00)."""
    if not raw_time:
        return datetime.now(KL_TZ).strftime("%a, %b %d, %Y %I:%M %p UTC+08:00")
    
    # Try ISO-8601 (from Atom XML feed)
    try:
        dt = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        return dt.astimezone(KL_TZ).strftime("%a, %b %d, %Y %I:%M %p UTC+08:00")
    except Exception:
        pass

    # Try common phpBB timestamp formats
    for fmt in ("%A, %d %b %Y, %H:%M", "%d %b %Y, %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(raw_time.strip(), fmt)
            dt = dt.replace(tzinfo=timezone.utc).astimezone(KL_TZ)
            return dt.strftime("%a, %b %d, %Y %I:%M %p UTC+08:00")
        except Exception:
            continue

    return f"{raw_time} (UTC+08:00)"


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


def extract_metadata(text: str, topic_title: str) -> Dict[str, Optional[str]]:
    """Extracts structured metadata from release post text."""
    meta: Dict[str, Optional[str]] = {
        "release_name": None,
        "group": None,
        "version": None,
        "platform": None,
        "size": None
    }

    # 1. Scene release directory tag: Game_Name_v1.0-GROUP or Game.Name-GROUP
    scene_match = re.search(
        r'\b([A-Za-z0-9_.\-]+-(?:ElAmigos|RUNE|TENOKE|FLT|CODEX|SKIDROW|Razor1911|FitGirl|DODI|GOLDBERG|Fairlight|TinyRepack))\b',
        text,
        re.IGNORECASE
    )
    if scene_match:
        rel = scene_match.group(1).strip()
        meta["release_name"] = rel
        group = rel.split("-")[-1]
        meta["group"] = group

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
    """
    # 1. Clean the post content
    cleaned_body = scrub_ugly_content(post.clean_markdown)
    meta = extract_metadata(post.clean_markdown, post.topic_title)

    # 2. Determine Category, Title, and Color
    category_name = release_label or "Update"
    lbl_lower = category_name.lower()

    if "steam version" in lbl_lower or "csf" in lbl_lower or "build" in lbl_lower:
        icon = "🔄"
        embed_color = COLOR_STEAM_VER
        badge_text = "Steam Version / CSF Update"
    elif "bypass" in lbl_lower or "hypervisor" in lbl_lower:
        icon = "⚡"
        embed_color = COLOR_BYPASS
        badge_text = "Bypass / Hypervisor"
    elif "repack" in lbl_lower:
        icon = "📦"
        embed_color = COLOR_REPACK
        badge_text = f"{meta['group'] or 'Repack'} Release"
    elif "crack" in lbl_lower or meta.get("group"):
        icon = "🚀"
        embed_color = COLOR_CRACK
        badge_text = f"{meta['group'] or 'Scene'} Crack Release"
    else:
        icon = "💬"
        embed_color = COLOR_NEW_POST
        badge_text = "Forum Post"

    # Clean Game Title (strip bracket tags if already in topic title)
    clean_game_title = post.topic_title.strip()
    if clean_game_title.startswith("Re:"):
        clean_game_title = clean_game_title[3:].strip()

    title = f"{icon} {clean_game_title}"
    if len(title) > 250:
        title = title[:247] + "..."

    embed = discord.Embed(
        title=title,
        url=post.post_url,
        color=embed_color
    )

    # Top Author / Category Badge
    embed.set_author(name=f"👤 {post.author} • {badge_text}")

    # Structured Fields Grid
    if meta.get("release_name"):
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

    kl_time = convert_time_to_kl(post.posted_time)
    embed.add_field(name="🕒 Posted Time", value=f"`{kl_time}`", inline=True)

    # 3. Notes / Details (Clean description, omitting duplicate release name)
    notes_lines = []
    rel_name = meta.get("release_name") or ""
    for line in cleaned_body.splitlines():
        trimmed = line.strip()
        # Skip line if it's just the release name already displayed in field
        if rel_name and rel_name in trimmed and len(trimmed) <= len(rel_name) + 5:
            continue
        notes_lines.append(trimmed)

    clean_notes = "\n".join(notes_lines).strip()
    if clean_notes and len(clean_notes) > 10:
        if len(clean_notes) > 1000:
            clean_notes = clean_notes[:990] + "..."
        embed.add_field(name="📝 Details / Notes", value=clean_notes, inline=False)
    elif meta.get("release_name"):
        embed.add_field(
            name="📝 Details",
            value="ℹ️ *Scene release registered. Check the forum thread for direct discussions and files.*",
            inline=False
        )

    # 4. Direct Forum Source Link Field (NO repo links)
    embed.add_field(
        name="🌐 Forum Link",
        value=f"👉 **[Open Thread on CS.RIN.RU]({post.post_url})**",
        inline=False
    )

    # If post includes images, set the primary image
    if post.images:
        embed.set_image(url=post.images[0])

    embed.set_footer(text=f"CS.RIN.RU Forum Monitor • Post #{post.post_id} • Kuala Lumpur (UTC+08:00)")
    return embed


def create_title_change_embed(topic_id: str, old_title: str, new_title: str, url: str) -> discord.Embed:
    """Builds an alert embed when the thread title changes (e.g. crack status updated)."""
    kl_now = datetime.now(KL_TZ).strftime("%a, %b %d, %Y %I:%M %p UTC+08:00")
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
    kl_time = convert_time_to_kl(post.posted_time)
    cleaned_body = scrub_ugly_content(post.clean_markdown)
    if len(cleaned_body) > 1200:
        cleaned_body = cleaned_body[:1190] + "..."

    embed = discord.Embed(
        title=f"📝 Main Post (OP) Updated: {post.topic_title}",
        url=post.post_url,
        description=cleaned_body or "*[Main post edited]*",
        color=COLOR_OP_UPDATE
    )
    embed.set_author(name=f"Author: {post.author}", url=post.author_profile_url or "")
    embed.add_field(
        name="🌐 Forum Link",
        value=f"👉 **[Open Thread on CS.RIN.RU]({post.post_url})**",
        inline=False
    )
    if post.images:
        embed.set_image(url=post.images[0])
    embed.set_footer(text=f"CS.RIN.RU • OP Post #{post.post_id} Edited • {kl_time}")
    return embed


def create_new_thread_embed(thread_info: dict, forum_id: str) -> discord.Embed:
    """Builds an embed when a brand new game topic is posted to a monitored subforum."""
    kl_now = datetime.now(KL_TZ).strftime("%a, %b %d, %Y %I:%M %p UTC+08:00")
    embed = discord.Embed(
        title=f"🆕 New Topic: {thread_info.get('title', 'Untitled')}",
        url=thread_info.get("url", ""),
        description=f"A new topic was started in forum section #{forum_id}.",
        color=COLOR_NEW_POST
    )
    embed.add_field(
        name="🌐 Forum Link",
        value=f"👉 **[View Topic on CS.RIN.RU]({thread_info.get('url', '')})**",
        inline=False
    )
    embed.set_footer(text=f"CS.RIN.RU • Forum #{forum_id} • {kl_now}")
    return embed
