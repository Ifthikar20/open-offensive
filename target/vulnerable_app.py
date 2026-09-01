"""Juice-Box — a deliberately vulnerable demo web app (for the Strix-Lite POC).

This app exists ONLY so the Strix-Lite agents have something safe and local to
test. It ships a handful of intentional, textbook weaknesses (reflected XSS, a
leaked SQL error, an IDOR, missing security headers, a hardcoded secret). It is
never meant to run on a public interface — it binds to 127.0.0.1 and is the only
target the POC ever points its agents at.

DO NOT deploy this. It is vulnerable on purpose.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# A fake "users table". The IDOR endpoint hands any of these out without auth,
# including fields a caller should never see.
_USERS = {
    "1": {"id": 1, "name": "Alice Reyes", "email": "alice@juicebox.test", "role": "admin",
          "api_token": "jbx_live_9f2b7c1a44e8"},
    "2": {"id": 2, "name": "Bob Tran", "email": "bob@juicebox.test", "role": "user",
          "api_token": "jbx_live_1122aabbccdd"},
    "3": {"id": 3, "name": "Carla Diaz", "email": "carla@juicebox.test", "role": "user",
          "api_token": "jbx_live_77aa88bb99cc"},
}

_HOME = """<!doctype html><html><head><title>Juice-Box</title></head>
<body style="font-family:sans-serif">
<h1>Juice-Box</h1>
<p>Tiny demo shop. Endpoints: <code>/search?q=</code>, <code>/login</code>,
<code>/api/user/&lt;id&gt;</code>, <code>/static/app.js</code>.</p>
<form action="/search"><input name="q" placeholder="search products"><button>Go</button></form>
</body></html>"""

# A static asset with a secret carelessly left in a comment — classic recon find.
_APP_JS = """// Juice-Box front-end bundle (demo)
// TODO: move this out of the client before launch
const CONFIG = { apiBase: "/api", stripeKey: "sk_live_51JbXdemo00secretLEAKED" };
function search(q){ location = "/search?q=" + q; }
"""


class _Handler(BaseHTTPRequestHandler):
    server_version = "JuiceBox/0.1"  # deliberately advertises a version

    def log_message(self, *args):  # silence default stderr logging
        return

    def _send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # NOTE: intentionally NOT setting Content-Security-Policy,
        # X-Frame-Options, X-Content-Type-Options, etc.
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        if path == "/" or path == "/index.html":
            return self._send(200, _HOME)

        if path == "/static/app.js":
            return self._send(200, _APP_JS, "application/javascript")

        if path == "/robots.txt":
            return self._send(200, "User-agent: *\nDisallow: /admin\n", "text/plain")

        if path == "/search":
            q = params.get("q", "")
            # VULN: reflected XSS — q is echoed into HTML without escaping.
            html = f"<!doctype html><html><body><h2>Results for: {q}</h2>" \
                   f"<p>No products matched.</p></body></html>"
            return self._send(200, html)

        if path == "/login":
            user = params.get("user", "")
            pw = params.get("pass", "")
            # VULN: unsanitized input into a SQL string; a quote breaks it and
            # the raw DB error is leaked to the client.
            if "'" in user or "'" in pw:
                err = ("SQLite3::SQLException: unrecognized token: \"'\" while "
                       f"executing: SELECT * FROM users WHERE name='{user}' AND "
                       f"pass='{pw}'")
                return self._send(500, err, "text/plain")
            return self._send(401, "Invalid credentials", "text/plain")

        if path.startswith("/api/user/"):
            uid = path.rsplit("/", 1)[-1]
            # VULN: IDOR — any id is returned, no authentication or ownership check.
            user = _USERS.get(uid)
            if user is None:
                return self._send(404, json.dumps({"error": "not found"}),
                                  "application/json")
            return self._send(200, json.dumps(user), "application/json")

        return self._send(404, "Not found", "text/plain")


def make_server(host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    """Create (but do not start) the demo target server. port=0 picks a free port."""
    return ThreadingHTTPServer((host, port), _Handler)


def serve_in_thread(host: str = "127.0.0.1", port: int = 0):
    """Start the demo target in a background thread; return (server, base_url)."""
    server = make_server(host, port)
    actual_port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, name="target", daemon=True)
    thread.start()
    return server, f"http://{host}:{actual_port}"


if __name__ == "__main__":
    srv, url = serve_in_thread("127.0.0.1", 8666)
    print(f"Juice-Box (vulnerable demo) running at {url}")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        srv.shutdown()
