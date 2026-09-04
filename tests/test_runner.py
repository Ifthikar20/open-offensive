"""Runner behavior: the LLM preflight gate and loud failure when agents crash.

These lock in the fix for the "silent 0-finding scan" problem — a run where the
model is unreachable (or every specialist crashes) must end in status ``error``,
never a clean-looking ``done`` with exit 0.
"""

from __future__ import annotations

import sys
import types

from conftest import SCANNED_TARGET, build_settings

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
