"""The tool layer — real HTTP probes against the demo target.

Every method makes an actual request to the bundled Juice-Box app and logs the
request/response as a `tool` event, so the live log reflects real traffic rather
than a script reading from a fixture. A host allowlist keeps the POC pointed only
at the local demo target — the agents cannot be repurposed against anything else.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

from .coordinator import Coordinator
from .models import AgentState


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: str
    url: str


class Toolbox:
    """Bound to one acting agent + the run target. Logs every call."""

    def __init__(self, coord: Coordinator, agent: AgentState) -> None:
        self.coord = coord
        self.agent = agent
        self.base = coord.target.rstrip("/")
        self._allowed_host = urlparse(self.base).hostname

    def _guard(self, url: str) -> None:
        host = urlparse(url).hostname
        if host != self._allowed_host:
            raise PermissionError(
                f"out-of-scope host '{host}' blocked (allowed: {self._allowed_host})")

    def http_get(self, path: str, params: dict | None = None,
                 note: str = "") -> Response:
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        self._guard(url)
        self.coord.bill(self.agent)
        label = note or f"GET {path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
        req = urllib.request.Request(url, headers={"User-Agent": "strix-lite/0.1"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                body = r.read().decode("utf-8", "replace")
                resp = Response(r.status, {k.lower(): v for k, v in r.headers.items()},
                                body, url)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            resp = Response(e.code, {k.lower(): v for k, v in (e.headers or {}).items()},
                            body, url)
        except Exception as e:  # noqa: BLE001 — surface as a tool result, never crash the agent
            self.coord.emit("tool", self.agent, f"{label} → ERROR {e}", ok=False)
            return Response(0, {}, "", url)
        ms = int((time.time() - t0) * 1000)
        self.coord.emit("tool", self.agent, f"{label} → {resp.status} ({len(body)}b, {ms}ms)",
                        ok=True, status=resp.status)
        # A little pacing so the live stream reads at human speed.
        time.sleep(0.35)
        return resp
