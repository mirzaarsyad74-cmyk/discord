import requests
import json

conn = "postgresql://neondb_owner:npg_1oBy0JMPfzsd@ep-crimson-dream-b3cs1xnt-pooler.c-4.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"
endpoint = "https://ep-crimson-dream-b3cs1xnt-pooler.c-4.ap-southeast-1.aws.neon.tech/sql"
headers = {
    "Neon-Connection-String": conn,
    "Content-Type": "application/json"
}

# 1. Simple select
res = requests.post(endpoint, headers=headers, json={"query": "SELECT key FROM bot_state"}, timeout=8)
print("1. Select keys:", res.status_code, res.text[:200])

# 2. Select with params vs direct
res2 = requests.post(endpoint, headers=headers, json={"query": "SELECT * FROM bot_state WHERE key = 'main_state'"}, timeout=8)
print("2. Direct select:", res2.status_code, "Length of response:", len(res2.text))

# 3. Test how Neon expects parameters or escaping
# Neon's /sql endpoint accepts: {"query": "...", "params": [...]}
res3 = requests.post(endpoint, headers=headers, json={"query": "SELECT * FROM bot_state WHERE key = $1", "params": ["main_state"]}, timeout=8)
print("3. Query with $1:", res3.status_code, res3.text[:200])

# Test upsert
upsert_q = """
INSERT INTO bot_state (key, value)
VALUES ($1, $2::jsonb)
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value, updated_at = NOW()
RETURNING key;
"""
res4 = requests.post(endpoint, headers=headers, json={"query": upsert_q, "params": ["bot_config", json.dumps({"test": 123})]}, timeout=8)
print("4. Upsert result:", res4.status_code, res4.text)

res5 = requests.post(endpoint, headers=headers, json={"query": "SELECT value FROM bot_state WHERE key = $1", "params": ["bot_config"]}, timeout=8)
print("5. Read bot_config:", res5.status_code, res5.json())
