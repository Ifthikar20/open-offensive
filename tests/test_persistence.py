"""RunStore — writing and reading back the five per-run artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from openoffensive.persistence import RunStore

_ARTIFACTS = ("run.json", "findings.json", "findings.sarif", "report.md", "events.jsonl")


def test_save_writes_all_five_artifacts(scanned):
    # run_scan already persisted; re-saving is idempotent and exercises save().
    out_dir = scanned.store.save(scanned.coord, scanned.result)
    assert out_dir == scanned.store.dir_for(scanned.scan_id)
    for name in _ARTIFACTS:
        p = out_dir / name
        assert p.exists(), name
        assert p.stat().st_size > 0, name


def test_run_json_and_sarif_parse_as_json(scanned):
    d = scanned.store.dir_for(scanned.scan_id)
    run = json.loads((d / "run.json").read_text(encoding="utf-8"))
    assert run["scan_id"] == scanned.scan_id
    assert run["status"] == "done"
    assert run["counts"]["critical"] == 1

    sarif = json.loads((d / "findings.sarif").read_text(encoding="utf-8"))
    assert sarif["version"] == "2.1.0"
    assert len(sarif["runs"][0]["results"]) == 6

    findings = json.loads((d / "findings.json").read_text(encoding="utf-8"))
    assert isinstance(findings, list)
    assert len(findings) == 6


def test_events_jsonl_is_one_object_per_line(scanned):
    p = scanned.store.dir_for(scanned.scan_id) / "events.jsonl"
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines
    for ln in lines:
        obj = json.loads(ln)
        assert "seq" in obj and "level" in obj and "message" in obj


def test_list_runs_reports_total_and_status(scanned):
    runs = scanned.store.list_runs()
    assert len(runs) == 1
    rec = runs[0]
    assert rec["scan_id"] == scanned.scan_id
    assert rec["status"] == "done"
    assert rec["total"] == 6
    assert rec["mode"] == "scripted"
    assert rec["target"] == scanned.target
    assert rec["top_severity"] == "critical"


def test_list_runs_sorted_newest_first(scanned):
    # Add a second, newer run to the same store and confirm ordering.
    store = scanned.store
    older = scanned.result
    newer = type(older)(
        scan_id="scan-newer", target=older.target, mode="scripted", status="done",
        findings=[], counts={}, started_at=older.started_at + 100.0,
        finished_at=older.finished_at, report_md="# later",
    )
    store.save(scanned.coord, newer)
    runs = store.list_runs()
    ids = [r["scan_id"] for r in runs]
    assert ids[0] == "scan-newer"
    assert set(ids) == {"scan-newer", scanned.scan_id}


def test_load_run_returns_saved_record(scanned):
    rec = scanned.store.load_run(scanned.scan_id)
    assert rec is not None
    assert rec["scan_id"] == scanned.scan_id
    assert rec["counts"]["high"] == 2
    assert rec["mode"] == "scripted"


def test_load_run_missing_returns_none(scanned):
    assert scanned.store.load_run("does-not-exist") is None


def test_load_events_returns_dicts(scanned):
    events = scanned.store.load_events(scanned.scan_id)
    assert isinstance(events, list)
    assert len(events) > 0
    assert all(isinstance(e, dict) for e in events)
    # the run's opening system event is present
    assert any(e["level"] == "system" for e in events)


def test_load_events_missing_returns_empty(scanned):
    assert scanned.store.load_events("nope") == []


def test_load_report_returns_markdown(scanned):
    md = scanned.store.load_report(scanned.scan_id)
    assert md.startswith("# OpenOffensive")
    assert md == scanned.result.report_md


def test_load_report_missing_returns_empty(scanned):
    assert scanned.store.load_report("nope") == ""


def test_list_runs_empty_store(tmp_path):
    store = RunStore(str(Path(tmp_path) / "empty"))
    assert store.list_runs() == []
