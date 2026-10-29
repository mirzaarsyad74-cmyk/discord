import os
import re
import json
import hashlib
import logging
import urllib.parse
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import requests
from scraper import CsRinScraper, ForumPost, TopicMetadata

logger = logging.getLogger("cs_rin_monitor")

STATE_FILE = os.path.join(os.path.dirname(__file__), "data", "state.json")

@dataclass
class TopicUpdateEvents:
    topic_id: str
    topic_title: str
    new_posts: List[ForumPost]
    title_change: Optional[Tuple[str, str]] = None  # (old_title, new_title)
    op_update: Optional[ForumPost] = None


class ForumMonitor:
    def __init__(self, scraper: CsRinScraper, state_file: str = STATE_FILE):
        self.scraper = scraper
        self.state_file = state_file
        self.state: Dict[str, Any] = self._load_state()

    def _get_neon_connection_string(self) -> str:
        """Resolves Neon PostgreSQL connection string from environment variables or config.json."""
        conn_str = os.getenv("NEON_DATABASE_URL", "").strip() or os.getenv("DATABASE_URL", "").strip()
        if not conn_str:
            cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                        conn_str = cfg.get("neon_database_url", "").strip() or cfg.get("database_url", "").strip()
                except Exception:
                    pass
        return conn_str

    def _query_neon(self, query: str, params: Optional[List[Any]] = None) -> Optional[Dict[str, Any]]:
        """Executes a SQL query against Neon's serverless HTTP API without requiring PostgreSQL native drivers."""
        conn_str = self._get_neon_connection_string()
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
            else:
                logger.warning(f"Neon HTTP SQL returned HTTP {res.status_code}: {res.text[:120]}")
        except Exception as e:
            logger.warning(f"Error executing query on Neon: {e}")
        return None

    def _get_supabase_credentials(self) -> Tuple[str, str]:
        """Resolves Supabase URL and Key from environment variables or config.json."""
        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_KEY", "").strip()
        if not url or not key:
            cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                        url = url or cfg.get("supabase_url", "").strip()
                        key = key or cfg.get("supabase_key", "").strip()
                except Exception:
                    pass
        return url, key

    def _load_state(self) -> Dict[str, Any]:
        """Loads state from Neon Cloud Database (primary), Supabase (fallback), or local state.json."""
        # 1. Primary: Neon Cloud Database
        if self._get_neon_connection_string():
            try:
                res_data = self._query_neon(
                    "SELECT value FROM bot_state WHERE key = $1",
                    params=["main_state"]
                )
                if res_data and "rows" in res_data and len(res_data["rows"]) > 0:
                    cloud_state = res_data["rows"][0].get("value")
                    if cloud_state and isinstance(cloud_state, dict):
                        logger.info("⚡ Successfully loaded persistent bot state from Neon Cloud Database!")
                        try:
                            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
                            with open(self.state_file, "w", encoding="utf-8") as f:
                                json.dump(cloud_state, f, indent=2, ensure_ascii=False)
                        except Exception:
                            pass
                        return cloud_state
            except Exception as e:
                logger.warning(f"Could not load state from Neon, falling back: {e}")

        # 2. Secondary Fallback: Supabase Cloud Database
        supa_url, supa_key = self._get_supabase_credentials()
        if supa_url and supa_key:
            try:
                headers = {
                    "apikey": supa_key,
                    "Authorization": f"Bearer {supa_key}"
                }
                res = requests.get(
                    f"{supa_url}/rest/v1/bot_state?key=eq.main_state&select=value",
                    headers=headers,
                    timeout=8
                )
                if res.status_code == 200:
                    data = res.json()
                    if data and isinstance(data, list) and len(data) > 0 and "value" in data[0]:
                        cloud_state = data[0]["value"]
                        logger.info("☁️ Successfully loaded persistent bot state from Supabase Cloud Database!")
                        try:
                            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
                            with open(self.state_file, "w", encoding="utf-8") as f:
                                json.dump(cloud_state, f, indent=2, ensure_ascii=False)
                        except Exception:
                            pass
                        return cloud_state
            except Exception as e:
                logger.warning(f"Could not load state from Supabase, falling back to local file: {e}")

        # 3. Local fallback
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error reading state file {self.state_file}: {e}")
        return {"topics": {}, "subforums": {}}

    def save_state(self):
        """Saves state to local state.json and syncs to Neon Cloud Database (primary) and Supabase (fallback)."""
        # 1. Save local file cache
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error writing state file: {e}")

        # 2. Primary: Sync to Neon Cloud Database
        if self._get_neon_connection_string():
            try:
                upsert_q = (
                    "INSERT INTO bot_state (key, value) "
                    "VALUES ($1, $2::jsonb) "
                    "ON CONFLICT (key) DO UPDATE "
                    "SET value = EXCLUDED.value, updated_at = NOW() "
                    "RETURNING key"
                )
                self._query_neon(upsert_q, params=["main_state", json.dumps(self.state)])
            except Exception as e:
                logger.warning(f"Failed to sync state to Neon: {e}")

        # 3. Secondary Fallback: Sync to Supabase Cloud Database (if configured)
        supa_url, supa_key = self._get_supabase_credentials()
        if supa_url and supa_key:
            try:
                headers = {
                    "apikey": supa_key,
                    "Authorization": f"Bearer {supa_key}",
                    "Content-Type": "application/json",
                    "Prefer": "resolution=merge-duplicates"
                }
                res = requests.post(
                    f"{supa_url}/rest/v1/bot_state",
                    headers=headers,
                    json={"key": "main_state", "value": self.state},
                    timeout=8
                )
                if res.status_code not in (200, 201):
                    logger.warning(f"Supabase sync status: {res.status_code}")
            except Exception as e:
                logger.warning(f"Failed to sync state to Supabase: {e}")


    @staticmethod
    def compute_post_fingerprint(post: ForumPost) -> str:
        """Generates a stable content hash to prevent duplicate alerts even if post ID varies."""
        clean_excerpt = post.clean_markdown[:400].strip()
        data = f"{post.topic_id}:{post.author}:{clean_excerpt}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def is_post_seen(self, topic_id: str, post: ForumPost) -> bool:
        """Double-check deduplication: checks both Post ID and Content Fingerprint across topic and global feed."""
        topic_id = self.scraper.extract_topic_id(topic_id)
        pid_str = str(post.post_id)
        fp = self.compute_post_fingerprint(post)

        # 1. Check topic state
        topic_state = self.state.get("topics", {}).get(topic_id, {})
        if pid_str in set(str(pid) for pid in topic_state.get("seen_post_ids", [])):
            return True
        if fp in set(topic_state.get("seen_fingerprints", [])):
            return True

        # 2. Check global feed state
        feed_state = self.state.get("feed", {})
        if pid_str in set(str(pid) for pid in feed_state.get("seen_post_ids", [])):
            return True
        if fp in set(feed_state.get("seen_fingerprints", [])):
            return True

        return False

    def mark_post_seen(self, topic_id: str, post: ForumPost):
        """Immediately marks a post as seen with preserved chronological ordering."""
        topic_id = self.scraper.extract_topic_id(topic_id)
        pid_str = str(post.post_id)
        fp = self.compute_post_fingerprint(post)

        # Update topic state
        topics_state = self.state.setdefault("topics", {})
        topic_state = topics_state.setdefault(topic_id, {
            "title": "",
            "op_hash": "",
            "max_start": 0,
            "seen_post_ids": [],
            "seen_fingerprints": []
        })

        seen_pids = [str(pid) for pid in topic_state.setdefault("seen_post_ids", [])]
        if pid_str not in seen_pids:
            seen_pids.append(pid_str)
        topic_state["seen_post_ids"] = seen_pids[-500:]

        seen_fps = list(topic_state.setdefault("seen_fingerprints", []))
        if fp not in seen_fps:
            seen_fps.append(fp)
        topic_state["seen_fingerprints"] = seen_fps[-300:]

        # Also record in global feed state so global feed never duplicates it
        feed_state = self.state.setdefault("feed", {})
        feed_pids = [str(pid) for pid in feed_state.setdefault("seen_post_ids", [])]
        if pid_str not in feed_pids:
            feed_pids.append(pid_str)
        feed_state["seen_post_ids"] = feed_pids[-1000:]

        feed_fps = list(feed_state.setdefault("seen_fingerprints", []))
        if fp not in feed_fps:
            feed_fps.append(fp)
        feed_state["seen_fingerprints"] = feed_fps[-600:]

        self.save_state()

    def check_topic(self, topic_id: str, is_first_run_init: bool = False) -> TopicUpdateEvents:
        """
        Polls a topic on CS.RIN.RU with bulletproof deduplication:
        - Detects title changes (e.g. [NOT CRACKED] -> [CRACKED])
        - Detects OP post modifications
        - Detects new replies / posts without any duplicate alerts
        """
        topic_id = self.scraper.extract_topic_id(topic_id)
        topics_state = self.state.setdefault("topics", {})
        topic_state = topics_state.setdefault(topic_id, {
            "title": "",
            "op_hash": "",
            "max_start": 0,
            "seen_post_ids": [],
            "seen_fingerprints": []
        })

        seen_pids_list = [str(pid) for pid in topic_state.get("seen_post_ids", [])]
        seen_pids = set(seen_pids_list)
        seen_fps_list = list(topic_state.get("seen_fingerprints", []))
        seen_fps = set(seen_fps_list)

        # Cross-reference global feed
        feed_pids = set(str(pid) for pid in self.state.get("feed", {}).get("seen_post_ids", []))
        feed_fps = set(self.state.get("feed", {}).get("seen_fingerprints", []))
        seen_pids.update(feed_pids)
        seen_fps.update(feed_fps)

        last_title = topic_state.get("title", "")
        last_op_hash = topic_state.get("op_hash", "")
        last_max_start = topic_state.get("max_start", 0)

        # Step 1: Fetch metadata (title, OP, max_start)
        meta = self.scraper.get_topic_metadata(topic_id)
        if not meta or not meta.title or meta.title == "Unknown":
            logger.warning(f"Could not retrieve metadata for topic {topic_id}")
            return TopicUpdateEvents(topic_id=topic_id, topic_title=last_title or "Unknown", new_posts=[])

        current_title = meta.title
        title_change = None
        if last_title and last_title != current_title:
            logger.info(f"Topic {topic_id} title changed: '{last_title}' -> '{current_title}'")
            title_change = (last_title, current_title)

        # Check OP post updates
        op_update = None
        current_op_hash = ""
        if meta.op_post:
            current_op_hash = hashlib.sha256(meta.op_post.raw_content.encode("utf-8")).hexdigest()
            # If OP hash is known and changed, trigger OP update
            if last_op_hash and last_op_hash != current_op_hash:
                logger.info(f"Topic {topic_id} OP post updated!")
                op_update = meta.op_post

        # If this is the very first time tracking this topic (or explicit init):
        # Mark all existing posts on the latest page and OP as seen so we NEVER post historical content!
        if is_first_run_init or not last_title:
            logger.info(f"First-time initialization for topic {topic_id}. Marking all existing posts as seen...")
            existing_posts = self.scraper.get_posts_page(topic_id, start=meta.max_start, topic_title=current_title)
            for p in existing_posts:
                seen_pids.add(str(p.post_id))
                seen_fps.add(self.compute_post_fingerprint(p))
            if meta.op_post:
                seen_pids.add(str(meta.op_post.post_id))
                seen_fps.add(self.compute_post_fingerprint(meta.op_post))

            topic_state["title"] = current_title
            topic_state["op_hash"] = current_op_hash
            topic_state["max_start"] = meta.max_start
            topic_state["seen_post_ids"] = list(seen_pids)
            topic_state["seen_fingerprints"] = list(seen_fps)
            self.save_state()
            return TopicUpdateEvents(topic_id=topic_id, topic_title=current_title, new_posts=[])

        # Step 2: Determine pages to fetch for new posts
        # Only check from last_max_start up to current max_start
        pages_to_check = [start for start in meta.all_starts if start >= last_max_start]
        if not pages_to_check:
            pages_to_check = [meta.max_start]

        found_new_posts: List[ForumPost] = []
        for start in pages_to_check:
            posts = self.scraper.get_posts_page(topic_id, start=start, topic_title=current_title)
            for p in posts:
                p_id_str = str(p.post_id)
                fp = self.compute_post_fingerprint(p)
                # Deduplication check
                if p_id_str not in seen_pids and fp not in seen_fps:
                    found_new_posts.append(p)
                    seen_pids.add(p_id_str)
                    seen_fps.add(fp)
                    if p_id_str not in seen_pids_list:
                        seen_pids_list.append(p_id_str)
                    if fp not in seen_fps_list:
                        seen_fps_list.append(fp)

        # Update saved state
        topic_state["title"] = current_title
        topic_state["op_hash"] = current_op_hash
        topic_state["max_start"] = meta.max_start
        topic_state["seen_post_ids"] = seen_pids_list[-500:]
        topic_state["seen_fingerprints"] = seen_fps_list[-300:]

        # Also add to feed state
        feed_state = self.state.setdefault("feed", {})
        feed_pids = [str(pid) for pid in feed_state.setdefault("seen_post_ids", [])]
        for p in found_new_posts:
            if str(p.post_id) not in feed_pids:
                feed_pids.append(str(p.post_id))
        feed_state["seen_post_ids"] = feed_pids[-1000:]

        self.save_state()

        # Sort posts by numeric ID so they are posted in chronological order
        found_new_posts.sort(key=lambda p: int(p.post_id) if p.post_id.isdigit() else 0)

        return TopicUpdateEvents(
            topic_id=topic_id,
            topic_title=current_title,
            new_posts=found_new_posts,
            title_change=title_change,
            op_update=op_update
        )

    def check_subforum(self, forum_id: str, is_first_run_init: bool = False) -> List[Dict[str, str]]:
        """
        Polls a subforum (e.g. f=10 Main Forum) and returns any brand new game threads.
        """
        f_id = self.scraper.extract_forum_id(forum_id)
        subforums_state = self.state.setdefault("subforums", {})
        subforum_state = subforums_state.setdefault(f_id, {
            "seen_topic_ids": []
        })

        seen_set = set(str(tid) for tid in subforum_state.get("seen_topic_ids", []))
        topics = self.scraper.get_subforum_topics(f_id)
        if not topics:
            return []

        new_threads = []
        for t in topics:
            t_id = str(t["topic_id"])
            if t_id not in seen_set:
                new_threads.append(t)
                seen_set.add(t_id)

        if is_first_run_init or not subforum_state.get("seen_topic_ids"):
            subforum_state["seen_topic_ids"] = list(seen_set)
            self.save_state()
            return []

        subforum_state["seen_topic_ids"] = list(seen_set)
        self.save_state()
        return new_threads

    def check_live_feed(self, forum_id: str = "10") -> List[ForumPost]:
        """
        Polls the global Atom feed across all games for newly published releases,
        repacks, bypasses, and Steam version/build updates with full deduplication.
        """
        f_id = self.scraper.extract_forum_id(forum_id)
        feed_state = self.state.setdefault("feed", {})
        seen_pids_list = [str(pid) for pid in feed_state.setdefault("seen_post_ids", [])]
        seen_pids_set = set(seen_pids_list)
        seen_fps_list = list(feed_state.setdefault("seen_fingerprints", []))
        seen_fps_set = set(seen_fps_list)

        feed_posts = self.scraper.get_live_forum_feed(f_id)
        if not feed_posts:
            return []

        # If first run of live feed, mark current entries as seen to avoid posting old history
        if not seen_pids_set:
            logger.info("Initializing global live feed. Marking existing entries as seen...")
            for p in feed_posts:
                pid = str(p.post_id)
                fp = self.compute_post_fingerprint(p)
                if pid not in seen_pids_set:
                    seen_pids_list.append(pid)
                    seen_pids_set.add(pid)
                if fp not in seen_fps_set:
                    seen_fps_list.append(fp)
                    seen_fps_set.add(fp)
            feed_state["seen_post_ids"] = seen_pids_list[-1000:]
            feed_state["seen_fingerprints"] = seen_fps_list[-600:]
            self.save_state()
            return []

        new_items = []
        for p in feed_posts:
            p_id_str = str(p.post_id)
            fp = self.compute_post_fingerprint(p)

            # Cross-check topic state if topic is tracked
            topic_state = self.state.get("topics", {}).get(str(p.topic_id), {})
            topic_pids = set(str(pid) for pid in topic_state.get("seen_post_ids", []))
            topic_fps = set(topic_state.get("seen_fingerprints", []))

            if p_id_str not in seen_pids_set and fp not in seen_fps_set and p_id_str not in topic_pids and fp not in topic_fps:
                new_items.append(p)
                seen_pids_list.append(p_id_str)
                seen_pids_set.add(p_id_str)
                seen_fps_list.append(fp)
                seen_fps_set.add(fp)
                
                # Also mark seen in topic state if tracked
                if p.topic_id and str(p.topic_id) in self.state.get("topics", {}):
                    t_seen = self.state["topics"][str(p.topic_id)].setdefault("seen_post_ids", [])
                    if p_id_str not in t_seen:
                        t_seen.append(p_id_str)

        feed_state["seen_post_ids"] = seen_pids_list[-1000:]
        feed_state["seen_fingerprints"] = seen_fps_list[-600:]
        self.save_state()
        return new_items

    def check_steam_client_version(self) -> List[Dict[str, Any]]:
        """
        Monitors official Steam Client updates directly from Valve's official sources:
        1. Stable Client channel: Valve ISteamNews API for AppID 593110 (Steam Client).
        2. Beta Client channel: Valve Steam Client Beta RSS announcements.
        Returns a list of new version updates, converted to Kuala Lumpur Time (GMT+8).
        """
        from steam_client_watcher import check_steam_client_updates
        client_state = self.state.setdefault("steam_client", {})

        last_seen_stable = int(client_state.get("last_seen_date_stable") or client_state.get("last_seen_date", 0))
        last_seen_beta = int(client_state.get("last_seen_date_beta", 0))

        updates, new_stable, new_beta = check_steam_client_updates(
            last_seen_stable=last_seen_stable,
            last_seen_beta=last_seen_beta
        )

        if new_stable:
            client_state["last_seen_date_stable"] = new_stable
            client_state["last_seen_date"] = new_stable
        if new_beta:
            client_state["last_seen_date_beta"] = new_beta

        if updates:
            for upd in updates:
                logger.info(f"Detected Steam Client Update on {upd.get('branch_display', 'Steam')}! Title: {upd.get('title')} (Date: {upd.get('date')})")
            self.save_state()

        return updates

    def is_release_duplicate(self, topic_id: str, release_name: Optional[str]) -> bool:
        """Checks if this specific release tag was already broadcasted for this game."""
        if not release_name:
            return False
        clean_tag = re.sub(r'[^a-zA-Z0-9]', '', release_name.lower())
        sig = f"{topic_id}:{clean_tag}"
        sigs = set(self.state.setdefault("seen_release_signatures", []))
        return sig in sigs

    def mark_release_seen(self, topic_id: str, release_name: Optional[str]):
        """Records the release signature so mirrors / duplicate reposts are ignored."""
        if not release_name:
            return
        clean_tag = re.sub(r'[^a-zA-Z0-9]', '', release_name.lower())
        sig = f"{topic_id}:{clean_tag}"
        sigs = self.state.setdefault("seen_release_signatures", [])
        if sig not in sigs:
            sigs.append(sig)
            self.state["seen_release_signatures"] = sigs[-600:]
            self.save_state()

    def extract_download_links(self, text: str) -> List[str]:
        """Extracts normalized download URLs / magnets from post text for deduplication."""
        patterns = [
            r'magnet:\?xt=[a-zA-Z0-9:+%._-]+',
            r'https?://(?:www\.)?(?:mega\.nz|pixeldrain\.com|1fichier\.com|gofile\.io|mediafire\.com|qiwi\.gg|rapidgator\.net|drive\.google\.com|multiup\.(?:org|io)|krakenfiles\.com|ddownload\.com|buzzheavier\.com|datanodes\.to)/[^\s)\]"\'>]+'
        ]
        links = []
        for pat in patterns:
            for match in re.findall(pat, text, re.IGNORECASE):
                norm = match.rstrip(".,;!?'\"<>")
                links.append(norm)
        return list(dict.fromkeys(links))

    def is_link_duplicate(self, topic_id: str, links: List[str]) -> bool:
        """Returns True if ALL links in this post have already been broadcasted for this topic."""
        if not links:
            return False
        seen_links = set(self.state.setdefault("seen_download_links", []))
        return all(f"{topic_id}:{lnk.lower()}" in seen_links for lnk in links)

    def mark_links_seen(self, topic_id: str, links: List[str]):
        """Records download links so reposted mirrors and quote replies are ignored."""
        if not links:
            return
        seen_links = self.state.setdefault("seen_download_links", [])
        for lnk in links:
            key = f"{topic_id}:{lnk.lower()}"
            if key not in seen_links:
                seen_links.append(key)
        self.state["seen_download_links"] = seen_links[-1000:]
        self.save_state()

    def check_fitgirl_updates(self) -> List[Dict[str, Any]]:
        """Checks for new FitGirl Repacks."""
        from external_monitors import check_fitgirl_feed
        updates = check_fitgirl_feed(self.state)
        self.save_state()
        return updates

    def check_dodi_updates(self) -> List[Dict[str, Any]]:
        """Checks for new DODI Repacks."""
        from external_monitors import check_dodi_feed
        updates = check_dodi_feed(self.state)
        self.save_state()
        return updates

    def check_crackwatch_updates(self) -> List[Dict[str, Any]]:
        """Checks for new releases and announcements on Reddit r/CrackWatch."""
        from external_monitors import check_crackwatch_reddit
        updates = check_crackwatch_reddit(self.state)
        self.save_state()
        return updates

    def check_steamrip_updates(self) -> List[Dict[str, Any]]:
        """Checks for newly published games and updates on SteamRIP (https://steamrip.com/)."""
        from external_monitors import check_steamrip_updates
        updates = check_steamrip_updates(self.state)
        self.save_state()
        return updates

    def check_suo_updates(self) -> List[Dict[str, Any]]:
        """Checks for newly published games on SteamUnlock Wannabe (https://steamunlockonennabe.click/)."""
        from external_monitors import check_suo_updates
        updates = check_suo_updates(self.state)
        self.save_state()
        return updates

    def check_steam_deals(self) -> List[Dict[str, Any]]:
        """Checks for newly featured Steam deals and promotions with MYR prices."""
        from external_monitors import check_steam_deals
        updates = check_steam_deals(self.state)
        self.save_state()
        return updates

    def check_onlinefix_updates(self) -> List[Dict[str, Any]]:
        """Checks for newly published multiplayer & co-op fixes on Online-Fix.me."""
        from external_monitors import check_onlinefix_feed
        updates = check_onlinefix_feed(self.state)
        self.save_state()
        return updates

    def check_wemod_updates(self) -> List[Dict[str, Any]]:
        """Checks for newly released game trainers and cheat updates from WeMod / Wand."""
        from external_monitors import check_wemod_feed
        updates = check_wemod_feed(self.state)
        self.save_state()
        return updates

    def check_steam_free_games(self) -> List[Dict[str, Any]]:
        """Checks for 100% free Steam games and limited-time giveaways."""
        from external_monitors import check_steam_free_games
        updates = check_steam_free_games(self.state)
        self.save_state()
        return updates

    def check_denuvo_status(self, watchlist: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, Any]]:
        """Tracks Denuvo Anti-Tamper removals and additions via Steam Store API and r/CrackWatch."""
        from external_monitors import check_denuvo_status
        updates = check_denuvo_status(self.state, watchlist=watchlist)
        self.save_state()
        return updates

    def check_steam_app_patches(self, monitored_apps: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, Any]]:
        """Checks for official patch notes, version updates, and depot changes for monitored Steam apps."""
        from external_monitors import check_steam_app_patches
        updates = check_steam_app_patches(self.state, monitored_apps=monitored_apps)
        self.save_state()
        return updates

    def check_steam_free_weekends(self) -> List[Dict[str, Any]]:
        """Checks for active Steam Free Weekend promotions."""
        from external_monitors import check_steam_free_weekends
        updates = check_steam_free_weekends(self.state)
        self.save_state()
        return updates



    def remove_topic(self, topic_id: str):
        topic_id = self.scraper.extract_topic_id(topic_id)
        if "topics" in self.state and topic_id in self.state["topics"]:
            del self.state["topics"][topic_id]
            self.save_state()
