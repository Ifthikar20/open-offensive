# OpenOffensive documentation

[OpenOffensive](https://openoffensive.ai) is a Docker-based, multi-agent AI pentester with a
live dashboard. Each scan spins up an isolated Kali container, pulls the target's source into
it, and turns a root orchestrator loose: it delegates to specialist sub-agents that load
skills, drive real tools **inside the container** (`nmap`, `curl`, `sqlmap`, `grep` the source,
…) via `docker exec`, and file validated findings — every step streamed to a browser in real
time. With an `ANTHROPIC_API_KEY` a real model decides each command; without one a fixed
in-container playbook runs the same tools.

This directory is the reference set. Start with whichever door fits what you need.

| Document | What it covers |
| --- | --- |
| [VISION.md](VISION.md) | The problem we're attacking, the goal, the design principles, non-goals, and the roadmap. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | The full system: diagrams, a module-by-module walkthrough, the sandbox lifecycle, the two run modes, and the coordinator/event model. |
| [USAGE.md](USAGE.md) | Requirements, install, the first-run image build, every CLI subcommand and flag, all environment variables, enabling LLM mode, and reading the artifacts. |
| [TESTING.md](TESTING.md) | Running the pytest suite without Docker (FakeSandbox + mocked `docker` CLI + mocked model), the Docker-gated integration test, a real container scan, and adding tests. |
| [EXTENDING.md](EXTENDING.md) | Adding a specialist agent, a tool, or a skill; extending the sandbox image; plugging in or swapping the LLM; extending the demo target. |
| [SECURITY.md](SECURITY.md) | The isolation and authorization model: arbitrary commands inside a throwaway container, scope reliance, the `--authorized` gate, the demo target, and Docker daemon trust. |

## Reference

Background material on the upstream project OpenOffensive draws from — reference reading, not
part of OpenOffensive's own product docs.

| Document | What it covers |
| --- | --- |
| [reference/strix-architecture.md](reference/strix-architecture.md) | A comprehensive, source-level analysis of the open-source **Strix** project (usestrix/strix, v1.5.3): the OpenAI Agents SDK foundation, the multi-agent coordinator, the two tool-execution planes, the Docker/Caido sandbox, the skills system, the reporting pipeline, and the interfaces — with diagrams and a map back to OpenOffensive. |

## Fast path

```bash
pip install -e .          # the CLI
openoffensive doctor --build   # verify Docker and build the Kali sandbox image (first run is slow)
openoffensive scan        # headless scan of the bundled demo target
openoffensive serve       # live dashboard (or ./run.sh)
```

Docker is required (every scan runs in a container). See [USAGE.md](USAGE.md) for the rest.

## A note on names

The product is **OpenOffensive** (openoffensive.ai). Its architecture *references* a prior
open-source multi-agent pentester; that single, honest attribution lives in
[ARCHITECTURE.md](ARCHITECTURE.md), with source-level reference reading in
[reference/strix-architecture.md](reference/strix-architecture.md). Everything else is
OpenOffensive's own implementation.
