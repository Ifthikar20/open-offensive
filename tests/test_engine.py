"""End-to-end scripted scan through an INJECTED sandbox — the whole engine wired
up with no Docker and no LLM.

The runner is handed a :class:`FakeSandbox` (``demo_sandbox()``) that simulates
the bundled vulnerable app, so the root agent + its three specialists run their
scripted playbooks against it and file all six findings.
"""

from __future__ import annotations

from conftest import SCANNED_TARGET, build_settings, demo_sandbox

from openoffensive import Coordinator, run_scan
from openoffensive.persistence import RunStore


def test_full_scripted_scan_findings_and_severities(scanned):
    result = scanned.result
    assert result.status == "done"
    assert result.mode == "scripted"

    # exactly six findings, spanning all five severities
    assert len(result.findings) == 6
    assert result.counts == {
        "critical": 1,
        "high": 2,
        "medium": 1,
        "low": 1,
        "info": 1,
    }
    assert result.top_severity == "critical"


def test_expected_finding_titles(scanned):
    titles = {f["title"] for f in scanned.result.findings}
    assert titles == {
        "Server version disclosure",
        "Hardcoded live secret key in client bundle",
        "Missing security headers",
        "Error-based SQL injection",
        "Reflected cross-site scripting (XSS)",
        "IDOR — unauthenticated access to any user record",
    }


def test_agent_graph_is_root_plus_three_specialists(scanned):
    agents = list(scanned.coord.agents.values())
    assert len(agents) == 4

    roots = [a for a in agents if a.parent is None]
    assert len(roots) == 1
    root = roots[0]
    assert root.role == "root"

    specialists = [a for a in agents if a.parent is not None]
    assert len(specialists) == 3
    assert all(a.parent == root.id for a in specialists)
    assert {a.role for a in specialists} == {"recon", "injection", "access"}


def test_all_agents_finish_cleanly(scanned):
    # No specialist crashed: every node ends 'done' (root included).
    statuses = {a.status for a in scanned.coord.agents.values()}
    assert statuses == {"done"}


def test_findings_carry_cvss_scores(scanned):
    for f in scanned.result.findings:
        assert f["cvss"] == {
            "critical": 9.4, "high": 7.8, "medium": 5.6, "low": 3.3, "info": 0.0,
        }[f["severity"]]


def test_injected_sandbox_is_started_used_but_not_closed(scanned):
    # The runner starts an injected sandbox and runs real commands in it, but —
    # unlike one it created itself — never closes it (the caller owns it).
    sb = scanned.sandbox
    assert sb.started is True
    assert sb.closed is False
    # the specialists' curl/for probes were recorded by the sandbox
    assert any("curl" in c for c in sb.calls)
    assert any(c.startswith("for i in") for c in sb.calls)


def test_scripted_scan_bills_no_model_turns(scanned):
    # Scripted mode never calls a model, so the spend meter stays at zero.
    assert scanned.result.turns == 0
    assert scanned.result.cost == 0.0


def test_scan_is_deterministic_across_runs(tmp_path):
    # Two independent runs of the scripted methodology agree on the outcome.
    def run_once(sub):
        settings = build_settings(tmp_path / sub)
        coord = Coordinator(SCANNED_TARGET)
        store = RunStore(str(tmp_path / sub / "runs"))
        return run_scan(coord, settings=settings, scan_id="scan-x", store=store,
                        sandbox=demo_sandbox())

    a = run_once("a")
    b = run_once("b")
    assert a.counts == b.counts
    assert {f["title"] for f in a.findings} == {f["title"] for f in b.findings}
