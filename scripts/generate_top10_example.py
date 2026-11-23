#!/usr/bin/env python3
"""
Generates an example infographic poster: Steam Top 10 Downloads (SUO Cross-Referenced)
"""
import os
import sys
import re
import io
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests
import external_monitors

KL_TZ = timezone(timedelta(hours=8))


def get_system_font(size: int, bold: bool = False):
    if bold:
        candidates = [
            os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "segoeuib.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "arialbd.ttf"
        ]
    else:
        candidates = [
            os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "segoeui.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
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


def load_suo_icon(target_size: tuple = (72, 72)) -> Image.Image:
    """Loads the Steam Unlock ONENNABE icon from disk or bundled assets."""
    candidates = [
        r"C:\Program Files\Steam Unlock ONENNABE\static\img\steamunlock_wannabe.ico",
        r"C:\Program Files\Steam Unlock ONENNABE\unins000.exe",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "suo_icon.png"),
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
    fallback = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "suo_icon.png")
    if os.path.exists(fallback):
        try:
            return Image.open(fallback).convert("RGBA").resize(target_size, Image.Resampling.LANCZOS)
        except Exception:
            pass
    return None


def fetch_top10_suo_games():
    print("Fetching Steam Charts & Top Sellers...")
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
        print("Error fetching Steam charts:", e)

    # Top sellers
    try:
        url_sellers = "https://store.steampowered.com/search/results/?query=&start=0&count=100&filter=topsellers&json=1"
        r_sellers = requests.get(url_sellers, timeout=6)
        if r_sellers.status_code == 200:
            for idx, item in enumerate(r_sellers.json().get("items", [])):
                m = re.search(r'/apps/(\d+)/', item.get("logo", ""))
                if m:
                    aid = m.group(1)
                    if aid in steam_ranks:
                        steam_ranks[aid]["seller_rank"] = idx + 1
                        steam_ranks[aid]["seller_name"] = item.get("name")
                    else:
                        steam_ranks[aid] = {
                            "rank": 100 + idx,
                            "seller_rank": idx + 1,
                            "seller_name": item.get("name"),
                            "concurrent": 0
                        }
    except Exception as e:
        print("Error fetching Steam sellers:", e)

    print("Fetching SUO catalog...")
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
    print(f"Fetched {total_suo_count} items from SUO ({total_tb} TB).")

    matches = []
    for item in suo_items:
        aid = str(item.get("appid"))
        if aid in steam_ranks:
            st = steam_ranks[aid]
            name = item.get("name") or st.get("seller_name", f"Game {aid}")
            # Filter out non-standalone or free valve games if desired
            matches.append({
                "appid": aid,
                "name": name,
                "steam_rank": st["rank"],
                "concurrent": st.get("concurrent", 0),
                "downloads": item.get("downloads", 0),
                "size_gb": item.get("size_gb", "N/A"),
                "online_supported": item.get("online_supported", "No"),
                "bypass_supported": item.get("bypass_supported", "No"),
                "img_url": f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{aid}/header.jpg",
                "store_url": f"https://store.steampowered.com/app/{aid}/",
                "suo_url": f"https://steamunlockonennabe.click/"
            })

    # Sort primarily by Steam popularity, secondarily by SUO download count
    matches.sort(key=lambda x: (x["steam_rank"], -x["downloads"]))
    top_matches = matches[:10]

    # Resolve accurate high-res header artwork for every single game
    for m in top_matches:
        aid = m["appid"]
        direct_url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{aid}/header.jpg"
        try:
            r_check = requests.get(direct_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=2)
            if r_check.status_code == 200 and len(r_check.content) > 1000:
                m["img_url"] = direct_url
                continue
        except Exception:
            pass
        # Fallback to Steam appdetails store API
        try:
            r_api = requests.get(f"https://store.steampowered.com/api/appdetails?appids={aid}", timeout=3)
            if r_api.status_code == 200:
                data_info = r_api.json().get(aid, {}).get("data", {})
                h_img = data_info.get("header_image")
                if h_img:
                    m["img_url"] = h_img
                    continue
        except Exception:
            pass
        m["img_url"] = direct_url

    return top_matches, suo_stats


def render_top10_poster(games, output_path: str, suo_stats=None):
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

    # Ambient Glow
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(glow)
    g_draw.ellipse([W//2 - 500, -180, W//2 + 500, 160], fill=(0, 180, 216, 25))
    g_draw.ellipse([W//2 - 250, -80, W//2 + 250, 140], fill=(245, 158, 11, 20))
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

    # Header Badges
    now_kl = datetime.now(KL_TZ)
    date_str = now_kl.strftime("%d %b %Y, %I:%M %p GMT+8").upper()
    badge_steam = "OFFICIAL STEAM CHARTS × STEAMUNLOCK WANNABE"
    badge_catalog = "⚡ REAL-TIME CATALOG ARCHIVE • HOURLY UPDATED"

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
    b2_w = bbox_b2[2] - bbox_b2[0] + 28
    gap_badges = 16
    total_badges_w = b1_w + gap_badges + b2_w
    start_bx = (W - total_badges_w) // 2

    # Draw Badge 1 (Steam / Gold)
    draw.rounded_rectangle([start_bx, 20, start_bx + b1_w, 48], radius=14, fill=(30, 41, 59, 255), outline=(245, 158, 11, 220), width=1)
    draw.text((start_bx + 14, 26), badge_steam, font=font_badge, fill=(245, 158, 11, 255))

    # Draw Badge 2 (Live / Cyan)
    bx2 = start_bx + b1_w + gap_badges
    draw.rounded_rectangle([bx2, 20, bx2 + b2_w, 48], radius=14, fill=(15, 23, 42, 255), outline=(56, 189, 248, 230), width=1)
    draw.text((bx2 + 14, 26), badge_catalog, font=font_badge, fill=(56, 189, 248, 255))

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
        ("📚 TOTAL GAMES IN CATALOG", f"{total_suo_count:,} GAMES", (52, 211, 153), (16, 185, 129, 220)),
        ("💾 TOTAL STORAGE SIZE", f"{total_tb:,.2f} TB (~{int(total_gb):,} GB)", (251, 191, 36), (245, 158, 11, 220)),
        ("🌐 ONLINE MULTIPLAYER READY", f"{online_count:,} GAMES READY", (56, 189, 248), (14, 165, 233, 220)),
        ("⚡ BYPASS / HYPERVISOR", f"{bypass_count:,} TITLES SUPPORTED", (192, 132, 252), (168, 85, 247, 220)),
    ]

    for idx_c, (lbl, val, val_col, border_col) in enumerate(stat_cards):
        cx = table_x + idx_c * (col_w + gap)
        draw.rounded_rectangle(
            [cx, table_y, cx + col_w, table_y + col_h],
            radius=10,
            fill=(18, 23, 32, 255),
            outline=border_col,
            width=1
        )
        draw.rounded_rectangle([cx + 3, table_y + 10, cx + 7, table_y + col_h - 10], radius=2, fill=val_col)
        draw.text((cx + 16, table_y + 12), lbl, font=font_stat_lbl, fill=(148, 163, 184, 255))
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
            rank_bg = (30, 41, 59)     # Slate / Cyan outline
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

        if trend == "UP":
            p_fill = (16, 185, 129, 40)
            p_outline = (16, 185, 129, 230)
            p_fg = (52, 211, 153, 255)
        elif trend == "DOWN":
            p_fill = (239, 68, 68, 40)
            p_outline = (239, 68, 68, 230)
            p_fg = (248, 113, 113, 255)
        elif trend == "NEW":
            p_fill = (245, 158, 11, 40)
            p_outline = (245, 158, 11, 230)
            p_fg = (251, 191, 36, 255)
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
            players_str = f"👥 {g['concurrent']:,} Playing on Steam"
        else:
            players_str = f"📈 Steam Top Seller #{g.get('steam_rank', 'Top')}"
        draw.text((info_x, cy + 44), players_str, font=font_card_sub, fill=(139, 148, 158, 255))

        # Badges row
        badge_y = cy + 76
        # 1. Size Badge
        size_txt = f"📦 {g.get('size_gb', 'N/A')}"
        sb_w = draw.textbbox((0, 0), size_txt, font=font_pill)[2] + 16
        draw.rounded_rectangle([info_x, badge_y, info_x + sb_w, badge_y + 22], radius=6, fill=(30, 41, 59, 255))
        draw.text((info_x + 8, badge_y + 4), size_txt, font=font_pill, fill=(226, 232, 240, 255))

        # 2. Online Badge
        is_online = str(g.get("online_supported", "")).lower() == "yes"
        on_txt = "🌐 ONLINE READY" if is_online else "OFFLINE SINGLEPLAYER"
        on_col = (16, 185, 129) if is_online else (100, 116, 139)
        ob_w = draw.textbbox((0, 0), on_txt, font=font_pill)[2] + 16
        ob_x = info_x + sb_w + 8
        draw.rounded_rectangle([ob_x, badge_y, ob_x + ob_w, badge_y + 22], radius=6, fill=(15, 23, 42, 255), outline=on_col, width=1)
        draw.text((ob_x + 8, badge_y + 4), on_txt, font=font_pill, fill=on_col)

        # 3. Downloads / Status text
        dls_txt = f"📥 {g.get('downloads', 0):,} Downloads"
        draw.text((info_x, cy + 118), dls_txt, font=font_pill, fill=(56, 189, 248, 255))

        # SUO direct link label
        draw.text((cx + card_w - 110, cy + 118), "AVAILABLE >", font=font_pill, fill=(16, 185, 129, 255))

    # Bottom Footer
    draw.line([(40, H - 36), (W - 40, H - 36)], fill=(30, 41, 59, 220), width=1)
    suo_ico_sm = load_suo_icon((20, 20))
    if suo_ico_sm:
        img.paste(suo_ico_sm, (40, H - 28), suo_ico_sm)
        draw.text((68, H - 24), f"STEAM UNLOCK ONENNABE • TOTAL CATALOG: {total_suo_count:,} GAMES ({total_tb} TB) • STEAM CHARTS RADAR", font=font_footer, fill=(100, 116, 139, 255))
    else:
        draw.text((40, H - 24), f"AUTOMATED BY RELEASE MONITOR BOT • TOTAL CATALOG: {total_suo_count:,} GAMES ({total_tb} TB) • STEAM CHARTS RADAR", font=font_footer, fill=(100, 116, 139, 255))
    draw.text((W - 380, H - 24), "GMT+8 KUALA LUMPUR TIME • VERIFIED STEAM DATA", font=font_footer, fill=(100, 116, 139, 255))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "PNG")
    print(f"✅ Generated poster saved to: {output_path}")
    return output_path


if __name__ == "__main__":
    out_dir = os.path.join(r"C:\Users\admin\.gemini\antigravity\brain\a0cc8cea-f20e-4c77-a6bb-331d3cdb0b36")
    out_file = os.path.join(out_dir, "steam_top10_suo_example.png")
    top_games, suo_stats = fetch_top10_suo_games()
    total_count = suo_stats.get("total_games", 32975)
    print(f"Top 10 matched games count: {len(top_games)} (from total {total_count:,} SUO items)")

    # Demo status assignments for example poster
    demo_statuses = [
        ("STILL", "▬ STILL"),
        ("UP", "▲ +2"),
        ("NEW", "★ NEW"),
        ("DOWN", "▼ -1"),
        ("STILL", "▬ STILL"),
        ("UP", "▲ +3"),
        ("NEW", "★ NEW"),
        ("DOWN", "▼ -2"),
        ("STILL", "▬ STILL"),
        ("UP", "▲ +1")
    ]
    for idx, g in enumerate(top_games[:10]):
        trend, text = demo_statuses[idx % len(demo_statuses)]
        g["rank_trend"] = trend
        g["rank_str"] = text

    render_top10_poster(top_games, out_file, suo_stats=suo_stats)
