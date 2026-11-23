from datetime import datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup

KL_TZ = timezone(timedelta(hours=8))
now = datetime.now(KL_TZ)
today_pattern = f"{now.day} {now.strftime('%b')}, {now.year}"
tomorrow = now + timedelta(days=1)
tomorrow_pattern = f"{tomorrow.day} {tomorrow.strftime('%b')}, {tomorrow.year}"

print(f"Current KL Time: {now.strftime('%Y-%m-%d %H:%M:%S %z')}")
print(f"Target Today: {today_pattern}")
print(f"Target Tomorrow: {tomorrow_pattern}")

def get_items(category_id, count=100):
    url = f"https://store.steampowered.com/search/results/?filter=popularcomingsoon&category1={category_id}&cc=my&l=en&count={count}&infinite=1"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).json()
    soup = BeautifulSoup(r["results_html"], "html.parser")
    results = []
    for a in soup.select("a.search_result_row"):
        appid = a.get("data-ds-appid")
        title = a.select_one(".title").text.strip()
        date = a.select_one(".search_released").text.strip() if a.select_one(".search_released") else ""
        img = a.select_one(".search_capsule img")
        img_url = img.get("src") if img else None
        price_el = a.select_one(".discount_final_price") or a.select_one(".search_price")
        price = price_el.text.strip() if price_el else "Free / Unpriced"
        results.append({
            "appid": appid,
            "title": title,
            "date": date,
            "img_url": img_url,
            "price": price,
            "category": "Base Game" if category_id == "998" else "DLC"
        })
    return results

games = get_items("998", 100)
dlcs = get_items("21", 100)

all_items = games + dlcs
today_items = [i for i in all_items if i["date"] == today_pattern]
tomorrow_items = [i for i in all_items if i["date"] == tomorrow_pattern]

print(f"\nReleases Today ({today_pattern}): {len(today_items)}")
for i in today_items:
    print(f" - [{i['category']}] {i['title']} ({i['price']}) -> AppID {i['appid']}")

print(f"\nReleases Tomorrow ({tomorrow_pattern}): {len(tomorrow_items)}")
for i in tomorrow_items:
    print(f" - [{i['category']}] {i['title']} ({i['price']}) -> AppID {i['appid']}")
