import os
import sys
import time
import requests
import threading

sys.path.insert(0, ".")
os.environ["PORT"] = "8099"
os.environ["ADMIN_PASSWORD"] = "secret123"

from main import start_health_server

print("Starting background server on port 8099...")
start_health_server()
time.sleep(1.5)

base = "http://127.0.0.1:8099"

# 1. Root without auth -> redirect to /login
r1 = requests.get(base + "/", allow_redirects=False)
print("1. Root without auth:", r1.status_code, "Location:", r1.headers.get("Location"))
assert r1.status_code == 302 and r1.headers.get("Location") == "/login"

# 2. Login page -> 200
r2 = requests.get(base + "/login")
print("2. Login page status:", r2.status_code, "Contains HTML:", "<form" in r2.text)
assert r2.status_code == 200 and "<form" in r2.text

# 3. Bad login -> redirect to /login?error=1
r3 = requests.post(base + "/api/login", data={"password": "wrongpassword"}, allow_redirects=False)
print("3. Bad login redirect:", r3.status_code, "Location:", r3.headers.get("Location"))
assert r3.status_code == 302 and "error=1" in r3.headers.get("Location", "")

# 4. Good login -> sets cookie & redirect to /admin
r4 = requests.post(base + "/api/login", data={"password": "secret123"}, allow_redirects=False)
cookie = r4.headers.get("Set-Cookie", "")
print("4. Good login status:", r4.status_code, "Cookie set:", "admin_session=" in cookie)
assert r4.status_code == 302 and "admin_session=" in cookie

# 5. Access dashboard with cookie -> 200
cookie_str = cookie.split(";")[0]
r5 = requests.get(base + "/admin", headers={"Cookie": cookie_str})
print("5. Dashboard with cookie:", r5.status_code, "Contains title:", "Release Monitor Admin" in r5.text)
assert r5.status_code == 200 and "Release Monitor Admin" in r5.text

# 6. API config -> 200
r6 = requests.get(base + "/api/config", headers={"Cookie": cookie_str})
print("6. API config status:", r6.status_code, "watch_steam_deals:", r6.json().get("watch_steam_deals"))
assert r6.status_code == 200 and "watch_steam_deals" in r6.json()

# 7. Health endpoint -> 200
r7 = requests.get(base + "/health")
print("7. Health status:", r7.status_code, "Service:", r7.json().get("service"))
assert r7.status_code == 200 and r7.json().get("status") == "healthy"

print("\n🎉 ALL 7 SERVER TESTS PASSED PERFECTLY!")
os._exit(0)

