import os
import sys
import requests
import json
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import external_monitors

def test_selection():
    # 1. Fetch Steam Charts
    url_charts = "https://api.steampowered.com/ISteamChartsService/GetGamesByConcurrentPlayers/v1/"
    r_charts = requests.get(url_charts, timeout=6).json()
    steam_ranks = {
        str(g["appid"]): {"rank": g["rank"], "concurrent": g.get("concurrent_in_game", 0)}
        for g in r_charts.get("response", {}).get("ranks", [])
    }

    # 2. Fetch SUO
    suo_items = external_monitors.fetch_suo_catalog(limit=0)
    suo_map = {str(g["appid"]): g for g in suo_items}

    cadences = ["hourly", "daily", "weekly", "monthly"]
    for cad in cadences:
        if cad == "hourly":
            # Real-time Steam concurrent charts cross-referenced with SUO
            candidates = []
            for aid, info in sorted(steam_ranks.items(), key=lambda x: x[1]["rank"]):
                if aid in suo_map:
                    candidates.append(suo_map[aid])
                if len(candidates) >= 10:
                    break
        elif cad == "daily":
            # Trending recent releases on SUO
            candidates = sorted(
                [g for g in suo_items if g.get("downloads", 0) > 0 and g.get("added_on")],
                key=lambda x: (x.get("added_on", "")[:10], int(x.get("downloads", 0))),
                reverse=True
            )[:10]
        elif cad == "weekly":
            # Top Online Multiplayer & Co-op Hits on SUO
            online_items = [g for g in suo_items if str(g.get("online_supported", "")).lower() == "yes"]
            candidates = sorted(online_items, key=lambda x: int(x.get("downloads", 0)), reverse=True)[:10]
        elif cad == "monthly":
            # All-Time Hall of Fame Downloads
            candidates = sorted(suo_items, key=lambda x: int(x.get("downloads", 0)), reverse=True)[:10]

        print(f"\n=== {cad.upper()} TOP 10 ===")
        for idx, c in enumerate(candidates):
            conc = steam_ranks.get(str(c["appid"]), {}).get("concurrent", 0)
            print(f"#{idx+1} {c.get('name')} | AppID: {c.get('appid')} | DLs: {c.get('downloads')} | Online: {c.get('online_supported')} | Steam Players: {conc:,}")

if __name__ == "__main__":
    test_selection()
