"""The sandbox runtime.

Three layers, none of which need a running Docker daemon:

* :class:`FakeSandbox` — the in-memory test double: it answers ``exec`` from a
  rules map, records every command, and no-ops the Docker lifecycle;
* :class:`DockerSandbox` — the real backend, whose exact ``docker`` CLI argv we
  pin by monkeypatching ``subprocess.run`` with a recorder;
* ``docker_available()`` — the preflight, which here reports Docker is
  unusable and *why*.

A real end-to-end DockerSandbox test is included but skips without a daemon.
"""

from __future__ import annotations

import uuid

import pytest

from openoffensive.sandbox import (
    SANDBOX_DIR,
    DockerSandbox,
    ExecResult,
    FakeSandbox,
    docker_available,
)
import openoffensive.sandbox.docker as docker_mod


# ---------------------------------------------------------------------------
# FakeSandbox
# ---------------------------------------------------------------------------
def test_fake_exec_matches_rule_then_default():
    sb = FakeSandbox(responses={"/login": ("boom", 500)}, default=("home", 0))

    hit = sb.exec("curl -s http://t/login?x=1")
    assert isinstance(hit, ExecResult)
    assert hit.stdout == "boom"
    assert hit.exit_code == 500
    assert hit.ok is False

    miss = sb.exec("curl -s http://t/")
    assert miss.stdout == "home"
    assert miss.exit_code == 0
    assert miss.ok is True


def test_fake_exec_supports_callable_rule():
    sb = FakeSandbox(responses={"echo": lambda cmd: (cmd.upper(), 0)})
    res = sb.exec("echo hi")
    assert res.stdout == "ECHO HI"


def test_fake_records_calls_in_order():
    sb = FakeSandbox()
    sb.exec("one")
    sb.exec("two")
    assert sb.calls == ["one", "two"]


def test_fake_lifecycle_flags_and_noops():
    sb = FakeSandbox()
    assert sb.started is False and sb.closed is False
    assert sb.image_exists() is True
    assert sb.ensure_image() is None  # no-op, never touches Docker
    sb.start()
    assert sb.started is True
    sb.close()
    assert sb.closed is True


def test_fake_add_repo_records_and_clones():
    sb = FakeSandbox()
    dest = sb.add_repo("https://github.com/acme/app.git", "app")
    assert dest == "/workspace/app"
    assert sb.repos == [("https://github.com/acme/app.git", "app")]
    # add_repo issues a real clone command through exec, so it is recorded.
    assert any(c.startswith("git clone --depth 1") and "/workspace/app" in c
               for c in sb.calls)


def test_fake_add_dir_and_read_file():
    sb = FakeSandbox(responses={"cat /workspace/app/x": ("contents", 0)})
    dest = sb.add_dir("/host/src", "app")
    assert dest == "/workspace/app"
    assert sb.dirs == [("/host/src", "app")]
    assert sb.read_file("/workspace/app/x") == "contents"


# ---------------------------------------------------------------------------
# ExecResult
# ---------------------------------------------------------------------------
def test_exec_result_combined_and_timeout():
    ok = ExecResult("cmd", "out", "warn", 0)
    text = ok.combined()
    assert "out" in text and "[stderr]" in text and "warn" in text

    to = ExecResult("cmd", "", "", 124, timed_out=True)
    assert to.ok is False
    assert "timed out" in to.combined()

    empty = ExecResult("cmd", "", "", 0)
    assert empty.combined() == "(no output)"


# ---------------------------------------------------------------------------
# DockerSandbox — pin the exact `docker` CLI argv (no daemon needed)
# ---------------------------------------------------------------------------
class _FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _Recorder:
    """Stand-in for subprocess.run: records argv and answers plausibly."""

    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, args, capture_output=True, text=True, timeout=None, **kw):
        self.calls.append(list(args))
        # `docker image inspect` → non-zero so ensure_image() takes the build path.
        if args[1:3] == ["image", "inspect"]:
            return _FakeCompleted(returncode=1)
        if args[1] == "exec" and "echo hi" in args[-1]:
            return _FakeCompleted(returncode=0, stdout="hi\n")
        return _FakeCompleted(returncode=0)


@pytest.fixture
def recorder(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(docker_mod.subprocess, "run", rec)
    return rec


def test_docker_ensure_image_builds_bundled_dockerfile(recorder):
    sb = DockerSandbox("abc123", image="openoffensive-sandbox:kali")
    sb.ensure_image(dockerfile_dir=SANDBOX_DIR)
    # first checks presence, then builds our bundled Dockerfile for the local tag
    assert ["docker", "image", "inspect", "openoffensive-sandbox:kali"] in recorder.calls
    assert ["docker", "build", "-t", "openoffensive-sandbox:kali",
            "-f", str(SANDBOX_DIR / "Dockerfile"), str(SANDBOX_DIR)] in recorder.calls


def test_docker_start_runs_keepalive_container(recorder):
    sb = DockerSandbox("abc123", image="openoffensive-sandbox:kali")
    sb.start()
    assert ["docker", "run", "-d", "--name", "oo-abc123",
            "--add-host", "host.docker.internal:host-gateway",
            "--cap-add", "NET_ADMIN", "--cap-add", "NET_RAW",
            "openoffensive-sandbox:kali", "tail", "-f", "/dev/null"] in recorder.calls


def test_docker_start_with_network_flag(recorder):
    sb = DockerSandbox("abc123", image="img", network="oo-net")
    sb.start()
    run_call = next(c for c in recorder.calls if c[:2] == ["docker", "run"])
    assert "--network" in run_call
    assert run_call[run_call.index("--network") + 1] == "oo-net"


def test_docker_exec_shells_into_container(recorder):
    sb = DockerSandbox("abc123", image="img")
    res = sb.exec("echo hi")
    assert ["docker", "exec", "-w", "/workspace", "oo-abc123",
            "sh", "-lc", "echo hi"] in recorder.calls
    assert res.stdout == "hi\n"
    assert res.exit_code == 0


def test_docker_add_repo_clones_via_exec(recorder):
    sb = DockerSandbox("abc123", image="img")
    dest = sb.add_repo("https://github.com/acme/app.git", "app")
    assert dest == "/workspace/app"
    clone = next(c for c in recorder.calls
                 if c[:2] == ["docker", "exec"] and c[-1].startswith("git clone"))
    assert clone[-1] == "git clone --depth 1 https://github.com/acme/app.git /workspace/app"


def test_docker_close_removes_container(recorder):
    sb = DockerSandbox("abc123", image="img")
    sb.start()
    sb.close()
    assert ["docker", "rm", "-f", "oo-abc123"] in recorder.calls


# ---------------------------------------------------------------------------
# docker_available — honest preflight
# ---------------------------------------------------------------------------
def test_docker_available_reports_a_reason_when_unusable():
    ok, reason = docker_available()
    # In this hermetic environment there is no daemon; either way it must explain.
    if not ok:
        assert reason  # non-empty explanation
    else:
        assert reason == ""


# ---------------------------------------------------------------------------
# real end-to-end DockerSandbox — SKIPPED without a daemon
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not docker_available()[0], reason="no docker daemon available")
def test_docker_sandbox_end_to_end(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM alpine:3\nCMD [\"sh\"]\n")
    image = f"openoffensive-sandbox:pytest-{uuid.uuid4().hex[:8]}"
    sb = DockerSandbox(uuid.uuid4().hex[:8], image=image)
    try:
        sb.ensure_image(dockerfile_dir=tmp_path)
        sb.start()
        res = sb.exec("echo hi")
        assert res.exit_code == 0
        assert res.stdout.strip() == "hi"
    finally:
        sb.close()
