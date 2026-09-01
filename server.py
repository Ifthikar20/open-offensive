#!/usr/bin/env python3
"""Strix-Lite server — the local dashboard, à la `strix view`.

Boots the bundled vulnerable target, serves a tiny single-page UI, and streams
the running scan's events to the browser over Server-Sent Events so you can watch
the multi-agent pentest happen live. Pure standard library — just run it:

    python3 server.py            # then open the printed URL

No API keys, no Docker, no external target. The only thing the agents touch is
the demo app this process starts on localhost.
"""

from __future__ import annotations

import json
import queue
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from strixlite import skills
from strixlite.coordinator import Coordinator
from strixlite.runner import run_scan
from target.vulnerable_app import serve_in_thread

BASE_DIR = Path(__file__).resolve().parent


class App:
    """Shared server state: the current run, and the fixed demo target."""

    def __init__(self, target_url: str) -> None:
        self.target_url = target_url
        self.lock = threading.Lock()
        self.coord: Coordinator | None = None
        self.scan_thread: threading.Thread | None = None

    def scanning(self) -> bool:
        return self.scan_thread is not None and self.scan_thread.is_alive()

    def start_scan(self) -> bool:
        with self.lock:
            if self.scanning():
                return False
            self.coord = Coordinator(self.target_url)
            self.scan_thread = threading.Thread(
                target=run_scan, args=(self.coord,), name="scan", daemon=True)
            self.scan_thread.start()
            return True


APP: App  # set in main()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # keep the console clean
        return

    # -- helpers --------------------------------------------------------------
    def _json(self, code: int, payload) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, ctype: str) -> None:
        if not path.exists():
            return self._json(404, {"error": "not found"})
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- routing --------------------------------------------------------------
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._file(BASE_DIR / "web" / "index.html", "text/html; charset=utf-8")
        if path == "/api/state":
            coord = APP.coord
            snap = coord.snapshot() if coord else {"status": "idle", "target": APP.target_url,
                                                   "agents": [], "findings": []}
            snap["skills"] = skills.describe_catalog()
            snap["scanning"] = APP.scanning()
            return self._json(200, snap)
        if path == "/api/log":
            # One-shot dump of the current run's events — used by ?snap render
            # and handy for debugging. No streaming, so it never holds a socket.
            coord = APP.coord
            events = [e.to_dict() for e in coord.events] if coord else []
            return self._json(200, {"events": events, "scanning": APP.scanning(),
                                    "target": APP.target_url})
        if path == "/api/events":
            return self._sse()
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        if urlparse(self.path).path == "/api/scan":
            started = APP.start_scan()
            return self._json(200 if started else 409,
                              {"ok": started, "target": APP.target_url,
                               "message": "scan started" if started
                               else "a scan is already running"})
        return self._json(404, {"error": "not found"})

    # -- server-sent events: the live log ------------------------------------
    def _sse(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        last_coord: Coordinator | None = None
        sub: queue.Queue | None = None
        last_beat = time.time()
        try:
            while True:
                coord = APP.coord
                if coord is not last_coord:  # a (new) run appeared — follow it
                    if last_coord is not None and sub is not None:
                        last_coord.unsubscribe(sub)
                    sub = coord.subscribe() if coord is not None else None
                    last_coord = coord
                if sub is None:
                    self._beat()
                    time.sleep(0.4)
                    continue
                try:
                    ev = sub.get(timeout=1.0)
                except queue.Empty:
                    if time.time() - last_beat > 12:
                        self._beat()
                        last_beat = time.time()
                    continue
                self.wfile.write(f"data: {json.dumps(ev.to_dict())}\n\n".encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # browser navigated away / reconnected
        finally:
            if last_coord is not None and sub is not None:
                last_coord.unsubscribe(sub)

    def _beat(self) -> None:
        self.wfile.write(b": keep-alive\n\n")
        self.wfile.flush()


def main() -> None:
    global APP
    _, target_url = serve_in_thread("127.0.0.1", 0)
    APP = App(target_url)

    httpd = ThreadingHTTPServer(("127.0.0.1", 8777), Handler)
    dash = f"http://127.0.0.1:{httpd.server_address[1]}"
    print("\n  Strix-Lite — multi-agent pentest POC")
    print(f"  dashboard : {dash}")
    print(f"  target    : {target_url}  (bundled vulnerable demo app)")
    print("  press Ctrl-C to stop\n")
    try:
        webbrowser.open(dash)
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  bye")
        httpd.shutdown()


if __name__ == "__main__":
    main()
