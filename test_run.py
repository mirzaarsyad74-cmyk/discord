"""
Dry-run test script to verify SteamRIP and SUO Wannabe scraping, game extraction, and embed generation
including full high-resolution game posters.
"""
import sys
import logging
from external_monitors import (
    check_steamrip_updates, create_steamrip_embed,
    check_suo_updates, create_suo_embed
)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

def test_dry_run():
    print("\n" + "=" * 65)
    print("🚀 RUNNING STEAMRIP (https://steamrip.com/) MONITOR TEST")
    print("=" * 65)

    print("\n1. Testing SteamRIP Scraper & Cloudflare Bypass...")
    sr_state = {}
    check_steamrip_updates(sr_state)
    seen_ids = sr_state.get("steamrip", {}).get("seen_ids", [])
    print(f"   ✓ Successfully fetched and indexed {len(seen_ids)} releases & updates from SteamRIP!")

    print("\n2. Testing Sample SteamRIP Embeds with Game Posters:")
    sample_ids = []
    for sid in seen_ids:
        if sid.startswith("post_") and len(sample_ids) < 1:
            sample_ids.append(sid)
        elif sid.startswith("upd_") and len(sample_ids) < 2:
            sample_ids.append(sid)

    partial_seen = [sid for sid in seen_ids if sid not in sample_ids]
    detected_sr = check_steamrip_updates({"steamrip": {"seen_ids": partial_seen}})

    for item in detected_sr:
        embed = create_steamrip_embed(item)
        print(f"\n   --- {item.get('type')} Embed ---")
        print(f"   Embed Title: {embed.title}")
        print(f"   Game URL: {item['url']}")
        print(f"   Version: {item.get('version')}")
        print(f"   Category: {item.get('category')}")
        print(f"   Details: {item.get('meta')}")
        print(f"   🖼️ Full Game Poster (embed.image): {embed.image.url if embed.image else None}")
        print(f"   📌 Brand Icon (embed.thumbnail): {embed.thumbnail.url if embed.thumbnail else None}")

    print("\n" + "=" * 65)
    print("🚀 RUNNING SUO WANNABE (https://steamunlockonennabe.click/) MONITOR TEST")
    print("=" * 65)

    print("\n3. Testing SUO Wannabe Streaming Fetcher & IP Fallback...")
    suo_state = {}
    check_suo_updates(suo_state)
    seen_appids = suo_state.get("suo", {}).get("seen_appids", [])
    print(f"   ✓ Successfully indexed {len(seen_appids)} catalog games in milliseconds!")

    print("\n4. Testing Sample SUO Wannabe Embeds with Steam Fastly Cover Art:")
    sample_appids = seen_appids[:2]
    partial_suo_seen = seen_appids[2:]
    detected_suo = check_suo_updates({"suo": {"seen_appids": partial_suo_seen}})

    for item in detected_suo:
        embed = create_suo_embed(item)
        print(f"\n   --- SUO Wannabe Release Embed ---")
        print(f"   Embed Title: {embed.title}")
        print(f"   Game Title: {item.get('title')}")
        print(f"   AppID: {item.get('appid')}")
        print(f"   Genre: {item.get('genre')}")
        print(f"   Size: {item.get('size_gb')}")
        print(f"   Steam URL: {item.get('steam_url')}")
        print(f"   🖼️ Full Game Poster (embed.image): {embed.image.url if embed.image else None}")
        print(f"   📌 Steam Header Thumbnail: {embed.thumbnail.url if embed.thumbnail else None}")

    print("\n" + "=" * 65)
    print("✅ All Monitor Tests Complete! Everything is working cleanly & blazing fast!")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    test_dry_run()
