import re
import html
import logging
import socket
import urllib3.util.connection as urllib_conn
from urllib.parse import urljoin, urlparse, parse_qs
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
import requests
from bs4 import BeautifulSoup, NavigableString, Tag

# Force IPv4 socket resolution to prevent Errno 101 Network is unreachable on GitHub Actions / cloud runners
try:
    urllib_conn.allowed_gai_family = lambda: socket.AF_INET
except Exception:
    pass

logger = logging.getLogger("cs_rin_scraper")

BASE_URL = "https://cs.rin.ru"
FORUM_URL = "https://cs.rin.ru/forum"

@dataclass
class ForumPost:
    post_id: str
    topic_id: str
    topic_title: str
    author: str
    author_profile_url: Optional[str]
    posted_time: str
    post_url: str
    raw_content: str
    clean_markdown: str
    images: List[str] = field(default_factory=list)
    is_op: bool = False

@dataclass
class TopicMetadata:
    topic_id: str
    title: str
    max_start: int
    op_post: Optional[ForumPost] = None
    all_starts: List[int] = field(default_factory=list)


class CsRinScraper:
    def __init__(self, session_cookie: Optional[str] = None, user_agent: Optional[str] = None):
        self.session = requests.Session()
        ua = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        self.session.headers.update({
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://cs.rin.ru/forum/",
        })
        
        # If user provided a session cookie string (e.g., "phpbb3_...=xxx; ...")
        if session_cookie:
            self._load_cookie_string(session_cookie)

    def _load_cookie_string(self, cookie_str: str):
        for part in cookie_str.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                self.session.cookies.set(k.strip(), v.strip(), domain="cs.rin.ru")

    def _bypass_security(self, res: requests.Response, original_url: str) -> requests.Response:
        """Solves CS.RIN.RU lightweight JS security challenge token."""
        token_match = re.search(r'securitytoken=([a-zA-Z0-9_-]+)', res.text)
        exp_match = re.search(r'securitytoken_expiration=([0-9]+)', res.text)

        if not token_match or not exp_match:
            logger.warning("401 encountered, but could not extract security token regex.")
            return res

        token = token_match.group(1)
        exp = exp_match.group(1)
        logger.debug(f"Handling CS.RIN security challenge with token={token[:6]}...")

        self.session.cookies.set("securitytoken", token, domain="cs.rin.ru")
        self.session.cookies.set("securitytoken_expiration", exp, domain="cs.rin.ru")

        # The script does: newURL = newURL.replace(location.pathname, "/securitycheck" + location.pathname)
        parsed = urlparse(original_url)
        path = parsed.path
        if not path.startswith("/"):
            path = "/" + path
        sec_path = "/securitycheck" + path
        query_part = f"?{parsed.query}" if parsed.query else ""
        sec_url = f"{parsed.scheme}://{parsed.netloc}{sec_path}{query_part}"

        sec_res = self.session.get(sec_url, allow_redirects=True, timeout=15)
        return sec_res

    def fetch_html(self, url: str) -> str:
        """Fetches page HTML with automatic security challenge bypass."""
        res = self.session.get(url, timeout=15)
        if res.status_code == 401 and "securitytoken=" in res.text:
            res = self._bypass_security(res, url)
        
        if res.status_code != 200:
            logger.error(f"Failed to fetch {url}: HTTP {res.status_code}")
            return ""

        return res.text

    @staticmethod
    def extract_topic_id(url_or_id: str) -> str:
        """Extracts topic ID integer string from URL or raw ID."""
        url_or_id = str(url_or_id).strip()
        if url_or_id.isdigit():
            return url_or_id
        parsed = urlparse(url_or_id)
        qs = parse_qs(parsed.query)
        if "t" in qs:
            return qs["t"][0]
        match = re.search(r't[=-](\d+)', url_or_id)
        if match:
            return match.group(1)
        return url_or_id

    @staticmethod
    def extract_forum_id(url_or_id: str) -> str:
        """Extracts subforum ID (f=...) from URL or raw ID."""
        url_or_id = str(url_or_id).strip()
        if url_or_id.isdigit():
            return url_or_id
        parsed = urlparse(url_or_id)
        qs = parse_qs(parsed.query)
        if "f" in qs:
            return qs["f"][0]
        match = re.search(r'f[=-](\d+)', url_or_id)
        if match:
            return match.group(1)
        return url_or_id

    def get_subforum_topics(self, forum_id: str) -> List[Dict[str, str]]:
        """Scrapes the list of topics from a subforum section (e.g., f=10 Main Forum)."""
        f_id = self.extract_forum_id(forum_id)
        url = f"{FORUM_URL}/viewforum.php?f={f_id}"
        html_text = self.fetch_html(url)
        if not html_text:
            return []

        soup = BeautifulSoup(html_text, "html.parser")
        topics = []
        for a in soup.find_all("a", class_="topictitle"):
            href = a.get("href", "")
            title = a.get_text(strip=True)
            m = re.search(r't=(\d+)', href)
            if m:
                t_id = m.group(1)
                full_url = f"{FORUM_URL}/viewtopic.php?t={t_id}"
                topics.append({
                    "topic_id": t_id,
                    "title": title,
                    "url": full_url
                })
        return topics

    def get_live_forum_feed(self, forum_id: str = "10") -> List[ForumPost]:
        """
        Fetches the live Atom feed from CS.RIN.RU (e.g. f=10 Main Forum)
        and parses all recent posts across all games into ForumPost objects.
        """
        import xml.etree.ElementTree as ET
        f_id = self.extract_forum_id(forum_id)
        url = f"{FORUM_URL}/feed.php?f={f_id}"
        xml_data = self.fetch_html(url)
        if not xml_data:
            return []

        # Replace HTML entities that break strict XML parsers
        clean_xml = re.sub(r'&nbsp;', '&#160;', xml_data)
        clean_xml = re.sub(r'&bull;', '&#8226;', clean_xml)
        clean_xml = re.sub(r'&hellip;', '&#8230;', clean_xml)
        clean_xml = re.sub(r'&mdash;', '&#8212;', clean_xml)
        clean_xml = re.sub(r'&ndash;', '&#8211;', clean_xml)
        clean_xml = re.sub(r'&copy;', '&#169;', clean_xml)
        clean_xml = re.sub(r'&reg;', '&#174;', clean_xml)
        clean_xml = re.sub(r'&trade;', '&#8482;', clean_xml)
        clean_xml = re.sub(r'&rsquo;', '&#8217;', clean_xml)
        clean_xml = re.sub(r'&lsquo;', '&#8216;', clean_xml)
        clean_xml = re.sub(r'&rdquo;', '&#8220;', clean_xml)
        clean_xml = re.sub(r'&ldquo;', '&#8221;', clean_xml)

        try:
            root = ET.fromstring(clean_xml)
        except Exception as e:
            logger.error(f"Failed to parse Atom feed XML: {e}")
            return []

        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        posts = []
        for e in root.findall('atom:entry', ns):
            raw_title = e.find('atom:title', ns).text if e.find('atom:title', ns) is not None else ''
            link = e.find('atom:link', ns).attrib.get('href', '')
            content_html = e.find('atom:content', ns).text if e.find('atom:content', ns) is not None else ''
            author_el = e.find('atom:author/atom:name', ns)
            author = author_el.text if author_el is not None else 'Anonymous'
            published_el = e.find('atom:published', ns)
            published = published_el.text if published_el is not None else ''

            # Clean game title (strip 'Main Forum • Re: ' or similar prefixes)
            clean_title = re.sub(r'^(?:Main Forum\s*[•\-]\s*)+(?:Re:\s*)?', '', raw_title).strip()
            if not clean_title:
                clean_title = raw_title

            m_p = re.search(r'p=(\d+)', link)
            m_t = re.search(r't=(\d+)', link)
            post_id = m_p.group(1) if m_p else '0'
            topic_id = m_t.group(1) if m_t else '0'

            soup_tag = BeautifulSoup(f"<div class='postbody'>{content_html}</div>", "html.parser")
            clean_md = self._html_to_markdown(soup_tag)
            images = self._extract_images(soup_tag)

            # Standardize URL to cs.rin.ru
            link = re.sub(r'https?://(?:www\.)?csrin\.org', 'https://cs.rin.ru', link)

            posts.append(ForumPost(
                post_id=post_id,
                topic_id=topic_id,
                topic_title=clean_title,
                author=author,
                author_profile_url=None,
                posted_time=published,
                post_url=link,
                raw_content=clean_md,
                clean_markdown=clean_md,
                images=images
            ))

        return posts

    def get_topic_metadata(self, topic_id: str) -> TopicMetadata:
        """Fetches the 1st page of topic to extract title, max_start pagination, and OP post."""
        topic_id = self.extract_topic_id(topic_id)
        url = f"{FORUM_URL}/viewtopic.php?t={topic_id}"
        html_text = self.fetch_html(url)
        if not html_text:
            return TopicMetadata(topic_id=topic_id, title="Unknown", max_start=0)

        soup = BeautifulSoup(html_text, "html.parser")
        
        # Topic Title
        title = "CS.RIN Topic"
        maintitle = soup.find("a", class_="maintitle")
        if maintitle:
            title = maintitle.get_text(strip=True)
        elif soup.title:
            title_text = soup.title.get_text(strip=True)
            # e.g. "CS RIN - Steam Underground • View topic - SHINOBI: ..."
            if "View topic -" in title_text:
                title = title_text.split("View topic -", 1)[-1].strip()
            else:
                title = title_text

        # Pagination
        starts = [0]
        for a in soup.find_all("a", href=re.compile(r'start=\d+')):
            m = re.search(r'start=(\d+)', a.get("href"))
            if m:
                starts.append(int(m.group(1)))
        
        max_start = max(starts)
        all_starts = sorted(list(set(starts)))

        # OP Post (First post on page 1)
        op_post = None
        posts_on_page = self._parse_posts_from_soup(soup, topic_id, title)
        if posts_on_page:
            op_post = posts_on_page[0]
            op_post.is_op = True

        return TopicMetadata(
            topic_id=topic_id,
            title=title,
            max_start=max_start,
            op_post=op_post,
            all_starts=all_starts
        )

    def get_posts_page(self, topic_id: str, start: int = 0, topic_title: str = "") -> List[ForumPost]:
        """Fetches posts from a specific page start index."""
        topic_id = self.extract_topic_id(topic_id)
        url = f"{FORUM_URL}/viewtopic.php?t={topic_id}&start={start}"
        html_text = self.fetch_html(url)
        if not html_text:
            return []

        soup = BeautifulSoup(html_text, "html.parser")
        if not topic_title:
            maintitle = soup.find("a", class_="maintitle")
            if maintitle:
                topic_title = maintitle.get_text(strip=True)
            elif soup.title:
                topic_title = soup.title.get_text(strip=True)

        return self._parse_posts_from_soup(soup, topic_id, topic_title)

    def _parse_posts_from_soup(self, soup: BeautifulSoup, topic_id: str, topic_title: str) -> List[ForumPost]:
        """Parses all post bodies and authors from the phpBB subsilver2 table structure."""
        posts = []
        tables = soup.find_all("table", class_="tablebg")

        for table in tables:
            postbody = table.find("div", class_="postbody")
            if not postbody:
                continue

            # Post ID
            post_id = None
            post_link_tag = table.find("a", href=re.compile(r'p=(\d+)'))
            if post_link_tag:
                m = re.search(r'p=(\d+)', post_link_tag.get("href"))
                if m:
                    post_id = m.group(1)

            if not post_id:
                # Try finding in anchors inside table
                anchor = table.find("a", attrs={"name": re.compile(r'^p\d+')})
                if anchor and anchor.get("name"):
                    post_id = anchor.get("name")[1:]

            if not post_id:
                continue

            # Author
            author_tag = table.find("b", class_="postauthor")
            author = author_tag.get_text(strip=True) if author_tag else "Anonymous"

            # Profile link
            profile_url = None
            if author_tag:
                p_link = author_tag.find_parent("a") or author_tag.find("a")
                if p_link and p_link.get("href"):
                    profile_url = urljoin(FORUM_URL + "/", p_link.get("href"))

            # Posted time
            posted_time = ""
            for td in table.find_all("td"):
                txt = td.get_text()
                if "Posted:" in txt:
                    m_time = re.search(r'Posted:\s*([^\n\r]+)', txt)
                    if m_time:
                        posted_time = m_time.group(1).strip()
                        break

            # Images in post body
            images = self._extract_images(postbody)

            # Markdown conversion
            clean_md = self._html_to_markdown(postbody)

            if topic_id and topic_id != "0":
                post_url = f"{FORUM_URL}/viewtopic.php?t={topic_id}&p={post_id}#p{post_id}"
            else:
                post_url = f"{FORUM_URL}/viewtopic.php?p={post_id}#p{post_id}"

            posts.append(ForumPost(
                post_id=post_id,
                topic_id=topic_id,
                topic_title=topic_title,
                author=author,
                author_profile_url=profile_url,
                posted_time=posted_time,
                post_url=post_url,
                raw_content=postbody.get_text(separator="\n", strip=True),
                clean_markdown=clean_md,
                images=images
            ))

        return posts

    def _extract_images(self, postbody: Tag) -> List[str]:
        """Extracts valid image URLs, ignoring smileys, icons, and transparent spacers."""
        images = []
        for img in postbody.find_all("img"):
            src = img.get("src", "").strip()
            if not src:
                continue
            src_lower = src.lower()
            if any(skip in src_lower for skip in [
                "spacer.gif", "images/smiles", "images/smilies", 
                "icon_platform", "icon_singleplayer", "icon_achievements", 
                "icon_cards", "icon_cloud"
            ]):
                continue
            full_url = urljoin(FORUM_URL + "/", src)
            if full_url not in images:
                images.append(full_url)
        return images

    def _html_to_markdown(self, element: Tag) -> str:
        """Converts phpBB post HTML elements to readable Discord Markdown."""
        # Work on a clone
        clone = BeautifulSoup(str(element), "html.parser")
        root = clone.find("div", class_="postbody") or clone

        # Remove signature if attached at bottom
        for sig in root.find_all(text=re.compile(r'_________________')):
            parent = sig.parent
            if parent:
                parent.decompose()

        # Convert line breaks first so text extraction preserves newlines
        for br in root.find_all("br"):
            br.replace_with(NavigableString("\n"))

        # Handle Quotes: <div class="quotetitle"><b>Author wrote:</b></div><div class="quotecontent">...</div>
        for quote_content in root.find_all("div", class_="quotecontent"):
            quote_text = quote_content.get_text()
            # Find quote title if present
            title_tag = quote_content.find_previous_sibling("div", class_="quotetitle")
            author_text = title_tag.get_text(strip=True) if title_tag else "Quote:"
            if title_tag:
                title_tag.decompose()
            
            # Convert to blockquote
            bq_lines = [f"> {line.strip()}" for line in quote_text.splitlines() if line.strip()]
            formatted_quote = f"\n> **{author_text}**\n" + "\n".join(bq_lines) + "\n"
            quote_content.replace_with(NavigableString(formatted_quote))

        # Handle <blockquote> tags
        for bq in root.find_all("blockquote"):
            bq_text = bq.get_text()
            bq_lines = [f"> {line.strip()}" for line in bq_text.splitlines() if line.strip()]
            formatted_bq = "\n" + "\n".join(bq_lines) + "\n"
            bq.replace_with(NavigableString(formatted_bq))

        # Clean all codetitle and quotetitle buttons / UI elements first
        for title_tag in root.find_all("div", class_=["codetitle", "quotetitle"]):
            title_tag.decompose()

        # Handle Code blocks: <div class="codecontent">...</div>
        box_chars = set("░▒▓█▀▄▌▐■═║╔╗╚╝─│┌┐└┘▲▼►◄◆◇○●☺☻")
        for code in root.find_all("div", class_="codecontent"):
            code_text = code.get_text()
            # If code block is predominantly ASCII art / NFO banners, strip it
            if any(c in box_chars for c in code_text) or len(code_text) > 800:
                code.decompose()
            else:
                code.replace_with(NavigableString(f"\n```\n{code_text.strip()}\n```\n"))

        # Handle Links: <a href="...">...</a>
        for a in root.find_all("a"):
            href = a.get("href", "").strip()
            link_text = a.get_text(strip=True) or href
            if not href:
                continue
            full_href = urljoin(FORUM_URL + "/", href)
            # Avoid markdown link loop if link_text is the URL itself
            if link_text == href or link_text == full_href:
                a.replace_with(NavigableString(f" {full_href} "))
            else:
                a.replace_with(NavigableString(f" [{link_text}]({full_href}) "))

        # Handle bold, italic, underline
        for b in root.find_all(["b", "strong"]):
            b.replace_with(NavigableString(f"**{b.get_text()}**"))
        for i in root.find_all(["i", "em"]):
            i.replace_with(NavigableString(f"*{i.get_text()}*"))
        for u in root.find_all("u"):
            u.replace_with(NavigableString(f"__{u.get_text()}__"))

        # Convert line breaks
        for br in root.find_all("br"):
            br.replace_with(NavigableString("\n"))

        text = root.get_text()
        # Clean up forum "Please login to see this link" placeholders
        text = re.sub(r'\[\[Please login to see this link\.\]\]', '*(link)*', text)
        # Clean multiple spaces and blank lines
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()
        return text
