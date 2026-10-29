import re
from typing import Tuple, Optional, List
from scraper import ForumPost

# Well-known repackers, scene groups, and bypass creators
REPACKERS = [
    r'\bfitgirl\b', r'\belamigos\b', r'\bdodi\b', r'\bkaos\b',
    r'\bxatab\b', r'\bchotya\b', r'\btinyrepack\b', r'\bgoldberg\b'
]

SCENE_GROUPS = [
    r'\brune\b', r'\btenoke\b', r'\bflt\b', r'\bfairlight\b',
    r'\bcodex\b', r'\bskidrow\b', r'\bplaza\b', r'\brazor1911\b',
    r'\bcaviator\b', r'\bempress\b', r'\bhypervisor\b', r'\bvoices38\b'
]

CORE_RELEASE_TERMS = [
    r'\brepack\b',
    r'\bbypass\b',
    r'\bcrack(?:ed|fix)?\b',
    r'\bdenuvo removed\b',
    r'\bdenuvo disabled\b',
    r'\bclean steam files\b',
    r'\bcsf\b',
    r'\bmanifest\b'
]

# Steam Version & Build Watch Patterns
STEAM_VERSION_PATTERNS = [
    r'(?i)\bcsf\b',
    r'(?i)\bclean steam files\b',
    r'(?i)\bbuild\s*(\d{5,})\b',
    r'(?i)\bsteam\s+(?:update|version|patch|files|build)\b',
    r'(?i)\bdepot\s+(?:update|download|keys?)\b',
    r'(?i)\bmanifest\s*id\b'
]

# Patterns representing questions, casual chatter, or troubleshooting comments (to exclude false positives)
QUESTION_PATTERNS = [
    r'(?i)\b(?:any|when|where|is there|does anyone have|how to|can someone|can somebody|can anybody|will there be|anyone got|someone have|somebody have)\b.*\b(?:crack|repack|bypass|hypervisor|csf|update|clean steam files|files?)\b',
    r'(?i)\b(?:can|could|please|pls)\s+(?:someone|somebody|anybody|anyone)\s+(?:post|share|upload|send|provide|give|dump)\b',
    r'(?i)\b(?:can\s+you\s+explain|i\s+don\'?t\s+understand|what\s+does\s+.*?\s+mean|how\s+did\s+you\s+(?:get|make|run))\b',
    r'(?i)\b(?:clean steam files|csf|crack|bypass|hypervisor|repack)\s*(?:when|eta|pls|please|\?)\b',
    r'(?i)\b(?:thanks?|thx|thank you|working|works|good job|tested|save game|anyone have this|tested on|confirm working)\b',
    r'(?i)\b(?:not working|doesn\'?t work|wont work|won\'?t work|crash(?:es|ing)?|black screen|error|failed to launch|can\'?t (?:even )?launch|cannot launch|cant launch|won\'?t launch|doesn\'?t launch)\b',
    r'(?i)\b(?:request(?:ing)?|need|looking for|still waiting|any news|any update|no crack|no bypass)\b',
    r'(?i)\b(?:false positive|virus|trojan|malware|windows defender|antivirus)\b',
    r'(?i)\b(?:where (?:do i|to) (?:put|paste|copy)|how (?:do i|to) (?:run|install|apply))\b',
    r'\?\s*$'  # Post ends with a question mark
]

# Download links or file hosts
DOWNLOAD_LINK_PATTERNS = [
    r'(?i)\b(?:https?://|magnet:\?xt=)',
    r'(?i)\b(?:mega\.nz|pixeldrain|1fichier|gofile|mediafire|qiwi|rapidgator|drive\.google\.com|multiup|krakenfiles|ddownload|buzzheavier|datanodes)\b'
]

# Structural markers common in real releases
RELEASE_STRUCTURES = [
    r'\[\s*\d+(?:\.\d+)?\s*(?:MB|GB)\s*\]',                  # e.g. [5855 MB] or [10.80 GB]
    r'(?i)\b(?:archive|download|file)\s*size\s*:\s*\d+',    # e.g. Archive size: 10.80 GB
    r'(?i)\bbuild\s*(\d{5,})\b',                            # e.g. Build 22016198
    r'\b[A-Za-z0-9._]+-(?:ElAmigos|RUNE|TENOKE|FLT|CODEX|SKIDROW|HYPERViSOR|Razor1911|EMPRESS|Voices38)\b',  # Scene tag
    r'(?i)\b(?:selective download|lossless|repack features|nfo)\b'
]


def has_release_proof(text: str) -> bool:
    """Verifies that the post actually contains a download link, magnet, or release structure."""
    has_links = any(re.search(pat, text) for pat in DOWNLOAD_LINK_PATTERNS)
    has_structure = any(re.search(pat, text) for pat in RELEASE_STRUCTURES)
    return has_links or has_structure


def classify_release(
    post: ForumPost,
    custom_keywords: Optional[List[str]] = None,
    cracks_only: bool = False
) -> Tuple[bool, Optional[str]]:
    """
    Analyzes a forum post to determine if it is:
    1. A Scene Crack (RUNE, TENOKE, FLT, EMPRESS, etc.)
    2. A Bypass / Hypervisor release (Voices38, Denuvo bypasses)
    3. A Steam Version / Build / CSF Update (skipped if cracks_only=True)
    4. A Repack (FitGirl, ElAmigos, DODI, etc. - skipped if cracks_only=True)
    Returns (is_release: bool, release_type_label: Optional[str]).
    """
    # 1. Strip blockquotes and bbcode quotes so we only inspect the author's new text (avoids matching quoted text)
    text_no_bbquote = re.sub(r'(?is)\[quote(?:=[^\]]*)?\].*?\[/quote\]?', '', post.clean_markdown)
    text_no_bbquote = re.sub(r'(?i)\[/?quote(?:=[^\]]*)?\]', '', text_no_bbquote)
    own_text = re.sub(r'(?m)^>.*$', '', text_no_bbquote).strip()
    if not own_text or len(own_text) < 10:
        return False, None

    author_lower = (post.author or "").lower()
    text_lower = own_text.lower()
    proof = has_release_proof(own_text)

    # 0. Voices38 Priority Detection (Denuvo Bypasses & Hypervisor releases)
    if author_lower == "voices38":
        if any(term in text_lower for term in ["bypass", "hypervisor", "hv"]):
            return True, "Voices38 Denuvo Bypass"
        elif any(term in text_lower for term in ["crack", "denuvo", "fix", "patch"]):
            return True, "Voices38 Denuvo Crack"
        elif proof:
            return True, "Voices38 Release"

    # Mentions of Voices38 by regular users: require proof of release so comments like "waiting for voices38" are rejected
    if re.search(r'\bvoices38\b', own_text, re.IGNORECASE):
        if any(term in text_lower for term in ["bypass", "hypervisor", "hv", "crack", "denuvo"]):
            if proof:
                return True, "Voices38 Denuvo Bypass"
            else:
                return False, None  # User chatter/comment, not a release

    # 2. Check for question patterns / casual banter / comment chatter
    for q_pattern in QUESTION_PATTERNS:
        if re.search(q_pattern, own_text):
            # If it matches chatter, only allow if it has strong proof of release AND does not end in '?'
            if not proof or own_text.rstrip().endswith("?"):
                return False, None

    # 3. Detect Steam Version / Clean Steam Files (CSF) / Build updates (skipped if cracks_only=True)
    build_match = re.search(r'(?i)\bbuild\s*(\d{5,})\b', own_text)
    is_csf = bool(re.search(r'(?i)\b(?:csf|clean steam files)\b', own_text))

    if not cracks_only:
        has_links = any(re.search(pat, own_text) for pat in DOWNLOAD_LINK_PATTERNS)
        has_structure = any(re.search(pat, own_text) for pat in RELEASE_STRUCTURES)
        if (is_csf or build_match) and (len(own_text) > 15):
            if is_csf and not (has_links or has_structure or build_match or post.is_op):
                return False, None
            if build_match:
                return True, f"Steam Version Update (Build {build_match.group(1)})"
            return True, "Steam Version Update (CSF)"

    # 4. Detect Repackers
    repacker_found = None
    for pat in REPACKERS:
        m = re.search(pat, own_text, re.IGNORECASE)
        if m:
            matched_txt = m.group(0).lower()
            if matched_txt == "fitgirl":
                repacker_found = "FitGirl"
            elif matched_txt == "dodi":
                repacker_found = "DODI"
            else:
                repacker_found = m.group(0).capitalize()
            break

    # 5. Detect Scene Groups
    scene_found = None
    for pat in SCENE_GROUPS:
        m = re.search(pat, own_text, re.IGNORECASE)
        if m:
            scene_found = m.group(0).upper()
            break

    # 6. Detect Bypasses / Hypervisors (CRITICAL: Require proof of release so comments are rejected)
    if re.search(r'(?i)\b(?:hypervisor|bypass)\b', own_text):
        if proof or author_lower == "voices38":
            tag = f"{repacker_found or scene_found or ''} Bypass / Hypervisor".strip()
            return True, tag
        else:
            return False, None

    # 7. Detect Repacks (skipped if cracks_only=True)
    if not cracks_only and repacker_found and (re.search(r'(?i)\brepack\b', own_text) or any(re.search(pat, own_text) for pat in RELEASE_STRUCTURES)):
        return True, f"{repacker_found} Repack"

    # 8. Detect Scene Cracks (e.g. RUNE crack, FLT crack, or scene group with download links)
    if scene_found and proof and (re.search(r'(?i)\bcrack(?:ed|fix)?\b', own_text) or proof):
        return True, f"{scene_found} Crack Release"

    # 9. Generic Scene release structure (e.g. Game.Name-GROUP)
    scene_tag_match = re.search(r'\b[A-Za-z0-9._]+-(?:ElAmigos|RUNE|TENOKE|FLT|CODEX|SKIDROW|Razor1911|HYPERViSOR|EMPRESS)\b', own_text)
    if scene_tag_match:
        group_name = scene_tag_match.group(0).split('-')[-1]
        if "hypervisor" in group_name.lower():
            return True, "Hypervisor Bypass Release"
        return True, f"Scene Release ({group_name})"

    # 10. Standalone crackfix / denuvo removed announcement with links
    if re.search(r'(?i)\b(?:crackfix|denuvo removed|denuvo disabled)\b', own_text) and proof:
        return True, "Crack / Denuvo Removed"

    return False, None
