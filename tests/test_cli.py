"""The command-line interface: exit codes, artifact writing, and the safety guard.

A real scan needs Docker, which is unavailable here, so the scan tests inject a
:class:`FakeSandbox` by monkeypatching the runner's ``docker_available`` /
``open_sandbox`` seam (the ``no_docker`` fixture). ``doctor`` deliberately uses
the real preflight and reports Docker missing. The authorization guard is checked
to fire BEFORE any Docker/sandbox use.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import demo_sandbox

from openoffensive import cli

_ARTIFACTS = ("run.json", "findings.json", "findings.sarif", "report.md", "events.jsonl")


def _scan_dirs(runs_dir) -> list[str]:
    root = Path(runs_dir)
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir()
                  if p.is_dir() and p.name.startswith("scan-"))


@pytest.fixture
def no_docker(monkeypatch):
    """Make the runner build an injected FakeSandbox instead of a Docker container.

    ``docker_available`` is forced true and ``open_sandbox`` returns a sandbox
    that simulates the bundled demo app, so ``scan`` completes with findings and
    never touches a daemon.
    """
    import openoffensive.runner as runner
    monkeypatch.setattr(runner, "docker_available", lambda: (True, ""))
    monkeypatch.setattr(runner, "open_sandbox", lambda *a, **k: demo_sandbox())


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
# scan (through the injected sandbox — no Docker)
# ---------------------------------------------------------------------------
def test_scan_bundled_demo_returns_findings_and_writes_artifacts(no_docker, tmp_path, capsys):
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


def test_scan_explicit_loopback_target(no_docker, tmp_path):
    runs = tmp_path / "runs"
    rc = cli.main(["scan", "http://127.0.0.1:8123", "--runs-dir", str(runs)])
    assert rc == 2
    assert len(_scan_dirs(runs)) == 1


def test_scan_non_loopback_without_authorization_refuses(tmp_path, capsys):
    runs = tmp_path / "runs"
    # Must return 1 BEFORE any scan/sandbox activity (no no_docker fixture here).
    rc = cli.main(["scan", "http://example.com", "--runs-dir", str(runs)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "Refusing" in err
    # nothing was scanned or written
    assert _scan_dirs(runs) == []


def test_scan_scripted_mode_override(no_docker, tmp_path):
    runs = tmp_path / "runs"
    rc = cli.main(["scan", "--mode", "scripted", "--runs-dir", str(runs)])
    assert rc == 2
    run_dir = runs / _scan_dirs(runs)[0]
    rec = json.loads((run_dir / "run.json").read_text())
    assert rec["mode"] == "scripted"


# ---------------------------------------------------------------------------
# doctor — real preflight; Docker unavailable here
# ---------------------------------------------------------------------------
def test_doctor_returns_one_without_docker(capsys):
    rc = cli.main(["doctor"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "docker daemon" in out
    assert "UNAVAILABLE" in out


def _fake_anthropic(monkeypatch, *, raises=None):
    """Install a minimal fake `anthropic` module; its create() raises `raises`."""
    import sys
    import types
    mod = types.ModuleType("anthropic")

    class _Msgs:
        def create(self, **kw):
            if raises is not None:
                raise raises
            return object()

    class _Client:
        messages = _Msgs()

        def __init__(self, *a, **k):
            pass

    mod.Anthropic = _Client
    monkeypatch.setitem(sys.modules, "anthropic", mod)


def test_check_model_api_ok(monkeypatch):
    from openoffensive import Settings
    _fake_anthropic(monkeypatch)
    ok, msg = cli._check_model_api(Settings(model="claude-probe"))
    assert ok is True
    assert "claude-probe" in msg


def test_check_model_api_surfaces_underlying_cause(monkeypatch):
    # The SDK hides the real reason behind "Connection error."; doctor must reveal it.
    from openoffensive import Settings
    err = RuntimeError("Connection error.")
    err.__cause__ = ValueError("certificate verify failed")
    _fake_anthropic(monkeypatch, raises=err)
    ok, msg = cli._check_model_api(Settings(model="claude-probe"))
    assert ok is False
    assert "Connection error" in msg
    assert "certificate verify failed" in msg   # the hidden cause is now visible


def test_doctor_reports_model_api_when_key_present(monkeypatch, capsys):
    from openoffensive.config import reset_settings_cache
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    reset_settings_cache()
    _fake_anthropic(monkeypatch)               # API reachable
    cli.main(["doctor"])
    out = capsys.readouterr().out
    assert "model API" in out
    assert "reachable" in out


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------
def test_list_empty_returns_zero(tmp_path, capsys):
    rc = cli.main(["list", "--runs-dir", str(tmp_path / "runs")])
    assert rc == 0
    assert "No runs yet" in capsys.readouterr().out


def test_list_after_scan_shows_the_run(no_docker, tmp_path, capsys):
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
def test_report_prints_markdown_after_scan(no_docker, tmp_path, capsys):
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
