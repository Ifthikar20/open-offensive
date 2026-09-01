"""Shared pytest fixtures and helpers for the OpenOffensive test suite.

Everything here is designed to keep the suite deterministic, fast, and
side-effect-free:

* the bundled vulnerable demo target is served once per session on a random
  loopback port and yielded as a base URL;
* ``build_settings`` / ``fast_settings`` produce a frozen ``Settings`` with
  ``speed=0`` (instant scans) pointed at a throwaway ``runs_dir`` under
  ``tmp_path`` so no test ever writes to ``./runs``;
* an autouse fixture wipes OpenOffensive/Anthropic environment variables and
  drops the ``lru_cache``\\d settings before and after every test.
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
# the vulnerable demo target
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
# a completed scan (reused by engine/reporting/persistence tests)
# ---------------------------------------------------------------------------
@pytest.fixture
def scanned(demo_target, tmp_path):
    """Run one full scripted scan against the demo target and hand back the pieces."""
    settings = build_settings(tmp_path)
    store = RunStore(str(Path(tmp_path) / "runs"))
    scan_id = "scan-testrun"
    coord = Coordinator(demo_target)
    result = run_scan(coord, settings=settings, scan_id=scan_id, store=store)
    return types.SimpleNamespace(
        coord=coord,
        result=result,
        store=store,
        scan_id=scan_id,
        settings=settings,
        target=demo_target,
    )


# ---------------------------------------------------------------------------
# small shared helpers
# ---------------------------------------------------------------------------
def make_agent(name: str = "Tester", role: str = "tester") -> AgentState:
    """A bare agent-graph node, enough to drive a ToolContext."""
    return AgentState(id="agent-1", name=name, role=role, parent=None, task="testing")


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
