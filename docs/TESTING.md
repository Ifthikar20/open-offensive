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

`conftest.py` holds the shared fixtures — a live demo target (a plain Python HTTP server, no
Docker), a throwaway `runs_dir` under `tmp_path`, and settings helpers — plus an autouse
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
from conftest import build_settings

def test_scan_files_the_leaked_key(tmp_path):
    # Program the container's responses: the recon step curls the JS bundle.
    sandbox = FakeSandbox(responses={
        "static/app.js": ("const K = 'sk_live_51ABCdemoLEAKED';", 0),
    })
    settings = build_settings(tmp_path)               # scripted, temp runs_dir
    coord = Coordinator("http://target.test")
    run_scan(coord, settings=settings, scan_id="t", sandbox=sandbox)

    titles = [f.title for f in coord.findings]
    assert any("secret key" in t.lower() for t in titles)
    assert any("static/app.js" in c for c in sandbox.calls)   # the command really ran
```

Because the fake makes `exec()` instant, a full scripted scan runs in milliseconds. Point
`runs_dir` at a pytest `tmp_path` (the `build_settings` / `fast_settings` helpers already do)
so artifacts never touch the repo.

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

### 3. A mocked `anthropic` client for LLM mode

LLM mode is exercised without a key or the network by injecting a fake `anthropic` module into
`sys.modules` whose client replays a scripted list of responses (text blocks and `tool_use`
blocks). `run_agent_llm()` then executes those tool calls through the **real** shared registry
against a `FakeSandbox`, so the loop, the tool dispatch, the `think`/`tool` events, the billing,
and termination on `finish` / step budget / `refusal` are all covered:

```python
# see tests/test_llm.py: install_fake_anthropic(monkeypatch, [FakeResponse(...), ...])
```

`llm_available()` is honest about the real environment — it reports missing when no key is set
or the `anthropic` package is genuinely absent — so the "unavailable → falls back / raises
`LLMUnavailable`" paths are testable directly.

## Pinning ground truth on the demo target

The demo target is a plain `ThreadingHTTPServer`, so the tests that assert its intentional
weaknesses hit it directly over loopback — no Docker, no agents:

| Endpoint | Intended weakness |
| --- | --- |
| `/search?q=…` | The `q` value is reflected into the HTML un-encoded (reflected XSS). |
| `/login?user=admin'` | A single quote leaks a raw SQL error with a `500`. |
| `/api/user/1` | Returns a record with an `api_token` and no auth (IDOR). |
| `/static/app.js` | Embeds an `sk_live_` secret. |
| `/` response headers | No CSP / X-Frame-Options / X-Content-Type-Options. |

These assertions are the anchor: they pin the ground truth that the scripted specialists (fed
the matching output through a `FakeSandbox`) are expected to discover, so a regression in either
the target or an agent surfaces immediately.

## The Docker-gated integration test

One end-to-end test exercises a **real** container. It is skipped automatically unless a Docker
daemon is available, so the default suite stays Docker-free while CI on a Docker host still gets
real coverage:

```python
import pytest
from openoffensive import cli
from openoffensive.sandbox import docker_available

@pytest.mark.skipif(not docker_available()[0], reason="no Docker daemon")
def test_real_container_scan(tmp_path):
    # Go through the CLI so the demo is bound on 0.0.0.0 and the scan targets
    # host.docker.internal — the wiring a real container needs to reach it.
    rc = cli.main(["scan", "--runs-dir", str(tmp_path)])
    assert rc == 2        # the bundled demo is vulnerable → findings → exit 2
```

This build/pull-and-run test is slow on a cold cache (it pulls the Kali base), so keep it out of
the fast inner loop and let CI amortize the image across runs.

## Running a real container scan by hand

To smoke-test the real path on a machine with Docker:

```bash
# 1) Verify Docker and build the image up front (first build pulls Kali — slow).
openoffensive doctor --build

# 2) Scripted scan of the bundled demo into a temp runs dir.
OPENOFFENSIVE_RUNS_DIR=/tmp/oo-smoke openoffensive scan
echo "exit code: $?"        # expect 2 (findings)

# 3) The same run under a real model (optional).
export ANTHROPIC_API_KEY=sk-ant-...
OPENOFFENSIVE_RUNS_DIR=/tmp/oo-smoke openoffensive scan --mode llm

# 4) Inspect the artifacts.
openoffensive list --runs-dir /tmp/oo-smoke
SCAN=$(ls -1 /tmp/oo-smoke | head -1)
cat /tmp/oo-smoke/$SCAN/report.md
```

For a visual check, run `openoffensive serve` and click **Run scan** (also a real container).

## Adding a test for a new vuln or agent

When you add a vulnerability to the demo target and a specialist that finds it (see
[EXTENDING.md](EXTENDING.md)), add tests in two layers:

1. **Pin the ground truth on the target.** Start the demo target and assert the raw behavior
   directly — no agents, no Docker:

   ```python
   import urllib.request
   from openoffensive.demo_target import serve_in_thread

   def test_new_endpoint_is_vulnerable():
       srv, base = serve_in_thread("127.0.0.1", 0)
       try:
           body = urllib.request.urlopen(base + "/new-endpoint?x=PROBE").read().decode()
           assert "PROBE" in body        # the intended weakness
       finally:
           srv.shutdown()
   ```

2. **Assert the agent finds it — with a `FakeSandbox`.** Program the fake's response for the
   command your `scripted()` playbook runs, then run a scan and check the finding lands:

   ```python
   from openoffensive import Coordinator, run_scan
   from openoffensive.sandbox import FakeSandbox
   from conftest import build_settings

   def test_scan_reports_new_finding(tmp_path):
       sandbox = FakeSandbox(responses={"/new-endpoint": ("...PROBE reflected...", 0)})
       coord = Coordinator("http://target.test")
       run_scan(coord, settings=build_settings(tmp_path), scan_id="t", sandbox=sandbox)
       assert any("your new finding title" in f.title for f in coord.findings)
   ```

Keep both: the target assertion catches a broken fixture; the FakeSandbox scan assertion catches
a broken agent, without needing a daemon.

## Using it in CI

The `scan` exit-code contract is built for pipelines: **exit `2` means findings were filed**,
which you can use to fail a build. A real scan needs Docker, so the pipeline must run on a host
with a Docker daemon (GitHub's `ubuntu-latest` runners have one) and should build the sandbox
image before scanning — the first build pulls the multi-GB Kali base, so cache it where you can.

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
      - run: pip install -e '.[dev]'
      - run: make test            # unit + integration; the container test runs here
      - name: Build the sandbox image
        run: openoffensive doctor --build
      - name: Scan the bundled demo (fails the build on findings)
        run: openoffensive scan --runs-dir runs
      - name: Upload SARIF to code scanning
        if: always()
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: runs
```

Notes:

- The scan step exits `2` when findings are filed, which fails the job — the intended gate.
  Point it at a target you are authorized to test (a non-local URL needs `--authorized`); the
  example scans the bundled demo, which always finds six issues, so treat it as a wiring
  demonstration and swap in your own target and threshold.
- `if: always()` uploads the SARIF even when the scan step failed, so findings still show up in
  the code-scanning UI. Every run writes `findings.sarif` under the runs dir.
- If you want the pipeline to *report* findings without failing, run the scan in a step that
  tolerates a non-zero exit (e.g. `openoffensive scan … || true`) and rely on the SARIF upload
  for signal.
