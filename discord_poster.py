import logging
from typing import Optional, List
import discord
from scraper import ForumPost

logger = logging.getLogger("discord_poster")

COLOR_NEW_POST = 0x3498DB       # Vibrant Blue
COLOR_RELEASE = 0x9B59B6        # Purple for Repacks / Bypasses / Cracks
COLOR_TITLE_CHANGE = 0xE74C3C   # Alert Red
COLOR_OP_UPDATE = 0xF39C12      # Gold / Orange
COLOR_INFO = 0x2ECC71           # Green

def format_description(text: str, max_chars: int = 3500, post_url: str = "") -> str:
    """Safely formats and truncates markdown description to fit Discord's 4096 character limit."""
    if not text:
        return "*[No text content]*"
    
    if len(text) <= max_chars:
        return text
    
    truncated = text[:max_chars].rstrip()
    if post_url:
        return f"{truncated}...\n\n🔗 **[Read Full Post on CS.RIN.RU]({post_url})**"
    return f"{truncated}...\n\n*(Truncated due to Discord length limit)*"


def create_post_embed(post: ForumPost, release_label: Optional[str] = None) -> discord.Embed:
    """Builds a Discord Embed for a new post, release notification, or Steam version update."""
    if release_label:
        lbl_lower = release_label.lower()
        if "steam version" in lbl_lower or "csf" in lbl_lower or "build" in lbl_lower:
            title = f"🔄 [{release_label}] {post.topic_title}"
            embed_color = 0x3498DB  # Steam Blue
        elif "bypass" in lbl_lower or "hypervisor" in lbl_lower:
            title = f"⚡ [{release_label}] {post.topic_title}"
            embed_color = 0xE67E22  # Vibrant Orange
        elif "repack" in lbl_lower:
            title = f"📦 [{release_label}] {post.topic_title}"
            embed_color = 0x9B59B6  # Royal Purple
        else:
            title = f"🚀 [{release_label}] {post.topic_title}"
            embed_color = 0xE74C3C  # Alert Red
    else:
        title = f"💬 New Post: {post.topic_title}"
        embed_color = COLOR_NEW_POST

    if len(title) > 250:
        title = title[:247] + "..."

    embed = discord.Embed(
        title=title,
        url=post.post_url,
        description=format_description(post.clean_markdown, post_url=post.post_url),
        color=embed_color
    )

    # Author
    author_name = f"👤 {post.author}"
    if post.author_profile_url:
        embed.set_author(name=author_name, url=post.author_profile_url)
    else:
        embed.set_author(name=author_name)

    # Direct Forum Source Link Field
    embed.add_field(
        name="🌐 Forum Link",
        value=f"👉 **[Open Thread on CS.RIN.RU]({post.post_url})**",
        inline=False
    )

    # If post includes images, set the primary image
    if post.images:
        embed.set_image(url=post.images[0])

    embed.set_footer(text=f"CS.RIN.RU • Post #{post.post_id} • {post.posted_time}")
    return embed


def create_title_change_embed(topic_id: str, old_title: str, new_title: str, url: str) -> discord.Embed:
    """Builds an alert embed when the thread title changes (e.g. crack status updated)."""
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
    embed.set_footer(text=f"CS.RIN.RU • Topic ID: {topic_id}")
    return embed


def create_op_update_embed(post: ForumPost) -> discord.Embed:
    """Builds an embed when the main thread (first post) was edited."""
    embed = discord.Embed(
        title=f"📝 Main Post (OP) Updated: {post.topic_title}",
        url=post.post_url,
        description=format_description(post.clean_markdown, max_chars=3000, post_url=post.post_url),
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
    embed.set_footer(text=f"CS.RIN.RU • OP Post #{post.post_id} Edited")
    return embed


def create_new_thread_embed(thread_info: dict, forum_id: str) -> discord.Embed:
    """Builds an embed when a brand new game topic is posted to a monitored subforum."""
    embed = discord.Embed(
        title=f"🎮 New Game Thread Created: {thread_info.get('title', 'Unknown')}",
        url=thread_info.get("url", ""),
        description=(
            f"A new game discussion/release thread was opened in forum section **f={forum_id}**!\n\n"
            f"👉 **[Click here to view on CS.RIN.RU]({thread_info.get('url', '')})**"
        ),
        color=0x9B59B6
    )
    embed.set_footer(text=f"CS.RIN.RU • Subforum f={forum_id} • Topic ID: {thread_info.get('topic_id')}")
    return embed
