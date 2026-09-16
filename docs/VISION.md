# Vision — what we're trying to achieve

## The problem

Application security testing is caught between two bad options.

- **Manual penetration tests are slow and expensive.** A human expert is the gold
  standard for finding real, exploitable bugs — but engagements take days to weeks,
  cost thousands, and happen a few times a year. Most changes ship without ever being
  tested by one.
- **Static and dynamic scanners are noisy.** Automated tools are cheap and fast, but
  they flag *potential* issues from patterns and signatures. The result is a long
  queue of unvalidated alerts, most of them false positives, that engineers learn to
  ignore. A finding without proof is a finding nobody trusts.

The gap is a tester that has the *judgment* of the human — probe, observe, confirm,
rank honestly — at the *cost and speed* of the scanner.

## The goal

OpenOffensive is a step toward **autonomous, validated, multi-agent application
security testing**: a system that behaves like a small team of specialists rather than
a signature engine. It should

- **decompose** an engagement the way a lead would — into recon, injection, access
  control, and so on;
- **test with real tools**, not pattern matching, and **confirm** each issue from
  actual command output;
- **report like a professional**: every finding carries a severity, a CVSS score,
  the concrete evidence, a proof-of-concept, and a remediation;
- **stay in scope**, touching only systems it is authorized to test;
- and be **legible** — you can watch every decision and tool call happen live, and
  replay the whole run later.

## Design principles

These are the invariants the code is built around. Each maps to a concrete mechanism
(see [ARCHITECTURE.md](ARCHITECTURE.md)).

| Principle | What it means | Where it lives |
| --- | --- | --- |
| **The root orchestrates** | The root agent plans and delegates; it never tests hands-on. All probing is done by specialists it spawns. | `agents.py` — `RootAgent.work()` |
| **Plain text never ends a turn** | An agent finishes through an explicit lifecycle action (the `finish` tool), not by emitting prose. A model that stops talking without acting is nudged to continue or finish. | `tools.py` (`finish`), `llm.py` loop |
| **Knowledge is data** | Pentesting know-how is a catalog of skills loaded on demand, *before* an agent acts — not baked into code paths. | `skills.py`, `load_skill` |
| **Findings are validated and calibrated** | Nothing is reported without evidence from a real response. Each finding is severity-ranked honestly and de-duplicated. | `tools.py` (`report_finding`), `coordinator.py` |
| **Isolate, then scope** | Every command runs inside a single-use Kali container, never on the host; the agent is told to touch only the in-scope target, and non-local URL targets require explicit authorization. | `sandbox/` (`DockerSandbox`), `agents.py` (`_COMMON_SYSTEM`), `cli.py` (`--authorized`) |

## Non-goals

OpenOffensive is deliberately *not* trying to be:

- **A turnkey scanner for production targets.** It ships pointed at a bundled,
  intentionally vulnerable demo app on localhost. Pointing it elsewhere is a
  deliberate, authorized act (see [SECURITY.md](SECURITY.md)).
- **An exploitation framework.** Agents send benign, confirmatory probes — a single
  quote, a marked script string, sequential IDs. They do not weaponize, pivot, or
  persist.
- **A replacement for a human pentester.** It is an assistant that automates the
  repeatable parts of an engagement and produces auditable evidence, not a substitute
  for expert judgment on a high-stakes system.
- **A large framework.** The Python package pulls in nothing for scripted mode and stays
  on the standard library; the one heavyweight dependency is Docker, which every scan runs
  in — and it earns its place by buying a real toolset and real isolation. That constraint
  keeps the whole thing readable.

## Maturity — honest about POC → product

The current build is a working proof-of-concept with a real spine: a real Docker sandbox
in which the agents run a real Kali toolset, the target's source cloned into the
container, a real coordinator and event bus, real persisted artifacts (JSON, SARIF,
Markdown), and a real optional model brain. What is *small* is the surface area — three
specialists, a handful of skills, one bundled target, and a scripted methodology that is
intentionally fixed and auditable rather than open-ended.

The architecture was built so that growing the surface does not mean rewriting the
core: adding a specialist, a tool, a skill, or swapping in model-driven planning are
all local changes (see [EXTENDING.md](EXTENDING.md)).

## Roadmap

Rough direction, not commitments:

- **More specialists** — SSRF, authentication/session flaws, business-logic abuse,
  secrets and misconfiguration, each as another `BaseAgent` subclass.
- **Richer tools** — more of the Kali toolset wired in as first-class tools: a headless
  browser for DOM-context XSS, an authenticated-session helper, and a fuzzing helper.
- **Auth flows** — log in first, then test as an authenticated user, so access-control
  testing can compare "my records" against "someone else's".
- **Real LLM planning at the root** — today the root's orchestration is fixed; a
  natural next step is letting the model plan the engagement and decide which
  specialists to spawn, while keeping the containerized tool layer underneath.
- **A CI action** — package the `scan` exit-code contract and SARIF upload as a
  ready-made pipeline step (see [TESTING.md](TESTING.md)).
- **Deeper reporting** — full CVSS vectors, finding correlation, and trend history
  across runs.
