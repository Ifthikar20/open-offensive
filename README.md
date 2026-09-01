# OpenOffensive

**openoffensive.ai** — a tiny, **dependency-free** proof-of-concept of an autonomous,
**multi-agent AI pentester**, with a **very simple UI and a live log** so you can watch
the whole engagement happen in real time.

A **root orchestrator** agent plans an engagement and delegates to **specialist
sub-agents** that run in parallel. Each specialist **loads skills**, drives a **tool
layer** that makes **real HTTP requests** against a bundled, deliberately-vulnerable
demo app, calibrates severity, and **files findings** — every step streamed to the
browser over Server-Sent Events.

> It's a **teaching POC**, not a production pentest tool. The "AI reasoning" is a
> scripted methodology (no LLM/API key needed), and the only target it ever touches is
> the demo app it starts on `127.0.0.1`.

## Run it

No install, no dependencies, no Docker, no API keys — just Python 3.8+:

```bash
./run.sh
```

or equivalently:

```bash
python3 server.py
```

It starts the vulnerable demo target, opens a dashboard (default
`http://127.0.0.1:8777`), and prints the URL. Click **▶ Run scan** and watch:

- **Live log** — every agent action as it happens: planning, `create_agent`,
  `load_skill`, real tool calls (`GET … → 200`), `finding filed`, `finish_scan`.
- **Agent graph** — the root and its specialists, statuses updating live.
- **Findings** — each validated issue with severity, CVSS, evidence, and a fix
  (click to expand). A **report** is compiled when the run finishes.

## Architecture

Every piece is a small, readable stand-in for a component of a real autonomous
pentest engine. The design **references the open-source Strix project**
([usestrix/strix](https://github.com/usestrix/strix)) — OpenOffensive re-implements
the same ideas at POC scale so they're easy to follow:

| OpenOffensive (`openoffensive/`) | Reference pattern |
| --- | --- |
| `coordinator.py` — agent graph, event bus, findings store, resume-snapshot idea | a multi-agent coordinator |
| `agents.py` — root orchestrator + specialist sub-agents, lifecycle tools | a graph of agents |
| `tools.py` — real HTTP probes, host allowlist | sandboxed tool execution |
| `skills.py` — knowledge packs loaded on demand | a load-on-demand skills library |
| `models.py` — Finding with CVSS/severity | validated findings + CVSS |
| `reporting.py` — final markdown report | `finish_scan` → report artifacts |
| `server.py` — local dashboard + live event stream | a local run viewer |
| `target/vulnerable_app.py` | the target under test (here, bundled & safe) |

Key ideas the live log makes visible:

- **The root only orchestrates** — it delegates every hands-on step to a sub-agent.
- **Specialists run in parallel**, so their logs interleave (real threads here).
- **Plain text never ends a turn** — agents finish through explicit lifecycle
  events (`agent_finish` / `finish_scan`).
- **Knowledge is data** — an agent loads the relevant skill *before* it acts.
- **Findings are validated and calibrated**, each carrying evidence, a PoC, a fix,
  and an honest severity.

## Project layout

```
open-offensive/
├── run.sh                    # one-command launcher
├── server.py                 # dashboard + SSE live-log stream; boots the target
├── openoffensive/            # the engine
│   ├── coordinator.py        # agent graph + event bus + findings store
│   ├── agents.py             # RootAgent + Recon / Injection / Access specialists
│   ├── tools.py              # real HTTP tool layer (localhost-only)
│   ├── skills.py             # on-demand knowledge packs
│   ├── reporting.py          # findings → markdown report
│   └── models.py             # LogEvent / AgentState / Finding
├── target/
│   └── vulnerable_app.py     # "Juice-Box" — intentionally vulnerable demo (localhost)
└── web/
    └── index.html            # the single-page live dashboard
```

## The demo target (Juice-Box)

A ~120-line stdlib app with five textbook, intentional weaknesses for the agents to
find: reflected XSS (`/search`), an error-leaking SQL endpoint (`/login`), an IDOR
(`/api/user/<id>`), missing security headers, and a hardcoded live key in a client
asset. It binds to loopback only and is vulnerable **on purpose** — never deploy it.

## Extending it

- **Plug in a real LLM.** Replace each specialist's scripted `work()` with an
  agent loop that asks a model which tool to call next — the coordinator, tools,
  skills, and UI stay the same.
- **Add a specialist or a skill.** Drop a class in `agents.py` and register it in
  `SPECIALISTS`; add a playbook to `skills.py`.
- **Point at another target** *only with authorization.* The tool layer enforces a
  host allowlist; the POC ships pointed at the bundled demo on purpose.

## Safety

OpenOffensive performs **authorized security testing against its own bundled demo app
on localhost only**. Do not aim it (or any pentesting tool) at systems you do not own
or lack explicit, written permission to test.
