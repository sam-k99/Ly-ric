import os
import queue
import select
import shutil
import sys
import termios
import threading
import time
import tty
from rich.live import Live
from rich.console import Console
from player import lyrics, ui
from player.mpv_controller import MPVController
from player.youtube import Track, search, build_queue, get_next_from_queue

console = Console()

def check_dependencies():
    missing = [b for b in ("mpv",) if shutil.which(b) is None]
    if missing:
        console.print(
            f"[bold red]Missing required binary: {', '.join(missing)}[/bold red]\n"
            "Install mpv first."
        )
        sys.exit(1)

class KeyListener:
    def __init__(self):
        self.q: "queue.Queue[str]" = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._fd = sys.stdin.fileno()
        self._old_settings = termios.tcgetattr(self._fd)

    def start(self):
        tty.setcbreak(self._fd)
        self._thread.start()

    def _read_char(self):
        """Read one full UTF-8 char straight from the fd (no hidden buffering)."""
        b = os.read(self._fd, 1)
        if not b:
            return ""
        c = b[0]
        if c < 0x80:
            return chr(c)
        if c >= 0xF0:
            n = 3
        elif c >= 0xE0:
            n = 2
        elif c >= 0xC0:
            n = 1
        else:
            return b.decode("utf-8", errors="replace")
        rest = b""
        while len(rest) < n:
            more = os.read(self._fd, n - len(rest))
            if not more:
                break
            rest += more
        return (b + rest).decode("utf-8", errors="replace")
    def _run(self):
        while not self._stop.is_set():
            r, _, _ = select.select([self._fd], [], [], 0.05)
            if not r:
                continue
            ch = self._read_char()
            if ch == "\x1b":
                # Arrow keys: the remaining 2 bytes sit in the fd buffer, so
                # select sees them instantly. A bare ESC times out and stays
                # "\x1b" (search mode uses that to clear).
                r2, _, _ = select.select([self._fd], [], [], 0.02)
                if r2:
                    ch += self._read_char()
                    r3, _, _ = select.select([self._fd], [], [], 0.02)
                    if r3:
                        ch += self._read_char()
                if ch == "\x1bOC":
                    ch = "\x1b[C"
                elif ch == "\x1bOD":
                    ch = "\x1b[D"
            self.q.put(ch)
    def get_nowait(self):
        try:
            return self.q.get_nowait()
        except queue.Empty:
            return None

    def stop(self):
        self._stop.set()
        termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_settings)

class SearchWorker(threading.Thread):
    def __init__(self, query: str):
        super().__init__(daemon=True)
        self.query = query
        self.results = []
        self.error = None
        self.done = threading.Event()

    def run(self):
        try:
            self.results = search(self.query)
        except Exception as e:
            self.error = str(e)
        finally:
            self.done.set()

class LyricsWorker(threading.Thread):
    def __init__(self, title: str, artist: str):
        super().__init__(daemon=True)
        self.title = title
        self.artist = artist
        self.synced = None
        self.plain = None
        self.done = threading.Event()

    def run(self):
        try:
            self.synced = lyrics.fetch_synced(self.title, self.artist)
            if not self.synced:
                self.plain = lyrics.fetch_plain(self.title)
        except Exception:
            pass
        finally:
            self.done.set()

def current_lyric_index(lines, elapsed: float) -> int:
    idx = 0
    if not lines: return 0
    for i, line in enumerate(lines):
        t = line.time if hasattr(line, "time") else i
        if hasattr(line, "time"):
            if t <= elapsed:
                idx = i
            else:
                break
    return idx

def main():
    check_dependencies()
    # Global MPV instance - created ONCE
    mpv = MPVController()
    keys = KeyListener()
    keys.start()
    
    history = []
    track = None
    lyric_lines = None
    lyrics_worker = None
    
    # Search State
    mode = "search"
    search_query = ""
    search_results = []
    selected_idx = 0
    searching = False
    search_error = ""
    search_worker = None
    
    status_msg = ""
    status_until = 0.0
    track_load_time = 0.0

    try:
        with Live(console=console, screen=True, refresh_per_second=10) as live:
            while True:
                key = keys.get_nowait()
                
                # ==========================================================
                # SEARCH MODE
                # ==========================================================
                if mode == "search":
                    if key == "q":
                        break
                    
                    # Handle Enter
                    if key in ("\r", "\n"):
                        if search_results and 0 <= selected_idx < len(search_results):
                            # Play selected track
                            track = search_results[selected_idx]
                            try:
                                build_queue(track)
                            except Exception as e:
                                status_msg = f"Queue error: {e}"
                                status_until = time.time() + 3.0
                            
                            # Start loading lyrics and song
                            lyrics_worker = LyricsWorker(track.title, track.uploader)
                            lyrics_worker.start()
                            lyric_lines = None
                            
                            # LOAD NEW TRACK (Reset ended flag inside load)
                            mpv.load(track.url)
                            track_load_time = time.time()
                            
                            # Switch to player mode
                            mode = "player"
                            
                            # Reset search state for next time
                            search_results = []
                            search_query = ""
                            selected_idx = 0
                            searching = False
                            search_worker = None
                            
                        elif search_query and not searching:
                            # Start search
                            search_worker = SearchWorker(search_query)
                            search_worker.start()
                            searching = True
                            search_error = ""
                    
                    # Handle Backspace
                    elif key == "\x7f":
                        search_query = search_query[:-1]
                        search_results = []
                        selected_idx = 0
                        search_error = ""
                    
                    # Handle Escape
                    elif key == "\x1b":
                        if search_results:
                            search_results = []
                            selected_idx = 0
                        else:
                            search_query = ""
                        search_error = ""
                    
                    # Handle Navigation
                    elif key == "j" and search_results:
                        selected_idx = min(len(search_results) - 1, selected_idx + 1)
                    elif key == "k" and search_results:
                        selected_idx = max(0, selected_idx - 1)
                    
                    # Handle Typing
                    elif key and len(key) == 1 and key.isprintable():
                        search_query += key
                        search_results = []
                        selected_idx = 0
                        search_error = ""
                    
                    # Check Search Worker
                    if searching and search_worker and search_worker.done.is_set():
                        searching = False
                        if search_worker.error:
                            search_error = search_worker.error
                            search_results = []
                        else:
                            search_results = search_worker.results
                            selected_idx = 0
                            if not search_results:
                                search_error = "No results found"
                        search_worker = None
                    
                    # Update Search UI
                    live.update(ui.render_search(
                        query=search_query,
                        results=search_results,
                        selected_idx=selected_idx,
                        searching=searching,
                        error=search_error,
                    ))

                # ==========================================================
                # PLAYER MODE
                # ==========================================================
                elif mode == "player":
                    if key == "q":
                        mpv.quit() # Quit mpv entirely on q
                        break
                    
                    elif key == "f": # 'f' for search/new
                        # Don't stop mpv, just switch mode. 
                        # If we stop mpv, the next load might race.
                        # Actually, let's keep mpv idle.
                        mpv.stop() 
                        mode = "search"
                        track = None
                        lyric_lines = None
                        continue
                    
                    elif key == "j": # Next
                        # Do NOT mpv.stop() here. load() replaces.
                        history.append(track)
                        next_track = get_next_from_queue()
                        if next_track:
                            track = next_track
                            lyrics_worker = LyricsWorker(track.title, track.uploader)
                            lyrics_worker.start()
                            lyric_lines = None
                            mpv.load(track.url)
                            track_load_time = time.time()
                        else:
                            mpv.stop()
                            mode = "search"
                            track = None
                            lyric_lines = None
                        continue
                    
                    elif key == "k": # Prev
                        # Do NOT mpv.stop() here.
                        if history:
                            track = history.pop()
                            lyrics_worker = LyricsWorker(track.title, track.uploader)
                            lyrics_worker.start()
                            lyric_lines = None
                            mpv.load(track.url)
                            track_load_time = time.time()
                        else:
                            status_msg = "No previous track"
                            status_until = time.time() + 2.0
                        continue
                    
                    elif key == "r": # Replay
                        mpv.load(track.url)
                        track_load_time = time.time()
                    
                    elif key == " ":
                        mpv.toggle_pause()
                    
                    elif key == "\x1b[C": # Right Arrow (Seek +5)
                        mpv.seek(5)
                    
                    elif key == "\x1b[D": # Left Arrow (Seek -5)
                        mpv.seek(-5)

                    # Check if lyrics are ready
                    if lyrics_worker and lyrics_worker.done.is_set():
                        lyric_lines = lyrics_worker.synced or lyrics_worker.plain
                        lyrics_worker = None

                    # Get playback state
                    elapsed = mpv.get_time_pos() or 0.0
                    duration = mpv.get_duration() or (track.duration if track else 0.0) or 0.0
                    paused = mpv.is_paused()
                    idx = current_lyric_index(lyric_lines, elapsed) if lyric_lines else 0

                    if time.time() > status_until:
                        status_msg = ""

                    # Auto-advance logic
                    if mpv.has_ended and track:
                        time_since_load = time.time() - track_load_time
                        
                        # Failure guard: if ended too fast
                        if elapsed < 1.0 and time_since_load < 5.0:
                            status_msg = "Error: Track failed to load"
                            status_until = time.time() + 3.0
                            mpv.stop()
                            mode = "search"
                            track = None
                            lyric_lines = None
                        else:
                            # Normal end
                            history.append(track)
                            next_track = get_next_from_queue()
                            if next_track:
                                track = next_track
                                lyrics_worker = LyricsWorker(track.title, track.uploader)
                                lyrics_worker.start()
                                lyric_lines = None
                                mpv.load(track.url)
                                track_load_time = time.time()
                            else:
                                mpv.stop()
                                mode = "search"
                                track = None
                                lyric_lines = None

                    # Update Player UI
                    if track:
                        live.update(
                            ui.render(
                                track_title=track.title,
                                track_uploader=track.uploader,
                                elapsed=elapsed,
                                duration=duration,
                                paused=paused,
                                lyric_lines=lyric_lines,
                                current_index=idx,
                                status_msg=status_msg,
                            )
                        )
                    else:
                        # Fallback if track is None but in player mode (shouldn't happen)
                        mode = "search"

                time.sleep(0.05)

    except KeyboardInterrupt:
        pass
    finally:
        keys.stop()
        try:
            mpv.quit()
        except Exception:
            pass
        console.print("\n[dim]Exited.[/dim]")

if __name__ == "__main__":
    main()
