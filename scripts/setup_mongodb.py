#!/usr/bin/env python3
"""
Automated MongoDB Atlas Setup & Migration Script for Game Release Monitor.
Usage:
    python scripts/setup_mongodb.py "mongodb+srv://<user>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority"
Or simply run without arguments to be prompted for the connection string.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("setup_mongodb")

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
except ImportError:
    logger.error("pymongo is not installed. Please run: pip install pymongo dnspython")
    sys.exit(1)


def setup_mongodb(uri: str) -> bool:
    uri = uri.strip().strip("'").strip('"')
    if not uri.startswith("mongodb://") and not uri.startswith("mongodb+srv://"):
        logger.error("Invalid MongoDB connection string. Must start with 'mongodb://' or 'mongodb+srv://'.")
        return False

    logger.info("Connecting to MongoDB Atlas...")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=8000)
        # Force connection verification
        client.admin.command("ping")
        logger.info("✅ Successfully connected and authenticated to MongoDB Atlas!")
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        logger.error(f"❌ Connection to MongoDB Atlas failed: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Authentication or network error: {e}")
        return False

    # Target database
    db_name = "game_release_monitor"
    db = client[db_name]
    logger.info(f"Targeting database: '{db_name}'")

    # 1. Setup bot_state collection & unique index
    state_col = db["bot_state"]
    state_col.create_index("key", unique=True)
    logger.info("Created unique index on collection 'bot_state' ('key')")

    # 2. Setup bot_config collection & unique index
    config_col = db["bot_config"]
    config_col.create_index("key", unique=True)
    logger.info("Created unique index on collection 'bot_config' ('key')")

    # 3. Migrate local state.json into MongoDB
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    state_path = os.path.join(root_dir, "data", "state.json")
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state_data = json.load(f)
            state_col.update_one(
                {"key": "main_state"},
                {"$set": {"key": "main_state", "value": state_data, "updated_at": datetime.now(timezone.utc)}},
                upsert=True
            )
            logger.info("✅ Successfully migrated local 'data/state.json' into MongoDB Atlas ('bot_state')!")
        except Exception as e:
            logger.warning(f"Could not migrate state.json: {e}")

    # 4. Migrate local config.json into MongoDB
    cfg_path = os.path.join(root_dir, "config.json")
    local_cfg = {}
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                local_cfg = json.load(f)
            config_col.update_one(
                {"key": "bot_config"},
                {"$set": {"key": "bot_config", "value": local_cfg, "updated_at": datetime.now(timezone.utc)}},
                upsert=True
            )
            logger.info("✅ Successfully migrated local 'config.json' into MongoDB Atlas ('bot_config')!")
        except Exception as e:
            logger.warning(f"Could not migrate config.json: {e}")

    # 5. Save MONGODB_URI to config.json
    local_cfg["mongodb_uri"] = uri
    # Disable defunct Neon URL if it was pointing to expired DB
    if "neon_database_url" in local_cfg and "ep-crimson-dream" in local_cfg.get("neon_database_url", ""):
        local_cfg["neon_database_url"] = ""
    try:
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(local_cfg, f, indent=2, ensure_ascii=False)
        logger.info("✅ Saved 'mongodb_uri' into 'config.json'!")
    except Exception as e:
        logger.warning(f"Could not update config.json: {e}")

    # 6. Save MONGODB_URI to .env if present
    env_path = os.path.join(root_dir, ".env")
    try:
        env_lines = []
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                env_lines = f.readlines()
        has_mongo = False
        new_lines = []
        for line in env_lines:
            if line.startswith("MONGODB_URI="):
                new_lines.append(f"MONGODB_URI={uri}\n")
                has_mongo = True
            elif line.startswith("NEON_DATABASE_URL=") and "ep-crimson-dream" in line:
                new_lines.append("# " + line)
            else:
                new_lines.append(line)
        if not has_mongo:
            new_lines.append(f"\nMONGODB_URI={uri}\n")
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        logger.info("✅ Updated '.env' file with MONGODB_URI!")
    except Exception as e:
        logger.warning(f"Could not update .env: {e}")

    logger.info("🎉 MongoDB Atlas automated setup is 100% complete!")
    logger.info("The bot will now persist all state and configuration to MongoDB Atlas automatically.")
    return True


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_uri = sys.argv[1]
    else:
        target_uri = input("Enter your MongoDB Atlas connection string (mongodb+srv://...): ").strip()
    
    if not target_uri:
        print("No connection string provided. Exiting.")
        sys.exit(1)

    success = setup_mongodb(target_uri)
    sys.exit(0 if success else 1)
