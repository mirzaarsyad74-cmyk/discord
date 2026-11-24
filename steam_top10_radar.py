import os
import io
import re
import logging
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import requests
from PIL import Image, ImageDraw, ImageFont

import external_monitors

logger = logging.getLogger("steam_top10_radar")

KL_TZ = timezone(timedelta(hours=8))


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


def draw_vector_icon(draw: ImageDraw.Draw, icon_type: str, x: float, y: float, color: tuple, size: float = 12):
    """
    Renders pixel-perfect, crisp vector icons directly on the canvas without
    relying on system emoji fonts (which cause missing glyph tofu squares).
    """
    s = size / 12.0
    if icon_type == "catalog":
        # Library / Database books archive
        draw.rounded_rectangle([x, y + 8*s, x + 12*s, y + 11*s], radius=1, fill=color)
        draw.rounded_rectangle([x + 1*s, y + 4*s, x + 13*s, y + 7*s], radius=1, fill=color)
        draw.rounded_rectangle([x + 2*s, y, x + 12*s, y + 3*s], radius=1, fill=color)
    elif icon_type == "storage":
        # Storage Drive / SSD
        draw.rounded_rectangle([x, y + 1*s, x + 13*s, y + 11*s], radius=2, outline=color, width=1)
        draw.line([(x + 2*s, y + 4*s), (x + 8*s, y + 4*s)], fill=color, width=1)
        draw.ellipse([x + 9*s, y + 7*s, x + 11*s, y + 9*s], fill=color)
    elif icon_type == "network":
        # Global Network Sphere
        draw.ellipse([x, y, x + 12*s, y + 12*s], outline=color, width=1)
        draw.ellipse([x + 3*s, y, x + 9*s, y + 12*s], outline=color, width=1)
        draw.line([(x, y + 6*s), (x + 12*s, y + 6*s)], fill=color, width=1)
    elif icon_type == "lightning":
        # Lightning Bolt
        pts = [
            (x + 6*s, y),
            (x + 2*s, y + 7*s),
            (x + 5.5*s, y + 7*s),
            (x + 3.5*s, y + 12*s),
            (x + 10.5*s, y + 5*s),
            (x + 6.5*s, y + 5*s),
            (x + 8.5*s, y)
        ]
        draw.polygon(pts, fill=color)
    elif icon_type == "players":
        # Dual Player Avatars
        draw.ellipse([x + 2*s, y + 1*s, x + 6.5*s, y + 5.5*s], fill=color)
        draw.pieslice([x, y + 6*s, x + 8.5*s, y + 14*s], 180, 360, fill=color)
        draw.ellipse([x + 7*s, y, x + 11*s, y + 4*s], fill=color)
        draw.pieslice([x + 5*s, y + 5*s, x + 13*s, y + 13*s], 180, 360, fill=color)
    elif icon_type == "box":
        # Package Box
        draw.rounded_rectangle([x, y + 1*s, x + 11*s, y + 11*s], radius=1, outline=color, width=1)
        draw.line([(x, y + 4*s), (x + 11*s, y + 4*s)], fill=color, width=1)
        draw.line([(x + 5.5*s, y + 4*s), (x + 5.5*s, y + 11*s)], fill=color, width=1)
    elif icon_type == "download":
        # Download Arrow into Tray
        draw.line([(x + 5.5*s, y), (x + 5.5*s, y + 7*s)], fill=color, width=2)
        draw.polygon([(x + 2.5*s, y + 6*s), (x + 8.5*s, y + 6*s), (x + 5.5*s, y + 9.5*s)], fill=color)
        draw.line([(x + 1*s, y + 8*s), (x + 1*s, y + 11*s), (x + 10*s, y + 11*s), (x + 10*s, y + 8*s)], fill=color, width=1)
    elif icon_type == "star":
        # 5-pointed Star
        import math
        pts = []
        for i in range(10):
            r = (5.5 * s) if i % 2 == 0 else (2.4 * s)
            angle = i * math.pi / 5 - math.pi / 2
            pts.append((x + 6 * s + r * math.cos(angle), y + 6 * s + r * math.sin(angle)))
        draw.polygon(pts, fill=color)


def load_suo_icon(target_size: tuple = (72, 72)) -> Optional[Image.Image]:
    """
    Loads the official Steam Unlock ONENNABE application icon from disk or bundled assets.
    Supports C:\\Program Files\\Steam Unlock ONENNABE\\unins000.exe and static img .ico.
    """
    candidates = [
        r"C:\Program Files\Steam Unlock ONENNABE\static\img\steamunlock_wannabe.ico",
        r"C:\Program Files\Steam Unlock ONENNABE\unins000.exe",
        os.path.join(os.path.dirname(__file__), "assets", "suo_icon.png"),
        os.path.join("assets", "suo_icon.png")
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                if path.lower().endswith(".ico") or path.lower().endswith(".png"):
                    ico = Image.open(path).convert("RGBA")
                    return ico.resize(target_size, Image.Resampling.LANCZOS)
            except Exception:
                pass
    fallback = os.path.join(os.path.dirname(__file__), "assets", "suo_icon.png")
    if os.path.exists(fallback):
        try:
            return Image.open(fallback).convert("RGBA").resize(target_size, Image.Resampling.LANCZOS)
        except Exception:
            pass
    return None


def fetch_top10_suo_games():
    """
    Fetches the Top 10 most downloaded games from SteamUnlock Wannabe (SUO)
    and cross-references each with official live Steam data (player count, high-res artwork, store link).
    Returns (top_10_games, suo_stats).
    """
    steam_ranks = {}
    try:
        url_charts = "https://api.steampowered.com/ISteamChartsService/GetGamesByConcurrentPlayers/v1/"
        r_charts = requests.get(url_charts, timeout=6)
        if r_charts.status_code == 200:
            for g in r_charts.json().get("response", {}).get("ranks", []):
                aid = str(g["appid"])
                steam_ranks[aid] = {
                    "rank": g["rank"],
                    "concurrent": g.get("concurrent_in_game", 0)
                }
    except Exception as e:
        logger.warning(f"Error fetching Steam charts: {e}")

    suo_items = external_monitors.fetch_suo_catalog(limit=0)
    total_suo_count = len(suo_items)
    online_count = sum(1 for g in suo_items if str(g.get("online_supported")).lower() == "yes")
    bypass_count = sum(
        1 for g in suo_items
        if str(g.get("bypass_supported")).lower() == "yes" or str(g.get("hypervisor_bypass")).lower() == "yes"
    )
    total_gb = 0.0
    for g in suo_items:
        s = g.get("size_gb", "0")
        try:
            total_gb += float(str(s).replace("GB", "").strip())
        except Exception:
            pass
    total_tb = round(total_gb / 1024.0, 2)

    suo_stats = {
        "total_games": total_suo_count,
        "total_tb": total_tb,
        "total_gb": round(total_gb, 1),
        "online_count": online_count,
        "bypass_count": bypass_count
    }

    logger.info(f"Filtering Top 10 most downloaded games across {total_suo_count:,} SUO games ({total_tb} TB)...")

    # Sort SUO catalog strictly by download count (Highest Downloads First)
    suo_items.sort(key=lambda x: int(x.get("downloads", 0)), reverse=True)
    top_candidates = suo_items[:15]

    top_matches = []
    for item in top_candidates:
        if len(top_matches) >= 10:
            break
        aid = str(item.get("appid"))
        official_name = item.get("name", f"App {aid}")
        header_url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{aid}/header.jpg"

        # Check Steam API for official title and high-res header image
        try:
            r_api = requests.get(f"https://store.steampowered.com/api/appdetails?appids={aid}", timeout=3)
            if r_api.status_code == 200:
                app_data = r_api.json().get(aid, {}).get("data", {})
                if app_data:
                    official_name = app_data.get("name") or official_name
                    h_img = app_data.get("header_image")
                    if h_img:
                        header_url = h_img
        except Exception:
            pass

        # Check live Steam concurrent players
        concurrent = 0
        if aid in steam_ranks:
            concurrent = steam_ranks[aid].get("concurrent", 0)
        else:
            try:
                r_p = requests.get(f"https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={aid}", timeout=3).json()
                concurrent = r_p.get("response", {}).get("player_count", 0)
            except Exception:
                pass

        top_matches.append({
            "appid": aid,
            "name": official_name,
            "steam_rank": len(top_matches) + 1,
            "concurrent": concurrent,
            "downloads": item.get("downloads", 0),
            "size_gb": item.get("size_gb", "N/A"),
            "online_supported": item.get("online_supported", "No"),
            "bypass_supported": item.get("bypass_supported", "No"),
            "img_url": header_url,
            "store_url": f"https://store.steampowered.com/app/{aid}/",
            "suo_url": "https://steamunlockonennabe.click/"
        })

    return top_matches, suo_stats


def render_steam_top10_poster(games: List[Dict[str, Any]], output_path: str, suo_stats: Optional[Any] = None) -> str:
    """
    Renders a 1600x1160 high-resolution cyber infographic poster
    featuring Top 10 Steam Hits available on SUO, live ranking movement badges,
    and a prominent 4-column platform statistics HUD table.
    """
    if isinstance(suo_stats, int):
        total_suo_count = suo_stats
        total_tb = 187.65
        total_gb = 192153.0
        online_count = 407
        bypass_count = 208
    elif isinstance(suo_stats, dict):
        total_suo_count = suo_stats.get("total_games", 32975)
        total_tb = suo_stats.get("total_tb", 187.65)
        total_gb = suo_stats.get("total_gb", 192153.0)
        online_count = suo_stats.get("online_count", 407)
        bypass_count = suo_stats.get("bypass_count", 208)
    else:
        total_suo_count = 32975
        total_tb = 187.65
        total_gb = 192153.0
        online_count = 407
        bypass_count = 208

    W, H = 1600, 1160
    img = Image.new("RGBA", (W, H), (13, 17, 23, 255))
    draw = ImageDraw.Draw(img)

    # 1. Dark Cyber Gradient Background
    for y in range(H):
        ratio = y / H
        r = int(10 + (16 - 10) * ratio)
        g = int(14 + (22 - 14) * ratio)
        b = int(22 + (34 - 22) * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b, 255))

    # Ambient Top Glow
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(glow)
    g_draw.ellipse([W // 2 - 500, -180, W // 2 + 500, 160], fill=(0, 180, 216, 25))
    g_draw.ellipse([W // 2 - 250, -80, W // 2 + 250, 140], fill=(245, 158, 11, 20))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    # Fonts
    font_badge = get_system_font(12, bold=True)
    font_title = get_system_font(34, bold=True)
    font_sub = get_system_font(13, bold=False)
    font_stat_val = get_system_font(16, bold=True)
    font_stat_lbl = get_system_font(10, bold=True)
    font_rank = get_system_font(26, bold=True)
    font_card_title = get_system_font(17, bold=True)
    font_card_sub = get_system_font(12, bold=False)
    font_pill = get_system_font(11, bold=True)
    font_footer = get_system_font(11, bold=False)

    # Header Dual Badges (Steam + Live Status)
    now_kl = datetime.now(KL_TZ)
    date_str = now_kl.strftime("%d %b %Y, %I:%M %p GMT+8").upper()
    badge_steam = "OFFICIAL STEAM CHARTS × STEAMUNLOCK WANNABE"
    badge_catalog = "REAL-TIME CATALOG ARCHIVE • HOURLY UPDATED"

    # Paste Official Steam Unlock ONENNABE App Icon in Header
    suo_ico_70 = load_suo_icon((70, 70))
    if suo_ico_70:
        draw.rounded_rectangle([58, 30, 58 + 74, 104], radius=12, fill=(18, 23, 32, 255), outline=(48, 54, 61, 230), width=1)
        img.paste(suo_ico_70, (60, 32), suo_ico_70)
        rx = W - 58 - 74
        draw.rounded_rectangle([rx, 30, rx + 74, 104], radius=12, fill=(18, 23, 32, 255), outline=(48, 54, 61, 230), width=1)
        img.paste(suo_ico_70, (rx + 2, 32), suo_ico_70)

    bbox_b1 = draw.textbbox((0, 0), badge_steam, font=font_badge)
    b1_w = bbox_b1[2] - bbox_b1[0] + 28
    bbox_b2 = draw.textbbox((0, 0), badge_catalog, font=font_badge)
    b2_w = bbox_b2[2] - bbox_b2[0] + 46
    gap_badges = 16
    total_badges_w = b1_w + gap_badges + b2_w
    start_bx = (W - total_badges_w) // 2

    # Draw Badge 1 (Steam / Gold)
    draw.rounded_rectangle([start_bx, 20, start_bx + b1_w, 48], radius=14, fill=(30, 41, 59, 255), outline=(245, 158, 11, 220), width=1)
    draw.text((start_bx + 14, 26), badge_steam, font=font_badge, fill=(245, 158, 11, 255))

    # Draw Badge 2 (Live / Cyan)
    bx2 = start_bx + b1_w + gap_badges
    draw.rounded_rectangle([bx2, 20, bx2 + b2_w, 48], radius=14, fill=(15, 23, 42, 255), outline=(56, 189, 248, 230), width=1)
    draw_vector_icon(draw, "lightning", bx2 + 14, 28, (56, 189, 248), size=12)
    draw.text((bx2 + 32, 26), badge_catalog, font=font_badge, fill=(56, 189, 248, 255))

    # Main Title
    title_text = "TOP 10 STEAM HITS (AVAILABLE FOR DOWNLOAD)"
    t_bbox = draw.textbbox((0, 0), title_text, font=font_title)
    draw.text(((W - (t_bbox[2] - t_bbox[0])) // 2, 56), title_text, font=font_title, fill=(255, 255, 255, 255))

    # Subtitle
    sub_text = f"REAL-TIME CATALOG CROSS REFERENCE • UPDATED: {date_str} • HTTPS://STEAMUNLOCKONENNABE.CLICK"
    s_bbox = draw.textbbox((0, 0), sub_text, font=font_sub)
    draw.text(((W - (s_bbox[2] - s_bbox[0])) // 2, 98), sub_text, font=font_sub, fill=(148, 163, 184, 255))

    # --- MINI TABLE (4-Column Platform Statistics HUD) ---
    table_x = 60
    table_y = 126
    table_w = 1480
    gap = 16
    col_w = (table_w - (3 * gap)) // 4
    col_h = 66

    stat_cards = [
        ("catalog", "TOTAL GAMES IN CATALOG", f"{total_suo_count:,} GAMES", (52, 211, 153), (16, 185, 129, 220)),
        ("storage", "TOTAL STORAGE SIZE", f"{total_tb:,.2f} TB (~{int(total_gb):,} GB)", (251, 191, 36), (245, 158, 11, 220)),
        ("network", "ONLINE MULTIPLAYER READY", f"{online_count:,} GAMES READY", (56, 189, 248), (14, 165, 233, 220)),
        ("lightning", "BYPASS / HYPERVISOR", f"{bypass_count:,} TITLES SUPPORTED", (192, 132, 252), (168, 85, 247, 220)),
    ]

    for idx_c, (icon_type, lbl, val, val_col, border_col) in enumerate(stat_cards):
        cx = table_x + idx_c * (col_w + gap)
        draw.rounded_rectangle(
            [cx, table_y, cx + col_w, table_y + col_h],
            radius=10,
            fill=(18, 23, 32, 255),
            outline=border_col,
            width=1
        )
        draw.rounded_rectangle([cx + 3, table_y + 10, cx + 7, table_y + col_h - 10], radius=2, fill=val_col)
        draw_vector_icon(draw, icon_type, cx + 16, table_y + 13, val_col, size=13)
        draw.text((cx + 35, table_y + 12), lbl, font=font_stat_lbl, fill=(148, 163, 184, 255))
        draw.text((cx + 16, table_y + 34), val, font=font_stat_val, fill=val_col)

    # Top separator
    draw.line([(40, 208), (W - 40, 208)], fill=(30, 41, 59, 220), width=1)

    # Card Grid: 2 Columns × 5 Rows
    cols = 2
    rows = 5
    card_w = 720
    card_h = 160
    start_x = 60
    start_y = 222
    gap_x = 40
    gap_y = 16

    for idx, g in enumerate(games[:10]):
        c = idx // rows
        r = idx % rows
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

        # Rank badge
        rank_num = idx + 1
        if rank_num == 1:
            rank_bg = (245, 158, 11)   # Gold
            rank_fg = (255, 255, 255)
        elif rank_num == 2:
            rank_bg = (148, 163, 184)  # Silver
            rank_fg = (255, 255, 255)
        elif rank_num == 3:
            rank_bg = (180, 83, 9)     # Bronze
            rank_fg = (255, 255, 255)
        else:
            rank_bg = (30, 41, 59)     # Slate / Cyan
            rank_fg = (0, 180, 216)

        draw.rounded_rectangle([cx + 12, cy + 12, cx + 58, cy + card_h - 12], radius=8, fill=rank_bg)
        r_str = f"#{rank_num}"
        r_bbox = draw.textbbox((0, 0), r_str, font=font_rank)
        rx = cx + 12 + (46 - (r_bbox[2] - r_bbox[0])) // 2
        ry = cy + (card_h - (r_bbox[3] - r_bbox[1])) // 2
        draw.text((rx, ry), r_str, font=font_rank, fill=rank_fg)

        # Game Header Image
        img_w = 240
        img_h = 136
        img_x = cx + 70
        img_y = cy + 12
        if g.get("img_url"):
            try:
                req = urllib.request.Request(g["img_url"], headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=6) as resp:
                    raw_data = resp.read()
                cap_img = Image.open(io.BytesIO(raw_data)).convert("RGBA")
                cap_img = cap_img.resize((img_w, img_h), Image.Resampling.LANCZOS)

                mask = Image.new("L", (img_w, img_h), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.rounded_rectangle([0, 0, img_w, img_h], radius=8, fill=255)
                img.paste(cap_img, (img_x, img_y), mask)
            except Exception:
                draw.rounded_rectangle([img_x, img_y, img_x + img_w, img_y + img_h], radius=8, fill=(33, 38, 45, 255))
        else:
            draw.rounded_rectangle([img_x, img_y, img_x + img_w, img_y + img_h], radius=8, fill=(33, 38, 45, 255))

        # Title & Info
        info_x = img_x + img_w + 16
        g_name = g.get("name", "Unknown Game")
        if len(g_name) > 26:
            g_name = g_name[:25] + "…"
        draw.text((info_x, cy + 16), g_name, font=font_card_title, fill=(240, 246, 252, 255))

        # Rank Movement Pill (UP / DOWN / STILL / NEW)
        rank_str = g.get("rank_str", "▬ STILL")
        trend = g.get("rank_trend", "STILL")

        if trend == "NEW":
            p_fill = (245, 158, 11, 40)
            p_outline = (245, 158, 11, 230)
            p_fg = (251, 191, 36, 255)
            txt_bbox = draw.textbbox((0, 0), "NEW", font=font_pill)
            p_w = 20 + (txt_bbox[2] - txt_bbox[0]) + 10
            p_h = 22
            px = cx + card_w - p_w - 14
            py = cy + 14
            draw.rounded_rectangle([px, py, px + p_w, py + p_h], radius=6, fill=p_fill, outline=p_outline, width=1)
            draw_vector_icon(draw, "star", px + 8, py + 5, p_fg, size=11)
            draw.text((px + 22, py + 4), "NEW", font=font_pill, fill=p_fg)
        else:
            if trend == "UP":
                p_fill = (16, 185, 129, 40)
                p_outline = (16, 185, 129, 230)
                p_fg = (52, 211, 153, 255)
            elif trend == "DOWN":
                p_fill = (239, 68, 68, 40)
                p_outline = (239, 68, 68, 230)
                p_fg = (248, 113, 113, 255)
            else:  # STILL
                p_fill = (30, 41, 59, 180)
                p_outline = (71, 85, 105, 200)
                p_fg = (148, 163, 184, 255)

            p_bbox = draw.textbbox((0, 0), rank_str, font=font_pill)
            p_w = p_bbox[2] - p_bbox[0] + 16
            p_h = 22
            px = cx + card_w - p_w - 14
            py = cy + 14
            draw.rounded_rectangle([px, py, px + p_w, py + p_h], radius=6, fill=p_fill, outline=p_outline, width=1)
            draw.text((px + 8, py + 4), rank_str, font=font_pill, fill=p_fg)

        # Steam Popularity Subtitle
        if g.get("concurrent", 0) > 0:
            draw_vector_icon(draw, "players", info_x, cy + 47, (139, 148, 158), size=12)
            draw.text((info_x + 18, cy + 44), f"{g['concurrent']:,} Playing on Steam", font=font_card_sub, fill=(139, 148, 158, 255))
        else:
            draw_vector_icon(draw, "lightning", info_x, cy + 47, (139, 148, 158), size=11)
            draw.text((info_x + 16, cy + 44), f"Steam Top Seller #{g.get('steam_rank', 'Top')}", font=font_card_sub, fill=(139, 148, 158, 255))

        # Badges row
        badge_y = cy + 76
        # 1. Size Badge
        size_val = str(g.get("size_gb", "N/A"))
        s_bbox = draw.textbbox((0, 0), size_val, font=font_pill)
        sb_w = 24 + (s_bbox[2] - s_bbox[0]) + 10
        draw.rounded_rectangle([info_x, badge_y, info_x + sb_w, badge_y + 22], radius=6, fill=(30, 41, 59, 255))
        draw_vector_icon(draw, "box", info_x + 8, badge_y + 5, (226, 232, 240), size=11)
        draw.text((info_x + 24, badge_y + 4), size_val, font=font_pill, fill=(226, 232, 240, 255))

        # 2. Online Badge
        is_online = str(g.get("online_supported", "")).lower() == "yes"
        if is_online:
            on_txt = "ONLINE READY"
            on_col = (16, 185, 129)
            ob_bbox = draw.textbbox((0, 0), on_txt, font=font_pill)
            ob_w = 24 + (ob_bbox[2] - ob_bbox[0]) + 10
            ob_x = info_x + sb_w + 8
            draw.rounded_rectangle([ob_x, badge_y, ob_x + ob_w, badge_y + 22], radius=6, fill=(15, 23, 42, 255), outline=on_col, width=1)
            draw_vector_icon(draw, "network", ob_x + 8, badge_y + 5, on_col, size=11)
            draw.text((ob_x + 24, badge_y + 4), on_txt, font=font_pill, fill=on_col)
        else:
            on_txt = "OFFLINE ONLY"
            on_col = (100, 116, 139)
            ob_bbox = draw.textbbox((0, 0), on_txt, font=font_pill)
            ob_w = 12 + (ob_bbox[2] - ob_bbox[0]) + 12
            ob_x = info_x + sb_w + 8
            draw.rounded_rectangle([ob_x, badge_y, ob_x + ob_w, badge_y + 22], radius=6, fill=(15, 23, 42, 255), outline=on_col, width=1)
            draw.text((ob_x + 10, badge_y + 4), on_txt, font=font_pill, fill=on_col)

        # 3. Downloads / Status text
        draw_vector_icon(draw, "download", info_x, cy + 120, (56, 189, 248), size=12)
        draw.text((info_x + 18, cy + 118), f"{g.get('downloads', 0):,} Downloads", font=font_pill, fill=(56, 189, 248, 255))

        # SUO direct link label
        draw.text((cx + card_w - 110, cy + 118), "AVAILABLE >", font=font_pill, fill=(16, 185, 129, 255))

    # Bottom Footer
    draw.line([(40, H - 36), (W - 40, H - 36)], fill=(30, 41, 59, 220), width=1)
    suo_ico_sm = load_suo_icon((20, 20))
    if suo_ico_sm:
        img.paste(suo_ico_sm, (40, H - 28), suo_ico_sm)
        draw.text((68, H - 24), f"STEAM UNLOCK ONENNABE • TOTAL CATALOG: {total_suo_count:,} GAMES ({total_tb} TB) • STEAM CHARTS RADAR", font=font_footer, fill=(100, 116, 139, 255))
    else:
        draw.text((40, H - 24), f"AUTOMATED BY RELEASE MONITOR BOT • TOTAL CATALOG: {total_suo_count:,} GAMES ({total_tb} TB) • STEAM CHARTS & PRE-INSTALLED RADAR", font=font_footer, fill=(100, 116, 139, 255))
    draw.text((W - 380, H - 24), "GMT+8 KUALA LUMPUR TIME • VERIFIED STEAM DATA", font=font_footer, fill=(100, 116, 139, 255))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "PNG")
    logger.info(f"Steam Top 10 SUO poster saved to: {output_path}")
    return output_path


def check_steam_top10_radar(state: dict, force: bool = False, **kwargs) -> Optional[Dict[str, Any]]:
    """
    Checks if the hourly Steam Top 10 SUO Radar needs to be posted.
    Strictly aligns with the clock hours: triggers at the nearest top-of-the-hour (e.g., 4:00 AM, 5:00 AM, etc.).
    If the bot is started mid-hour (e.g. 3:38 AM), it arms and waits for 4:00 AM unless force=True.
    """
    now_kl = datetime.now(KL_TZ)
    hour_key = now_kl.strftime("%Y-%m-%d-%H")

    radar_state = state.setdefault("steam_top10_radar", {})
    last_posted_hour = radar_state.get("last_posted_hour")

    if not force:
        # If this is the initial boot/run and last_posted_hour is unset,
        # arm for the next upcoming top-of-the-hour (e.g., 4:00 AM).
        if last_posted_hour is None:
            radar_state["last_posted_hour"] = hour_key
            next_hour = (now_kl + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            logger.info(
                f"Hourly Top 10 SUO Radar armed! Current time: {now_kl.strftime('%I:%M %p')}. "
                f"Next automated post will trigger at the nearest hour: {next_hour.strftime('%I:00 %p')} GMT+8."
            )
            return None

        # Already posted for this hour window
        if last_posted_hour == hour_key:
            return None

    logger.info(
        f"⏰ Triggering Hourly Steam Top 10 SUO Radar for {hour_key} (KL Time: {now_kl.strftime('%I:%M %p')})..."
    )

    games, suo_stats = fetch_top10_suo_games()
    if not games:
        logger.warning("No Steam Top 10 games matched with SUO catalog.")
        return None

    # Calculate ranking movement (UP / DOWN / STILL / NEW)
    previous_ranks = radar_state.get("previous_ranks") or {}
    for idx, g in enumerate(games[:10]):
        aid = g["appid"]
        curr_rank = idx + 1
        prev_rank = previous_ranks.get(aid)

        if not previous_ranks:
            # First initialization
            g["rank_trend"] = "STILL"
            g["rank_delta"] = 0
            g["rank_str"] = "▬ STILL"
            g["rank_discord"] = "▬ STILL"
        elif prev_rank is None:
            g["rank_trend"] = "NEW"
            g["rank_delta"] = 0
            g["rank_str"] = "NEW"
            g["rank_discord"] = "✨ NEW"
        elif prev_rank > curr_rank:
            diff = prev_rank - curr_rank
            g["rank_trend"] = "UP"
            g["rank_delta"] = diff
            g["rank_str"] = f"▲ +{diff}"
            g["rank_discord"] = f"🔼 +{diff}"
        elif prev_rank < curr_rank:
            diff = curr_rank - prev_rank
            g["rank_trend"] = "DOWN"
            g["rank_delta"] = diff
            g["rank_str"] = f"▼ -{diff}"
            g["rank_discord"] = f"🔽 -{diff}"
        else:
            g["rank_trend"] = "STILL"
            g["rank_delta"] = 0
            g["rank_str"] = "▬ STILL"
            g["rank_discord"] = "▬ STILL"

    poster_filename = f"steam_top10_{hour_key}.png"
    assets_dir = os.path.join(os.path.dirname(__file__), "assets", "steam_top10")
    poster_path = os.path.join(assets_dir, poster_filename)

    render_steam_top10_poster(games, poster_path, suo_stats=suo_stats)

    # Save hourly state & current ranks for the next comparison
    radar_state["previous_ranks"] = {g["appid"]: idx + 1 for idx, g in enumerate(games[:10])}
    radar_state["last_posted_hour"] = hour_key
    radar_state["last_posted_date"] = now_kl.strftime("%Y-%m-%d")

    return {
        "date_key": hour_key,
        "date_display": now_kl.strftime("%A, %b %d, %Y — %I:00 %p GMT+8"),
        "games": games,
        "total_suo_count": suo_stats.get("total_games", 32975),
        "suo_stats": suo_stats,
        "poster_path": poster_path
    }


def create_steam_top10_radar_embed(data: Dict[str, Any]):
    """
    Builds a Discord Embed for the Steam Top 10 SUO Radar post.
    Guarantees every field value is safely <= 850 characters (well under Discord's 1024 limit).
    """
    import discord
    date_display = data.get("date_display", "")
    games = data.get("games", [])
    suo_stats = data.get("suo_stats") or {}
    total_count = suo_stats.get("total_games", data.get("total_suo_count", 32975))
    total_tb = suo_stats.get("total_tb", 187.65)
    total_gb = suo_stats.get("total_gb", 192153.0)
    online_count = suo_stats.get("online_count", 407)
    bypass_count = suo_stats.get("bypass_count", 208)

    embed = discord.Embed(
        title=f"🏆 Steam Top 10 Downloads — Available on SteamUnlock Wannabe",
        description=(
            f"Here are the top trending games on Steam right now that are verified available for "
            f"instant pre-installed download on **[SteamUnlock Wannabe](https://steamunlockonennabe.click/)**!\n"
            f"📅 *Live Update: {date_display} (GMT+8)*"
        ),
        color=0xF59E0B  # Cyber Gold
    )

    # Mini Table: Platform Catalog & Archive Health HUD
    hud_table = (
        "```yaml\n"
        f"📚 Total Games in Catalog : {total_count:,} Games\n"
        f"💾 Total Storage Size     : {total_tb:,.2f} Terabytes (~{int(total_gb):,} GB)\n"
        f"🌐 Online Ready Titles    : {online_count:,} Games Supported\n"
        f"⚡ Bypass / Hypervisor    : {bypass_count:,} Games Supported\n"
        "```"
    )
    embed.add_field(
        name="📊 Platform Archive Statistics",
        value=hud_table,
        inline=False
    )

    embed.set_footer(
        text=f"Official Steam Charts × SteamUnlock Wannabe • {total_count:,}+ Games in Catalog • GMT+8",
        icon_url="https://raw.githubusercontent.com/mirzaarsyad74-cmyk/hv-bypass-tool/main/assets/icons/steam_deals_icon.png"
    )

    return embed
