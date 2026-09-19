# Extending OpenOffensive

The engine is built so that growing its surface is a set of local changes — a new specialist, a
new tool, a new skill, a new image tool — without touching the coordinator, the event model, or
the UI. This page shows each seam. Pair anything here with tests ([TESTING.md](TESTING.md)) and
keep the isolation model intact ([SECURITY.md](SECURITY.md)).

## Add a new specialist agent

A specialist is a `BaseAgent` subclass with a `role` (it colors the agent graph) and a `focus` —
a plain-English mandate the model is handed as its task. It carries no methodology code: a real
model drives it through the shared tool-use loop, so all you write is the mandate. Add it to
`agents.py`.

```python
class SsrfAgent(BaseAgent):
    role = "ssrf"
    focus = ("Test for server-side request forgery: find parameters that fetch a URL "
             "and check whether they can be pointed at internal/link-local addresses "
             "(e.g. 169.254.169.254). Confirm from the real response before reporting.")
```

Then register it in the `SPECIALISTS` list — name, class, and the skills it advertises in the
agent graph:

```python
SPECIALISTS = [
    ("Recon Scout", ReconAgent, ["reconnaissance", "security_headers"]),
    ("Injection Hunter", InjectionAgent, ["sql_injection", "xss"]),
    ("Access Auditor", AccessAgent, ["idor"]),
    ("SSRF Sentinel", SsrfAgent, ["ssrf"]),        # new
]
```

That is all the wiring: `RootAgent` spawns every entry in `SPECIALISTS` as its own thread,
sharing the one container, and waits on it. `BaseAgent.work()` hands the model your `focus` as
its task plus the shared tool set, and the model plans the work itself — issuing `run_command`s
in the container, reading the real output, and filing findings with `report_finding`, one tool
call per step until it calls `finish`. You write no methodology and no separate model path.

**Source-review focus.** When a repo or dir was cloned/copied in, its source lives at
`/workspace/<name>` in the container and the model is told the path in its prompt. Point a
specialist's `focus` at it — e.g. "grep the source under `/workspace` for hardcoded secrets and
confirm any hit" — and the model uses `run_command` / `read_file` to inspect it. For a black-box
URL target there is no source, so the model probes over the network instead.

**Optional UI polish.** The dashboard colors agents by `role` (`web/index.html`, `AGENT_COLORS`
plus the `--a-*` CSS variables). A new role renders in a neutral color until you add an entry
there.

## Add a new tool

A tool is a `name` + JSON schema + handler, registered in `tools.REGISTRY`. The handler takes
the `ToolContext` first and returns a string (the observation shown to the model or the caller).
Run work in the container through `ctx.run(...)`. Handlers should return errors as text rather
than raise — `execute()` guards, but returning a clear message is better.

```python
import shlex
from openoffensive.tools import Tool, ToolContext, REGISTRY

def tool_nmap_quick(ctx: ToolContext, ports: str = "1-1000") -> str:
    res = ctx.run(f"nmap -sV -p {shlex.quote(ports)} {shlex.quote(ctx.target)}")
    return res.combined()

REGISTRY["nmap_quick"] = Tool(
    "nmap_quick",
    "Run a quick service/version scan against the in-scope target with nmap (in the sandbox).",
    {
        "type": "object",
        "properties": {"ports": {"type": "string", "default": "1-1000"}},
    },
    tool_nmap_quick,
)
```

The model can only call a tool that is **offered** to it — the names in `agents._TOOLS`. Add your
tool's name there so the model can call it:

```python
_TOOLS = ["run_command", "read_file", "load_skill", "list_skills",
          "report_finding", "nmap_quick", "finish"]
```

Every tool inherits the same properties automatically: it runs **inside the isolated container**
(nothing executes on the host), and all calls are logged as `tool` events. If your tool needs a
binary that is not in the image, add it to the Dockerfile (below).

## Add a skill

Skills are knowledge packs kept as data in `skills.CATALOG` — a name mapped to a
`(one-line description, playbook body)`. Add an entry:

```python
CATALOG["ssrf"] = (
    "Server-side request forgery (SSRF)",
    "Find parameters that fetch a URL and try pointing them at internal or link-local "
    "addresses (e.g. 169.254.169.254). A response from an internal service confirms it.",
)
```

It is immediately visible via `list_skills` and loadable via `load_skill("ssrf")`. Keep
playbooks short and about *method*, not a specific target.

## Extend the sandbox image

The toolset the agents can run is whatever is installed in the image. It is defined in
`openoffensive/sandbox/Dockerfile` (a `kalilinux/kali-rolling` base plus an apt install line).
To add a tool the agents can call, add its package:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl wget git jq dnsutils netcat-traditional \
        python3 python3-requests python3-pip \
        nmap sqlmap nikto whatweb dirb gobuster wafw00f \
        ffuf \                       # ← new tool
    && rm -rf /var/lib/apt/lists/*
```

`ensure_image()` only builds when the tag is **absent**, so after editing the Dockerfile force a
rebuild rather than expecting the next scan to pick it up:

```bash
docker rmi openoffensive-sandbox:kali          # drop the stale image
openoffensive doctor --build                   # rebuild from the Dockerfile
# or build directly:
docker build -t openoffensive-sandbox:kali -f openoffensive/sandbox/Dockerfile openoffensive/sandbox
```

Alternatively, point `OPENOFFENSIVE_SANDBOX_IMAGE` at a custom image you maintain — any tag that
does **not** start with `openoffensive-sandbox` is `docker pull`ed instead of built, so you can
publish a pre-baked image and pin it.

## Plug in or swap the LLM

The model brain lives in `llm.py` (`run_agent_llm`), and its knobs are configuration:

| Knob | Where |
| --- | --- |
| Model id | `OPENOFFENSIVE_MODEL` / `--model` (default `claude-opus-5`). |
| Tokens per call | `OPENOFFENSIVE_MAX_TOKENS` (default 4096). |
| Per-agent step budget | `OPENOFFENSIVE_MAX_STEPS` (default 24). |
| System prompt & offered tools | `agents._COMMON_SYSTEM` and `agents._TOOLS`. |
| Cost-meter pricing | `llm._PRICES` (input/output USD per 1M tokens). |

**Swapping the model.** Set `--model` or `OPENOFFENSIVE_MODEL`. If it is a new id, add a matching
`_PRICES` entry so the run's cost meter is accurate (unknown ids fall back to `claude-opus-5`
pricing).

**Changing the loop.** `run_agent_llm` is a manual tool-use loop against the Anthropic SDK: it
constructs `anthropic.Anthropic()`, calls `client.messages.create(model, max_tokens, system,
tools, messages)`, turns text blocks into `think` events, executes each `tool_use` block through
the shared `execute(ctx, name, args)` (so `run_command` runs in the container), feeds the results
back as `tool_result` blocks, and stops when the model calls `finish` (or the step budget is
reached). To evolve it — for example to enable adaptive thinking (`thinking={"type": "adaptive"}`)
or set an effort level via `output_config` — add those parameters to the `messages.create` call.
The one invariant to preserve: **keep every action flowing through the shared tool registry**, so
container execution, logging, and the findings store keep working unchanged. The SDK is imported
lazily, so the package core still installs with no dependencies (the `[llm]` extra adds
`anthropic`, which a scan requires).

**A different provider.** Replace the client construction and the `messages.create` call with the
other provider's SDK, keeping the same contract: emit `think` for reasoning text, call
`execute(ctx, name, args)` for each tool call, feed results back, and end when `ctx.finished` is
set. `llm_available()` gates whether a real model call can be made — update its SDK import check
to match.

## A complete example, end to end

Adding SSRF coverage touches these files, each in the way shown above:

1. `skills.py` — add the `ssrf` playbook to `CATALOG`.
2. `agents.py` — add `SsrfAgent` and register it in `SPECIALISTS`.
3. `sandbox/Dockerfile` — only if the check needs a tool not already in the image.
4. `tests/` — assert the scan reports the finding by driving a fake model client (which issues the
   tool calls) against a `FakeSandbox` programmed with the command output (see
   [TESTING.md](TESTING.md#adding-a-test-for-a-new-specialist)).

No changes to the coordinator, runner, persistence, reporting, or server are needed — the new
specialist, skill, and finding flow through the existing machinery.
