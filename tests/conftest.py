"""Shared pytest fixtures and helpers for the OpenOffensive test suite.

The engine runs a single mode: a real model drives each agent through a tool-use
loop inside a per-scan sandbox container. To keep the suite deterministic, fast,
and free of Docker and the network, tests:

* inject a :class:`FakeSandbox` into ``run_scan`` / ``ToolContext`` instead of a
  real Docker container; and
* inject a fake ``anthropic`` SDK (:func:`install_scan_anthropic`) that "drives"
  each specialist to run one command and file its findings, then finish — so a
  full scan reproduces a known set of findings with no API key and no network.

There is no scripted mode and no bundled demo target: findings only ever come
from real tool output (here, the FakeSandbox's), never canned data.
"""

from __future__ import annotations

import os
import sys
import types
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from openoffensive import Coordinator, Settings, run_scan
from openoffensive.config import reset_settings_cache
from openoffensive.models import AgentState
from openoffensive.persistence import RunStore
from openoffensive.sandbox.fake import FakeSandbox
from openoffensive.tools import ToolContext

# A loopback URL used as the scan target. It must classify as a live "url" (not a
# local dir / git repo) so the runner does NOT try to clone/copy source into a
# workspace.
SCANNED_TARGET = "http://127.0.0.1:8123"


# ---------------------------------------------------------------------------
# a fake anthropic SDK that drives a full scan deterministically
# ---------------------------------------------------------------------------
class FakeBlock:
    def __init__(self, type, *, text=None, name=None, input=None, id=None):
        self.type = type
        self.text = text
        self.name = name
        self.input = input
        self.id = id


class FakeUsage:
    def __init__(self, input_tokens=100, output_tokens=50):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class FakeResponse:
    def __init__(self, content, stop_reason="tool_use"):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = FakeUsage()


# The canonical six findings a scan reproduces, grouped by the specialist that
# files them. Keyed by a phrase unique to each specialist's focus (see agents.py),
# so the fake can route by the task it is handed — thread-safe because each agent
# drives its own message list.
_SCAN_PLAYBOOK = {
    "attack surface": {
        "command": "curl -s -i {t}/",
        "findings": [
            dict(title="Hardcoded live secret key in client bundle", severity="critical",
                 endpoint="/static/app.js",
                 evidence="Client-served JS embeds a live sk_live_ key.",
                 remediation="Revoke the key; move secrets server-side.", cwe="CWE-798"),
            dict(title="Missing security headers", severity="low", endpoint="/",
                 evidence="CSP, X-Frame-Options and X-Content-Type-Options are absent.",
                 remediation="Add the missing security headers.", cwe="CWE-693"),
            dict(title="Server version disclosure", severity="info", endpoint="/",
                 evidence="The Server header reveals the stack.",
                 remediation="Genericise the Server header.", cwe="CWE-200"),
        ],
    },
    "SQL injection": {
        "command": 'curl -s -i "{t}/login?user=admin%27"',
        "findings": [
            dict(title="Error-based SQL injection", severity="high", endpoint="/login",
                 evidence="A single quote triggers a raw SQL error in the response.",
                 remediation="Use parameterised queries; never concatenate input.", cwe="CWE-89"),
            dict(title="Reflected cross-site scripting (XSS)", severity="medium",
                 endpoint="/search",
                 evidence="The q parameter is reflected un-encoded into the HTML body.",
                 remediation="Context-encode output; add a strict CSP.", cwe="CWE-79"),
        ],
    },
    "object-level authorization": {
        "command": "for i in 1 2 3; do curl -s {t}/api/user/$i; done",
        "findings": [
            dict(title="IDOR — unauthenticated access to any user record", severity="high",
                 endpoint="/api/user/{id}",
                 evidence="Sequential ids return other users' records without auth.",
                 remediation="Enforce authentication and an ownership check per lookup.",
                 cwe="CWE-639"),
        ],
    },
}


def _target_from_task(task: str) -> str:
    if "Target: " in task:
        return task.split("Target: ", 1)[1].splitlines()[0].strip()
    return "http://127.0.0.1"


def install_scan_anthropic(monkeypatch):
    """Inject a fake ``anthropic`` module whose model drives each specialist to run
    one command and file its findings, then finish. Returns the module (``.calls``
    counts create() invocations). Deterministic and threading-safe."""
    calls: list[dict] = []

    def _play_for(task: str):
        for key, play in _SCAN_PLAYBOOK.items():
            if key in task:
                return play
        return None

    class FakeMessages:
        def create(self, **kwargs):
            calls.append({"messages": len(kwargs.get("messages") or [])})
            msgs = kwargs.get("messages") or []
            first = msgs[0].get("content") if msgs else None
            # preflight probe: a single "ping" user turn
            if len(msgs) == 1 and first == "ping":
                return FakeResponse([], stop_reason="end_turn")
            task = first if isinstance(first, str) else ""
            play = _play_for(task)
            if play is None:            # the root or an unknown agent → just finish
                return FakeResponse([FakeBlock("tool_use", name="finish",
                                               input={"summary": "done"}, id="fin")])
            steps = sum(1 for m in msgs if m.get("role") == "assistant")
            if steps == 0:              # first: run one real command in the sandbox
                cmd = play["command"].format(t=_target_from_task(task))
                return FakeResponse([FakeBlock("tool_use", name="run_command",
                                               input={"command": cmd}, id="cmd")])
            if steps == 1:              # then: file this specialist's findings
                blocks = [FakeBlock("tool_use", name="report_finding", input=dict(f),
                                    id=f"rf{i}") for i, f in enumerate(play["findings"])]
                return FakeResponse(blocks)
            return FakeResponse([FakeBlock("tool_use", name="finish",
                                           input={"summary": "focus covered"}, id="fin")])

    class FakeAnthropic:
        def __init__(self, *args, **kwargs):
            self.messages = FakeMessages()

    module = types.ModuleType("anthropic")
    module.Anthropic = FakeAnthropic
    module.calls = calls
    monkeypatch.setitem(sys.modules, "anthropic", module)
    return module


def scan_sandbox() -> FakeSandbox:
    """A generic in-container sandbox for a faked scan: every command returns the
    same short output (a finding's provenance is the command that was run)."""
    return FakeSandbox(default=("TOOL OUTPUT", 0))


# ---------------------------------------------------------------------------
# environment hygiene
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Give every test a clean, deterministic configuration environment.

    Settings are ``lru_cache``\\d, so we drop the cache around each test and strip
    any OpenOffensive/Anthropic env vars that could leak between tests (or from the
    outer shell) and make a scan pick up a real key.
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
    """A frozen Settings for tests: instant pacing, no Docker autostart, temp runs."""
    params = dict(
        speed=0.0,
        api_key_present=False,
        docker_autostart=False,   # never try to spawn a real daemon in tests
        runs_dir=str(Path(tmp_path) / "runs"),
    )
    params.update(over)
    return Settings(**params)


@pytest.fixture
def fast_settings(tmp_path) -> Settings:
    """Ready-made Settings with speed=0 and a throwaway runs_dir."""
    return build_settings(tmp_path)


# ---------------------------------------------------------------------------
# a completed scan, driven by a fake model + injected FakeSandbox (no Docker/net)
# ---------------------------------------------------------------------------
@pytest.fixture
def scanned(tmp_path, monkeypatch):
    """Run one full scan through a fake model and injected sandbox and hand back the
    pieces (coord, result, store, sandbox, ...) reused by the engine, reporting,
    and persistence tests. Produces the canonical six findings."""
    install_scan_anthropic(monkeypatch)
    settings = build_settings(tmp_path, api_key_present=True)
    store = RunStore(str(Path(tmp_path) / "runs"))
    scan_id = "scan-testrun"
    sandbox = scan_sandbox()
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
    """Build a ToolContext backed by a FakeSandbox (the 5-arg signature)."""
    return ToolContext(
        coord,
        agent or make_agent(),
        settings or Settings(speed=0.0, api_key_present=False),
        sandbox if sandbox is not None else FakeSandbox(),
        target or coord.target,
    )


def http_get(url: str):
    """Perform a real GET and return (status, lowercased-headers, body).

    HTTPError (>=400) is unwrapped into the same tuple shape so callers can assert
    on error responses.
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
