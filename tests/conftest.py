"""Shared pytest fixtures and helpers for the OpenOffensive test suite.

The suite is built for the NEW architecture: a scan runs inside a per-scan
sandbox container and is driven either by a real LLM tool-use loop or a scripted
in-container playbook. To keep the suite deterministic, fast, and free of Docker
and network, tests inject a :class:`FakeSandbox` (see :func:`demo_sandbox`) into
``run_scan``/``ToolContext`` instead of a real Docker container, and inject a
fake ``anthropic`` SDK for the LLM loop.

Everything here keeps the suite hermetic:

* an autouse fixture wipes OpenOffensive/Anthropic environment variables and
  drops the ``lru_cache``\\d settings before and after every test;
* ``build_settings`` / ``fast_settings`` produce a frozen scripted ``Settings``
  pointed at a throwaway ``runs_dir`` under ``tmp_path``;
* ``demo_sandbox()`` builds an in-memory sandbox that simulates the bundled
  vulnerable demo app, so a scripted scan finds all six issues with no Docker;
* the real bundled demo target is still served (loopback, random port) for the
  handful of tests that assert it is genuinely vulnerable over real HTTP.
"""

from __future__ import annotations

import os
import types
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from openoffensive import Coordinator, Settings, run_scan
from openoffensive.config import reset_settings_cache
from openoffensive.demo_target import serve_in_thread
from openoffensive.models import AgentState
from openoffensive.persistence import RunStore
from openoffensive.sandbox.fake import FakeSandbox
from openoffensive.tools import ToolContext

# A loopback URL used as the scan target when the FakeSandbox does the answering.
# It must classify as a live "url" (not a local dir / git repo) so the runner
# does NOT try to clone/copy source into a workspace — a workspace would make
# recon file an extra "Secrets in source" finding and throw the count off.
SCANNED_TARGET = "http://127.0.0.1:8123"


# ---------------------------------------------------------------------------
# the FakeSandbox that simulates the bundled demo app
# ---------------------------------------------------------------------------
# Canned tool output keyed by the endpoint substring the command touches. A
# scripted scan against this sandbox reproduces all six intentional demo vulns:
# a leaked live key (critical), a SQL error + an IDOR (high x2), reflected XSS
# (medium), missing security headers (low), and a server banner (info).
DEMO_HOME = ("HTTP/1.1 200 OK\r\nServer: JuiceBox/0.1\r\n"
             "Content-Type: text/html\r\n\r\n<html>demo</html>")
DEMO_APPJS = '// bundle\nconst CONFIG={stripeKey:"sk_live_51JbXdemoLEAKED"};'
DEMO_LOGIN = ('HTTP/1.1 500 ERR\r\n\r\n'
              'SQLite3::SQLException: unrecognized token near "\'"')
DEMO_SEARCH = "<html><h2>Results for: <script>xss1()</script></h2></html>"
DEMO_IDOR = ('{"id":1,"api_token":"jbx_live_a"}\n'
             '{"id":2,"api_token":"jbx_live_b"}\n'
             '{"id":3,"api_token":"jbx_live_c"}')


def demo_sandbox() -> FakeSandbox:
    """An in-memory sandbox whose answers make a scripted scan find all 6 vulns."""
    return FakeSandbox(
        responses={
            "/static/app.js": (DEMO_APPJS, 0),
            "/login": (DEMO_LOGIN, 0),
            "/search": (DEMO_SEARCH, 0),
            "/api/user": (DEMO_IDOR, 0),
        },
        default=(DEMO_HOME, 0),
    )


# ---------------------------------------------------------------------------
# environment hygiene
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Give every test a clean, deterministic configuration environment.

    Settings are ``lru_cache``\\d, so we drop the cache around each test and
    strip any OpenOffensive/Anthropic env vars that could leak between tests
    (or from the outer shell) and make a scan pick LLM mode or a real key.
    """
    for key in list(os.environ):
        if key.startswith("OPENOFFENSIVE_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Never let a developer's local .env leak a real key into the hermetic suite.
    monkeypatch.setenv("OPENOFFENSIVE_NO_DOTENV", "1")
    reset_settings_cache()
    yield
    reset_settings_cache()


# ---------------------------------------------------------------------------
# settings helpers
# ---------------------------------------------------------------------------
def build_settings(tmp_path, **over) -> Settings:
    """A frozen Settings for tests: instant pacing, scripted mode, temp runs_dir."""
    params = dict(
        speed=0.0,
        llm_mode="scripted",
        api_key_present=False,
        runs_dir=str(Path(tmp_path) / "runs"),
    )
    params.update(over)
    return Settings(**params)


@pytest.fixture
def fast_settings(tmp_path) -> Settings:
    """Ready-made scripted Settings with speed=0 and a throwaway runs_dir."""
    return build_settings(tmp_path)


# ---------------------------------------------------------------------------
# the vulnerable demo target (real HTTP — for the "is it actually vulnerable" tests)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def demo_target():
    """Serve the bundled Juice-Box demo app on a random loopback port.

    Read-only and stateless, so one instance is shared for the whole session
    and torn down (stop serving + release the socket) at the end.
    """
    server, base_url = serve_in_thread("127.0.0.1", 0)
    try:
        yield base_url
    finally:
        server.shutdown()
        server.server_close()


# ---------------------------------------------------------------------------
# a completed scripted scan, driven by an injected FakeSandbox (no Docker)
# ---------------------------------------------------------------------------
@pytest.fixture
def scanned(tmp_path):
    """Run one full scripted scan through an injected demo sandbox and hand back
    the pieces (coord, result, store, sandbox, ...) reused by the engine,
    reporting, and persistence tests."""
    settings = build_settings(tmp_path)
    store = RunStore(str(Path(tmp_path) / "runs"))
    scan_id = "scan-testrun"
    sandbox = demo_sandbox()
    coord = Coordinator(SCANNED_TARGET)
    result = run_scan(coord, settings=settings, scan_id=scan_id, store=store,
                      sandbox=sandbox)
    return types.SimpleNamespace(
        coord=coord,
        result=result,
        store=store,
        scan_id=scan_id,
        settings=settings,
        sandbox=sandbox,
        target=SCANNED_TARGET,
    )


# ---------------------------------------------------------------------------
# small shared helpers
# ---------------------------------------------------------------------------
def make_agent(name: str = "Tester", role: str = "tester") -> AgentState:
    """A bare agent-graph node, enough to drive a ToolContext."""
    return AgentState(id="agent-1", name=name, role=role, parent=None, task="testing")


def tool_ctx(coord, *, settings=None, sandbox=None, target=None, agent=None) -> ToolContext:
    """Build a ToolContext backed by a FakeSandbox (the new 5-arg signature)."""
    return ToolContext(
        coord,
        agent or make_agent(),
        settings or Settings(speed=0.0, api_key_present=False),
        sandbox if sandbox is not None else FakeSandbox(),
        target or coord.target,
    )


def http_get(url: str):
    """Perform a real GET and return (status, lowercased-headers, body).

    HTTPError (>=400) is unwrapped into the same tuple shape so callers can
    assert on error responses (e.g. the demo's 500 SQL error).
    """
    req = urllib.request.Request(url, headers={"User-Agent": "openoffensive-tests/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return (resp.status,
                    {k.lower(): v for k, v in resp.headers.items()},
                    resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return (exc.code,
                {k.lower(): v for k, v in (exc.headers or {}).items()},
                exc.read().decode("utf-8", "replace"))
