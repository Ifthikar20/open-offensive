"""Deliverables: the markdown report, SARIF 2.1.0, and the ScanResult record."""

from __future__ import annotations

from openoffensive import reporting

_SARIF_LEVEL = {"critical": "error", "high": "error", "medium": "warning",
                "low": "note", "info": "note"}


# ---------------------------------------------------------------------------
# markdown
# ---------------------------------------------------------------------------
def test_markdown_has_title_and_every_finding(scanned):
    md = reporting.build_markdown(scanned.coord)
    assert md.startswith("# OpenOffensive")
    assert "Penetration Test Report" in md
    assert f"**Target:** {scanned.target}" in md
    assert "**Mode:** scripted" in md
    for f in scanned.coord.findings:
        assert f.title in md
        # each finding renders its severity/CVSS heading
        assert f"CVSS {f.cvss}" in md


def test_markdown_no_findings_message():
    from openoffensive import Coordinator
    md = reporting.build_markdown(Coordinator("http://127.0.0.1:1"))
    assert "_No findings._" in md


# ---------------------------------------------------------------------------
# SARIF 2.1.0
# ---------------------------------------------------------------------------
def test_sarif_top_level_shape(scanned):
    sarif = reporting.build_sarif(scanned.coord)
    assert sarif["version"] == "2.1.0"
    assert "$schema" in sarif
    assert len(sarif["runs"]) == 1
    driver = sarif["runs"][0]["tool"]["driver"]
    assert driver["name"] == "OpenOffensive"
    assert isinstance(driver["rules"], list)
    assert driver["rules"]  # at least one rule


def test_sarif_one_result_per_finding(scanned):
    sarif = reporting.build_sarif(scanned.coord)
    results = sarif["runs"][0]["results"]
    assert len(results) == len(scanned.coord.findings) == 6


def test_sarif_level_mapping(scanned):
    results = reporting.build_sarif(scanned.coord)["runs"][0]["results"]
    for res in results:
        severity = res["properties"]["severity"]
        assert res["level"] == _SARIF_LEVEL[severity]
    # the scan spans all three SARIF levels
    levels = {r["level"] for r in results}
    assert levels == {"error", "warning", "note"}


def test_sarif_rules_carry_security_severity(scanned):
    rules = reporting.build_sarif(scanned.coord)["runs"][0]["tool"]["driver"]["rules"]
    for rule in rules:
        assert "security-severity" in rule["properties"]
        # numeric string parseable as a float (SARIF convention)
        float(rule["properties"]["security-severity"])


def test_sarif_results_reference_defined_rules(scanned):
    sarif = reporting.build_sarif(scanned.coord)
    run = sarif["runs"][0]
    defined = {r["id"] for r in run["tool"]["driver"]["rules"]}
    for res in run["results"]:
        assert res["ruleId"] in defined


# ---------------------------------------------------------------------------
# to_result round-trip
# ---------------------------------------------------------------------------
def test_to_result_round_trips_counts(scanned):
    coord = scanned.coord
    result = reporting.to_result(coord, "scan-rt", "done", started_at=0.0)
    assert result.counts == coord.severity_counts()
    assert result.counts == {
        "critical": 1, "high": 2, "medium": 1, "low": 1, "info": 1,
    }
    assert len(result.findings) == len(coord.findings)
    assert result.scan_id == "scan-rt"
    assert result.status == "done"
    assert result.mode == coord.mode
    assert result.report_md == reporting.build_markdown(coord)


def test_summary_headline_points_at_top_finding(scanned):
    summ = reporting.summary(scanned.coord)
    assert summ["total"] == 6
    assert summ["counts"] == scanned.coord.severity_counts()
    # highest-CVSS finding is the critical leaked key
    assert summ["headline"].startswith("CRITICAL")
