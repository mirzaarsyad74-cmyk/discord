"""
Dry-run test script to verify CS.RIN.RU thread scraping and release filtering
without needing live Discord credentials.
"""
import sys
import logging
from scraper import CsRinScraper
from release_filter import classify_release
from discord_poster import create_post_embed, create_op_update_embed

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

def test_dry_run():
    topic_url = "https://cs.rin.ru/forum/viewtopic.php?f=10&t=146233&start=60"
    print("\n" + "=" * 65)
    print("🚀 RUNNING REPACK / BYPASS / CRACK FILTER TEST")
    print(f"Target URL: {topic_url}")
    print("=" * 65)

    scraper = CsRinScraper()
    topic_id = scraper.extract_topic_id(topic_url)

    print("\n1. Fetching topic metadata and OP post...")
    meta = scraper.get_topic_metadata(topic_id)
    print(f"   ✓ Title: {meta.title}")
    print(f"   ✓ Latest Page Start: {meta.max_start}")

    print(f"\n2. Fetching posts from page {meta.max_start}...")
    posts = scraper.get_posts_page(topic_id, start=meta.max_start, topic_title=meta.title)
    print(f"   ✓ Total posts on page: {len(posts)}")

    print("\n3. Testing Release Filter (Releases/Repacks/Bypasses ONLY):")
    releases_found = 0
    chatter_skipped = 0

    for idx, p in enumerate(posts, 1):
        is_rel, label = classify_release(p)
        print(f"\n   --- Post #{idx} (ID: {p.post_id}) by {p.author} ---")
        if is_rel:
            releases_found += 1
            print(f"   🎯 STATUS: [POSTED TO DISCORD] -> Detected Release: {label}")
            embed = create_post_embed(p, release_label=label)
            print(f"   Embed Title: {embed.title}")
            print(f"   Preview: {p.clean_markdown[:110]}...")
        else:
            chatter_skipped += 1
            print("   🚫 STATUS: [SKIPPED] -> Casual Discussion / Chatter")
            print(f"   Preview: {p.clean_markdown[:80]}...")

    print("\n" + "=" * 65)
    print(f"📊 SUMMARY: {releases_found} Release(s) kept | {chatter_skipped} Chatter/Questions filtered out")
    print("✅ Only actual releases, repacks, bypasses, & cracks will be posted!")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    test_dry_run()
