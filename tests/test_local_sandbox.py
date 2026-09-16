"""LocalSandbox — the host-execution backend (real subprocess, no Docker).

These are genuine integration tests: they run actual shell commands on the host,
so they prove the container-less path installs nothing but really executes tool
calls. Guarded where a needed host tool might be absent.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from openoffensive.sandbox import local
from openoffensive.sandbox.local import LocalSandbox


def _sb() -> LocalSandbox:
    sb = LocalSandbox("test")
    sb.start()
    return sb


def test_exec_runs_a_real_host_command():
    sb = _sb()
    try:
        r = sb.exec("echo hello-oo")
        assert r.exit_code == 0
        assert not r.timed_out
        assert "hello-oo" in r.stdout
    finally:
        sb.close()


def test_exec_reports_nonzero_exit_and_stderr():
    sb = _sb()
    try:
        r = sb.exec("echo oops 1>&2; exit 3")
        assert r.exit_code == 3
        assert "oops" in r.stderr
        assert not r.ok
    finally:
        sb.close()


def test_exec_times_out_cleanly():
    sb = _sb()
    try:
        r = sb.exec("sleep 3", timeout=0.5)
        assert r.timed_out is True
        assert r.exit_code == 124
    finally:
        sb.close()


def test_exec_runs_in_the_workspace_dir():
    sb = _sb()
    try:
        r = sb.exec("pwd")
        assert os.path.basename(sb.workspace) in r.stdout
    finally:
        sb.close()


def test_add_dir_copies_source_into_workspace(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "secrets.txt").write_text("api_key = sk_live_deadbeef\n")
    sb = _sb()
    try:
        dest = sb.add_dir(str(src), "app")
        got = sb.exec(f"cat {dest}/secrets.txt")
        assert "sk_live_deadbeef" in got.stdout
    finally:
        sb.close()


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on host")
def test_add_repo_clones_a_local_repo(tmp_path):
    # Build a throwaway local git repo and clone it via a file:// URL.
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    (repo / "README.md").write_text("hello\n")
    for cmd in (["git", "init", "-q"], ["git", "add", "."],
                ["git", "commit", "-q", "-m", "init"]):
        subprocess.run(cmd, cwd=repo, env=env, check=True, capture_output=True)
    sb = _sb()
    try:
        dest = sb.add_repo(f"file://{repo}", "cloned")
        got = sb.exec(f"cat {dest}/README.md")
        assert "hello" in got.stdout
    finally:
        sb.close()


def test_close_removes_the_workspace():
    sb = LocalSandbox("cleanup")
    sb.start()
    ws = sb.workspace
    assert os.path.isdir(ws)
    sb.close()
    assert not os.path.exists(ws)


def test_available_and_missing_tools_partition_the_expected_set():
    sb = LocalSandbox("tools")
    present = set(sb.available_tools())
    missing = set(sb.missing_tools())
    assert present.isdisjoint(missing)
    assert present | missing == set(local.EXPECTED_TOOLS)
