# Testing

OpenOffensive is designed to be easy to test: scripted mode is deterministic, the
bundled demo target is a known set of vulnerabilities, and every seam (tools, config,
reporting, persistence) is a small pure-ish unit. This page covers running the suite,
what it covers, a manual smoke test, adding tests, and gating CI.

## Running the suite

The test suite lives in `tests/`. Install the dev extra and run pytest:

```bash
pip install -e '.[llm,dev]'      # or: make dev
make test                        # or: python -m pytest
```

`pyproject.toml` configures pytest to collect from `tests/`, run quietly (`-q`), and
apply a 60-second per-test timeout (via `pytest-timeout`). Run a subset the usual ways:

```bash
python -m pytest tests/test_tools.py
python -m pytest -k sarif
python -m pytest -q tests/test_engine.py::test_full_scripted_scan_findings_and_severities
```

The suite is organized by module: `test_tools.py`, `test_config.py`,
`test_reporting.py`, `test_persistence.py`, `test_llm.py`, and `test_demo_target.py` for
units; `test_engine.py` for the full scripted scan and `test_cli.py` for the CLI;
`conftest.py` holds shared fixtures (a live demo target, an instant-speed `Settings`, a
temp runs dir). It is developed alongside the engine, so expect it to grow with new
specialists and tools.

### Keep tests fast and hermetic

Two knobs make scans instant and isolated in tests:

- **Speed.** Set `speed=0.0` on `Settings` (or `OPENOFFENSIVE_SPEED=0`) so the pacing
  sleeps that make the live log watchable become no-ops. A full scripted scan then runs
  in milliseconds.
- **Runs directory.** Point `runs_dir` at a pytest `tmp_path` so artifacts never touch
  the repo.

`config.load_settings()` is memoized with `lru_cache`; a test that mutates the
environment should call `config.reset_settings_cache()` afterward (or construct a
`Settings(...)` directly and pass it in).

## What the suite covers

### Unit tests

| Area | What is asserted |
| --- | --- |
| **tools** | The host allowlist blocks out-of-scope hosts; `http_request` returns status/headers/body; `report_finding` files a calibrated, de-duplicated `Finding`; `execute()` turns unknown tools and bad arguments into text instead of raising. |
| **config** | `load_settings()` parses each `OPENOFFENSIVE_*` variable and applies defaults; `Settings.llm_enabled` follows the `auto` / `llm` / `scripted` truth table; `reset_settings_cache()` clears the memo. |
| **reporting** | `build_markdown()` orders findings by CVSS; `build_sarif()` emits valid SARIF 2.1.0 (schema, `version`, one rule per CWE, correct SARIF levels and `security-severity`); `to_result()` produces a coherent `ScanResult`. |
| **persistence** | `RunStore.save()` writes all five artifacts atomically; `load_run` / `load_events` / `load_report` / `list_runs` round-trip them; `list_runs` sorts newest first. |
| **llm (mocked)** | With a fake Anthropic client returning canned `tool_use` blocks, `run_agent_llm()` dispatches through the shared registry, feeds results back, and terminates on `finish` (and on the step budget); a `refusal` stop reason ends the agent cleanly. No network and no real key. |

### Integration tests

| Area | What is asserted |
| --- | --- |
| **full scripted scan** | Spin up the demo target, run a scan end to end, and assert the coordinator ends with the six expected findings and the right severity mix (1 critical, 2 high, 1 medium, 1 low, 1 info). |
| **CLI exit codes** | `cli.main(["scan", ...])` returns `2` when the demo yields findings, `0` for a clean target, and `1` for a refused non-loopback target (no `--authorized`). |
| **demo-target vulns** | Hit each Juice-Box endpoint directly and assert the intended weakness is present: reflected `q` on `/search`, a `500` SQL error on `/login?user=admin'`, an unauthenticated record with an `api_token` on `/api/user/1`, `sk_live_` in `/static/app.js`, and the absence of CSP / X-Frame-Options / X-Content-Type-Options. |

The demo-target assertions are the anchor: they pin the ground truth that the scripted
specialists are expected to discover, so a regression in either the target or an agent
surfaces immediately.

## Manual smoke test

A 30-second check that the whole pipeline works, writing to a throwaway directory:

```bash
# 1) Run a scan of the bundled demo into a temp runs dir.
OPENOFFENSIVE_RUNS_DIR=/tmp/oo-smoke openoffensive scan
echo "exit code: $?"        # expect 2 (findings)

# 2) Confirm the run and its findings.
openoffensive list --runs-dir /tmp/oo-smoke

# 3) Inspect the artifacts.
SCAN=$(ls -1 /tmp/oo-smoke | head -1)
cat /tmp/oo-smoke/$SCAN/report.md
python -c "import json,sys; d=json.load(open('/tmp/oo-smoke/$SCAN/findings.sarif')); \
  print('SARIF', d['version'], '-', len(d['runs'][0]['results']), 'results')"
```

You should see six findings topped by the critical hardcoded-secret finding, a
`report.md`, and `SARIF 2.1.0 - 6 results`. For a visual check, run `openoffensive serve`
and click **Run scan**.

## Adding a test for a new vuln or agent

When you add a vulnerability to the demo target and a specialist (or a check) that finds
it (see [EXTENDING.md](EXTENDING.md)), add tests in two layers. `conftest.py` already
provides the pieces you need — a session-scoped `demo_target` fixture (the base URL), a
`fast_settings` fixture (instant, scripted, temp runs dir), and a `scanned` fixture (a
completed scan) — so most tests just request those. The examples below call the
primitives directly to make the mechanism explicit:

1. **Pin the ground truth on the target.** Start the demo target and assert the raw
   behavior directly — no agents involved:

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

2. **Assert the agent finds it.** Run a scan against the target and check the finding
   lands with the expected severity:

   ```python
   from dataclasses import replace
   from openoffensive.config import load_settings
   from openoffensive.coordinator import Coordinator
   from openoffensive.runner import run_scan
   from openoffensive.persistence import RunStore

   def test_scan_reports_new_finding(tmp_path):
       srv, base = serve_in_thread("127.0.0.1", 0)
       settings = replace(load_settings(), speed=0.0, runs_dir=str(tmp_path))
       try:
           coord = Coordinator(base)
           run_scan(coord, settings=settings, scan_id="t", store=RunStore(tmp_path))
       finally:
           srv.shutdown()
       titles = [f.title for f in coord.findings]
       assert any("your new finding title" in t for t in titles)
   ```

Keep both: the target assertion catches a broken fixture; the scan assertion catches a
broken agent.

## Using it in CI

The `scan` exit-code contract is built for pipelines: **exit `2` means findings were
filed**, which you can use to fail a build. Because scripted mode has zero dependencies
and needs no API key, it runs anywhere Python does.

```yaml
# .github/workflows/appsec.yml
name: appsec
on: [push, pull_request]
jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e '.[dev]'
      - run: make test
      - name: Scan the bundled demo (fails the build on findings)
        run: openoffensive scan --runs-dir runs
      - name: Upload SARIF to code scanning
        if: always()
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: runs
```

Notes:

- The scan step exits `2` when findings are filed, which fails the job — the intended
  gate. Point it at a target you are authorized to test (a non-loopback target needs
  `--authorized`); the example scans the bundled demo, which always finds six issues, so
  treat it as a wiring demonstration and swap in your own target and threshold.
- `if: always()` uploads the SARIF even when the scan step failed, so findings still
  show up in the code-scanning UI. Every run writes `findings.sarif` under the runs dir.
- If you want the pipeline to *report* findings without failing, run the scan in a step
  that tolerates a non-zero exit (e.g. `openoffensive scan … || true`) and rely on the
  SARIF upload for signal.
