# Extending OpenOffensive

The engine is built so that growing its surface is a set of local changes — a new specialist, a
new tool, a new skill, a new image tool — without touching the coordinator, the event model, or
the UI. This page shows each seam. Pair anything here with tests ([TESTING.md](TESTING.md)) and
keep the isolation model intact ([SECURITY.md](SECURITY.md)).

## Add a new specialist agent

A specialist is a `BaseAgent` subclass with a `role`, a `focus`, and a `scripted()` methodology
that drives real commands in the container through `self.ctx.run(...)`. Add it to `agents.py`.

```python
class SsrfAgent(BaseAgent):
    role = "ssrf"
    focus = ("Test for server-side request forgery: find parameters that fetch a URL "
             "and check whether they can be pointed at internal/link-local addresses.")

    def scripted(self) -> None:
        self.ctx.phase("SSRF testing — URL-fetching parameters")
        # run a real command INSIDE the container; ctx.run returns an ExecResult
        r = self.ctx.run(f"curl -s '{self.target}/fetch?url=http://169.254.169.254/'")
        if r.ok and "instance-id" in r.stdout:
            self._file(
                title="Server-side request forgery (SSRF)", severity="high",
                endpoint="/fetch",
                evidence="The url parameter fetched an internal metadata endpoint.",
                remediation="Allowlist destination hosts; block link-local ranges.",
                cwe="CWE-918",
                poc='curl "$TARGET/fetch?url=http://169.254.169.254/"',
            )
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
sharing the one container, and waits on it. The pieces available inside `scripted()`:

| Call | Effect |
| --- | --- |
| `self.ctx.phase(msg)` / `self.ctx.think(msg)` | Emit a `phase` / `think` event to the live log. |
| `self.ctx.run(command, timeout=180)` | Run a shell command in the container (`docker exec`); logs it and returns an `ExecResult` with `.stdout`, `.stderr`, `.exit_code`, `.ok`, `.timed_out`, and `.combined()`. |
| `self._file(title=…, severity=…, endpoint=…, evidence=…, remediation=…, cwe="", poc="")` | File a validated finding (a thin wrapper over `self.ctx.report`). |
| `self.workspace_path` | Path to the target's source inside the container (`/workspace/<name>`) when a repo or dir was cloned/copied in, or `None` for a black-box URL target. Use it to `grep`/`read` the source. |

A source-review specialist keys off `self.workspace_path`:

```python
if self.workspace_path:
    hits = self.ctx.run(f"grep -rEn 'password|api_key' {self.workspace_path} | head -20")
    if hits.stdout.strip():
        self._file(title="Secrets in source", severity="high", endpoint=self.workspace_path,
                   evidence="grep found credential-like strings in the source.",
                   remediation="Remove secrets from source; rotate them.", cwe="CWE-798")
```

**LLM mode comes for free.** `BaseAgent.work()` dispatches by mode: in scripted mode it calls
your `scripted()`; in LLM mode it hands the model your `focus` as the task and the shared tool
set, and the model issues `run_command`s itself. You do not write a separate LLM path.

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

- **Scripted agents** can invoke any registered tool by name with
  `execute(self.ctx, "nmap_quick", {})`, or just call `self.ctx.run(...)` directly.
- **LLM agents** are only offered the tools named in `agents._TOOLS`. Add your tool's name there
  for the model to be able to call it:

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

It is immediately visible via `list_skills` and loadable via `load_skill("ssrf")` — in both
scripted and LLM mode. Keep playbooks short and about *method*, not a specific target.

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
container execution, logging, and the findings store work identically to scripted mode. The SDK
is imported lazily, so the package still installs with no dependencies (LLM mode adds `anthropic`
via the `[llm]` extra).

**A different provider.** Replace the client construction and the `messages.create` call with the
other provider's SDK, keeping the same contract: emit `think` for reasoning text, call
`execute(ctx, name, args)` for each tool call, feed results back, and end when `ctx.finished` is
set. `llm_available()` gates whether LLM mode can run — update its SDK import check to match.

## Add endpoints and vulnerabilities to the demo target

The demo target is "Juice-Box" in `demo_target.py`. Requests are dispatched in `_Handler.do_GET`
by path; each branch returns `self._send(code, body, ctype)`. To add a practice vulnerability,
add a branch and mark it with a `# VULN:` comment so it stays obviously intentional:

```python
if path == "/fetch":
    url = params.get("url", "")
    # VULN (demo): fetches an attacker-controlled URL with no allowlist (SSRF).
    if url.startswith("http://169.254.169.254"):
        return self._send(200, json.dumps({"instance-id": "i-demo", "role": "admin"}),
                          "application/json")
    return self._send(200, json.dumps({"fetched": url}), "application/json")
```

Rules for the demo target:

- **It is a throwaway practice target — never deploy it.** It binds to `127.0.0.1` by default,
  but the `scan` / `serve` paths bind it to `0.0.0.0` so the scan container can reach it via
  `host.docker.internal`. It is vulnerable on purpose; run it only on a machine you control. See
  [SECURITY.md](SECURITY.md).
- Add the new endpoint to the home page listing if you want it discoverable by recon.
- Then close the loop: add a specialist or check that finds it, a skill if it needs one, an image
  tool if the check needs one, and tests on both the target and the scan (see
  [TESTING.md](TESTING.md#adding-a-test-for-a-new-vuln-or-agent)).

## A complete example, end to end

Adding SSRF coverage touches these files, each in the way shown above:

1. `skills.py` — add the `ssrf` playbook to `CATALOG`.
2. `demo_target.py` — add the vulnerable `/fetch` endpoint.
3. `agents.py` — add `SsrfAgent` and register it in `SPECIALISTS`.
4. `sandbox/Dockerfile` — only if the check needs a tool not already in the image.
5. `tests/` — pin the target behavior, and assert the scan reports the finding using a
   `FakeSandbox` programmed with the command output.

No changes to the coordinator, runner, persistence, reporting, or server are needed — the new
specialist, skill, and finding flow through the existing machinery.
