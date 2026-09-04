# OpenOffensive

[openoffensive.ai](https://openoffensive.ai) — a **Docker-based, multi-agent AI pentester**
with a live dashboard. Each scan spins up an isolated **Kali Linux container**, pulls the
target's source into it, and turns a **root orchestrator** loose: it delegates to
**specialist sub-agents** (Recon, Injection, Access) that each drive a tool-use loop,
running `nmap` / `curl` / `sqlmap` / `grep` and friends **inside the container** via
`docker exec`. Every finding is confirmed from real command output and carries a severity,
a CVSS score, evidence, a proof-of-concept, and a fix — streamed to the browser live. Point
it at a git repo, a live URL, or a local directory; with an `ANTHROPIC_API_KEY` a real model
decides each command, otherwise a fixed in-container playbook runs the same tools.

## Requirements

- **Docker — required.** Every scan runs in a container. The first run builds the sandbox
  image (`openoffensive-sandbox:kali`), which pulls a multi-GB Kali base and is slow (the
  same tradeoff Strix makes). No Docker, no scan.
- **Python 3.9+** to run the CLI and dashboard.
- **`ANTHROPIC_API_KEY` — optional.** With a key (plus `pip install 'openoffensive[llm]'`)
  the agents reason with a real model (**llm** mode). Without one they run a fixed
  in-container playbook of real commands (**scripted** mode) — which still needs Docker.

## Run it

```bash
pip install -e .                                # puts `openoffensive` on your PATH
openoffensive doctor --build                    # check Docker/LLM readiness, build the image
openoffensive scan                              # scan the bundled demo app
openoffensive scan https://github.com/org/repo  # clone a git repo into the container and scan it
openoffensive serve                             # live dashboard (or ./run.sh)
```

`scan` with no target starts a bundled, deliberately vulnerable demo app on the host — bound
so the container can reach it via `host.docker.internal` — scans it, prints the live log,
writes artifacts to `runs/`, and exits `2` (findings found). A non-local URL target requires
`--authorized`. Full command and environment reference: [docs/USAGE.md](docs/USAGE.md).

## Features

- **A Docker sandbox per scan** — one Kali container, built from
  [`openoffensive/sandbox/Dockerfile`](openoffensive/sandbox/Dockerfile) (nmap, sqlmap,
  nikto, whatweb, dirb, gobuster, wafw00f, curl/wget, git, python3, jq, dnsutils, netcat),
  created at the start of a run and `docker rm -f`'d at the end.
- **Target source pulled into the container** — a git repo is `git clone --depth 1`'d into
  `/workspace/<name>`, a local directory is `docker cp`'d in, and a live URL is probed over
  the network (nothing cloned). `classify_target()` picks repo / dir / url.
- **Tools run inside the container** — the core tool is `run_command`, which `docker exec`s a
  shell command in the Kali box; agents also `read_file`, `report_finding`, `load_skill` /
  `list_skills`, and `finish`. There is no host-side HTTP tool.
- **Multi-agent by design** — a root that only orchestrates, plus Recon, Injection, and
  Access specialists that run as real parallel threads against the one shared container.
- **Two run modes, both in the container** — **llm** (a real model decides each
  `run_command`) or **scripted** (a fixed playbook of real commands, no key). The mode
  auto-resolves: llm when a key is present, else scripted.
- **Live dashboard** — agent graph, findings, and a Server-Sent-Events live log, with a mode
  badge and a run-history dropdown.
- **Portable artifacts** — every run is persisted to `runs/<scan_id>/` as JSON, **SARIF
  2.1.0**, Markdown, and a full event stream.
- **Safe by design** — the agent runs arbitrary commands, but only inside an isolated,
  throwaway container; the CLI refuses a non-local URL target without `--authorized`.
- **CI-friendly** — `scan` exit codes: `0` clean, `1` error, `2` findings.

## Architecture

The runner preflights Docker, ensures the sandbox image, starts one keep-alive container,
gets the target's source in, and runs the root agent; the specialists share that container
and drive their tools through `docker exec`. Findings and every step flow through one
**Coordinator** (agent graph + event bus + findings store), which the dashboard reads over
SSE. When the run ends the container is removed and the findings become a report, SARIF, and
a persisted record.

```
openoffensive scan <repo | url | dir>
        │
        ▼
  runner.run_scan ──▶ docker_available? ──▶ ensure_image  (build/pull openoffensive-sandbox:kali)
        │
        ▼  docker run -d … tail -f /dev/null
   ┌──────────────────────── Kali sandbox container (one per scan) ────────────────────────┐
   │  /workspace/<target>  ◀── git clone --depth 1   │   docker cp   │   (url: nothing cloned) │
   │                                                                                          │
   │  Root Orchestrator ──spawn threads──▶  Recon · Injection · Access                        │
   │                                              │                                           │
   │                       run_command  ──▶  docker exec sh -lc  (nmap · curl · sqlmap · grep)│
   └──────────────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
  Coordinator (events + findings) ──▶ report.md · findings.sarif · runs/<scan_id>/
        │
        ▼  docker rm -f   (container torn down)
```

The architecture references the open-source **Strix** project
([github.com/usestrix/strix](https://github.com/usestrix/strix)) — a real Docker sandbox with
a Kali toolset, a multi-agent coordinator, load-on-demand skills, and validated CVSS
findings — re-implemented here at proof-of-concept scale in OpenOffensive's own code. The full
walkthrough, mermaid diagrams, and the two-mode model are in
**[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

## Documentation

| Document | What it covers |
| --- | --- |
| [docs/README.md](docs/README.md) | Index of the documentation set. |
| [docs/VISION.md](docs/VISION.md) | The problem, the goal, the design principles, non-goals, and the roadmap. |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Diagrams, a module-by-module walkthrough, the sandbox lifecycle, the two run modes, and the coordinator/event model. |
| [docs/USAGE.md](docs/USAGE.md) | Requirements, install, every CLI subcommand and flag, all environment variables, the first-run image build, LLM mode, and the artifacts. |
| [docs/TESTING.md](docs/TESTING.md) | Running the pytest suite without Docker (FakeSandbox + mocked `docker` CLI + mocked model), the Docker-gated integration test, and a real container scan. |
| [docs/EXTENDING.md](docs/EXTENDING.md) | Adding a specialist, a tool, or a skill; swapping the LLM; extending the sandbox image. |
| [docs/SECURITY.md](docs/SECURITY.md) | The isolation model: arbitrary commands inside a throwaway container, scope reliance, the `--authorized` gate, the demo target, and Docker daemon trust. |

## Project layout

```
open-offensive/
├── run.sh                     # one-command dashboard launcher
├── Makefile                   # dev shortcuts: install, dev, test, scan, serve
├── docs/                      # the documentation set (above)
└── openoffensive/             # the engine
    ├── cli.py                 # openoffensive scan | doctor | serve | list | report
    ├── server.py              # dashboard HTTP server + SSE; boots the demo target
    ├── runner.py              # preflight Docker → sandbox → target in → root agent → persist
    ├── coordinator.py         # agent graph + event bus + findings store
    ├── agents.py              # RootAgent + Recon / Injection / Access specialists
    ├── tools.py               # the tool registry, executed inside the container (run_command …)
    ├── skills.py              # on-demand knowledge packs
    ├── llm.py                 # optional model brain (manual tool-use loop)
    ├── reporting.py           # findings → Markdown + SARIF 2.1.0
    ├── persistence.py         # runs/<scan_id>/ artifacts
    ├── models.py              # LogEvent / AgentState / Finding / ScanResult
    ├── config.py              # env-driven Settings
    ├── demo_target.py         # "Juice-Box" — intentionally vulnerable demo app
    ├── sandbox/               # the Docker sandbox runtime
    │   ├── docker.py          #   DockerSandbox — one Kali container per scan, driven via the `docker` CLI
    │   ├── fake.py            #   FakeSandbox — in-memory stand-in for tests (no Docker)
    │   └── Dockerfile         #   the Kali image (openoffensive-sandbox:kali)
    └── web/index.html         # the single-page live dashboard
```

## Safety

OpenOffensive performs **authorized security testing only**. The agent is designed to run
arbitrary commands — that is the point — but it does so **inside an isolated, single-use Kali
container**, and it is told to touch only the in-scope target. By default it tests just its own
bundled, deliberately vulnerable demo app, reached from the container over
`host.docker.internal`. The CLI refuses a non-local URL target without `--authorized`. Do not
aim it (or any pentesting tool) at systems you do not own or lack explicit, written permission
to test. Never deploy the demo target — it is vulnerable on purpose and is bound so the
container can reach it. See [docs/SECURITY.md](docs/SECURITY.md).

## License

Apache-2.0.
