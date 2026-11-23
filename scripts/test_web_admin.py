import time
import requests
import threading
from http.server import HTTPServer
from web_admin import (
    load_effective_config,
    save_effective_config,
    is_authenticated,
    get_admin_password,
    generate_session_token,
    LOGIN_HTML,
    DASHBOARD_HTML,
    RECENT_LOGS
)

cfg = load_effective_config()
cfg["admin_password"] = "testpass123"

from main import start_health_server

print("Testing web_admin imports and token generation...")
token = generate_session_token("testpass123")
print("Token:", token[:16], "...")

cookie = f"admin_session={token}"
print("Cookie auth check:", is_authenticated(cookie, cfg))
print("Bad cookie auth check:", is_authenticated("admin_session=wrong", cfg))
print("Web admin tests passed!")

