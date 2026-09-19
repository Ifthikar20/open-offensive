# Usage

## Requirements

- **Docker — required.** Every scan runs inside a container, so the Docker daemon must be
  installed and running. The first scan builds the sandbox image (`openoffensive-sandbox:kali`),
  which pulls a multi-GB Kali base and is slow; later scans reuse it. Preflight with
  `openoffensive doctor`.
- **Python 3.9 or newer** for the CLI and dashboard. The package core has no runtime
  dependencies — but Docker is not optional.
- **A reachable model is required.** Every scan is driven by a real model, so a scan needs the
  `anthropic` SDK (the `[llm]` extra) and an `ANTHROPIC_API_KEY` (see
  [The model key](#the-model-key)). Without a reachable model a scan fails at preflight — it
  never falls back to canned or demo output.

## Install

From the repository root:

```bash
pip install -e .                 # the CLI (no runtime Python deps)
```

Optional extras:

```bash
pip install -e '.[llm]'          # add the anthropic SDK (required to run a scan)
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

`doctor` reports whether the Docker daemon is reachable, the sandbox backend and image tag,
whether `ANTHROPIC_API_KEY` is set, and the model a scan would use. With `--build` it builds (or
pulls) the image so the first real scan does not pay the multi-GB download inline. Example output:

```
docker daemon    : OK
sandbox backend  : docker
sandbox image    : openoffensive-sandbox:kali
ANTHROPIC_API_KEY: not set
mode             : llm (claude-opus-5)
  set ANTHROPIC_API_KEY to run scans

building the sandbox image (first time pulls Kali — slow)…
  building sandbox image openoffensive-sandbox:kali (first run — pulls Kali, slow)…
  sandbox image built
image ready.
```

If Docker is unavailable, `doctor` exits `1` and says so; start the daemon and re-run.

## Quickstart

```bash
openoffensive doctor --build                          # one-time: verify Docker, build the image
openoffensive scan https://example.com --authorized   # headless scan of a target
openoffensive serve https://example.com --authorized  # the live dashboard (or ./run.sh <target>)
```

Every scan needs an explicit target — a git repo URL, a live URL/host, or a local directory — and
a reachable model. `scan` preflights the model, scans the target, prints the live log, and writes
artifacts under `runs/`, exiting `2` when it files findings. A non-local URL target requires
`--authorized`.

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
| `target` | What to scan — **required**. A **git repo URL** is cloned into the container; a **local directory** is copied into the container; a **live URL/host** is probed over the network. A bare host with no scheme gets `http://` prepended. |
| `--sandbox {auto,docker,local}` | Override the execution backend (otherwise from `OPENOFFENSIVE_SANDBOX`). `local` runs the tools on the host. |
| `--model MODEL` | Override the model id the agents reason with (otherwise from `OPENOFFENSIVE_MODEL`). |
| `--runs-dir DIR` | Where to write run artifacts (otherwise from `OPENOFFENSIVE_RUNS_DIR`, default `runs`). |
| `--authorized` | Confirm you are authorized to test a **non-local URL** target. Required for any live host that is not localhost / `host.docker.internal`. |

How the target is handled is decided by `classify_target()`: a URL ending `.git`, starting
`git@`, or a `github.com` / `gitlab.com` / `bitbucket.org` repo path is a **repo** (cloned with
`git clone --depth 1`); an existing local path is a **dir** (`docker cp`'d in); anything else is
a **url** (probed black-box, nothing cloned).

Examples:

```bash
openoffensive scan https://github.com/org/repo            # clone a git repo into the container
openoffensive scan ./path/to/source                       # copy a local directory into the container
openoffensive scan http://127.0.0.1:8000                  # probe a local app black-box
openoffensive scan ./path/to/source --model claude-sonnet-5   # override the model
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
| `--no-api-check` | Skip the live model API test (no token spend). |

Prints Docker daemon status, the sandbox backend and image tag, whether a key is set, and the
model a scan will use. Exits `1` if Docker is unavailable. When a key is present it also makes a **tiny real
model call** and prints a `model API` line — `OK — <model> reachable`, or the actual failure
(SSL/cert, auth, model-not-found) the SDK otherwise hides behind "Connection error." Since the
agents call the model from the host on their first step, a failure here is why an LLM scan would
otherwise crash — fix it before scanning.

### `serve` — start the live dashboard

```bash
openoffensive serve <target> [--authorized] [--no-open]
```

| Option | Description |
| --- | --- |
| `target` | What to scan — **required**: a git repo URL, a live URL/host, or a local directory (classified exactly as for `scan`). |
| `--authorized` | Confirm you are authorized to test a non-local URL target. |
| `--no-open` | Do not open a browser automatically. |

Starts the dashboard server (default `http://127.0.0.1:8777`) for the target you pass, prints the
URLs, the active model, and the Docker status, and serves the single-page UI. Click **Run scan**
to start; the agent graph, findings, and live log update in real time. Scans launched from the
dashboard run in a container exactly like the CLI path, so Docker must be available and a model
key must be set. The dashboard is configured through environment variables (host, port, model,
sandbox) — see the table below.

### `list` — list persisted runs

```bash
openoffensive list [--runs-dir DIR]
```

Prints a table of past runs (newest first) from the runs directory:

```
SCAN ID          STATUS   MODE      FINDINGS  TARGET
scan-ab6cce7e    done     llm       4         https://staging.example.com
```

### `report` — print a run's Markdown report

```bash
openoffensive report <scan_id> [--runs-dir DIR]
```

Prints the stored `report.md` for a run to stdout (handy for piping or redirecting).

## Environment variables

All configuration is read from the environment by `config.py`. Every variable is optional, but a
scan additionally requires `ANTHROPIC_API_KEY` and an explicit target.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENOFFENSIVE_HOST` | `127.0.0.1` | Dashboard bind host. |
| `OPENOFFENSIVE_PORT` | `8777` | Dashboard bind port. |
| `OPENOFFENSIVE_MODEL` | `claude-opus-5` | Model id the agents reason with. |
| `OPENOFFENSIVE_MAX_TOKENS` | `4096` | Max tokens per model call. |
| `OPENOFFENSIVE_MAX_STEPS` | `24` | Per-agent tool-call budget. |
| `OPENOFFENSIVE_SANDBOX` | `auto` | Execution backend for tool calls: `auto` (Docker if a daemon is reachable, else local host execution), `docker` (require a Kali container), or `local` (run tools directly on the host — no container isolation, only host-installed tools). |
| `OPENOFFENSIVE_DOCKER_AUTOSTART` | `1` | When Docker is wanted (`auto`/`docker`) but the daemon is down, try to start it (`service`/`systemctl`, or `dockerd` directly) before falling back. Needs root or passwordless sudo. Set `0` to disable. |
| `OPENOFFENSIVE_SANDBOX_IMAGE` | `openoffensive-sandbox:kali` | The container image a scan runs in. A tag starting with `openoffensive-sandbox` is built from the bundled `Dockerfile`; any other tag is `docker pull`ed instead. |
| `OPENOFFENSIVE_SANDBOX_NETWORK` | (empty) | Docker network for the scan container. Empty uses the default bridge; set it to attach the container to a specific network. |

## Building the sandbox image (including locked-down networks)

The default image builds from `openoffensive/sandbox/Dockerfile` (a Kali base). Where a
network blocks Docker Hub and the distro apt mirrors, that base can't be pulled. For those
environments there is a portable build that pulls its base from a reachable registry and
installs tools from PyPI, git-over-HTTPS, and static GitHub Release binaries:

```bash
./openoffensive/sandbox/build-image.sh      # tags openoffensive-sandbox:kali
```

It auto-detects an egress proxy (`HTTPS_PROXY`) and its CA and, when present, builds with
`--network host` so the build steps reach the allowed package sources. Once built, the
engine finds the image and runs scans in it. The portable toolset covers sqlmap, wafw00f,
wapiti, dirsearch, arjun, ffuf, gobuster, nuclei, and httpx; a few apt-native tools
(nmap, nikto, whatweb) aren't included and need a static binary or a prebuilt image.

## Running without Docker (local backend)

Where Docker isn't usable — a cloud or CI session, a locked-down network that can't pull the
Kali image, or a machine with no daemon — run the tool calls directly on the host:

```bash
pip install -e '.[llm]'
export ANTHROPIC_API_KEY=sk-ant-...
OPENOFFENSIVE_SANDBOX=local openoffensive scan https://github.com/org/repo
```

The `auto` default already falls back to `local` when no daemon is reachable, so this is
usually automatic. Two tradeoffs to know: local mode has **no container isolation** (the
agents' commands run as your user in a temporary workspace), and only the tools already
installed on the host are available — the full Kali suite (nmap, sqlmap, nikto, gobuster, …)
is only present in the Docker backend, so local scans lean on curl/python and source review.
Scope guardrails are unchanged: a non-local URL target still requires `--authorized`.
| `OPENOFFENSIVE_RUNS_DIR` | `runs` | Directory for persisted run artifacts. |
| `ANTHROPIC_API_KEY` | (unset) | Anthropic API key. **Required to run a scan** — the agents reason with a real model, and a scan fails at preflight without a reachable one. |

CLI flags override the corresponding variables for a single `scan` (`--model`, `--runs-dir`,
`--sandbox`).

> `config.py` also still parses `OPENOFFENSIVE_SCOPE` and `OPENOFFENSIVE_SPEED` from the
> pre-container methodology, but neither affects a run under the container model: scope is now
> enforced by container isolation, the prompt, and the `--authorized` gate rather than a host
> allowlist, and the model-driven run does not pace itself with artificial sleeps.

## The model key

Every scan is driven by a real model, so a reachable model is **required** — there is no scripted
or no-key mode. Set it up once:

1. **Install the extra:** `pip install -e '.[llm]'` (adds the `anthropic` SDK).
2. **Set a key:** `export ANTHROPIC_API_KEY=sk-ant-...`
3. **Run.** Pick a model with `--model` or `OPENOFFENSIVE_MODEL` (default `claude-opus-5`).

```bash
export ANTHROPIC_API_KEY=sk-ant-...
openoffensive scan https://example.com --authorized                          # default model, claude-opus-5
openoffensive scan https://example.com --authorized --model claude-sonnet-5  # pick the model
```

Every action flows through the same tool registry and runs inside the same container. See
[ARCHITECTURE.md](ARCHITECTURE.md#the-model-driven-agent-loop) for the full loop.

**Loud failure (no silent empty scans).** The run **preflights the model** before building the
container; if it can't be reached (a missing key or SDK, SSL/cert, auth, wrong model), the scan
**stops with a clear error and exit `1`** instead of the old behavior — three opaque
`crashed: Connection error` lines followed by a misleading `done / 0 findings / exit 0`. It never
falls back to canned or demo output. As a backstop, a run where every specialist crashes and
nothing is found is also reported as `error`. Run `openoffensive doctor` first to see the exact
cause.

### Windows

Works on **Docker Desktop in Linux-container mode** (the default) — all pentest tools run inside
the Linux Kali container, so the Windows host only shells out to `docker`. Notes:

- The CLI reconfigures stdout to UTF-8 and degrades gracefully if a captured console can't encode
  the live-log glyphs, so a piped/redirected scan won't die on `UnicodeEncodeError`.
- Put the key in a `.env` file in the repo (`ANTHROPIC_API_KEY=sk-ant-...`) — it's loaded
  automatically and is git-ignored — or `set ANTHROPIC_API_KEY=...` in the shell.
- A **local target** on `127.0.0.1` is reached via `host.docker.internal`, which Windows Firewall
  may block on first run; a git-repo or remote-URL scan uses ordinary container networking and is
  unaffected. Docker Desktop must be in Linux-container mode (a Kali image can't build under
  Windows containers).

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
