# OpenOffensive

[openoffensive.ai](https://openoffensive.ai) — an autonomous, multi-agent AI pentester
with a live dashboard. A **root orchestrator** plans an engagement and delegates to
**specialist sub-agents** that run in parallel; each loads skills, drives a **real HTTP
tool layer** against a target, calibrates severity, and files **validated findings** —
every step streamed to the browser in real time. It runs a fixed, auditable methodology
out of the box with **zero dependencies and no API key**, or has the agents reason with a
real model when one is configured.

## Run it

No install, no dependencies, no API key — just Python 3.9+:

```bash
./run.sh                     # start the live dashboard (opens a browser)
```

Or use the CLI:

```bash
pip install -e .             # puts `openoffensive` on your PATH
openoffensive serve          # the dashboard
openoffensive scan           # headless scan of the bundled demo target
```

`scan` with no target starts a bundled, deliberately vulnerable demo app on localhost,
scans it, prints the live log, writes artifacts to `runs/`, and exits `2` (findings
found). Full command and environment reference: [docs/USAGE.md](docs/USAGE.md).

## Features

- **Multi-agent by design** — a root that only orchestrates, plus Recon, Injection, and
  Access specialists that run as real parallel threads.
- **Real probing** — a shared tool layer makes real, scope-checked HTTP requests; every
  finding is confirmed from an actual response and carries severity, CVSS, evidence, a
  proof-of-concept, and a fix.
- **Two run modes** — **scripted** (default, deterministic, dependency-free) or **llm**
  (`pip install 'openoffensive[llm]'` + `ANTHROPIC_API_KEY`), using the exact same tools
  and findings store.
- **Live dashboard** — agent graph, findings, and a Server-Sent-Events live log, with a
  mode badge and a run-history dropdown.
- **Portable artifacts** — every run is persisted to `runs/<scan_id>/` as JSON, **SARIF
  2.1.0**, Markdown, and a full event stream.
- **Safe by scope** — a host allowlist confines the agents to the target; the CLI refuses
  non-loopback targets without `--authorized`.
- **CI-friendly** — `scan` exit codes: `0` clean, `1` error, `2` findings.

## Architecture

A root orchestrator delegates to specialist sub-agents; they share one **Coordinator**
(agent graph + event bus + findings store), one **tool registry**, and one **skills
library**. The runner resolves the mode, runs the root agent, and persists the result;
the dashboard reads the coordinator's events over SSE.

```
CLI / Dashboard → runner → Root Orchestrator → {Recon, Injection, Access}
                                    │
                     shared tool layer (real HTTP, allowlist-scoped)
                                    │
                      Coordinator (events + findings) → report.md · SARIF · runs/
```

The architecture references the open-source **Strix** project
([github.com/usestrix/strix](https://github.com/usestrix/strix)), re-implemented here at
proof-of-concept scale in OpenOffensive's own code. The full walkthrough, mermaid
diagrams, and the two-mode model are in **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

## Documentation

| Document | What it covers |
| --- | --- |
| [docs/README.md](docs/README.md) | Index of the documentation set. |
| [docs/VISION.md](docs/VISION.md) | The problem, the goal, the design principles, non-goals, and the roadmap. |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Diagrams, a module-by-module walkthrough, the two run modes, and the coordinator/event model. |
| [docs/USAGE.md](docs/USAGE.md) | Install, quickstart, every CLI subcommand and flag, all environment variables, LLM mode, and the artifacts. |
| [docs/TESTING.md](docs/TESTING.md) | Running the pytest suite, coverage, a manual smoke test, adding tests, and gating CI. |
| [docs/EXTENDING.md](docs/EXTENDING.md) | Adding a specialist, a tool, or a skill; swapping the LLM; extending the demo target. |
| [docs/SECURITY.md](docs/SECURITY.md) | The authorization and safety model: allowlist, the `--authorized` gate, and the localhost demo. |

## Project layout

```
open-offensive/
├── run.sh                     # one-command dashboard launcher
├── Makefile                   # dev shortcuts: install, dev, test, scan, serve
├── docs/                      # the documentation set (above)
└── openoffensive/             # the engine (pure standard library in scripted mode)
    ├── cli.py                 # openoffensive scan | serve | list | report
    ├── server.py              # dashboard HTTP server + SSE; boots the demo target
    ├── runner.py              # resolve mode → run root agent → persist
    ├── coordinator.py         # agent graph + event bus + findings store
    ├── agents.py              # RootAgent + Recon / Injection / Access specialists
    ├── tools.py               # real HTTP tool layer (host-allowlist scoped)
    ├── skills.py              # on-demand knowledge packs
    ├── llm.py                 # optional model brain (manual tool-use loop)
    ├── reporting.py           # findings → Markdown + SARIF 2.1.0
    ├── persistence.py         # runs/<scan_id>/ artifacts
    ├── models.py              # LogEvent / AgentState / Finding / ScanResult
    ├── config.py              # env-driven Settings
    ├── demo_target.py         # "Juice-Box" — intentionally vulnerable demo (localhost)
    └── web/index.html         # the single-page live dashboard
```

## Safety

OpenOffensive performs **authorized security testing only**. By default it tests just its
own bundled, deliberately vulnerable demo app on `127.0.0.1`. A host allowlist confines
the agents to the target, and the CLI refuses non-loopback targets without
`--authorized`. Do not aim it (or any pentesting tool) at systems you do not own or lack
explicit, written permission to test. Never deploy the demo target — it is vulnerable on
purpose. See [docs/SECURITY.md](docs/SECURITY.md).

## License

Apache-2.0.
