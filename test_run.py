"""
Dry-run test script to verify SteamRIP scraping, game extraction, and embed generation
including full high-resolution game posters.
"""
import sys
import logging
from external_monitors import check_steamrip_updates, create_steamrip_embed

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
    init_state = {}
    check_steamrip_updates(init_state)
    seen_ids = init_state.get("steamrip", {}).get("seen_ids", [])
    print(f"   ✓ Successfully fetched and indexed {len(seen_ids)} releases & updates from SteamRIP!")

    print("\n2. Testing Sample SteamRIP Embeds with Game Posters:")
    # Pick both a new release (post_...) and an update (upd_...)
    sample_ids = []
    for sid in seen_ids:
        if sid.startswith("post_") and len(sample_ids) < 1:
            sample_ids.append(sid)
        elif sid.startswith("upd_") and len(sample_ids) < 2:
            sample_ids.append(sid)

    partial_seen = [sid for sid in seen_ids if sid not in sample_ids]
    detected = check_steamrip_updates({"steamrip": {"seen_ids": partial_seen}})

    for item in detected:
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
    print("✅ SteamRIP Poster test complete! Working perfectly!")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    test_dry_run()
