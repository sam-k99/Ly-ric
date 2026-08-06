"""
Fetches synced (LRC) lyrics via the `syncedlyrics` package, which pulls
from providers like Musixmatch/NetEase/Lrclib. Falls back to plain,
unsynced lyrics from lyrics.ovh if no synced version is found.
"""

import re
from dataclasses import dataclass
from typing import List, Optional

import requests

try:
    import syncedlyrics
except ImportError:  # pragma: no cover
    syncedlyrics = None

LRC_LINE_RE = re.compile(r"\[(\d{2}):(\d{2})(?:[.:](\d{1,3}))?\](.*)")


@dataclass
class LyricLine:
    time: float  # seconds
    text: str


def _parse_lrc(lrc_text: str) -> List[LyricLine]:
    lines = []
    for raw in lrc_text.splitlines():
        m = LRC_LINE_RE.match(raw.strip())
        if not m:
            continue
        minutes, seconds, frac, text = m.groups()
        t = int(minutes) * 60 + int(seconds)
        if frac:
            t += int(frac.ljust(3, "0")) / 1000
        text = text.strip()
        if text:
            lines.append(LyricLine(time=t, text=text))
    lines.sort(key=lambda l: l.time)
    return lines


def fetch_synced(title: str, artist: str = "") -> Optional[List[LyricLine]]:
    """Try to get time-synced lyrics. Returns None if unavailable."""
    if syncedlyrics is None:
        return None
    query = f"{artist} {title}".strip() if artist else title
    try:
        lrc = syncedlyrics.search(query)
    except Exception:
        lrc = None
    if not lrc:
        return None
    parsed = _parse_lrc(lrc)
    return parsed or None


def fetch_plain(title: str, artist: str = "") -> Optional[List[str]]:
    """Fallback: plain unsynced lyrics from lyrics.ovh."""
    try:
        resp = requests.get(
            f"https://api.lyrics.ovh/v1/{artist or 'unknown'}/{title}",
            timeout=5,
        )
        if resp.status_code == 200:
            text = resp.json().get("lyrics", "")
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            return lines or None
    except Exception:
        pass
    return None
