"""Runner behavior: the LLM preflight gate and loud failure when agents crash.

These lock in the fix for the "silent 0-finding scan" problem — a run where the
model is unreachable (or every specialist crashes) must end in status ``error``,
never a clean-looking ``done`` with exit 0.
"""

from __future__ import annotations

import sys
import types

from conftest import SCANNED_TARGET, build_settings, demo_sandbox

from openoffensive import Coordinator, run_scan
from openoffensive.models import AgentState, Finding
from openoffensive.persistence import RunStore
from openoffensive.runner import _failed_from_crashes
from openoffensive.sandbox.fake import FakeSandbox
from openoffensive.demo_target import serve_in_thread

import shutil
import pytest


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
    settings = build_settings(tmp_path, llm_mode="llm", api_key_present=True)
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


def test_scripted_scan_skips_preflight(scanned):
    # Scripted mode makes no model call, so the preflight never runs and the run
    # completes normally with findings (guards against the gate over-firing).
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
# backend selection — local host execution runs without Docker; docker requires a daemon
# ---------------------------------------------------------------------------
@pytest.mark.skipif(shutil.which("curl") is None, reason="curl not on host")
def test_local_backend_scans_the_demo_without_docker(tmp_path):
    """A real LocalSandbox (no injected sandbox, no Docker) runs the scripted tools
    on the host against the bundled demo and files findings — the core unblock."""
    from openoffensive import Settings
    srv, _ = serve_in_thread("127.0.0.1", 0)
    port = srv.server_address[1]
    try:
        settings = Settings(speed=0.0, llm_mode="scripted", api_key_present=False,
                            sandbox_backend="local", runs_dir=str(tmp_path / "runs"))
        coord = Coordinator(f"http://127.0.0.1:{port}")
        result = run_scan(coord, settings=settings, scan_id="scan-local",
                          store=RunStore(str(tmp_path / "runs")))  # sandbox=None → real LocalSandbox
        assert result.status == "done"
        assert len(coord.findings) >= 1
        titles = " ".join(f.title.lower() for f in coord.findings)
        assert ("sql" in titles) or ("idor" in titles) or ("secret" in titles)
        # tool calls really executed on the host (not a container)
        assert any("host" in ev.message for ev in coord.events if ev.level == "system")
    finally:
        srv.shutdown()
        srv.server_close()


def test_docker_backend_without_daemon_errors(tmp_path, monkeypatch):
    """An explicit docker backend with no daemon fails loudly at the Docker gate."""
    import openoffensive.runner as runner
    monkeypatch.setattr(runner, "docker_available",
                        lambda: (False, "the Docker daemon is not running or not reachable"))
    settings = build_settings(tmp_path, llm_mode="scripted", sandbox_backend="docker")
    coord = Coordinator(SCANNED_TARGET)
    result = run_scan(coord, settings=settings, scan_id="scan-nd",
                      store=RunStore(str(tmp_path / "runs")))  # sandbox=None
    assert result.status == "error"
    assert any(ev.level == "error" and "Docker is required" in ev.message
               for ev in coord.events)


# ---------------------------------------------------------------------------
# Docker daemon auto-start (blocker 1): try to start dockerd, else fall back
# ---------------------------------------------------------------------------
def test_docker_autostart_attempted_then_local_fallback(tmp_path, monkeypatch):
    """auto mode: when the daemon is down it tries to start it, and if that fails
    (or the image is unavailable) the scan still runs on the host."""
    import openoffensive.runner as runner
    calls = []
    monkeypatch.setattr(runner, "docker_available", lambda: (False, "down"))
    monkeypatch.setattr(runner, "try_start_docker_daemon",
                        lambda **k: (calls.append(1), (False, "test: cannot start"))[1])
    monkeypatch.setattr(runner, "resolve_backend", lambda s: "local")
    monkeypatch.setattr(runner, "open_sandbox", lambda *a, **k: demo_sandbox())
    settings = build_settings(tmp_path, llm_mode="scripted", sandbox_backend="auto",
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
    import openoffensive.runner as runner
    calls = []
    monkeypatch.setattr(runner, "docker_available", lambda: (False, "down"))
    monkeypatch.setattr(runner, "try_start_docker_daemon",
                        lambda **k: (calls.append(1), (False, "test: no daemon"))[1])
    settings = build_settings(tmp_path, llm_mode="scripted", sandbox_backend="docker",
                              docker_autostart=True)
    coord = Coordinator(SCANNED_TARGET)
    result = run_scan(coord, settings=settings, scan_id="scan-de",
                      store=RunStore(str(tmp_path / "runs")))
    assert calls == [1]
    assert result.status == "error"
    assert any(ev.level == "error" and "Docker is required" in ev.message
               for ev in coord.events)
