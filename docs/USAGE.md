# Usage

## Requirements

- **Docker — required.** Every scan runs inside a container, so the Docker daemon must be
  installed and running. The first scan builds the sandbox image (`openoffensive-sandbox:kali`),
  which pulls a multi-GB Kali base and is slow; later scans reuse it. Preflight with
  `openoffensive doctor`.
- **Python 3.9 or newer** for the CLI and dashboard. The package itself has no runtime
  dependencies in scripted mode — but Docker is not optional.
- **LLM mode** additionally needs the `anthropic` SDK and an `ANTHROPIC_API_KEY` (see
  [Enabling LLM mode](#enabling-llm-mode)).

## Install

From the repository root:

```bash
pip install -e .                 # the CLI (no runtime Python deps)
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

## First run: build the sandbox image

Before the first scan, check the environment and build the Kali image:

```bash
openoffensive doctor --build
```

`doctor` reports whether the Docker daemon is reachable, the sandbox image tag, whether
`ANTHROPIC_API_KEY` is set, and the mode a scan would use. With `--build` it builds (or pulls)
the image so the first real scan does not pay the multi-GB download inline. Example output:

```
docker daemon   : OK
sandbox image   : openoffensive-sandbox:kali
ANTHROPIC_API_KEY: not set
mode            : scripted

building the sandbox image (first time pulls Kali — slow)…
  building sandbox image openoffensive-sandbox:kali (first run — pulls Kali, slow)…
  sandbox image built
image ready.
```

If Docker is unavailable, `doctor` exits `1` and says so; start the daemon and re-run.

## Quickstart

```bash
openoffensive doctor --build     # one-time: verify Docker, build the image
openoffensive scan               # headless scan of the bundled demo target
openoffensive serve              # the live dashboard (or ./run.sh)
```

With no target, `scan` starts the bundled vulnerable demo app on the host — bound to `0.0.0.0`
so the scan container can reach it via `host.docker.internal` — scans it, prints the live log,
and writes artifacts under `runs/`. Expect six findings and exit code `2`.

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
| `target` | What to scan — optional. A **git repo URL** is cloned into the container; a **local directory** is copied into the container; a **live URL/host** is probed over the network. Omit it to scan the bundled demo app. A bare host with no scheme gets `http://` prepended. |
| `--mode {auto,llm,scripted}` | Override the run mode for this scan (otherwise from `OPENOFFENSIVE_LLM_MODE`). |
| `--model MODEL` | Override the model id used in LLM mode (otherwise from `OPENOFFENSIVE_MODEL`). |
| `--runs-dir DIR` | Where to write run artifacts (otherwise from `OPENOFFENSIVE_RUNS_DIR`, default `runs`). |
| `--authorized` | Confirm you are authorized to test a **non-local URL** target. Required for any live host that is not localhost / `host.docker.internal`. |

How the target is handled is decided by `classify_target()`: a URL ending `.git`, starting
`git@`, or a `github.com` / `gitlab.com` / `bitbucket.org` repo path is a **repo** (cloned with
`git clone --depth 1`); an existing local path is a **dir** (`docker cp`'d in); anything else is
a **url** (probed black-box, nothing cloned).

Examples:

```bash
openoffensive scan                                        # the bundled demo
openoffensive scan https://github.com/org/repo            # clone a git repo into the container
openoffensive scan ./path/to/source                       # copy a local directory into the container
openoffensive scan http://127.0.0.1:8000                  # probe a local app black-box
openoffensive scan --mode llm --model claude-opus-5       # force LLM mode + model
openoffensive scan https://staging.example.com --authorized   # authorized live host
```

**Exit codes** (designed for CI):

| Code | Meaning |
| --- | --- |
| `0` | Scan completed, no findings. |
| `1` | Error (including a refused non-local URL target without `--authorized`, or Docker unavailable). |
| `2` | Scan completed with one or more findings. |

Scanning a non-local **URL** target without `--authorized` is refused before the container is
even started:

```
Refusing to scan a non-local target without authorization.
Only scan systems you own or have explicit written permission to test.
Re-run with --authorized once you have confirmed you are in scope.
```

(The gate applies to live-URL targets only. A git repo URL is cloned and reviewed, not
attacked over the network, so it does not require `--authorized`.)

### `doctor` — check readiness and build the image

```bash
openoffensive doctor [--build]
```

| Option | Description |
| --- | --- |
| `--build` | Build (or pull) the sandbox image now, instead of on the first scan. |

Prints Docker daemon status, the sandbox image tag, whether a key is set, and the resolved
mode. Exits `1` if Docker is unavailable.

### `serve` — start the live dashboard

```bash
openoffensive serve [--no-open]
```

| Option | Description |
| --- | --- |
| `--no-open` | Do not open a browser automatically. |

Boots the bundled demo target on `0.0.0.0` (so the scan container can reach it via
`host.docker.internal`) and the dashboard server (default `http://127.0.0.1:8777`), prints the
URLs, the active mode, and the Docker status, and serves the single-page UI. Click **Run scan**
to start; the agent graph, findings, and live log update in real time. Scans launched from the
dashboard run in a container exactly like the CLI path, so Docker must be available. The
dashboard is configured through environment variables (host, port, mode, model, sandbox) — see
the table below.

### `list` — list persisted runs

```bash
openoffensive list [--runs-dir DIR]
```

Prints a table of past runs (newest first) from the runs directory:

```
SCAN ID          STATUS   MODE      FINDINGS  TARGET
scan-ab6cce7e    done     scripted  6         http://host.docker.internal:44965
```

### `report` — print a run's Markdown report

```bash
openoffensive report <scan_id> [--runs-dir DIR]
```

Prints the stored `report.md` for a run to stdout (handy for piping or redirecting).

## Environment variables

All configuration is read from the environment by `config.py`. Every variable is optional; the
defaults run scripted mode against the bundled demo.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENOFFENSIVE_HOST` | `127.0.0.1` | Dashboard bind host. |
| `OPENOFFENSIVE_PORT` | `8777` | Dashboard bind port. |
| `OPENOFFENSIVE_LLM_MODE` | `auto` | `auto` (LLM when a key is present, else scripted), `llm` (force), or `scripted` (force). The `--mode` flag overrides this per scan. |
| `OPENOFFENSIVE_MODEL` | `claude-opus-5` | Model id used in LLM mode. |
| `OPENOFFENSIVE_MAX_TOKENS` | `4096` | Max tokens per model call (LLM mode). |
| `OPENOFFENSIVE_MAX_STEPS` | `24` | Per-agent tool-call budget in LLM mode. |
| `OPENOFFENSIVE_SANDBOX_IMAGE` | `openoffensive-sandbox:kali` | The container image a scan runs in. A tag starting with `openoffensive-sandbox` is built from the bundled `Dockerfile`; any other tag is `docker pull`ed instead. |
| `OPENOFFENSIVE_SANDBOX_NETWORK` | (empty) | Docker network for the scan container. Empty uses the default bridge; set it to attach the container to a specific network. |
| `OPENOFFENSIVE_RUNS_DIR` | `runs` | Directory for persisted run artifacts. |
| `ANTHROPIC_API_KEY` | (unset) | Anthropic API key. Its presence enables LLM mode when `OPENOFFENSIVE_LLM_MODE=auto`. |

CLI flags override the corresponding variables for a single `scan` (`--mode`, `--model`,
`--runs-dir`).

> `config.py` also still parses `OPENOFFENSIVE_SCOPE` and `OPENOFFENSIVE_SPEED` from the
> pre-container methodology, but neither affects a run under the container model: scope is now
> enforced by container isolation, the prompt, and the `--authorized` gate rather than a host
> allowlist, and the scripted methodology no longer paces itself with sleeps.

## Enabling LLM mode

Scripted mode is the default and needs no key (but does need Docker). To have the agents reason
with a real model instead:

1. **Install the extra:** `pip install -e '.[llm]'` (adds the `anthropic` SDK).
2. **Set a key:** `export ANTHROPIC_API_KEY=sk-ant-...`
3. **Run.** With `OPENOFFENSIVE_LLM_MODE=auto` (the default), a present key switches the run to
   LLM mode automatically. Force it explicitly with `--mode llm` or `OPENOFFENSIVE_LLM_MODE=llm`.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
openoffensive scan --mode llm                    # default model, claude-opus-5
openoffensive scan --mode llm --model claude-sonnet-5
```

The mode is resolved by `runner.resolve_mode`: if LLM mode is requested but the SDK or key is
missing, the scan falls back to scripted and logs a note explaining why. Both modes run inside
the container and use the same tools; only *who chooses each command* differs. See
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

In the dashboard, the **history** dropdown loads any past run and replays its log, graph, and
findings; the **view report** link opens the Markdown report.
