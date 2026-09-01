# Usage

## Requirements

- Python 3.9 or newer.
- Nothing else for scripted mode — it runs on the standard library.
- LLM mode additionally needs the `anthropic` SDK and an API key (see
  [Enabling LLM mode](#enabling-llm-mode)).

## Install

From the repository root:

```bash
pip install -e .                 # scripted mode — zero runtime dependencies
```

Optional extras:

```bash
pip install -e '.[llm]'          # add the anthropic SDK for LLM mode
pip install -e '.[llm,dev]'      # LLM + test tooling (pytest, pytest-timeout)
```

The `Makefile` wraps these:

```bash
make install                     # pip install -e .
make dev                         # pip install -e '.[llm,dev]'
```

Installing puts an `openoffensive` command on your PATH. Everything below also works as
`python -m openoffensive …` without installing.

## Quickstart

Three ways to get going, from least to most typing:

```bash
./run.sh                         # start the live dashboard (opens a browser)
```

```bash
openoffensive serve              # same dashboard, via the CLI
```

```bash
openoffensive scan               # headless scan of the bundled demo target
```

With no target, `scan` starts the bundled vulnerable demo app on `127.0.0.1`, scans it,
prints the live log, and writes artifacts under `runs/`. Expect six findings and exit
code `2`.

`make scan` and `make serve` are convenience wrappers (`scan --watch` and
`serve --no-open` respectively).

## CLI reference

```
openoffensive [--version] <command> [options]
```

### `scan` — run a headless scan

```bash
openoffensive scan [target] [options]
```

| Option | Description |
| --- | --- |
| `target` | URL or host to scan. Optional — omit it to scan the bundled demo app. A bare host gets `http://` prepended. |
| `--mode {auto,llm,scripted}` | Override the run mode for this scan (otherwise from `OPENOFFENSIVE_LLM_MODE`). |
| `--model MODEL` | Override the model id used in LLM mode (otherwise from `OPENOFFENSIVE_MODEL`). |
| `--runs-dir DIR` | Where to write run artifacts (otherwise from `OPENOFFENSIVE_RUNS_DIR`, default `runs`). |
| `--watch` | Pace the live log for human viewing. Without it the scan runs at full speed (used for CI and tests). |
| `--authorized` | Confirm you are authorized to test a **non-loopback** target. Required for any host that is not localhost. |

Examples:

```bash
openoffensive scan                                  # the bundled demo
openoffensive scan http://127.0.0.1:8000 --watch    # a local app, paced log
openoffensive scan --mode llm --model claude-opus-5 # force LLM mode + model
openoffensive scan https://staging.example.com --authorized   # authorized remote host
```

**Exit codes** (designed for CI):

| Code | Meaning |
| --- | --- |
| `0` | Scan completed, no findings. |
| `1` | Error (including a refused non-loopback target without `--authorized`). |
| `2` | Scan completed with one or more findings. |

Scanning a non-loopback target without `--authorized` is refused before any request is
sent:

```
Refusing to scan a non-loopback target without authorization.
Only scan systems you own or have explicit written permission to test.
Re-run with --authorized once you have confirmed you are in scope.
```

### `serve` — start the live dashboard

```bash
openoffensive serve [--no-open]
```

| Option | Description |
| --- | --- |
| `--no-open` | Do not open a browser automatically. |

Boots the bundled demo target and the dashboard server (default
`http://127.0.0.1:8777`), prints the URLs and the active mode, and serves the
single-page UI. Click **Run scan** to start; the agent graph, findings, and live log
update in real time. The dashboard is configured through environment variables (host,
port, mode, model) — see the table below.

### `list` — list persisted runs

```bash
openoffensive list [--runs-dir DIR]
```

Prints a table of past runs (newest first) from the runs directory:

```
SCAN ID          STATUS   MODE      FINDINGS  TARGET
scan-ab6cce7e    done     scripted  6         http://127.0.0.1:44965
```

### `report` — print a run's Markdown report

```bash
openoffensive report <scan_id> [--runs-dir DIR]
```

Prints the stored `report.md` for a run to stdout (handy for piping or redirecting).

## Environment variables

All configuration is read from the environment by `config.py`. Every variable is
optional; the defaults run scripted mode against the bundled demo.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENOFFENSIVE_HOST` | `127.0.0.1` | Dashboard bind host. |
| `OPENOFFENSIVE_PORT` | `8777` | Dashboard bind port. |
| `OPENOFFENSIVE_LLM_MODE` | `auto` | `auto` (LLM when a key is present, else scripted), `llm` (force), or `scripted` (force). |
| `OPENOFFENSIVE_MODEL` | `claude-opus-5` | Model id used in LLM mode. |
| `OPENOFFENSIVE_MAX_TOKENS` | `4096` | Max tokens per model call (LLM mode). |
| `OPENOFFENSIVE_MAX_STEPS` | `24` | Per-agent tool-call budget in LLM mode. |
| `OPENOFFENSIVE_RUNS_DIR` | `runs` | Directory for persisted run artifacts. |
| `OPENOFFENSIVE_SCOPE` | (empty) | Comma-separated extra hostnames the tool layer may reach, beyond the target. |
| `OPENOFFENSIVE_SPEED` | `1.0` | Multiplier on the small pacing sleeps that make the live log readable. `0` = instant. |
| `ANTHROPIC_API_KEY` | (unset) | Anthropic API key. Its presence enables LLM mode when `OPENOFFENSIVE_LLM_MODE=auto`. |

CLI flags override the corresponding variables for a single `scan` (`--mode`,
`--model`, `--runs-dir`).

## Enabling LLM mode

Scripted mode is the default and needs nothing. To have the agents reason with a real
model instead:

1. **Install the extra:** `pip install -e '.[llm]'` (adds the `anthropic` SDK).
2. **Set a key:** `export ANTHROPIC_API_KEY=sk-ant-...`
3. **Run.** With `OPENOFFENSIVE_LLM_MODE=auto` (the default), a present key switches the
   run to LLM mode automatically. Force it explicitly with `--mode llm` or
   `OPENOFFENSIVE_LLM_MODE=llm`.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
openoffensive scan --mode llm                    # default model, claude-opus-5
openoffensive scan --mode llm --model claude-sonnet-5
```

The mode is resolved by `runner.resolve_mode`: if LLM mode is requested but the SDK or
key is missing, the scan falls back to scripted and logs a note explaining why. See
[ARCHITECTURE.md](ARCHITECTURE.md#the-two-run-modes) for the full resolution logic.

## Reading the artifacts

Each run writes a directory under the runs dir (default `runs/<scan_id>/`):

| File | Contents |
| --- | --- |
| `run.json` | The full run record: status, severity counts, turns, cost, duration, and the embedded Markdown report. |
| `findings.json` | The findings array (id, title, severity, CVSS, endpoint, evidence, remediation, CWE, PoC, agent). |
| `findings.sarif` | SARIF 2.1.0 — upload to a code-scanning dashboard or ingest in CI. |
| `report.md` | The human-readable penetration-test report, ordered by CVSS. |
| `events.jsonl` | The complete live-log event stream, one JSON object per line — enough to replay the run. |

Quick ways to look at them:

```bash
openoffensive list                       # all runs, newest first
openoffensive report scan-ab6cce7e       # print that run's report.md
cat runs/scan-ab6cce7e/findings.sarif    # the SARIF document
```

In the dashboard, the **history** dropdown loads any past run and replays its log,
graph, and findings; the **view report** link opens the Markdown report.
