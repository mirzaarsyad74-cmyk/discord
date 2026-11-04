import os
import json
import time
import hmac
import hashlib
import logging
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
import urllib.parse
import requests

logger = logging.getLogger("web_admin")
KL_TZ = timezone(timedelta(hours=8))

# In-memory circular buffer for live logs in the dashboard
RECENT_LOGS = deque(maxlen=100)


class MemoryLogHandler(logging.Handler):
    """Captures the most recent log records for the Admin Web Interface."""
    def emit(self, record):
        try:
            msg = self.format(record)
            now_str = datetime.now(KL_TZ).strftime("%H:%M:%S")
            RECENT_LOGS.append(f"[{now_str}] [{record.levelname}] {msg}")
        except Exception:
            pass


# Install memory logger
mem_handler = MemoryLogHandler()
mem_handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
logging.getLogger().addHandler(mem_handler)


def get_neon_connection_string(cfg: Optional[Dict[str, Any]] = None) -> str:
    """Resolves Neon PostgreSQL connection string."""
    conn_str = os.getenv("NEON_DATABASE_URL", "").strip() or os.getenv("DATABASE_URL", "").strip()
    if not conn_str and cfg:
        conn_str = cfg.get("neon_database_url", "").strip() or cfg.get("database_url", "").strip()
    if not conn_str:
        cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    conn_str = data.get("neon_database_url", "").strip() or data.get("database_url", "").strip()
            except Exception:
                pass
    return conn_str


def query_neon(query: str, params: Optional[List[Any]] = None, cfg: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Executes a query against Neon's serverless HTTP API."""
    conn_str = get_neon_connection_string(cfg)
    if not conn_str:
        return None
    try:
        parsed = urllib.parse.urlparse(conn_str)
        host = parsed.hostname
        if not host:
            return None
        endpoint = f"https://{host}/sql"
        headers = {
            "Neon-Connection-String": conn_str,
            "Content-Type": "application/json"
        }
        payload: Dict[str, Any] = {"query": query}
        if params is not None:
            payload["params"] = params
        res = requests.post(endpoint, headers=headers, json=payload, timeout=8)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        logger.debug(f"Neon query error: {e}")
    return None


def load_effective_config() -> Dict[str, Any]:
    """
    Loads config from local config.json and merges cloud config stored in Neon DB (if present).
    This ensures web UI changes persist across Koyeb rebuilds and restarts.
    """
    cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
    local_cfg = {}
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                local_cfg = json.load(f)
        except Exception as e:
            logger.error(f"Error loading local config.json: {e}")

    # Query Neon Cloud DB for persisted bot_config
    try:
        neon_res = query_neon("SELECT value FROM bot_state WHERE key = $1", params=["bot_config"], cfg=local_cfg)
        if neon_res and neon_res.get("rows") and len(neon_res["rows"]) > 0:
            cloud_cfg = neon_res["rows"][0].get("value")
            if isinstance(cloud_cfg, dict):
                # Merge cloud settings over local settings
                for k, v in cloud_cfg.items():
                    local_cfg[k] = v
                logger.info("⚡ Successfully synced dynamic bot configuration from Neon Cloud Database!")
    except Exception as e:
        logger.debug(f"Could not fetch cloud config from Neon: {e}")

    return local_cfg


def save_effective_config(new_cfg: Dict[str, Any]):
    """
    Saves configuration to both local config.json and Neon Cloud Database.
    """
    cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(new_cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error writing config.json: {e}")

    # Upsert into Neon DB
    try:
        upsert_q = (
            "INSERT INTO bot_state (key, value) "
            "VALUES ($1, $2::jsonb) "
            "ON CONFLICT (key) DO UPDATE "
            "SET value = EXCLUDED.value, updated_at = NOW() "
            "RETURNING key;"
        )
        query_neon(upsert_q, params=["bot_config", json.dumps(new_cfg)], cfg=new_cfg)
        logger.info("☁️ Persisted bot configuration to Neon Cloud Database!")
    except Exception as e:
        logger.warning(f"Could not persist config to Neon: {e}")


def get_admin_password(cfg: Dict[str, Any]) -> str:
    """Gets admin password from environment or config (defaults to 'admin')."""
    return os.getenv("ADMIN_PASSWORD", "").strip() or cfg.get("admin_password", "admin").strip() or "admin"


def generate_session_token(password: str) -> str:
    """Generates an authentication token for the session cookie."""
    salt = "GameReleaseMonitorSalt_2026"
    return hmac.new(salt.encode(), password.encode(), hashlib.sha256).hexdigest()


def is_authenticated(cookie_header: str, cfg: Dict[str, Any]) -> bool:
    """Checks if request cookie contains a valid admin session token."""
    if not cookie_header:
        return False
    pw = get_admin_password(cfg)
    expected_token = generate_session_token(pw)
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith("admin_session="):
            token = part.split("=", 1)[1]
            return hmac.compare_digest(token, expected_token)
    return False


# ==============================================================================
# HTML TEMPLATES (Cyberpunk / Modern Glassmorphism Admin Interface)
# ==============================================================================

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Admin Login • Release Monitor Bot</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body {
      background: radial-gradient(circle at 50% 20%, #161b22, #0a0c10 80%);
      color: #f0f6fc;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }
    .login-card {
      background: rgba(22, 27, 34, 0.85);
      border: 1px solid #30363d;
      backdrop-filter: blur(16px);
      border-radius: 16px;
      padding: 36px 32px;
      width: 100%;
      max-width: 420px;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.6), 0 0 30px rgba(0, 180, 216, 0.15);
      text-align: center;
    }
    .brand-icon {
      font-size: 44px;
      margin-bottom: 12px;
      display: inline-block;
      filter: drop-shadow(0 0 10px rgba(0, 180, 216, 0.5));
    }
    h1 { font-size: 22px; font-weight: 700; color: #ffffff; margin-bottom: 6px; }
    p.subtitle { font-size: 13px; color: #8b949e; margin-bottom: 26px; }
    .form-group { text-align: left; margin-bottom: 20px; }
    label { font-size: 12px; font-weight: 600; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-bottom: 8px; }
    input[type="password"], input[type="text"] {
      width: 100%;
      padding: 13px 16px;
      background: #0d1117;
      border: 1px solid #30363d;
      border-radius: 10px;
      color: #ffffff;
      font-size: 15px;
      outline: none;
      transition: all 0.2s;
    }
    input[type="password"]:focus, input[type="text"]:focus {
      border-color: #00b4d8;
      box-shadow: 0 0 0 3px rgba(0, 180, 216, 0.2);
    }
    button {
      width: 100%;
      padding: 14px;
      background: linear-gradient(135deg, #00b4d8, #0077b6);
      border: none;
      border-radius: 10px;
      color: #ffffff;
      font-size: 15px;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.2s;
      box-shadow: 0 4px 14px rgba(0, 180, 216, 0.3);
    }
    button:hover {
      background: linear-gradient(135deg, #00c4ec, #0088cc);
      transform: translateY(-1px);
    }
    .error-msg {
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid #ef4444;
      color: #fca5a5;
      padding: 10px;
      border-radius: 8px;
      font-size: 13px;
      margin-bottom: 18px;
      display: none;
    }
    .footer-note { font-size: 11px; color: #64748b; margin-top: 24px; }
  </style>
</head>
<body>
  <div class="login-card">
    <div class="brand-icon">🎮</div>
    <h1>Release Monitor Admin</h1>
    <p class="subtitle">Secure Settings & Source Management</p>
    
    <div id="errorBanner" class="error-msg">Incorrect password. Please try again.</div>

    <form id="loginForm" method="POST" action="/api/login">
      <div class="form-group">
        <label for="password">Admin Password</label>
        <input type="password" id="password" name="password" placeholder="Enter admin password (default: admin)..." required autofocus>
      </div>
      <button type="submit">Unlock Dashboard 🚀</button>
    </form>
    <div class="footer-note">Kuala Lumpur Time (GMT+8) • Koyeb Cloud Native</div>
  </div>

  <script>
    const params = new URLSearchParams(window.location.search);
    if (params.get('error') === '1') {
      document.getElementById('errorBanner').style.display = 'block';
    }
  </script>
</body>
</html>
"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Admin Dashboard • Release Monitor Bot</title>
  <style>
    :root {
      --bg: #0b0e14;
      --card-bg: rgba(22, 27, 34, 0.85);
      --card-border: #30363d;
      --accent: #00b4d8;
      --accent-glow: rgba(0, 180, 216, 0.25);
      --success: #10b981;
      --danger: #ef4444;
      --text: #f0f6fc;
      --text-muted: #8b949e;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body {
      background: radial-gradient(circle at 50% 0%, #161b22, var(--bg) 70%);
      color: var(--text);
      min-height: 100vh;
      padding: 24px 20px 100px 20px;
    }
    .container { max-width: 1100px; margin: 0 auto; }
    
    /* Header */
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 24px;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 28px;
      flex-wrap: wrap;
      gap: 16px;
    }
    .header-left { display: flex; align-items: center; gap: 14px; }
    .header-icon { font-size: 32px; filter: drop-shadow(0 0 10px var(--accent-glow)); }
    .header-title h1 { font-size: 22px; font-weight: 700; }
    .header-title p { font-size: 13px; color: var(--text-muted); }
    .header-right { display: flex; align-items: center; gap: 12px; }
    .status-pill {
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid var(--success);
      color: var(--success);
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--success); box-shadow: 0 0 8px var(--success); }
    .btn-logout {
      background: #21262d;
      border: 1px solid var(--card-border);
      color: var(--text-muted);
      padding: 8px 16px;
      border-radius: 8px;
      font-size: 13px;
      cursor: pointer;
      text-decoration: none;
      transition: all 0.2s;
    }
    .btn-logout:hover { background: #30363d; color: var(--text); }

    /* Section Title */
    .section-header {
      display: flex;
      align-items: center;
      gap: 10px;
      margin: 32px 0 16px 0;
    }
    .section-header h2 { font-size: 17px; font-weight: 700; color: #ffffff; }
    .section-badge {
      background: rgba(0, 180, 216, 0.12);
      border: 1px solid var(--accent);
      color: var(--accent);
      font-size: 11px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 10px;
    }

    /* Grid of Toggles */
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 16px;
    }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 18px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      backdrop-filter: blur(12px);
      transition: border-color 0.2s, box-shadow 0.2s;
    }
    .card:hover {
      border-color: #484f58;
      box-shadow: 0 4px 16px rgba(0,0,0,0.3);
    }
    .card-info { flex: 1; padding-right: 16px; }
    .card-title {
      font-size: 15px;
      font-weight: 600;
      color: #ffffff;
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 4px;
    }
    .card-desc { font-size: 12px; color: var(--text-muted); line-height: 1.4; }

    /* Switch Component */
    .switch {
      position: relative;
      display: inline-block;
      width: 52px;
      height: 28px;
      flex-shrink: 0;
    }
    .switch input { opacity: 0; width: 0; height: 0; }
    .slider {
      position: absolute;
      cursor: pointer;
      top: 0; left: 0; right: 0; bottom: 0;
      background-color: #374151;
      transition: .3s cubic-bezier(0.4, 0, 0.2, 1);
      border-radius: 28px;
    }
    .slider:before {
      position: absolute;
      content: "";
      height: 20px;
      width: 20px;
      left: 4px;
      bottom: 4px;
      background-color: white;
      transition: .3s cubic-bezier(0.4, 0, 0.2, 1);
      border-radius: 50%;
      box-shadow: 0 2px 4px rgba(0,0,0,0.3);
    }
    input:checked + .slider {
      background-color: var(--success);
      box-shadow: 0 0 12px rgba(16, 185, 129, 0.4);
    }
    input:checked + .slider:before {
      transform: translateX(24px);
    }

    /* General Settings Form */
    .settings-panel {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 24px;
      margin-top: 16px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 20px;
    }
    .field-group label {
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      display: block;
      margin-bottom: 8px;
    }
    .field-group input {
      width: 100%;
      padding: 12px 14px;
      background: #0d1117;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      color: #ffffff;
      font-size: 14px;
      outline: none;
    }
    .field-group input:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 2px var(--accent-glow);
    }

    /* Actions row */
    .actions-row {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 16px;
    }
    .btn-action {
      background: #21262d;
      border: 1px solid var(--card-border);
      color: #f0f6fc;
      padding: 11px 20px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s;
    }
    .btn-action:hover {
      background: #30363d;
      border-color: var(--accent);
      color: #ffffff;
    }

    /* Logs console */
    .log-console {
      background: #0d1117;
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 16px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 12px;
      color: #94a3b8;
      height: 220px;
      overflow-y: auto;
      line-height: 1.6;
      margin-top: 16px;
    }
    .log-line-info { color: #38bdf8; }
    .log-line-warn { color: #fbbf24; }
    .log-line-err { color: #f87171; }

    /* Sticky Footer Save Bar */
    .save-bar {
      position: fixed;
      bottom: 20px;
      left: 50%;
      transform: translateX(-50%);
      background: rgba(22, 27, 34, 0.95);
      border: 1px solid var(--accent);
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.8), 0 0 20px var(--accent-glow);
      backdrop-filter: blur(16px);
      padding: 14px 28px;
      border-radius: 40px;
      display: flex;
      align-items: center;
      gap: 20px;
      z-index: 999;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .save-bar-text { font-size: 14px; font-weight: 600; color: #ffffff; }
    .btn-save {
      background: linear-gradient(135deg, var(--accent), #0077b6);
      border: none;
      padding: 10px 24px;
      border-radius: 20px;
      color: #ffffff;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
      box-shadow: 0 4px 12px rgba(0, 180, 216, 0.4);
      transition: all 0.2s;
    }
    .btn-save:hover { transform: scale(1.04); }

    /* Toast */
    .toast {
      position: fixed;
      top: 24px;
      right: 24px;
      background: rgba(16, 185, 129, 0.95);
      color: white;
      padding: 12px 24px;
      border-radius: 10px;
      font-size: 14px;
      font-weight: 600;
      box-shadow: 0 8px 24px rgba(0,0,0,0.5);
      opacity: 0;
      pointer-events: none;
      transform: translateY(-10px);
      transition: all 0.3s;
      z-index: 1000;
    }
    .toast.show { opacity: 1; transform: translateY(0); }
  </style>
</head>
<body>
  <div class="container">
    <!-- Header -->
    <header>
      <div class="header-left">
        <div class="header-icon">🎮</div>
        <div class="header-title">
          <h1>Release Monitor Admin Dashboard</h1>
          <p>Real-time Monitor Controls & Dynamic Configuration</p>
        </div>
      </div>
      <div class="header-right">
        <div class="status-pill">
          <div class="status-dot"></div>
          <span>LIVE • KOYEB</span>
        </div>
        <a href="/logout" class="btn-logout">Logout 🚪</a>
      </div>
    </header>

    <!-- SECTION 1: Steam Store Ecosystem -->
    <div class="section-header">
      <h2>Steam Store & Launches</h2>
      <span class="section-badge">Official Store APIs</span>
    </div>
    <div class="grid">
      <div class="card">
        <div class="card-info">
          <div class="card-title">🚀 Steam Game Launches</div>
          <div class="card-desc">Alerts for brand new full PC game releases with store & webview links.</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="watch_steam_new_launches">
          <span class="slider"></span>
        </label>
      </div>

      <div class="card">
        <div class="card-info">
          <div class="card-title">🧩 Steam DLC Launches</div>
          <div class="card-desc">Alerts for newly released downloadable content & expansions.</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="watch_steam_dlc_launches">
          <span class="slider"></span>
        </label>
      </div>

      <div class="card">
        <div class="card-info">
          <div class="card-title">🎯 Daily Release Radar</div>
          <div class="card-desc">Midnight 12:00 AM (GMT+8) visual infographic poster of day's releases.</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="watch_daily_release_radar">
          <span class="slider"></span>
        </label>
      </div>

      <div class="card">
        <div class="card-info">
          <div class="card-title">💸 Steam Specials (MYR)</div>
          <div class="card-desc">Featured store promotions with prices formatted in Malaysian Ringgit.</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="watch_steam_deals">
          <span class="slider"></span>
        </label>
      </div>

      <div class="card">
        <div class="card-info">
          <div class="card-title">🎁 Steam 100% Free Games</div>
          <div class="card-desc">100% off free-to-keep promotions & community giveaways.</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="watch_steam_free_games">
          <span class="slider"></span>
        </label>
      </div>

      <div class="card">
        <div class="card-info">
          <div class="card-title">⚙️ Steam Client Watch</div>
          <div class="card-desc">Tracks official Valve Stable & Beta client updates via Protobuf.</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="watch_steam_versions">
          <span class="slider"></span>
        </label>
      </div>

      <div class="card">
        <div class="card-info">
          <div class="card-title">🛡️ Denuvo Status Tracker</div>
          <div class="card-desc">Monitors anti-tamper removals and status changes for watchlist games.</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="watch_denuvo_status">
          <span class="slider"></span>
        </label>
      </div>

      <div class="card">
        <div class="card-info">
          <div class="card-title">📦 Steam App Patches</div>
          <div class="card-desc">Tracks depot patch manifests for monitored competitive titles.</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="watch_steam_app_patches">
          <span class="slider"></span>
        </label>
      </div>

      <div class="card">
        <div class="card-info">
          <div class="card-title">🎟️ Steam Free Weekends</div>
          <div class="card-desc">Temporary free-to-play promotions and community trials.</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="watch_steam_free_weekends">
          <span class="slider"></span>
        </label>
      </div>
    </div>

    <!-- SECTION 2: Community & Repacks / Trainers -->
    <div class="section-header">
      <h2>Community, Bypasses & Trainers</h2>
      <span class="section-badge">Third-Party Feeds</span>
    </div>
    <div class="grid">
      <div class="card">
        <div class="card-info">
          <div class="card-title">🔓 SUO Wannabe</div>
          <div class="card-desc">Catalog watcher for newly uploaded cracked game builds.</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="watch_steamunlockonennabe">
          <span class="slider"></span>
        </label>
      </div>

      <div class="card">
        <div class="card-info">
          <div class="card-title">⚔️ Reddit r/CrackWatch</div>
          <div class="card-desc">Scene releases, crack announcements, and NFO breakdowns.</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="watch_crackwatch_reddit">
          <span class="slider"></span>
        </label>
      </div>

      <div class="card">
        <div class="card-info">
          <div class="card-title">👥 Online-Fix.me</div>
          <div class="card-desc">Multiplayer coop bypasses and Steam overlay LAN fixes.</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="watch_onlinefix">
          <span class="slider"></span>
        </label>
      </div>

      <div class="card">
        <div class="card-info">
          <div class="card-title">⚡ WeMod / Wand</div>
          <div class="card-desc">Newly released game trainers and cheat updates.</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="watch_wemod">
          <span class="slider"></span>
        </label>
      </div>

      <div class="card">
        <div class="card-info">
          <div class="card-title">🧙 FLiNG Trainer</div>
          <div class="card-desc">Official FLiNG standalone trainers with total cheat option counts.</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="watch_flingtrainer">
          <span class="slider"></span>
        </label>
      </div>

      <div class="card">
        <div class="card-info">
          <div class="card-title">🌐 CS.RIN.RU Watcher</div>
          <div class="card-desc">Forum topic and subforum updates monitor.</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="watch_csrin">
          <span class="slider"></span>
        </label>
      </div>

      <div class="card">
        <div class="card-info">
          <div class="card-title">📡 CS.RIN Global Live Feed</div>
          <div class="card-desc">Fast real-time live feed across subforum 10.</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="enable_global_feed">
          <span class="slider"></span>
        </label>
      </div>

      <div class="card">
        <div class="card-info">
          <div class="card-title">🏴‍☠️ FitGirl Repacks</div>
          <div class="card-desc">Official FitGirl RSS release announcements.</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="watch_fitgirl">
          <span class="slider"></span>
        </label>
      </div>

      <div class="card">
        <div class="card-info">
          <div class="card-title">📦 DODI Repacks</div>
          <div class="card-desc">Official DODI repack releases feed.</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="watch_dodi">
          <span class="slider"></span>
        </label>
      </div>
    </div>

    <!-- SECTION 3: Settings Panel -->
    <div class="section-header">
      <h2>General & Schedule Settings</h2>
      <span class="section-badge">Cadence</span>
    </div>
    <div class="settings-panel">
      <div class="field-group">
        <label for="check_interval_seconds">Check Interval (Seconds)</label>
        <input type="number" id="check_interval_seconds" min="30" max="3600" value="60">
      </div>
      <div class="field-group">
        <label for="daily_release_radar_hour_gmt8">Daily Radar Hour (GMT+8, 0 = Midnight)</label>
        <input type="number" id="daily_release_radar_hour_gmt8" min="0" max="23" value="0">
      </div>
      <div class="field-group">
        <label for="admin_password">Update Admin Password</label>
        <input type="text" id="admin_password" placeholder="Leave blank to keep unchanged">
      </div>
    </div>

    <!-- SECTION 4: Live Actions -->
    <div class="section-header">
      <h2>Quick Actions & Manual Triggers</h2>
      <span class="section-badge">Instant</span>
    </div>
    <div class="actions-row">
      <button class="btn-action" onclick="triggerAction('daily_radar')">🎯 Test Daily Radar Now</button>
      <button class="btn-action" onclick="triggerAction('check_launches')">🚀 Check Steam Launches</button>
      <button class="btn-action" onclick="triggerAction('check_deals')">💸 Check Steam Deals</button>
      <button class="btn-action" onclick="refreshLogs()">🔄 Refresh Live Logs</button>
    </div>

    <!-- SECTION 5: Live Logs Console -->
    <div class="section-header">
      <h2>Live Activity Feed</h2>
      <span class="section-badge">Real-Time</span>
    </div>
    <div class="log-console" id="logConsole">Loading recent logs...</div>

    <!-- Sticky Save Bar -->
    <div class="save-bar">
      <span class="save-bar-text">⚡ Settings take effect immediately without rebuilding</span>
      <button class="btn-save" onclick="saveConfig()">💾 Save Changes</button>
    </div>
  </div>

  <div id="toast" class="toast">Settings Saved Successfully!</div>

  <script>
    let currentConfig = {};

    const TOGGLE_KEYS = [
      'watch_steam_new_launches',
      'watch_steam_dlc_launches',
      'watch_daily_release_radar',
      'watch_steam_deals',
      'watch_steam_free_games',
      'watch_steam_versions',
      'watch_denuvo_status',
      'watch_steam_app_patches',
      'watch_steam_free_weekends',
      'watch_steamunlockonennabe',
      'watch_crackwatch_reddit',
      'watch_onlinefix',
      'watch_wemod',
      'watch_flingtrainer',
      'watch_csrin',
      'enable_global_feed',
      'watch_fitgirl',
      'watch_dodi'
    ];

    async function loadConfig() {
      try {
        const res = await fetch('/api/config');
        if (res.status === 401) {
          window.location.href = '/login';
          return;
        }
        currentConfig = await res.json();
        
        TOGGLE_KEYS.forEach(key => {
          const el = document.getElementById(key);
          if (el) el.checked = !!currentConfig[key];
        });

        if (document.getElementById('check_interval_seconds')) {
          document.getElementById('check_interval_seconds').value = currentConfig.check_interval_seconds || 60;
        }
        if (document.getElementById('daily_release_radar_hour_gmt8')) {
          document.getElementById('daily_release_radar_hour_gmt8').value = currentConfig.daily_release_radar_hour_gmt8 !== undefined ? currentConfig.daily_release_radar_hour_gmt8 : 0;
        }
      } catch (e) {
        console.error('Error loading config:', e);
      }
    }

    async function saveConfig() {
      const payload = { ...currentConfig };

      TOGGLE_KEYS.forEach(key => {
        const el = document.getElementById(key);
        if (el) payload[key] = el.checked;
      });

      const intVal = parseInt(document.getElementById('check_interval_seconds').value, 10);
      if (!isNaN(intVal) && intVal >= 30) {
        payload.check_interval_seconds = intVal;
      }

      const hourVal = parseInt(document.getElementById('daily_release_radar_hour_gmt8').value, 10);
      if (!isNaN(hourVal) && hourVal >= 0 && hourVal <= 23) {
        payload.daily_release_radar_hour_gmt8 = hourVal;
      }

      const newPw = document.getElementById('admin_password').value.trim();
      if (newPw) {
        payload.admin_password = newPw;
      }

      try {
        const res = await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        if (res.ok) {
          showToast('Settings saved & synced to Cloud DB!');
          if (newPw) {
            document.getElementById('admin_password').value = '';
          }
          await loadConfig();
        } else {
          alert('Failed to save settings. Please try again.');
        }
      } catch (e) {
        alert('Network error saving settings: ' + e);
      }
    }

    async function triggerAction(action) {
      try {
        showToast('Triggering action: ' + action + '...');
        const res = await fetch('/api/trigger', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: action })
        });
        const data = await res.json();
        showToast(data.message || 'Action executed successfully!');
        refreshLogs();
      } catch (e) {
        alert('Error triggering action: ' + e);
      }
    }

    async function refreshLogs() {
      try {
        const res = await fetch('/api/logs');
        if (res.ok) {
          const logs = await res.json();
          const el = document.getElementById('logConsole');
          if (logs.length === 0) {
            el.innerText = 'No log entries recorded yet.';
          } else {
            el.innerHTML = logs.map(l => {
              if (l.includes('[ERROR]')) return `<div class="log-line-err">${escapeHtml(l)}</div>`;
              if (l.includes('[WARNING]')) return `<div class="log-line-warn">${escapeHtml(l)}</div>`;
              return `<div class="log-line-info">${escapeHtml(l)}</div>`;
            }).join('');
            el.scrollTop = el.scrollHeight;
          }
        }
      } catch (e) {
        console.error(e);
      }
    }

    function showToast(msg) {
      const t = document.getElementById('toast');
      t.innerText = msg;
      t.classList.add('show');
      setTimeout(() => t.classList.remove('show'), 3000);
    }

    function escapeHtml(str) {
      return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // Init
    loadConfig();
    refreshLogs();
    setInterval(refreshLogs, 8000);
  </script>
</body>
</html>
"""

