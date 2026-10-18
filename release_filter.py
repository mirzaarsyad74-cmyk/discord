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
    r'\bcaviator\b', r'\bempress\b', r'\bhypervisor\b'
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

# Patterns representing questions or casual chatter (to exclude false positives)
QUESTION_PATTERNS = [
    r'(?i)\b(?:any|when|where|is there|does anyone have|how to|can someone|will there be)\b.*\b(?:crack|repack|bypass|csf|update)\b.*\?',
    r'(?i)\b(?:crack|bypass|repack|csf)\s*(?:when|eta|pls|please)\b',
    r'(?i)^(?:thanks?|thx|thank you|working|works|good job|tested|save game|anyone have this)\b'
]

# Structural markers common in real releases
RELEASE_STRUCTURES = [
    r'\[\s*\d+(?:\.\d+)?\s*(?:MB|GB)\s*\]',                  # e.g. [5855 MB] or [10.80 GB]
    r'(?i)\b(?:archive|download|file)\s*size\s*:\s*\d+',    # e.g. Archive size: 10.80 GB
    r'(?i)\bbuild\s*(\d{5,})\b',                            # e.g. Build 22016198
    r'\b[A-Za-z0-9._]+-(?:ElAmigos|RUNE|TENOKE|FLT|CODEX|SKIDROW|HYPERViSOR|Razor1911)\b',  # Scene tag
    r'(?i)\b(?:selective download|lossless|repack features|nfo)\b'
]


def classify_release(post: ForumPost, custom_keywords: Optional[List[str]] = None) -> Tuple[bool, Optional[str]]:
    """
    Analyzes a forum post to determine if it is:
    1. A Steam Version / Build / Patch / CSF Update
    2. A Repack (FitGirl, ElAmigos, DODI, etc.)
    3. A Bypass / Hypervisor release
    4. A Scene Crack (RUNE, TENOKE, FLT, etc.)
    Returns (is_release: bool, release_type_label: Optional[str]).
    """
    # 1. Strip blockquotes so we only inspect the author's new text
    own_text = re.sub(r'(?m)^>.*$', '', post.clean_markdown).strip()
    if not own_text or len(own_text) < 10:
        return False, None

    # 2. Check for question patterns / casual banter
    for q_pattern in QUESTION_PATTERNS:
        if re.search(q_pattern, own_text):
            has_structure = any(re.search(pat, own_text) for pat in RELEASE_STRUCTURES)
            if not has_structure:
                return False, None

    # 3. Detect Steam Version / Clean Steam Files (CSF) / Build updates
    build_match = re.search(r'(?i)\bbuild\s*(\d{5,})\b', own_text)
    is_csf = bool(re.search(r'(?i)\b(?:csf|clean steam files)\b', own_text))
    is_steam_update = any(re.search(pat, own_text) for pat in STEAM_VERSION_PATTERNS)

    if (is_csf or build_match) and (len(own_text) > 15):
        if build_match:
            return True, f"Steam Version Update (Build {build_match.group(1)})"
        return True, "Steam Version Update (CSF)"

    # 4. Detect Repackers
    repacker_found = None
    for pat in REPACKERS:
        m = re.search(pat, own_text, re.IGNORECASE)
        if m:
            repacker_found = m.group(0).capitalize()
            break

    # 5. Detect Scene Groups
    scene_found = None
    for pat in SCENE_GROUPS:
        m = re.search(pat, own_text, re.IGNORECASE)
        if m:
            scene_found = m.group(0).upper()
            break

    # 6. Detect Bypasses / Hypervisors
    if re.search(r'(?i)\b(?:hypervisor|bypass)\b', own_text):
        tag = f"{repacker_found or scene_found or ''} Bypass / Hypervisor".strip()
        return True, tag

    # 7. Detect Repacks
    if repacker_found and (re.search(r'(?i)\brepack\b', own_text) or any(re.search(pat, own_text) for pat in RELEASE_STRUCTURES)):
        return True, f"{repacker_found} Repack"

    # 8. Detect Scene Cracks
    if scene_found and (re.search(r'(?i)\bcrack(?:ed)?\b', own_text) or any(re.search(pat, own_text) for pat in RELEASE_STRUCTURES)):
        return True, f"{scene_found} Crack Release"

    # 9. Generic Scene release structure (e.g. Game.Name-GROUP)
    scene_tag_match = re.search(r'\b[A-Za-z0-9._]+-(?:ElAmigos|RUNE|TENOKE|FLT|CODEX|SKIDROW|Razor1911)\b', own_text)
    if scene_tag_match:
        return True, f"Scene Release ({scene_tag_match.group(0).split('-')[-1]})"

    return False, None
