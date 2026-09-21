"""End-to-end scan through an INJECTED sandbox and a fake model — the whole engine
wired up with no Docker and no network.

The runner is handed a :class:`FakeSandbox` and a fake ``anthropic`` client
(``install_scan_anthropic``) that drives the root agent's three specialists to run
real commands in the sandbox and file the canonical six findings.
"""

from __future__ import annotations

from conftest import SCANNED_TARGET, build_settings, install_scan_anthropic, scan_sandbox

from openoffensive import Coordinator, run_scan
from openoffensive.persistence import RunStore


def test_full_scan_findings_and_severities(scanned):
    result = scanned.result
    assert result.status == "done"
    assert result.mode == "llm"

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


def test_findings_carry_provenance(scanned):
    # The trust guarantee: every finding records the exact command the agent ran in
    # the container AND the raw output it was drawn from — so a finding is traceable
    # to real container I/O, not asserted out of thin air.
    for f in scanned.result.findings:
        assert f["command"], f"{f['title']} has no command provenance"
        assert f["output"], f"{f['title']} has no output provenance"


def test_injected_sandbox_is_started_used_but_not_closed(scanned):
    # The runner starts an injected sandbox and runs real commands in it, but —
    # unlike one it created itself — never closes it (the caller owns it).
    sb = scanned.sandbox
    assert sb.started is True
    assert sb.closed is False
    # the specialists' curl/for probes were recorded by the sandbox
    assert any("curl" in c for c in sb.calls)
    assert any(c.startswith("for i in") for c in sb.calls)


def test_llm_scan_bills_model_turns(scanned):
    # Every model call is billed, so a real (model-driven) run shows a live meter.
    assert scanned.result.turns > 0
    assert scanned.result.cost > 0


def test_scan_is_deterministic_across_runs(tmp_path, monkeypatch):
    # Two independent runs of the same fake-driven methodology agree on the outcome.
    install_scan_anthropic(monkeypatch)

    def run_once(sub):
        settings = build_settings(tmp_path / sub, api_key_present=True)
        coord = Coordinator(SCANNED_TARGET)
        store = RunStore(str(tmp_path / sub / "runs"))
        return run_scan(coord, settings=settings, scan_id="scan-x", store=store,
                        sandbox=scan_sandbox())

    a = run_once("a")
    b = run_once("b")
    assert a.counts == b.counts
    assert {f["title"] for f in a.findings} == {f["title"] for f in b.findings}
