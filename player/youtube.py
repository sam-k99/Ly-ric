from dataclasses import dataclass
from typing import List, Optional
from ytmusicapi import YTMusic

@dataclass
class Track:
    id: str
    title: str
    uploader: str
    duration: int  # seconds

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.id}"

    @property
    def duration_str(self) -> str:
        m, s = divmod(self.duration or 0, 60)
        return f"{m}:{s:02d}"

_ytm = YTMusic()

def _parse_duration(dur_str: str) -> int:
    parts = dur_str.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        return int(parts[0])
    except (ValueError, IndexError):
        return 0

def search(query: str, limit: int = 8) -> List[Track]:
    """Search YouTube Music for songs only."""
    results = _ytm.search(query, filter="songs", limit=limit)
    tracks = []
    for r in results:
        vid = r.get("videoId")
        if not vid:
            continue
        dur_str = r.get("duration", "0:00")
        artists = r.get("artists", [])
        uploader = artists[0].get("name", "Unknown") if artists else "Unknown"
        tracks.append(
            Track(
                id=vid,
                title=r.get("title", "Unknown"),
                uploader=uploader,
                duration=_parse_duration(dur_str),
            )
        )
    return tracks

# --- Queue System ---
_queue: List[Track] = []
_queue_index: int = 0

def build_queue(track: Track) -> None:
    """Build a radio queue from YouTube Music based on the given track."""
    global _queue, _queue_index
    try:
        result = _ytm.get_watch_playlist(videoId=track.id, limit=50, radio=True)
        _queue = []
        for item in result.get("tracks", []):
            vid = item.get("videoId")
            if not vid or vid == track.id:
                continue
            dur_str = item.get("length", "0:00")
            artists = item.get("artists", [])
            uploader = artists[0].get("name", "Unknown") if artists else "Unknown"
            _queue.append(
                Track(
                    id=vid,
                    title=item.get("title", "Unknown"),
                    uploader=uploader,
                    duration=_parse_duration(dur_str),
                )
            )
        _queue_index = 0
    except Exception:
        _queue = []
        _queue_index = 0

def get_next_from_queue() -> Optional[Track]:
    """Get next song from queue."""
    global _queue_index
    if _queue_index < len(_queue):
        track = _queue[_queue_index]
        _queue_index += 1
        return track
    return None
