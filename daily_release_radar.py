import os
import io
import logging
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("daily_release_radar")

KL_TZ = timezone(timedelta(hours=8))


def fetch_daily_upcoming_items(count_per_cat: int = 100) -> List[Dict[str, Any]]:
    """
    Fetches upcoming games and DLCs from Steam Store popularcomingsoon search.
    Returns list of items with real titles, release dates, prices, capsules, and store links.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    items: List[Dict[str, Any]] = []

    for cat_id, cat_type in [("998", "BASE GAME"), ("21", "DLC / EXPANSION")]:
        try:
            url = f"https://store.steampowered.com/search/results/?filter=popularcomingsoon&category1={cat_id}&cc=my&l=en&count={count_per_cat}&infinite=1"
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code != 200:
                continue
            data = r.json()
            soup = BeautifulSoup(data.get("results_html", ""), "html.parser")

            for row in soup.select("a.search_result_row"):
                appid = row.get("data-ds-appid")
                if not appid or not str(appid).isdigit():
                    continue

                title_el = row.select_one(".title")
                title = title_el.text.strip() if title_el else ""
                if not title:
                    continue

                date_el = row.select_one(".search_released")
                date_str = date_el.text.strip() if date_el else ""

                img_el = row.select_one(".search_capsule img")
                img_url = img_el.get("src") if img_el else None

                price_el = row.select_one(".discount_final_price") or row.select_one(".search_price")
                price = price_el.text.strip() if price_el else "Free / Unpriced"

                raw_href = row.get("href", "")
                store_url = raw_href.split("?")[0] if raw_href else f"https://store.steampowered.com/app/{appid}/"

                items.append({
                    "appid": appid,
                    "title": title,
                    "date": date_str,
                    "type": cat_type,
                    "price": price,
                    "img_url": img_url,
                    "store_url": store_url
                })
        except Exception as e:
            logger.error(f"Error fetching coming soon items (cat={cat_id}): {e}")

    return items


def get_system_font(size: int, bold: bool = False):
    """Safely retrieves a TrueType font on Windows or Linux (Docker/Koyeb)."""
    if bold:
        candidates = [
            os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "segoeuib.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "DejaVuSans-Bold.ttf",
            "arialbd.ttf"
        ]
    else:
        candidates = [
            os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "segoeui.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "DejaVuSans.ttf",
            "arial.ttf"
        ]

    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def generate_daily_poster(items: List[Dict[str, Any]], target_date_str: str, output_path: str) -> str:
    """
    Renders an infographic poster for today's Steam releases (1200x860, 2x3 grid).
    """
    W, H = 1200, 860
    img = Image.new("RGBA", (W, H), (13, 17, 23, 255))
    draw = ImageDraw.Draw(img)

    # 1. Gradient Background
    for y in range(H):
        ratio = y / H
        if ratio < 0.5:
            r = int(11 + (18 - 11) * (ratio * 2))
            g = int(14 + (23 - 14) * (ratio * 2))
            b = int(20 + (30 - 20) * (ratio * 2))
        else:
            r = int(18 + (9 - 18) * ((ratio - 0.5) * 2))
            g = int(23 + (12 - 23) * ((ratio - 0.5) * 2))
            b = int(30 + (16 - 30) * ((ratio - 0.5) * 2))
        draw.line([(0, y), (W, y)], fill=(r, g, b, 255))

    # Top cyber neon ambient glow
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse([W//2 - 450, -180, W//2 + 450, 160], fill=(0, 180, 216, 28))
    glow_draw.ellipse([W//2 - 220, -100, W//2 + 220, 120], fill=(99, 102, 241, 24))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    # Cross-platform fonts
    font_badge = get_system_font(11, bold=True)
    font_title = get_system_font(34, bold=True)
    font_sub = get_system_font(15, bold=False)
    font_card_title = get_system_font(18, bold=True)
    font_card_sub = get_system_font(13, bold=False)
    font_pill = get_system_font(11, bold=True)
    font_tag = get_system_font(10, bold=True)
    font_footer = get_system_font(12, bold=False)

    # Top badge
    badge_text = "DAILY RELEASE RADAR  //  STEAM"
    b_w = 230
    b_h = 24
    bx = (W - b_w) // 2
    by = 22
    draw.rounded_rectangle([bx, by, bx + b_w, by + b_h], radius=12, fill=(30, 41, 59, 255), outline=(56, 189, 248, 200), width=1)
    draw.text((bx + 20, by + 4), badge_text, font=font_badge, fill=(56, 189, 248, 255))

    # Main Title
    title_text = "TODAY'S STEAM RELEASES"
    t_bbox = draw.textbbox((0, 0), title_text, font=font_title)
    draw.text(((W - (t_bbox[2] - t_bbox[0])) // 2, 54), title_text, font=font_title, fill=(255, 255, 255, 255))

    # Subtitle
    sub_text = f"RELEASE DATE: {target_date_str.upper()}   -   CURATED HIGHLIGHTS (PC & DLCS)"
    s_bbox = draw.textbbox((0, 0), sub_text, font=font_sub)
    draw.text(((W - (s_bbox[2] - s_bbox[0])) // 2, 98), sub_text, font=font_sub, fill=(148, 163, 184, 255))

    # Decorative separator
    draw.line([(40, 135), (W - 40, 135)], fill=(30, 41, 59, 220), width=1)

    # Grid settings
    cols = 3
    card_w = 360
    card_h = 300
    gap_x = 20
    gap_y = 20
    start_x = 40
    start_y = 158

    display_items = items[:6]

    for idx, item in enumerate(display_items):
        c = idx % cols
        r = idx // cols
        cx = start_x + c * (card_w + gap_x)
        cy = start_y + r * (card_h + gap_y)

        # Card container
        draw.rounded_rectangle(
            [cx, cy, cx + card_w, cy + card_h],
            radius=12,
            fill=(22, 27, 34, 255),
            outline=(48, 54, 61, 230),
            width=1
        )

        # Capsule image
        img_w = card_w - 20
        img_h = 145
        capsule_x = cx + 10
        capsule_y = cy + 10

        if item.get("img_url"):
            try:
                req = urllib.request.Request(item["img_url"], headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    cap_data = resp.read()
                cap_img = Image.open(io.BytesIO(cap_data)).convert("RGBA")
                cap_img = cap_img.resize((img_w, img_h), Image.Resampling.LANCZOS)

                mask = Image.new("L", (img_w, img_h), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.rounded_rectangle([0, 0, img_w, img_h], radius=8, fill=255)

                img.paste(cap_img, (capsule_x, capsule_y), mask)
            except Exception as ex:
                logger.debug(f"Capsule load failed for {item['title']}: {ex}")
                draw.rounded_rectangle([capsule_x, capsule_y, capsule_x + img_w, capsule_y + img_h], radius=8, fill=(33, 38, 45, 255))
        else:
            draw.rounded_rectangle([capsule_x, capsule_y, capsule_x + img_w, capsule_y + img_h], radius=8, fill=(33, 38, 45, 255))

        # Badges over image
        # 1. Type
        is_dlc = item.get("type") == "DLC / EXPANSION"
        t_col = (217, 119, 6) if is_dlc else (14, 165, 233)
        t_label = "DLC / EXPANSION" if is_dlc else "BASE GAME"
        type_w = draw.textbbox((0, 0), t_label, font=font_pill)[2] + 16
        draw.rounded_rectangle(
            [capsule_x + 8, capsule_y + 8, capsule_x + 8 + type_w, capsule_y + 8 + 20],
            radius=6,
            fill=(t_col[0], t_col[1], t_col[2], 230)
        )
        draw.text((capsule_x + 16, capsule_y + 11), t_label, font=font_pill, fill=(255, 255, 255, 255))

        # 2. Date
        d_str = item.get("date") or "TODAY"
        date_w = draw.textbbox((0, 0), d_str, font=font_pill)[2] + 16
        date_x = capsule_x + img_w - date_w - 8
        draw.rounded_rectangle(
            [date_x, capsule_y + 8, date_x + date_w, capsule_y + 8 + 20],
            radius=6,
            fill=(13, 17, 23, 220),
            outline=(56, 189, 248, 160),
            width=1
        )
        draw.text((date_x + 8, capsule_y + 11), d_str, font=font_pill, fill=(255, 255, 255, 255))

        # Content area
        text_y = capsule_y + img_h + 16
        title_str = item.get("title", "Game Title")
        if len(title_str) > 26:
            title_str = title_str[:25] + "…"
        draw.text((cx + 16, text_y), title_str, font=font_card_title, fill=(240, 246, 252, 255))

        # Price / Status
        price_text = item.get("price", "Free / Unpriced")
        draw.text((cx + 16, text_y + 28), f"Price: {price_text}", font=font_card_sub, fill=(139, 148, 158, 255))

        # Bottom tag pill
        tag_text = "LAUNCHING TODAY" if item.get("is_today", True) else "UPCOMING TOMORROW"
        tag_color = (56, 189, 248) if item.get("is_today", True) else (251, 191, 36)
        tag_w = draw.textbbox((0, 0), tag_text, font=font_tag)[2] + 30
        draw.rounded_rectangle(
            [cx + 16, cy + card_h - 38, cx + 16 + tag_w, cy + card_h - 16],
            radius=6,
            fill=(30, 41, 59, 255),
            outline=(56, 189, 248, 120),
            width=1
        )
        draw.ellipse([cx + 26, cy + card_h - 29, cx + 32, cy + card_h - 23], fill=tag_color)
        draw.text((cx + 38, cy + card_h - 33), tag_text, font=font_tag, fill=tag_color)

        # Steam link text on right
        draw.text((cx + card_w - 76, cy + card_h - 33), "STEAM >", font=font_pill, fill=(139, 148, 158, 255))

    # Footer
    draw.line([(40, start_y + 2 * (card_h + gap_y) + 15), (W - 40, start_y + 2 * (card_h + gap_y) + 15)], fill=(30, 41, 59, 220), width=1)
    footer_y = H - 34
    draw.text((40, footer_y), "AUTOMATED BY RELEASE MONITOR BOT  -  DELIVERED EVERY MIDNIGHT 12:00 AM", font=font_footer, fill=(100, 116, 139, 255))
    draw.text((W - 390, footer_y), "KUALA LUMPUR TIME (GMT+8)   -   STORE PRICING IN MYR (RM)", font=font_footer, fill=(100, 116, 139, 255))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "PNG")
    logger.info(f"Daily Release Radar poster saved to {output_path}")
    return output_path


def check_daily_release_radar(state: dict, force: bool = False) -> Optional[Dict[str, Any]]:
    """
    Checks if today's Daily Release Radar needs to be posted at 12:00 AM (00:00 GMT+8).
    Returns dictionary with embed data, poster image path, and item count if due.
    """
    now_kl = datetime.now(KL_TZ)
    today_key = now_kl.strftime("%Y-%m-%d")

    radar_state = state.setdefault("daily_release_radar", {})
    last_posted = radar_state.get("last_posted_date")

    # Only post once per calendar day at midnight (hour 0), unless forced
    if not force:
        if last_posted == today_key:
            return None
        if now_kl.hour != 0:
            return None

    logger.info(f"Triggering Daily Steam Release Radar for {today_key} (KL Time: {now_kl.strftime('%I:%M %p')})...")

    # Target date patterns for Steam search
    today_pattern = f"{now_kl.day} {now_kl.strftime('%b')}, {now_kl.year}"
    tomorrow = now_kl + timedelta(days=1)
    tomorrow_pattern = f"{tomorrow.day} {tomorrow.strftime('%b')}, {tomorrow.year}"

    all_items = fetch_daily_upcoming_items(count_per_cat=100)

    # 1. Filter items launching today
    today_items = [it for it in all_items if it.get("date") == today_pattern]
    for it in today_items:
        it["is_today"] = True

    # 2. If quiet day (< 4 items), enrich with tomorrow's top upcoming items
    combined_items = list(today_items)
    if len(combined_items) < 6:
        tomorrow_items = [it for it in all_items if it.get("date") == tomorrow_pattern]
        for it in tomorrow_items:
            it["is_today"] = False
        combined_items.extend(tomorrow_items[: 6 - len(combined_items)])

    # If still empty, grab top coming soon
    if not combined_items:
        combined_items = all_items[:6]

    selected_items = combined_items[:6]

    # Render Infographic Poster
    poster_filename = f"daily_radar_{today_key}.png"
    assets_dir = os.path.join(os.path.dirname(__file__), "assets", "daily_radar")
    poster_path = os.path.join(assets_dir, poster_filename)
    generate_daily_poster(selected_items, today_pattern, poster_path)

    # Mark as posted
    radar_state["last_posted_date"] = today_key

    return {
        "date_key": today_key,
        "date_display": now_kl.strftime("%A, %b %d, %Y"),
        "items": selected_items,
        "poster_path": poster_path,
        "today_count": len(today_items)
    }


def create_daily_release_radar_embed(data: Dict[str, Any]):
    """
    Builds a Discord Embed for the Daily Release Radar post.
    Guarantees every field value is safely <= 850 characters (well under Discord's 1024 limit).
    """
    import discord
    date_display = data.get("date_display", "")
    items = data.get("items", [])

    embed = discord.Embed(
        title=f"🎯 Daily Steam Release Radar — {date_display}",
        description="Good morning! Here are today's top PC game and DLC releases launching on Steam:",
        color=0x00B4D8  # Cyber Cyan
    )

    formatted_items = []
    for it in items:
        icon = "🧩" if it.get("type") == "DLC / EXPANSION" else "🎮"
        tag = "Today" if it.get("is_today", True) else "Tomorrow"
        raw_title = it.get("title", "Release")
        title = raw_title if len(raw_title) <= 45 else raw_title[:44] + "…"
        url = it.get("store_url", "https://store.steampowered.com/")
        price = it.get("price", "Free / Unpriced")
        appid = it.get("appid", "")
        steamdb_url = f"https://steamdb.info/app/{appid}/" if appid else ""

        line = (
            f"{icon} **[{title}]({url})** — `{tag} • {price}`\n"
            f"   🌐 [Web Store]({url}) • 📊 [SteamDB]({steamdb_url})"
        )
        formatted_items.append(line)

    if not formatted_items:
        embed.add_field(
            name="🚀 Featured Releases",
            value="No major releases scheduled for today.",
            inline=False
        )
    else:
        # Split items into chunks of at most 3 items and max 800 characters
        chunks = []
        curr_chunk = []
        curr_len = 0
        for item_str in formatted_items:
            if (len(curr_chunk) >= 3 or (curr_len + len(item_str) + 1 > 800)) and curr_chunk:
                chunks.append("\n".join(curr_chunk))
                curr_chunk = [item_str]
                curr_len = len(item_str)
            else:
                curr_chunk.append(item_str)
                curr_len += len(item_str) + 1
        if curr_chunk:
            chunks.append("\n".join(curr_chunk))

        if len(chunks) == 1:
            embed.add_field(name="🚀 Featured Releases", value=chunks[0], inline=False)
        else:
            for idx, chunk in enumerate(chunks):
                embed.add_field(
                    name=f"🚀 Featured Releases ({idx + 1}/{len(chunks)})",
                    value=chunk,
                    inline=False
                )

    embed.set_footer(
        text="Daily Steam Release Radar • Automated at 12:00 AM GMT+8 • Prices in MYR (RM)",
        icon_url="https://raw.githubusercontent.com/mirzaarsyad74-cmyk/hv-bypass-tool/main/assets/icons/steam_deals_icon.png"
    )

    return embed