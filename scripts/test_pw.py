import requests

for pw in ["admin", "admin74", "secret123"]:
    r = requests.post("https://increasing-saree-yuno74-2b5073cf.koyeb.app/api/login", data={"password": pw}, allow_redirects=False)
    print(f"Password '{pw}':", r.status_code, "Location:", r.headers.get("Location"))

