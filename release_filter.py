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

# Patterns representing questions or casual chatter (to exclude false positives)
QUESTION_PATTERNS = [
    r'(?i)\b(?:any|when|where|is there|does anyone have|how to|can someone|will there be)\b.*\b(?:crack|repack|bypass)\b.*\?',
    r'(?i)\b(?:crack|bypass|repack)\s*(?:when|eta|pls|please)\b',
    r'(?i)^(?:thanks?|thx|thank you|working|works|good job|tested|save game)\b'
]

# Structural markers common in real releases
RELEASE_STRUCTURES = [
    r'\[\s*\d+(?:\.\d+)?\s*(?:MB|GB)\s*\]',                  # e.g. [5855 MB] or [10.80 GB]
    r'(?i)\b(?:archive|download|file)\s*size\s*:\s*\d+',    # e.g. Archive size: 10.80 GB
    r'(?i)\bbuild\s*\d{6,}\b',                              # e.g. Build 22016198
    r'\b[A-Za-z0-9._]+-(?:ElAmigos|RUNE|TENOKE|FLT|CODEX|SKIDROW|HYPERViSOR|Razor1911)\b',  # Scene tag
    r'(?i)\b(?:selective download|lossless|repack features|nfo)\b'
]


def classify_release(post: ForumPost, custom_keywords: Optional[List[str]] = None) -> Tuple[bool, Optional[str]]:
    """
    Analyzes a forum post to determine if it is an actual repack, bypass, or crack release.
    Returns (is_release: bool, release_type_label: Optional[str]).
    """
    # 1. Strip blockquotes so we only inspect the author's new text, not quoted text from other users
    own_text = re.sub(r'(?m)^>.*$', '', post.clean_markdown).strip()
    if not own_text or len(own_text) < 15:
        return False, None

    # 2. Check for question patterns / casual banter
    for q_pattern in QUESTION_PATTERNS:
        if re.search(q_pattern, own_text):
            # If the post is primarily asking a question without a release structure, skip it
            has_structure = any(re.search(pat, own_text) for pat in RELEASE_STRUCTURES)
            if not has_structure:
                return False, None

    # 3. Detect specific repacker or group
    detected_tags = []
    
    for pat in REPACKERS:
        m = re.search(pat, own_text, re.IGNORECASE)
        if m:
            detected_tags.append(m.group(0).capitalize())

    for pat in SCENE_GROUPS:
        m = re.search(pat, own_text, re.IGNORECASE)
        if m:
            detected_tags.append(m.group(0).upper())

    # Check custom keywords
    if custom_keywords:
        for kw in custom_keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', own_text, re.IGNORECASE):
                detected_tags.append(kw.upper())

    # 4. Check core release terms
    matched_core = []
    for pat in CORE_RELEASE_TERMS:
        m = re.search(pat, own_text, re.IGNORECASE)
        if m:
            matched_core.append(m.group(0).title())

    # 5. Check structural release markers (size, build, scene tag)
    matched_structure = any(re.search(pat, own_text) for pat in RELEASE_STRUCTURES)

    # Classification logic:
    # A true release has (Repacker/Scene Group OR Core Term) AND either:
    # - A release structure (size/build/scene tag)
    # - Multiple release keywords
    # - Or strong terms like "repack", "bypass", "crack" coupled with group name
    if detected_tags and (matched_core or matched_structure):
        tag_str = f"{'/'.join(set(detected_tags[:2]))} {'/'.join(set(matched_core[:2]))}".strip()
        return True, tag_str

    if matched_core and matched_structure:
        tag_str = f"{'/'.join(set(matched_core[:2]))} Release"
        return True, tag_str

    # Clean Steam Files release detection
    if re.search(r'(?i)\b(?:csf|clean steam files)\b', own_text) and matched_structure:
        return True, "Clean Steam Files"

    # Hypervisor or standalone bypass detection
    if re.search(r'(?i)\b(?:hypervisor|bypass)\b', own_text) and (matched_structure or len(own_text) > 80):
        return True, "Bypass / Hypervisor"

    return False, None
