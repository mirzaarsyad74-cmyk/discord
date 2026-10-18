import os
import json
import hashlib
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
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

    def _load_state(self) -> Dict[str, Any]:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error reading state file {self.state_file}: {e}")
        return {"topics": {}}

    def save_state(self):
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error writing state file: {e}")

    def check_topic(self, topic_id: str, is_first_run_init: bool = False) -> TopicUpdateEvents:
        """
        Polls a topic on CS.RIN.RU:
        - Detects title changes (e.g. [NOT CRACKED] -> [CRACKED])
        - Detects OP post modifications
        - Detects new replies / posts
        """
        topic_id = self.scraper.extract_topic_id(topic_id)
        topics_state = self.state.setdefault("topics", {})
        topic_state = topics_state.setdefault(topic_id, {
            "title": "",
            "op_hash": "",
            "max_start": 0,
            "seen_post_ids": []
        })

        seen_set = set(topic_state.get("seen_post_ids", []))
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
            if last_op_hash and last_op_hash != current_op_hash:
                logger.info(f"Topic {topic_id} OP post updated!")
                op_update = meta.op_post

        # Step 2: Determine pages to fetch for new posts
        # If max_start is greater than last_max_start, we should scan from last_max_start to current max_start
        pages_to_check = [start for start in meta.all_starts if start >= last_max_start]
        if not pages_to_check:
            pages_to_check = [meta.max_start]

        found_new_posts: List[ForumPost] = []
        for start in pages_to_check:
            posts = self.scraper.get_posts_page(topic_id, start=start, topic_title=current_title)
            for p in posts:
                if p.post_id not in seen_set:
                    found_new_posts.append(p)
                    seen_set.add(p.post_id)

        # If this is initial run and user doesn't want backfilled notifications
        if is_first_run_init or not last_title:
            logger.info(f"Initialized topic {topic_id} tracking with {len(seen_set)} existing posts.")
            topic_state["title"] = current_title
            topic_state["op_hash"] = current_op_hash
            topic_state["max_start"] = meta.max_start
            topic_state["seen_post_ids"] = list(seen_set)
            self.save_state()
            return TopicUpdateEvents(
                topic_id=topic_id,
                topic_title=current_title,
                new_posts=[]
            )

        # Update saved state
        topic_state["title"] = current_title
        topic_state["op_hash"] = current_op_hash
        topic_state["max_start"] = meta.max_start
        topic_state["seen_post_ids"] = list(seen_set)
        self.save_state()

        # Sort posts by numeric ID so they are posted sequentially
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

        seen_set = set(subforum_state.get("seen_topic_ids", []))
        topics = self.scraper.get_subforum_topics(f_id)
        if not topics:
            return []

        new_threads = []
        for t in topics:
            t_id = t["topic_id"]
            if t_id not in seen_set:
                new_threads.append(t)
                seen_set.add(t_id)

        # On first run, mark existing topics as seen so we don't spam 100 historical threads
        if is_first_run_init or not subforum_state.get("seen_topic_ids"):
            subforum_state["seen_topic_ids"] = list(seen_set)
            self.save_state()
            return []

        subforum_state["seen_topic_ids"] = list(seen_set)
        self.save_state()
        return new_threads

    def remove_topic(self, topic_id: str):
        topic_id = self.scraper.extract_topic_id(topic_id)
        if "topics" in self.state and topic_id in self.state["topics"]:
            del self.state["topics"][topic_id]
            self.save_state()
