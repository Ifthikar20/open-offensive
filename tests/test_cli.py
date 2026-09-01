"""The command-line interface: exit codes, artifact writing, and the safety guard.

Every scan here is either the bundled demo or a guard that returns before any
network call, so nothing reaches an external host.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from openoffensive import cli

_ARTIFACTS = ("run.json", "findings.json", "findings.sarif", "report.md", "events.jsonl")


def _scan_dirs(runs_dir) -> list[str]:
    root = Path(runs_dir)
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir()
                  if p.is_dir() and p.name.startswith("scan-"))


# ---------------------------------------------------------------------------
# --version / argument parsing
# ---------------------------------------------------------------------------
def test_version_prints_and_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "openoffensive" in out
    assert "1.0.0" in out


def test_no_subcommand_is_an_error():
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code != 0


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------
def test_scan_bundled_demo_returns_findings_and_writes_artifacts(tmp_path, capsys):
    runs = tmp_path / "runs"
    rc = cli.main(["scan", "--runs-dir", str(runs)])
    assert rc == 2  # bundled demo is vulnerable → findings present

    dirs = _scan_dirs(runs)
    assert len(dirs) == 1
    run_dir = runs / dirs[0]
    for name in _ARTIFACTS:
        assert (run_dir / name).exists(), name

    out = capsys.readouterr().out
    assert "bundled demo app" in out
    assert "Report:" in out


def test_scan_explicit_loopback_target(demo_target, tmp_path):
    runs = tmp_path / "runs"
    rc = cli.main(["scan", demo_target, "--runs-dir", str(runs)])
    assert rc == 2
    assert len(_scan_dirs(runs)) == 1


def test_scan_non_loopback_without_authorization_refuses(tmp_path, capsys):
    runs = tmp_path / "runs"
    # Must return 1 BEFORE any scan/network activity.
    rc = cli.main(["scan", "http://example.com", "--runs-dir", str(runs)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "Refusing" in err
    # nothing was scanned or written
    assert _scan_dirs(runs) == []


def test_scan_scripted_mode_override(tmp_path):
    runs = tmp_path / "runs"
    rc = cli.main(["scan", "--mode", "scripted", "--runs-dir", str(runs)])
    assert rc == 2
    run_dir = runs / _scan_dirs(runs)[0]
    import json
    rec = json.loads((run_dir / "run.json").read_text())
    assert rec["mode"] == "scripted"


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------
def test_list_empty_returns_zero(tmp_path, capsys):
    rc = cli.main(["list", "--runs-dir", str(tmp_path / "runs")])
    assert rc == 0
    assert "No runs yet" in capsys.readouterr().out


def test_list_after_scan_shows_the_run(tmp_path, capsys):
    runs = tmp_path / "runs"
    cli.main(["scan", "--runs-dir", str(runs)])
    capsys.readouterr()  # drop scan output

    rc = cli.main(["list", "--runs-dir", str(runs)])
    assert rc == 0
    out = capsys.readouterr().out
    scan_id = _scan_dirs(runs)[0]
    assert scan_id in out
    assert "done" in out
    assert "scripted" in out


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------
def test_report_prints_markdown_after_scan(tmp_path, capsys):
    runs = tmp_path / "runs"
    cli.main(["scan", "--runs-dir", str(runs)])
    capsys.readouterr()
    scan_id = _scan_dirs(runs)[0]

    rc = cli.main(["report", scan_id, "--runs-dir", str(runs)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "# OpenOffensive" in out
    assert "Penetration Test Report" in out


def test_report_missing_run_returns_one(tmp_path, capsys):
    rc = cli.main(["report", "scan-nope", "--runs-dir", str(tmp_path / "runs")])
    assert rc == 1
    assert "No report" in capsys.readouterr().err
