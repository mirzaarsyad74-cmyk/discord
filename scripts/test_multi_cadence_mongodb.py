import os
import sys
import json
from datetime import datetime, timezone, timedelta

# Add root directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from steam_top10_radar import (
    check_steam_top10_cadence,
    create_steam_top10_radar_embed,
    get_mongo_snapshots_collection,
    is_cadence_due,
    KL_TZ,
    CADENCES
)

def run_tests():
    print("=== 1. Testing MongoDB Snapshots Collection ===")
    col = get_mongo_snapshots_collection()
    assert col is not None, "MongoDB collection connection failed!"
    print(f"MongoDB connected! Snapshot docs count: {col.count_documents({})}")

    print("\n=== 2. Testing All 4 Cadences ===")
    state = {}
    for cad in ["hourly", "daily", "weekly", "monthly"]:
        print(f"Testing {cad} cadence...")
        res = check_steam_top10_cadence(state, cadence=cad, force=True)
        assert res is not None, f"{cad} failed to generate data!"
        p_path = res["poster_path"]
        assert os.path.exists(p_path), f"{cad} poster not found!"
        size = os.path.getsize(p_path)
        print(f"  [PASS] {cad.capitalize()} poster created: {p_path} ({size:,} bytes)")
        
        embed = create_steam_top10_radar_embed(res)
        assert embed.title == CADENCES[cad]["discord_title"]
        print(f"  [PASS] {cad.capitalize()} embed verified: {embed.title}")

    print("\n=== 3. Testing MongoDB Snapshot Persistence ===")
    for cad in ["hourly", "daily", "weekly", "monthly"]:
        doc = col.find_one({"cadence": cad})
        assert doc is not None, f"MongoDB missing snapshot doc for {cad}"
        print(f"  [PASS] MongoDB snapshot found for {cad}: {doc['period_key']} with {len(doc['games'])} games")

    print("\n=== 4. Testing Cadence Timing Conditions ===")
    # Test daily at 00:00 vs 14:00
    t_daily_midnight = datetime(2026, 11, 25, 0, 0, tzinfo=KL_TZ)
    t_daily_afternoon = datetime(2026, 11, 25, 14, 0, tzinfo=KL_TZ)
    due1, _ = is_cadence_due("daily", {"suo_top10_cadences": {"daily": {"last_posted_key": "2026-11-24"}}}, t_daily_midnight)
    due2, _ = is_cadence_due("daily", {"suo_top10_cadences": {"daily": {"last_posted_key": "2026-11-24"}}}, t_daily_afternoon)
    assert due1 is True and due2 is False
    print("  [PASS] Daily triggers strictly at 12:00 AM midnight (hour 0)!")

    # Test weekly at Monday 00:00 vs Tuesday 00:00
    # 2026-11-30 is Monday (weekday 0)
    t_mon_midnight = datetime(2026, 11, 30, 0, 0, tzinfo=KL_TZ)
    t_tue_midnight = datetime(2026, 12, 1, 0, 0, tzinfo=KL_TZ)
    due_w1, _ = is_cadence_due("weekly", {"suo_top10_cadences": {"weekly": {"last_posted_key": "2026-W47"}}}, t_mon_midnight)
    due_w2, _ = is_cadence_due("weekly", {"suo_top10_cadences": {"weekly": {"last_posted_key": "2026-W47"}}}, t_tue_midnight)
    assert due_w1 is True and due_w2 is False
    print("  [PASS] Weekly triggers strictly on Monday at 12:00 AM midnight!")

    # Test monthly on Nov 30 (last day of Nov) vs Nov 29
    t_nov30_midnight = datetime(2026, 11, 30, 0, 0, tzinfo=KL_TZ)
    t_nov29_midnight = datetime(2026, 11, 29, 0, 0, tzinfo=KL_TZ)
    due_m1, _ = is_cadence_due("monthly", {"suo_top10_cadences": {"monthly": {"last_posted_key": "2026-10"}}}, t_nov30_midnight)
    due_m2, _ = is_cadence_due("monthly", {"suo_top10_cadences": {"monthly": {"last_posted_key": "2026-10"}}}, t_nov29_midnight)
    assert due_m1 is True and due_m2 is False
    print("  [PASS] Monthly triggers strictly on the last day of the month at 12:00 AM midnight!")

    print("\nALL MULTI-CADENCE & MONGODB TESTS PASSED!")

if __name__ == "__main__":
    run_tests()
