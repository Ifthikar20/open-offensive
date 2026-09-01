# OpenOffensive documentation

[OpenOffensive](https://openoffensive.ai) is an autonomous, multi-agent AI pentester
with a live dashboard. A root orchestrator delegates to specialist sub-agents that
load skills, drive a real HTTP tool layer against a target, and file validated
findings — every step streamed to a browser in real time. It runs a fixed, auditable
methodology out of the box (no dependencies, no API key), or reasons with a real model
when one is configured.

This directory is the reference set. Start with whichever door fits what you need.

| Document | What it covers |
| --- | --- |
| [VISION.md](VISION.md) | The problem we're attacking, the goal, the design principles, non-goals, and the roadmap. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | The full system: diagrams, a module-by-module walkthrough, the two run modes, and the coordinator/event model. |
| [USAGE.md](USAGE.md) | Install, quickstart, every CLI subcommand and flag, all environment variables, enabling LLM mode, and reading the artifacts. |
| [TESTING.md](TESTING.md) | Running the pytest suite, what it covers, a manual smoke test, adding tests, and gating CI on findings. |
| [EXTENDING.md](EXTENDING.md) | Adding a specialist agent, a tool, or a skill; plugging in or swapping the LLM; extending the demo target. |
| [SECURITY.md](SECURITY.md) | The authorization and safety model: authorized-use-only, the host allowlist, the `--authorized` gate, and the localhost demo. |

## Reference

Background material on the upstream project OpenOffensive draws from — reference reading,
not part of OpenOffensive's own product docs.

| Document | What it covers |
| --- | --- |
| [reference/strix-architecture.md](reference/strix-architecture.md) | A comprehensive, source-level analysis of the open-source **Strix** project (usestrix/strix, v1.5.3): the OpenAI Agents SDK foundation, the multi-agent coordinator, the two tool-execution planes, the Docker/Caido sandbox, the skills system, the reporting pipeline, and the interfaces — with diagrams and a map back to OpenOffensive. |

## Fast path

```bash
pip install -e .          # scripted mode, zero dependencies
openoffensive scan        # headless scan of the bundled demo target
openoffensive serve       # live dashboard (or ./run.sh)
```

See [USAGE.md](USAGE.md) for the rest.

## A note on names

The product is **OpenOffensive** (openoffensive.ai). Its architecture *references* a
prior open-source multi-agent pentester; that single, honest attribution lives in
[ARCHITECTURE.md](ARCHITECTURE.md). Everything here is OpenOffensive's own
implementation.
