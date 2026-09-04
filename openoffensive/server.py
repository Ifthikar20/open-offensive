"""The dashboard server — serves the single-page UI, streams the live log over
Server-Sent Events, exposes a small REST API (start a scan, browse history), and
boots the bundled vulnerable demo target so there is always something to scan.

Pure standard library. Started via ``openoffensive serve`` or ``./run.sh``.
"""

from __future__ import annotations

import json
import queue
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import skills
from .config import Settings, load_settings
from .coordinator import Coordinator
from .demo_target import serve_in_thread
from .persistence import RunStore
from .runner import run_scan

WEB_DIR = Path(__file__).resolve().parent / "web"


class App:
    """Shared server state: the current run, run history, and the demo target."""

    def __init__(self, settings: Settings, target_url: str) -> None:
        self.settings = settings
        self.target_url = target_url
        self.store = RunStore(settings.runs_dir)
        self.lock = threading.Lock()
        self.coord: Coordinator | None = None
        self.scan_id: str | None = None
        self.scan_thread: threading.Thread | None = None

    def scanning(self) -> bool:
        return self.scan_thread is not None and self.scan_thread.is_alive()

    def start_scan(self) -> tuple[bool, str]:
        with self.lock:
            if self.scanning():
                return False, ""
            scan_id = f"scan-{uuid.uuid4().hex[:8]}"
            coord = Coordinator(self.target_url)
            self.coord = coord
            self.scan_id = scan_id

            def _run() -> None:
                run_scan(coord, settings=self.settings, scan_id=scan_id, store=self.store)

            self.scan_thread = threading.Thread(target=_run, name="scan", daemon=True)
            self.scan_thread.start()
            return True, scan_id


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

    def _text(self, code: int, text: str, ctype: str = "text/plain; charset=utf-8") -> None:
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- routing --------------------------------------------------------------
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
            return self._text(200, html, "text/html; charset=utf-8")
        if path == "/api/state":
            return self._json(200, self._state())
        if path == "/api/log":
            coord = APP.coord
            events = [e.to_dict() for e in coord.events] if coord else []
            return self._json(200, {"events": events, "scanning": APP.scanning()})
        if path == "/api/events":
            return self._sse()
        if path == "/api/runs":
            return self._json(200, {"runs": APP.store.list_runs()})
        if path.startswith("/api/runs/"):
            rest = path[len("/api/runs/"):]
            scan_id = rest.split("/", 1)[0]
            if rest.endswith("/report"):
                return self._text(200, APP.store.load_report(scan_id), "text/markdown; charset=utf-8")
            rec = APP.store.load_run(scan_id)
            if rec is None:
                return self._json(404, {"error": "run not found"})
            return self._json(200, {"run": rec, "events": APP.store.load_events(scan_id)})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        if urlparse(self.path).path == "/api/scan":
            started, scan_id = APP.start_scan()
            return self._json(200 if started else 409,
                              {"ok": started, "scan_id": scan_id, "target": APP.target_url,
                               "message": "scan started" if started
                               else "a scan is already running"})
        return self._json(404, {"error": "not found"})

    def _state(self) -> dict:
        coord = APP.coord
        if coord is not None:
            snap = coord.snapshot()
        else:
            snap = {"status": "idle", "target": APP.target_url, "agents": [], "findings": [],
                    "turns": 0, "cost": 0.0}
        snap["scan_id"] = APP.scan_id
        snap["scanning"] = APP.scanning()
        snap["mode"] = coord.mode if coord else ("llm" if APP.settings.llm_enabled else "scripted")
        snap["llm_enabled"] = APP.settings.llm_enabled
        snap["model"] = APP.settings.model
        snap["skills"] = skills.describe_catalog()
        return snap

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
                if coord is not last_coord:
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
            pass
        finally:
            if last_coord is not None and sub is not None:
                last_coord.unsubscribe(sub)

    def _beat(self) -> None:
        self.wfile.write(b": keep-alive\n\n")
        self.wfile.flush()


def main(open_browser: bool = True) -> None:
    global APP
    settings = load_settings()
    # Bind the demo on all interfaces so the scan container can reach it via
    # host.docker.internal; point the scan there.
    demo_srv, _ = serve_in_thread("0.0.0.0", 0)
    target_url = f"http://host.docker.internal:{demo_srv.server_address[1]}"
    APP = App(settings, target_url)

    from .sandbox import docker_available
    docker_ok, docker_reason = docker_available()

    httpd = ThreadingHTTPServer((settings.host, settings.port), Handler)
    dash = f"http://{settings.host}:{httpd.server_address[1]}"
    mode = "llm (" + settings.model + ")" if settings.llm_enabled else "scripted"
    print("\n  OpenOffensive — multi-agent pentest dashboard")
    print(f"  dashboard : {dash}")
    print(f"  target    : {target_url}  (bundled vulnerable demo app)")
    print(f"  mode      : {mode}")
    print(f"  docker    : {'OK' if docker_ok else 'UNAVAILABLE — ' + docker_reason + ' (scans need Docker)'}")
    print("  press Ctrl-C to stop\n")
    if open_browser:
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
