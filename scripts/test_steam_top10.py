import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests
import json
import external_monitors

print("1. Fetching Steam Most Played (Top 100)...")
url = "https://api.steampowered.com/ISteamChartsService/GetGamesByConcurrentPlayers/v1/"
r = requests.get(url, timeout=5)
steam_ranks = r.json().get("response", {}).get("ranks", [])
steam_dict = {str(g["appid"]): g for g in steam_ranks}
print(f"   Loaded {len(steam_dict)} Steam rank entries.")

print("2. Fetching SUO catalog...")
suo_items = external_monitors.fetch_suo_catalog(limit=600)
print(f"   Loaded {len(suo_items)} SUO catalog items.")

matched = []
for item in suo_items:
    aid = str(item.get("appid"))
    if aid in steam_dict:
        matched.append({
            "appid": aid,
            "name": item.get("name"),
            "rank": steam_dict[aid]["rank"],
            "concurrent": steam_dict[aid]["concurrent_in_game"],
            "downloads": item.get("downloads", 0),
            "size_gb": item.get("size_gb", "N/A"),
            "online_supported": item.get("online_supported", "No"),
            "bypass_supported": item.get("bypass_supported", "No"),
            "st_file": item.get("st_file", "")
        })

matched.sort(key=lambda x: x["rank"])
print(f"3. Found {len(matched)} matching games available on SUO!")
for m in matched[:10]:
    print(f" - #{m['rank']} {m['name']} (AppID: {m['appid']}) | Players: {m['concurrent']:,} | Size: {m['size_gb']} | SUO DLs: {m['downloads']}")
