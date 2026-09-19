# Testing

OpenOffensive runs each scan in a Docker container, but **its test suite does not need
Docker**. The engine is built with the seams that make that possible: the sandbox is an
injectable dependency, the `docker` CLI is reached only through `subprocess`, and the
`anthropic` SDK is imported lazily. So the suite substitutes a `FakeSandbox`, a mocked `docker`
CLI, and a mocked model, and runs the whole engine deterministically and offline. This page
covers running the suite, the seams it leans on, the Docker-gated integration test, running a
real container scan, and adding tests.

## Running the suite

The test suite lives in `tests/`. Install the dev extra and run pytest:

```bash
pip install -e '.[llm,dev]'      # or: make dev
make test                        # or: python -m pytest
```

`pyproject.toml` configures pytest to collect from `tests/`, run quietly (`-q`), and apply a
60-second per-test timeout (via `pytest-timeout`). Run a subset the usual ways:

```bash
python -m pytest tests/test_tools.py
python -m pytest -k sarif
python -m pytest -q tests/test_engine.py
```

`conftest.py` holds the shared fixtures — a fake `anthropic` client that drives a full scan
(`install_scan_anthropic`), `FakeSandbox` helpers, a `scanned` fixture that runs one complete
scan offline, a throwaway `runs_dir` under `tmp_path`, and settings helpers — plus an autouse
fixture that strips `OPENOFFENSIVE_*` / `ANTHROPIC_API_KEY` from the environment and drops the
memoized settings around every test.

## How the suite avoids Docker

Three substitutions keep the suite hermetic. None of them starts a container or makes a network
call to a model.

### 1. `FakeSandbox` — the sandbox as an injected dependency

`run_scan()` takes an optional `sandbox` argument. In production it is `None`, so the runner
preflights Docker and builds a real `DockerSandbox`; in tests you pass a
`sandbox.fake.FakeSandbox`, and the runner skips `docker_available()` / `open_sandbox()` and
never touches a daemon (it also skips the teardown, since it did not create the sandbox).

`FakeSandbox` implements the same interface as `DockerSandbox` — `ensure_image()`, `start()`,
`exec()`, `add_repo()`, `add_dir()`, `read_file()`, `close()` — entirely in memory. `exec()`
answers from a rules map (a substring of the command → `(stdout, exit_code)`, or a callable),
falls back to a default, and records every command in `.calls` (and repos/dirs added in
`.repos` / `.dirs`) so a test can assert exactly what the engine ran:

```python
from openoffensive import Coordinator, run_scan
from openoffensive.sandbox import FakeSandbox
from conftest import build_settings, install_scan_anthropic

def test_scan_reproduces_findings(tmp_path, monkeypatch):
    # A fake anthropic client drives each specialist to run a command and file its
    # findings; the FakeSandbox answers those commands. No Docker, no network, no key.
    install_scan_anthropic(monkeypatch)
    sandbox = FakeSandbox(default=("TOOL OUTPUT", 0))
    settings = build_settings(tmp_path, api_key_present=True)   # temp runs_dir
    coord = Coordinator("http://target.test")
    run_scan(coord, settings=settings, scan_id="t", sandbox=sandbox)

    titles = [f.title for f in coord.findings]
    assert any("secret key" in t.lower() for t in titles)   # a filed finding
    assert any("curl" in c for c in sandbox.calls)          # a real command ran in the sandbox
```

`run_scan()` always preflights the model, so a scan test injects both the fake `anthropic` client
and the `FakeSandbox`. Because the fake makes `exec()` instant, a full scan runs in milliseconds.
Point `runs_dir` at a pytest `tmp_path` (the `build_settings` / `fast_settings` helpers already
do) so artifacts never touch the repo.

### 2. A mocked `docker` CLI for the real sandbox

`DockerSandbox` never imports docker-py — it shells out with `subprocess.run(["docker", …])`
through one private helper. To test the sandbox itself without a daemon, monkeypatch that
`subprocess.run` and assert the exact `docker` argv it builds — `image inspect`, `build` /
`pull`, `run -d … tail -f /dev/null`, `exec -w <wd> … sh -lc <cmd>`, `cp`, `rm -f` — returning
canned `CompletedProcess` objects:

```python
import subprocess
from openoffensive.sandbox.docker import DockerSandbox

def test_start_builds_expected_docker_run(monkeypatch):
    calls = []
    def fake_run(argv, **kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)

    DockerSandbox("s1", image="openoffensive-sandbox:kali").start()
    run_argv = next(c for c in calls if c[:2] == ["docker", "run"])
    assert "--add-host" in run_argv and "tail" in run_argv
```

`sandbox.docker_available()` is likewise just a `shutil.which` + `docker info` probe, so a test
that wants to force "Docker present/absent" monkeypatches it (or `subprocess.run`) rather than
depending on the host.

### 3. A mocked `anthropic` client for the model brain

The model brain is exercised without a key or the network by injecting a fake `anthropic` module
into `sys.modules` whose client replays a fixed list of responses (text blocks and `tool_use`
blocks). `run_agent_llm()` then executes those tool calls through the **real** shared registry
against a `FakeSandbox`, so the loop, the tool dispatch, the `think`/`tool` events, the billing,
and termination on `finish` / step budget / `refusal` are all covered:

```python
# see tests/test_llm.py: install_fake_anthropic(monkeypatch, [FakeResponse(...), ...])
```

`llm_available()` is honest about the real environment — it reports missing when no key is set
or the `anthropic` package is genuinely absent — so the "unavailable → raises `LLMUnavailable`"
path is testable directly. There is no scripted or canned fallback: an unreachable model crashes
the agent, it never produces demo output.

## Pinning the canonical findings

There is no bundled demo target to hit directly. Instead the fake model's playbook
(`_SCAN_PLAYBOOK` in `conftest.py`) drives each specialist to run one command against the
`FakeSandbox` and file a fixed set of findings, so a full scan through `install_scan_anthropic` +
`FakeSandbox` reproduces a **canonical set of findings**:

| Specialist focus | Filed finding(s) |
| --- | --- |
| Recon / attack surface | Hardcoded `sk_live_` secret key (critical), missing security headers (low), server version disclosure (info). |
| Injection | Error-based SQL injection (high), reflected XSS (medium). |
| Access / object-level authorization | IDOR — unauthenticated access to any user record (high). |

The `scanned` fixture runs exactly that scan once and hands the result to the engine, reporting,
and persistence tests, so a regression anywhere in the pipeline surfaces immediately. Each finding
is stamped with the command that produced it, so it stays traceable to the (fake) tool output.

## The Docker-gated integration test

One test exercises a **real** `DockerSandbox` end to end. It is skipped automatically unless a
Docker daemon is available, so the default suite stays Docker-free while CI on a Docker host still
gets real coverage of the container plumbing:

```python
import pytest, uuid
from openoffensive.sandbox import docker_available
from openoffensive.sandbox.docker import DockerSandbox

@pytest.mark.skipif(not docker_available()[0], reason="no docker daemon available")
def test_docker_sandbox_end_to_end(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM alpine:3\nCMD [\"sh\"]\n")
    sb = DockerSandbox(uuid.uuid4().hex[:8],
                       image=f"openoffensive-sandbox:pytest-{uuid.uuid4().hex[:8]}")
    try:
        sb.ensure_image(dockerfile_dir=tmp_path)              # build
        sb.start()                                            # docker run -d … tail -f /dev/null
        assert sb.exec("echo hi").stdout.strip() == "hi"      # docker exec
    finally:
        sb.close()                                            # docker rm -f
```

It builds a throwaway image and runs a container, so it is slower than the hermetic tests — keep
it out of the fast inner loop and let CI amortize Docker across runs. A full model-driven scan
against a real container needs both a daemon and a reachable model, so it is smoke-tested by hand
(below) rather than in the automated suite.

## Running a real container scan by hand

To smoke-test the real path on a machine with Docker (a reachable model is required):

```bash
# 1) Verify Docker and the model, and build the image up front (first build pulls Kali — slow).
export ANTHROPIC_API_KEY=sk-ant-...
openoffensive doctor --build

# 2) Scan an authorized target into a temp runs dir.
OPENOFFENSIVE_RUNS_DIR=/tmp/oo-smoke openoffensive scan https://example.com --authorized
echo "exit code: $?"        # 2 when findings are filed

# 3) Inspect the artifacts.
openoffensive list --runs-dir /tmp/oo-smoke
SCAN=$(ls -1 /tmp/oo-smoke | head -1)
cat /tmp/oo-smoke/$SCAN/report.md
```

For a visual check, run `openoffensive serve https://example.com --authorized` and click **Run
scan** (also a real container).

## Adding a test for a new specialist

When you add a specialist (see [EXTENDING.md](EXTENDING.md)), assert that a full scan files its
finding — driven by a fake model against a `FakeSandbox`, so there is no Docker, no network, and
no real key:

```python
from openoffensive import Coordinator, run_scan
from openoffensive.sandbox import FakeSandbox
from conftest import build_settings, install_scan_anthropic

def test_scan_reports_new_finding(tmp_path, monkeypatch):
    # The fake model drives each specialist to run a command and file its findings;
    # the FakeSandbox returns the signal that command would surface.
    install_scan_anthropic(monkeypatch)
    sandbox = FakeSandbox(responses={"/new-endpoint": ("...PROBE reflected...", 0)})
    settings = build_settings(tmp_path, api_key_present=True)
    coord = Coordinator("http://target.test")
    run_scan(coord, settings=settings, scan_id="t", sandbox=sandbox)
    assert any("your new finding title" in f.title for f in coord.findings)
```

To drive the *new* specialist specifically, teach the fake model about it: add an entry to the
playbook (`_SCAN_PLAYBOOK` in `conftest.py`) keyed on the specialist's `focus`, or install a
bespoke fake `anthropic` client (the pattern in `tests/test_llm.py`) that issues the exact
`run_command` + `report_finding` calls you want to cover. The `FakeSandbox` records every command
in `.calls`, so you can also assert the command really ran — without needing a daemon.

## Using it in CI

The `scan` exit-code contract is built for pipelines: **exit `2` means findings were filed**,
which you can use to fail a build. A real scan needs Docker and a reachable model, so the pipeline
must run on a host with a Docker daemon (GitHub's `ubuntu-latest` runners have one), set
`ANTHROPIC_API_KEY`, and build the sandbox image before scanning — the first build pulls the
multi-GB Kali base, so cache it where you can.

```yaml
# .github/workflows/appsec.yml
name: appsec
on: [push, pull_request]
jobs:
  scan:
    runs-on: ubuntu-latest        # has a Docker daemon
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e '.[llm,dev]'   # the anthropic SDK (a scan needs it) + test tooling
      - run: make test            # unit + integration; the container test runs here
      - name: Build the sandbox image
        run: openoffensive doctor --build
      - name: Scan the checked-out source (fails the build on findings)
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: openoffensive scan . --runs-dir runs
      - name: Upload SARIF to code scanning
        if: always()
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: runs
```

Notes:

- The scan step exits `2` when findings are filed, which fails the job — the intended gate.
  Point it at a target you are authorized to test: the checked-out source (as above) or a git
  repo URL needs no flag, while a non-local URL needs `--authorized`. The scan also needs
  `ANTHROPIC_API_KEY` (an encrypted Actions secret) — without a reachable model it fails at
  preflight. Set your own finding threshold rather than treating every finding as a build break.
- `if: always()` uploads the SARIF even when the scan step failed, so findings still show up in
  the code-scanning UI. Every run writes `findings.sarif` under the runs dir.
- If you want the pipeline to *report* findings without failing, run the scan in a step that
  tolerates a non-zero exit (e.g. `openoffensive scan … || true`) and rely on the SARIF upload
  for signal.
