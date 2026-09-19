"""Runner behavior: the LLM preflight gate, loud failure when agents crash, and
backend selection (local host execution vs an explicit Docker requirement).

These lock in the fix for the "silent 0-finding scan" problem — a run where the
model is unreachable (or every specialist crashes) must end in status ``error``,
never a clean-looking ``done`` with exit 0. There is no scripted fallback.
"""

from __future__ import annotations

import shutil
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from conftest import (SCANNED_TARGET, build_settings, install_scan_anthropic,
                      scan_sandbox)

from openoffensive import Coordinator, run_scan
from openoffensive.models import AgentState, Finding
from openoffensive.persistence import RunStore
from openoffensive.runner import _failed_from_crashes
from openoffensive.sandbox.fake import FakeSandbox


def _install_raising_anthropic(monkeypatch, err: Exception) -> None:
    """Fake `anthropic` whose messages.create() always raises `err`."""
    class _Msgs:
        def create(self, **kw):
            raise err

    class _Client:
        messages = _Msgs()

        def __init__(self, *a, **k):
            pass

    module = types.ModuleType("anthropic")
    module.Anthropic = _Client
    monkeypatch.setitem(sys.modules, "anthropic", module)


# ---------------------------------------------------------------------------
# LLM preflight — the scan stops up front when the model can't be reached
# ---------------------------------------------------------------------------
def test_llm_preflight_failure_stops_scan_before_container(tmp_path, monkeypatch):
    _install_raising_anthropic(monkeypatch, RuntimeError("Connection error."))
    settings = build_settings(tmp_path, api_key_present=True)
    coord = Coordinator(SCANNED_TARGET)
    sandbox = FakeSandbox()

    result = run_scan(coord, settings=settings, scan_id="scan-pf",
                      store=RunStore(str(tmp_path / "runs")), sandbox=sandbox)

    assert result.status == "error"          # NOT a silent "done"
    assert result.findings == []
    assert coord.agents == {}                # no agent was ever spawned
    assert sandbox.started is False          # the container was never started
    assert any(ev.level == "error" and "unreachable" in ev.message
               for ev in coord.events)


def test_preflight_missing_key_stops_scan(tmp_path):
    # No key and no SDK: the scan must fail at preflight, never fall back to a demo
    # or scripted run.
    settings = build_settings(tmp_path, api_key_present=False)
    coord = Coordinator(SCANNED_TARGET)
    sandbox = FakeSandbox()
    result = run_scan(coord, settings=settings, scan_id="scan-nokey",
                      store=RunStore(str(tmp_path / "runs")), sandbox=sandbox)
    assert result.status == "error"
    assert result.findings == []
    assert sandbox.started is False


def test_scan_completes_with_findings(scanned):
    # A model-driven run through the fake client + injected sandbox completes and
    # files the canonical findings (guards against the preflight gate over-firing).
    assert scanned.result.status == "done"
    assert len(scanned.result.findings) == 6


# ---------------------------------------------------------------------------
# loud failure when specialists crash mid-run (e.g. a rate-limit past preflight)
# ---------------------------------------------------------------------------
def test_failed_from_crashes_true_when_all_crashed_and_nothing_found():
    coord = Coordinator(SCANNED_TARGET)
    for i in range(3):
        a = AgentState(id=f"a{i}", name=f"A{i}", role="recon", parent="root")
        coord.register(a)
        coord.set_status(a, "stopped", "stopped after error")
    coord.emit("error", None, "crashed: Connection error.")

    failed, reason = _failed_from_crashes(coord)
    assert failed is True
    assert "Connection error" in reason
    assert coord.snapshot()["crashed"] == 3
    assert len(coord.crashed_agents()) == 3


def test_failed_from_crashes_false_when_a_finding_exists():
    coord = Coordinator(SCANNED_TARGET)
    a = AgentState(id="a", name="A", role="recon", parent="root")
    coord.register(a)
    coord.set_status(a, "stopped", "stopped after error")
    coord.add_finding(a, Finding(id="", title="x", severity="low", target="t",
                                 endpoint="/", evidence="e", remediation="r", agent="A"))

    failed, _reason = _failed_from_crashes(coord)
    assert failed is False   # a crash alongside real findings is not a failed run


# ---------------------------------------------------------------------------
# backend selection — local host execution runs without Docker
# ---------------------------------------------------------------------------
class _Hello(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"<html>ok</html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        return


@pytest.mark.skipif(shutil.which("curl") is None, reason="curl not on host")
def test_local_backend_runs_tools_on_host_without_docker(tmp_path, monkeypatch):
    """A real LocalSandbox (no injected sandbox, no Docker) runs the agents' tools
    on the host and completes a scan — the core no-Docker unblock."""
    install_scan_anthropic(monkeypatch)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Hello)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    try:
        settings = build_settings(tmp_path, api_key_present=True, sandbox_backend="local")
        coord = Coordinator(f"http://127.0.0.1:{port}")
        result = run_scan(coord, settings=settings, scan_id="scan-local",
                          store=RunStore(str(tmp_path / "runs")))  # sandbox=None → LocalSandbox
        assert result.status == "done"
        assert len(coord.findings) >= 1
        # tool calls really executed on the host (not a container)
        assert any("host" in ev.message for ev in coord.events if ev.level == "system")
    finally:
        srv.shutdown()
        srv.server_close()


def test_docker_backend_without_daemon_errors(tmp_path, monkeypatch):
    """An explicit docker backend with no daemon fails loudly at the Docker gate,
    after a passing preflight."""
    install_scan_anthropic(monkeypatch)
    import openoffensive.runner as runner
    monkeypatch.setattr(runner, "docker_available",
                        lambda: (False, "the Docker daemon is not running or not reachable"))
    settings = build_settings(tmp_path, api_key_present=True, sandbox_backend="docker")
    coord = Coordinator(SCANNED_TARGET)
    result = run_scan(coord, settings=settings, scan_id="scan-nd",
                      store=RunStore(str(tmp_path / "runs")))  # sandbox=None
    assert result.status == "error"
    assert any(ev.level == "error" and "Docker is required" in ev.message
               for ev in coord.events)


# ---------------------------------------------------------------------------
# Docker daemon auto-start: try to start dockerd, else fall back
# ---------------------------------------------------------------------------
def test_docker_autostart_attempted_then_local_fallback(tmp_path, monkeypatch):
    """auto mode: when the daemon is down it tries to start it, and if that fails
    (or the image is unavailable) the scan still runs on the host."""
    install_scan_anthropic(monkeypatch)
    import openoffensive.runner as runner
    calls = []
    monkeypatch.setattr(runner, "docker_available", lambda: (False, "down"))
    monkeypatch.setattr(runner, "try_start_docker_daemon",
                        lambda **k: (calls.append(1), (False, "test: cannot start"))[1])
    monkeypatch.setattr(runner, "resolve_backend", lambda s: "local")
    monkeypatch.setattr(runner, "open_sandbox", lambda *a, **k: scan_sandbox())
    settings = build_settings(tmp_path, api_key_present=True, sandbox_backend="auto",
                              docker_autostart=True)
    coord = Coordinator(SCANNED_TARGET)
    result = run_scan(coord, settings=settings, scan_id="scan-as",
                      store=RunStore(str(tmp_path / "runs")))
    assert calls == [1]                                # the daemon start WAS attempted
    assert result.status == "done"
    assert len(result.findings) >= 1                   # fell back to local, scan ran
    assert any("attempting to start" in ev.message for ev in coord.events)


def test_docker_backend_autostart_fails_then_errors(tmp_path, monkeypatch):
    """explicit docker mode: it tries to start the daemon, and errors clearly if
    that fails (no silent local fallback for an explicit docker request)."""
    install_scan_anthropic(monkeypatch)
    import openoffensive.runner as runner
    calls = []
    monkeypatch.setattr(runner, "docker_available", lambda: (False, "down"))
    monkeypatch.setattr(runner, "try_start_docker_daemon",
                        lambda **k: (calls.append(1), (False, "test: no daemon"))[1])
    settings = build_settings(tmp_path, api_key_present=True, sandbox_backend="docker",
                              docker_autostart=True)
    coord = Coordinator(SCANNED_TARGET)
    result = run_scan(coord, settings=settings, scan_id="scan-de",
                      store=RunStore(str(tmp_path / "runs")))
    assert calls == [1]
    assert result.status == "error"
    assert any(ev.level == "error" and "Docker is required" in ev.message
               for ev in coord.events)
