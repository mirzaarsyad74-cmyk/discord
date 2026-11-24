import os
import io
import re
import json
import logging
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
import requests
from PIL import Image, ImageDraw, ImageFont

import external_monitors

logger = logging.getLogger("steam_top10_radar")

KL_TZ = timezone(timedelta(hours=8))

# Global MongoDB Client cache
_mongo_snapshots_client = None


def get_mongo_snapshots_collection(collection_name: str = "suo_top10_snapshots"):
    """
    Connects to MongoDB Atlas and returns the snapshots collection for persistent historical tracking.
    """
    global _mongo_snapshots_client
    uri = os.getenv("MONGODB_URI", "").strip() or os.getenv("MONGO_URL", "").strip()
    if not uri:
        cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    uri = json.load(f).get("mongodb_uri", "").strip()
            except Exception:
                pass
    if not uri:
        return None
    try:
        from pymongo import MongoClient
        if _mongo_snapshots_client is None:
            _mongo_snapshots_client = MongoClient(uri, serverSelectionTimeoutMS=4000)
        db = _mongo_snapshots_client["game_release_monitor"]
        return db[collection_name]
    except Exception as e:
        logger.debug(f"MongoDB connection error in steam_top10_radar: {e}")
        return None


def save_suo_snapshot(cadence: str, period_key: str, games: List[Dict[str, Any]], suo_stats: Dict[str, Any]) -> bool:
    """
    Persists a historical snapshot of SUO Top 10 game downloads to MongoDB Atlas.
    """
    col = get_mongo_snapshots_collection("suo_top10_snapshots")
    if col is None:
        return False
    try:
        snapshot_doc = {
            "cadence": cadence,
            "period_key": period_key,
            "updated_at": datetime.now(timezone.utc),
            "kl_time_str": datetime.now(KL_TZ).strftime("%Y-%m-%d %I:%M %p GMT+8"),
            "games": [
                {
                    "appid": g["appid"],
                    "name": g["name"],
                    "rank": idx + 1,
                    "downloads": g.get("downloads", 0),
                    "size_gb": g.get("size_gb", "N/A"),
                    "concurrent": g.get("concurrent", 0)
                }
                for idx, g in enumerate(games[:10])
            ],
            "suo_stats": suo_stats
        }
        col.update_one(
            {"cadence": cadence, "period_key": period_key},
            {"$set": snapshot_doc},
            upsert=True
        )
        logger.info(f"🍃 Saved SUO Top 10 snapshot for cadence '{cadence}' ({period_key}) into MongoDB Atlas!")
        return True
    except Exception as e:
        logger.warning(f"Could not persist snapshot to MongoDB Atlas: {e}")
        return False


def load_previous_suo_snapshot(cadence: str, current_period_key: str, state: dict) -> Dict[str, Dict[str, Any]]:
    """
    Retrieves the previous period's baseline snapshot (from MongoDB Atlas or state fallback)
    to calculate delta downloads and ranking shifts (UP/DOWN/STILL/NEW).
    Returns mapping: {appid: {"rank": int, "downloads": int}}.
    """
    # 1. Primary: MongoDB Atlas
    col = get_mongo_snapshots_collection("suo_top10_snapshots")
    if col is not None:
        try:
            doc = col.find_one(
                {"cadence": cadence, "period_key": {"$ne": current_period_key}},
                sort=[("updated_at", -1)]
            )
            if doc and "games" in doc and isinstance(doc["games"], list):
                res = {str(g["appid"]): {"rank": g.get("rank", idx + 1), "downloads": int(g.get("downloads", 0))} for idx, g in enumerate(doc["games"])}
                logger.info(f"🍃 Loaded previous '{cadence}' baseline snapshot from MongoDB Atlas ({doc.get('period_key')}).")
                return res
        except Exception as e:
            logger.debug(f"Could not load previous snapshot from MongoDB Atlas: {e}")

    # 2. Local State Fallback
    cadence_state = state.setdefault("suo_top10_cadences", {}).setdefault(cadence, {})
    prev_ranks = cadence_state.get("previous_ranks") or {}
    prev_downloads = cadence_state.get("previous_downloads") or {}
    res = {}
    for aid, r in prev_ranks.items():
        res[str(aid)] = {
            "rank": r,
            "downloads": prev_downloads.get(str(aid), 0)
        }
    return res


# Cadence configuration and visual theming metadata
CADENCES = {
    "hourly": {
        "name": "Hourly Radar",
        "title": "TOP 10 STEAM HITS (HOURLY DOWNLOAD RADAR)",
        "badge_steam": "OFFICIAL STEAM CHARTS × STEAMUNLOCK WANNABE",
        "badge_cadence": "REAL-TIME CATALOG ARCHIVE • HOURLY UPDATED",
        "period_label": "this hour",
        "accent_color": (56, 189, 248),      # Electric Cyan
        "glow_color": (0, 180, 216, 25),
        "embed_color": 0x38BDF8,
        "filename_prefix": "steam_top10_hourly",
        "discord_title": "🏆 Steam Top 10 Downloads — Hourly Radar"
    },
    "daily": {
        "name": "Daily Recap",
        "title": "TOP 10 STEAM HITS (DAILY 24-HOUR RECAP)",
        "badge_steam": "DAILY STEAM CHARTS × STEAMUNLOCK WANNABE",
        "badge_cadence": "24-HOUR CATALOG RECAP • DAILY 12:00 AM GMT+8",
        "period_label": "today",
        "accent_color": (16, 185, 129),      # Emerald Green
        "glow_color": (16, 185, 129, 25),
        "embed_color": 0x10B981,
        "filename_prefix": "steam_top10_daily",
        "discord_title": "🌅 Steam Top 10 Downloads — Daily 24-Hour Recap"
    },
    "weekly": {
        "name": "Weekly Chart",
        "title": "TOP 10 STEAM HITS (OFFICIAL WEEKLY CHART)",
        "badge_steam": "WEEKLY STEAM CHARTS × STEAMUNLOCK WANNABE",
        "badge_cadence": "7-DAY TOP DOWNLOAD CHART • WEEKLY MONDAY 12:00 AM",
        "period_label": "this week",
        "accent_color": (139, 92, 246),     # Royal Violet
        "glow_color": (139, 92, 246, 25),
        "embed_color": 0x8B5CF6,
        "filename_prefix": "steam_top10_weekly",
        "discord_title": "📅 Steam Top 10 Downloads — Weekly Monday Chart"
    },
    "monthly": {
        "name": "Monthly Hall of Fame",
        "title": "TOP 10 STEAM HITS (MONTHLY HALL OF FAME)",
        "badge_steam": "MONTHLY STEAM CHARTS × STEAMUNLOCK WANNABE",
        "badge_cadence": "MONTHLY CATALOG HALL OF FAME • 30-DAY RECAP",
        "period_label": "this month",
        "accent_color": (245, 158, 11),      # Cyber Gold
        "glow_color": (245, 158, 11, 25),
        "embed_color": 0xF59E0B,
        "filename_prefix": "steam_top10_monthly",
        "discord_title": "👑 Steam Top 10 Downloads — Monthly Hall of Fame"
    }
}


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
        draw.rounded_rectangle([x, y + 8*s, x + 12*s, y + 11*s], radius=1, fill=color)
        draw.rounded_rectangle([x + 1*s, y + 4*s, x + 13*s, y + 7*s], radius=1, fill=color)
        draw.rounded_rectangle([x + 2*s, y, x + 12*s, y + 3*s], radius=1, fill=color)
    elif icon_type == "storage":
        draw.rounded_rectangle([x, y + 1*s, x + 13*s, y + 11*s], radius=2, outline=color, width=1)
        draw.line([(x + 2*s, y + 4*s), (x + 8*s, y + 4*s)], fill=color, width=1)
        draw.ellipse([x + 9*s, y + 7*s, x + 11*s, y + 9*s], fill=color)
    elif icon_type == "network":
        draw.ellipse([x, y, x + 12*s, y + 12*s], outline=color, width=1)
        draw.ellipse([x + 3*s, y, x + 9*s, y + 12*s], outline=color, width=1)
        draw.line([(x, y + 6*s), (x + 12*s, y + 6*s)], fill=color, width=1)
    elif icon_type == "lightning":
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
        draw.ellipse([x + 2*s, y + 1*s, x + 6.5*s, y + 5.5*s], fill=color)
        draw.pieslice([x, y + 6*s, x + 8.5*s, y + 14*s], 180, 360, fill=color)
        draw.ellipse([x + 7*s, y, x + 11*s, y + 4*s], fill=color)
        draw.pieslice([x + 5*s, y + 5*s, x + 13*s, y + 13*s], 180, 360, fill=color)
    elif icon_type == "box":
        draw.rounded_rectangle([x, y + 1*s, x + 11*s, y + 11*s], radius=1, outline=color, width=1)
        draw.line([(x, y + 4*s), (x + 11*s, y + 4*s)], fill=color, width=1)
        draw.line([(x + 5.5*s, y + 4*s), (x + 5.5*s, y + 11*s)], fill=color, width=1)
    elif icon_type == "download":
        draw.line([(x + 5.5*s, y), (x + 5.5*s, y + 7*s)], fill=color, width=2)
        draw.polygon([(x + 2.5*s, y + 6*s), (x + 8.5*s, y + 6*s), (x + 5.5*s, y + 9.5*s)], fill=color)
        draw.line([(x + 1*s, y + 8*s), (x + 1*s, y + 11*s), (x + 10*s, y + 11*s), (x + 10*s, y + 8*s)], fill=color, width=1)
    elif icon_type == "star":
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
    """
    candidates = [
        r"C:\Program Files\Steam Unlock ONENNABE\static\img\steamunlock_wannabe.ico",
        r"C:\Program Files\Steam Unlock ONENNABE\unins000.exe",
        os.path.join(os.path.dirname(__file__), "assets", "icons", "discord_app_icon.png"),
        os.path.join(os.path.dirname(__file__), "assets", "suo_icon.png"),
        os.path.join("assets", "suo_icon.png")
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                if path.lower().endswith((".ico", ".png", ".jpg")):
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


def fetch_top10_suo_games(cadence: str = "hourly", previous_snapshot: Optional[Dict[str, Any]] = None):
    """
    Fetches the Top 10 games specifically tailored to the given cadence using TRUE data:
    - hourly: Live Steam Concurrent Players (Steam Charts) cross-referenced with SUO catalog.
    - daily: Top daily trending & recent launches on SUO (with 24h delta tracking).
    - weekly: Top community online multiplayer & co-op hits on SUO (with 7d delta tracking).
    - monthly: All-time heavyweight most downloaded games in SUO history (All-time Hall of Fame).
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

    suo_map = {str(g["appid"]): g for g in suo_items}

    # 1. Candidate Selection by Cadence using TRUE data
    if cadence == "hourly":
        logger.info(f"Hourly Cadence: Cross-referencing official live Steam concurrent player charts with {total_suo_count:,} SUO games...")
        top_candidates = []
        for aid, s_info in sorted(steam_ranks.items(), key=lambda x: x[1]["rank"]):
            if aid in suo_map:
                top_candidates.append(suo_map[aid])
            if len(top_candidates) >= 15:
                break
        if not top_candidates:
            top_candidates = suo_items[:15]

    elif cadence == "daily":
        logger.info("Daily Cadence: Filtering newest releases & daily trending downloads on SUO...")
        recent_candidates = [g for g in suo_items if g.get("downloads", 0) > 0 and g.get("added_on")]
        recent_candidates.sort(
            key=lambda x: (x.get("added_on", "")[:10], int(x.get("downloads", 0))),
            reverse=True
        )
        top_candidates = recent_candidates[:15] if recent_candidates else suo_items[:15]

    elif cadence == "weekly":
        logger.info("Weekly Cadence: Filtering top community online multiplayer & co-op titles on SUO...")
        online_items = [g for g in suo_items if str(g.get("online_supported", "")).lower() == "yes"]
        online_items.sort(key=lambda x: int(x.get("downloads", 0)), reverse=True)
        top_candidates = online_items[:15] if online_items else suo_items[:15]

    else:  # monthly
        logger.info("Monthly Cadence: Sorting entire catalog by all-time lifetime downloads (Hall of Fame)...")
        all_time = list(suo_items)
        all_time.sort(key=lambda x: int(x.get("downloads", 0)), reverse=True)
        top_candidates = all_time[:15]

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
            "downloads": int(item.get("downloads", 0)),
            "size_gb": item.get("size_gb", "N/A"),
            "online_supported": item.get("online_supported", "No"),
            "bypass_supported": item.get("bypass_supported", "No"),
            "img_url": header_url,
            "store_url": f"https://store.steampowered.com/app/{aid}/",
            "suo_url": "https://steamunlockonennabe.click/"
        })

    return top_matches, suo_stats


def render_steam_top10_poster(games: List[Dict[str, Any]], output_path: str, suo_stats: Optional[Any] = None, cadence: str = "hourly") -> str:
    """
    Renders a 1600x1160 high-resolution cyber infographic poster
    tailored specifically for the given cadence (Hourly, Daily, Weekly, Monthly).
    """
    cadence_info = CADENCES.get(cadence, CADENCES["hourly"])

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

    # Ambient Top Glow (Customized by cadence theme)
    accent_rgb = cadence_info["accent_color"]
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(glow)
    g_draw.ellipse([W // 2 - 500, -180, W // 2 + 500, 160], fill=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 25))
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
    badge_steam = cadence_info["badge_steam"]
    badge_catalog = cadence_info["badge_cadence"]

    # Paste Official Steam Unlock ONENNABE / Discord App Icon in Header
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

    # Draw Badge 1 (Steam / Amber or Gold)
    draw.rounded_rectangle([start_bx, 20, start_bx + b1_w, 48], radius=14, fill=(30, 41, 59, 255), outline=(245, 158, 11, 220), width=1)
    draw.text((start_bx + 14, 26), badge_steam, font=font_badge, fill=(245, 158, 11, 255))

    # Draw Badge 2 (Cadence Theme Accent)
    bx2 = start_bx + b1_w + gap_badges
    draw.rounded_rectangle([bx2, 20, bx2 + b2_w, 48], radius=14, fill=(15, 23, 42, 255), outline=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 230), width=1)
    draw_vector_icon(draw, "lightning", bx2 + 14, 28, accent_rgb, size=12)
    draw.text((bx2 + 32, 26), badge_catalog, font=font_badge, fill=accent_rgb)

    # Main Title
    title_text = cadence_info["title"]
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
            rank_bg = (30, 41, 59)     # Slate / Accent
            rank_fg = accent_rgb

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
        elif g.get("added_on"):
            draw_vector_icon(draw, "catalog", info_x, cy + 47, (139, 148, 158), size=11)
            draw.text((info_x + 16, cy + 44), f"Added on SUO: {str(g['added_on'])[:10]}", font=font_card_sub, fill=(139, 148, 158, 255))
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

        # 3. Downloads / Status text (With period delta indicator if available)
        draw_vector_icon(draw, "download", info_x, cy + 120, accent_rgb, size=12)
        dl_count = g.get('downloads', 0)
        delta_dl = g.get('delta_dl', 0)
        if delta_dl > 0:
            dl_text = f"{dl_count:,} DLs (+{delta_dl:,} {cadence_info['period_label']})"
        else:
            dl_text = f"{dl_count:,} Downloads"
        draw.text((info_x + 18, cy + 118), dl_text, font=font_pill, fill=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 255))

        # SUO direct link label
        draw.text((cx + card_w - 110, cy + 118), "AVAILABLE >", font=font_pill, fill=(16, 185, 129, 255))

    # Bottom Footer
    draw.line([(40, H - 36), (W - 40, H - 36)], fill=(30, 41, 59, 220), width=1)
    suo_ico_sm = load_suo_icon((20, 20))
    if suo_ico_sm:
        img.paste(suo_ico_sm, (40, H - 28), suo_ico_sm)
        draw.text((68, H - 24), f"STEAM UNLOCK ONENNABE • TOTAL CATALOG: {total_suo_count:,} GAMES ({total_tb} TB) • {cadence_info['name'].upper()}", font=font_footer, fill=(100, 116, 139, 255))
    else:
        draw.text((40, H - 24), f"STEAM UNLOCK ONENNABE • TOTAL CATALOG: {total_suo_count:,} GAMES ({total_tb} TB) • {cadence_info['name'].upper()}", font=font_footer, fill=(100, 116, 139, 255))
    draw.text((W - 380, H - 24), "GMT+8 KUALA LUMPUR TIME • MONGODB PERSISTED", font=font_footer, fill=(100, 116, 139, 255))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "PNG")
    logger.info(f"Steam Top 10 SUO poster ({cadence}) saved to: {output_path}")
    return output_path


def is_cadence_due(cadence: str, state: dict, now_kl: datetime, force: bool = False) -> Tuple[bool, str]:
    """
    Evaluates whether a specific cadence is due to be published.
    - hourly: top of every hour (:00)
    - daily: every day at 12:00 AM (00:00 GMT+8)
    - weekly: every Monday at 12:00 AM (00:00 GMT+8)
    - monthly: last day of month at 12:00 AM (00:00 GMT+8)
    """
    cadence_state = state.setdefault("suo_top10_cadences", {}).setdefault(cadence, {})
    last_posted_key = cadence_state.get("last_posted_key")

    if cadence == "hourly":
        period_key = now_kl.strftime("%Y-%m-%d-%H")
        if force:
            return True, period_key
        if last_posted_key is None:
            # First boot arming
            cadence_state["last_posted_key"] = period_key
            next_h = (now_kl + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            logger.info(f"Hourly Top 10 Radar armed! Next trigger at: {next_h.strftime('%I:00 %p')} GMT+8.")
            return False, period_key
        return (last_posted_key != period_key), period_key

    elif cadence == "daily":
        period_key = now_kl.strftime("%Y-%m-%d")
        if force:
            return True, period_key
        # Triggers at 12:00 AM (hour 0)
        is_due = (now_kl.hour == 0 and last_posted_key != period_key)
        return is_due, period_key

    elif cadence == "weekly":
        # Monday is weekday 0 in Python
        period_key = now_kl.strftime("%Y-W%W")
        if force:
            return True, period_key
        is_due = (now_kl.weekday() == 0 and now_kl.hour == 0 and last_posted_key != period_key)
        return is_due, period_key

    elif cadence == "monthly":
        period_key = now_kl.strftime("%Y-%m")
        if force:
            return True, period_key
        # Last day of month check: tomorrow is day 1 of next month
        tomorrow = now_kl + timedelta(days=1)
        is_last_day_of_month = (tomorrow.month != now_kl.month)
        is_due = (is_last_day_of_month and now_kl.hour == 0 and last_posted_key != period_key)
        return is_due, period_key

    return False, ""


def check_steam_top10_cadence(state: dict, cadence: str = "hourly", force: bool = False) -> Optional[Dict[str, Any]]:
    """
    Checks, calculates deltas against MongoDB baseline, and renders Steam Top 10 SUO Radar for a specific cadence.
    """
    now_kl = datetime.now(KL_TZ)
    is_due, period_key = is_cadence_due(cadence, state, now_kl, force=force)
    if not is_due:
        return None

    cadence_info = CADENCES.get(cadence, CADENCES["hourly"])
    logger.info(f"⏰ Triggering {cadence_info['name']} for period {period_key} (KL Time: {now_kl.strftime('%I:%M %p')})...")

    # Load baseline from MongoDB Atlas
    previous_snapshot = load_previous_suo_snapshot(cadence, period_key, state)

    games, suo_stats = fetch_top10_suo_games(cadence=cadence, previous_snapshot=previous_snapshot)
    if not games:
        logger.warning(f"No Steam Top 10 games matched with SUO catalog for cadence '{cadence}'.")
        return None

    # Calculate ranking movement and period download deltas
    for idx, g in enumerate(games[:10]):
        aid = str(g["appid"])
        curr_rank = idx + 1
        curr_dl = int(g.get("downloads", 0))

        prev_info = previous_snapshot.get(aid)
        if not previous_snapshot or prev_info is None:
            g["rank_trend"] = "NEW"
            g["rank_delta"] = 0
            g["rank_str"] = "NEW"
            g["delta_dl"] = 0
        else:
            prev_rank = prev_info.get("rank")
            prev_dl = prev_info.get("downloads", 0)
            g["delta_dl"] = max(0, curr_dl - prev_dl)

            if prev_rank is None:
                g["rank_trend"] = "NEW"
                g["rank_delta"] = 0
                g["rank_str"] = "NEW"
            elif prev_rank > curr_rank:
                diff = prev_rank - curr_rank
                g["rank_trend"] = "UP"
                g["rank_delta"] = diff
                g["rank_str"] = f"▲ +{diff}"
            elif prev_rank < curr_rank:
                diff = curr_rank - prev_rank
                g["rank_trend"] = "DOWN"
                g["rank_delta"] = diff
                g["rank_str"] = f"▼ -{diff}"
            else:
                g["rank_trend"] = "STILL"
                g["rank_delta"] = 0
                g["rank_str"] = "▬ STILL"

    # Poster image path
    poster_filename = f"{cadence_info['filename_prefix']}_{period_key}.png"
    assets_dir = os.path.join(os.path.dirname(__file__), "assets", "steam_top10")
    poster_path = os.path.join(assets_dir, poster_filename)

    render_steam_top10_poster(games, poster_path, suo_stats=suo_stats, cadence=cadence)

    # Persist Snapshot to MongoDB Atlas
    save_suo_snapshot(cadence, period_key, games, suo_stats)

    # Update local state cache
    cadence_state = state.setdefault("suo_top10_cadences", {}).setdefault(cadence, {})
    cadence_state["previous_ranks"] = {str(g["appid"]): idx + 1 for idx, g in enumerate(games[:10])}
    cadence_state["previous_downloads"] = {str(g["appid"]): int(g.get("downloads", 0)) for g in games[:10]}
    cadence_state["last_posted_key"] = period_key
    cadence_state["last_posted_date"] = now_kl.strftime("%Y-%m-%d")

    # Backwards-compatibility for hourly state
    if cadence == "hourly":
        state.setdefault("steam_top10_radar", {})["last_posted_hour"] = period_key
        state["steam_top10_radar"]["previous_ranks"] = cadence_state["previous_ranks"]

    return {
        "cadence": cadence,
        "cadence_name": cadence_info["name"],
        "date_key": period_key,
        "date_display": now_kl.strftime("%A, %b %d, %Y — %I:00 %p GMT+8"),
        "games": games,
        "total_suo_count": suo_stats.get("total_games", 32975),
        "suo_stats": suo_stats,
        "poster_path": poster_path
    }


def check_all_due_steam_top10_radars(state: dict, force_cadence: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Evaluates all 4 cadences (hourly, daily @ 12am, weekly @ Mon 12am, monthly @ month-end 12am)
    and returns a list of all due radars.
    """
    due_radars = []
    if force_cadence:
        res = check_steam_top10_cadence(state, cadence=force_cadence, force=True)
        if res:
            due_radars.append(res)
        return due_radars

    for cad in ["hourly", "daily", "weekly", "monthly"]:
        res = check_steam_top10_cadence(state, cadence=cad, force=False)
        if res:
            due_radars.append(res)
    return due_radars


def check_steam_top10_radar(state: dict, force: bool = False, cadence: str = "hourly", **kwargs) -> Optional[Dict[str, Any]]:
    """
    Backwards-compatible entrypoint. Checks and returns a specific cadence (defaults to hourly).
    """
    return check_steam_top10_cadence(state, cadence=cadence, force=force)


def create_steam_top10_radar_embed(data: Dict[str, Any]):
    """
    Builds a Discord Embed for the Steam Top 10 SUO Radar post tailored by cadence.
    """
    import discord
    cadence = data.get("cadence", "hourly")
    cadence_info = CADENCES.get(cadence, CADENCES["hourly"])

    date_display = data.get("date_display", "")
    suo_stats = data.get("suo_stats") or {}
    total_count = suo_stats.get("total_games", data.get("total_suo_count", 32975))
    total_tb = suo_stats.get("total_tb", 187.65)
    total_gb = suo_stats.get("total_gb", 192153.0)
    online_count = suo_stats.get("online_count", 407)
    bypass_count = suo_stats.get("bypass_count", 208)

    embed = discord.Embed(
        title=cadence_info["discord_title"],
        description=(
            f"Here are the top trending games on Steam right now verified available for "
            f"instant pre-installed download on **[SteamUnlock Wannabe](https://steamunlockonennabe.click/)**!\n"
            f"📅 *{cadence_info['name']} Update: {date_display} (GMT+8)*"
        ),
        color=cadence_info["embed_color"]
    )

    # Mini Table: Platform Catalog & Archive Health HUD
    hud_table = (
        "```yaml\n"
        f"📚 Total Games in Catalog : {total_count:,} Games\n"
        f"💾 Total Storage Size     : {total_tb:,.2f} Terabytes (~{int(total_gb):,} GB)\n"
        f"🌐 Online Ready Titles    : {online_count:,} Games Supported\n"
        f"⚡ Bypass / Hypervisor    : {bypass_count:,} Games Supported\n"
        f"🍃 MongoDB Persistence    : Live Synced Snapshot Archive\n"
        "```"
    )
    embed.add_field(
        name="📊 Platform Archive Statistics",
        value=hud_table,
        inline=False
    )

    embed.set_footer(
        text=f"{cadence_info['badge_steam']} • {total_count:,}+ Games in Catalog • GMT+8",
        icon_url="https://raw.githubusercontent.com/mirzaarsyad74-cmyk/hv-bypass-tool/main/assets/icons/steam_deals_icon.png"
    )

    return embed
