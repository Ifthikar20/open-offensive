# OpenOffensive documentation

[OpenOffensive](https://openoffensive.ai) is a Docker-based, multi-agent AI pentester with a
live dashboard. Each scan spins up an isolated Kali container, pulls the target's source into
it, and turns a root orchestrator loose: it delegates to specialist sub-agents that load
skills, drive real tools **inside the container** (`nmap`, `curl`, `sqlmap`, `grep` the source,
…) via `docker exec`, and file validated findings — every step streamed to a browser in real
time. A real model (Anthropic Claude, via `ANTHROPIC_API_KEY`) decides each command; a scan
requires a reachable model and fails loudly at preflight without one — findings only ever come
from real tool output, never canned or demo data.

This directory is the reference set. Start with whichever door fits what you need.

| Document | What it covers |
| --- | --- |
| [VISION.md](VISION.md) | The problem we're attacking, the goal, the design principles, non-goals, and the roadmap. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | The full system: diagrams, a module-by-module walkthrough, the sandbox lifecycle, the model-driven agent loop, and the coordinator/event model. |
| [USAGE.md](USAGE.md) | Requirements, install, the first-run image build, every CLI subcommand and flag, all environment variables, the required model key, and reading the artifacts. |
| [TESTING.md](TESTING.md) | Running the pytest suite without Docker (FakeSandbox + mocked `docker` CLI + mocked model), the Docker-gated integration test, a real container scan, and adding tests. |
| [EXTENDING.md](EXTENDING.md) | Adding a specialist agent, a tool, or a skill; extending the sandbox image; plugging in or swapping the LLM. |
| [SECURITY.md](SECURITY.md) | The isolation and authorization model: arbitrary commands inside a throwaway container, scope reliance, the `--authorized` gate, and Docker daemon trust. |

## Reference

Background material on the upstream project OpenOffensive draws from — reference reading, not
part of OpenOffensive's own product docs.

| Document | What it covers |
| --- | --- |

## Fast path

```bash
pip install -e '.[llm]'                # the CLI + the anthropic SDK
export ANTHROPIC_API_KEY=sk-ant-...    # required — the agents reason with a real model
openoffensive doctor --build           # verify Docker and build the Kali sandbox image (first run is slow)
openoffensive scan https://example.com --authorized   # scan a target: repo URL, live URL/host, or local dir
openoffensive serve https://example.com --authorized  # live dashboard for a target (or ./run.sh <target>)
```

A scan needs a reachable model (set `ANTHROPIC_API_KEY`) and, by default, Docker. See
[USAGE.md](USAGE.md) for the rest.
