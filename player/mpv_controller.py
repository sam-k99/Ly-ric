"""
Thin wrapper around mpv's JSON IPC protocol.

A background reader thread owns the socket:
  - command responses -> per-request threading.Event (no blocking reads on UI thread)
  - end-file events   -> reason stored; only "eof" = natural end, only "error" = failure.
    "stop"/"quit" reasons are ignored, so mpv.stop() can never poison end detection.
"""

import itertools
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import uuid


class MPVError(RuntimeError):
    pass


class MPVController:
    def __init__(self, ytdl_path: str = "yt-dlp", debug_log: bool = False):
        self.socket_path = os.path.join(
            tempfile.gettempdir(), f"mpv-lyrics-{uuid.uuid4().hex[:8]}.sock"
        )
        self.log_path = os.path.join(
            tempfile.gettempdir(), f"mpv-lyrics-{uuid.uuid4().hex[:8]}.log"
        )
        self._proc = subprocess.Popen(
            [
                "mpv",
                "--no-video",
                "--idle=yes",
                "--no-terminal",
                f"--input-ipc-server={self.socket_path}",
                f"--script-opts=ytdl_hook-ytdl_path={ytdl_path}",
                "--ytdl-format=bestaudio/best",
                "--msg-level=all=v" if debug_log else "--msg-level=all=warn",
                f"--log-file={self.log_path}",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._sock = self._connect_with_retry()
        self._write_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._req_ids = itertools.count(1)
        self._responses = {}
        self._waiters = {}
        self._end_reason = None
        threading.Thread(target=self._reader_loop, daemon=True).start()

    def _connect_with_retry(self, attempts: int = 50, delay: float = 0.1):
        last_err = None
        for _ in range(attempts):
            if self._proc.poll() is not None:
                raise MPVError(
                    f"mpv exited immediately (code {self._proc.returncode}). "
                    f"Check log: {self.log_path}"
                )
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(self.socket_path)
                return s
            except (FileNotFoundError, ConnectionRefusedError) as e:
                last_err = e
                time.sleep(delay)
        raise MPVError(f"Could not connect to mpv IPC socket: {last_err}")

    def _reader_loop(self):
        f = self._sock.makefile("rb")
        while True:
            try:
                line = f.readline()
            except (OSError, ValueError):
                break
            if not line:
                break
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "event" in msg:
                if msg.get("event") == "end-file":
                    with self._state_lock:
                        self._end_reason = msg.get("reason", "unknown")
                continue
            rid = msg.get("request_id")
            if rid is None:
                continue
            with self._state_lock:
                ev = self._waiters.pop(rid, None)
                self._responses[rid] = msg
            if ev is not None:
                ev.set()

    def _send(self, command: list, timeout: float = 10.0):
        rid = next(self._req_ids)
        ev = threading.Event()
        with self._state_lock:
            self._waiters[rid] = ev
        payload = json.dumps({"command": command, "request_id": rid}) + "\n"
        with self._write_lock:
            try:
                self._sock.sendall(payload.encode("utf-8"))
            except (BrokenPipeError, OSError):
                with self._state_lock:
                    self._waiters.pop(rid, None)
                return {}
        if not ev.wait(timeout):
            with self._state_lock:
                self._waiters.pop(rid, None)
                self._responses.pop(rid, None)
            return {}
        with self._state_lock:
            return self._responses.pop(rid, {})

    def load(self, url: str):
        with self._state_lock:
            self._end_reason = None
        self._send(["loadfile", url, "replace"])

    def stop(self):
        self._send(["stop"])

    def toggle_pause(self):
        self._send(["cycle", "pause"])

    def seek(self, seconds: float, mode: str = "relative"):
        self._send(["seek", float(seconds), mode])

    def get_time_pos(self):
        return self._send(["get_property", "time-pos"]).get("data")

    def get_duration(self):
        return self._send(["get_property", "duration"]).get("data")

    def is_paused(self) -> bool:
        return bool(self._send(["get_property", "pause"]).get("data"))

    @property
    def has_ended(self) -> bool:
        """True only when track played to natural end (reason 'eof')."""
        with self._state_lock:
            return self._end_reason == "eof"

    @property
    def has_failed(self) -> bool:
        """True when track failed to load/play (reason 'error')."""
        with self._state_lock:
            return self._end_reason == "error"

    def read_log(self) -> str:
        try:
            with open(self.log_path, "r", errors="replace") as f:
                return f.read()
        except Exception:
            return ""

    def quit(self):
        try:
            self._send(["quit"], timeout=2.0)
        except Exception:
            pass
        try:
            self._sock.close()
        except Exception:
            pass
        try:
            self._proc.terminate()
        except Exception:
            pass
        try:
            os.remove(self.socket_path)
        except OSError:
            pass
        try:
            os.remove(self.log_path)
        except OSError:
            pass
