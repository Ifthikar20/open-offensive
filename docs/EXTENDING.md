# Extending OpenOffensive

The engine is built so that growing its surface is a set of local changes — a new
specialist, a new tool, a new skill — without touching the coordinator, the event
model, or the UI. This page shows each seam. Pair anything here with tests
([TESTING.md](TESTING.md)) and keep the safety model intact ([SECURITY.md](SECURITY.md)).

## Add a new specialist agent

A specialist is a `BaseAgent` subclass with a `role`, a `focus`, and a `scripted()`
methodology. Add it to `agents.py`.

```python
class SsrfAgent(BaseAgent):
    role = "ssrf"
    focus = ("Test for server-side request forgery: find parameters that fetch a URL "
             "and check whether they can be pointed at internal/link-local addresses.")

    def scripted(self) -> None:
        self.phase("SSRF testing — URL-fetching parameters")
        self.load_skill("ssrf")                     # narrate the knowledge step first
        r = self.ctx.http("/fetch", params={"url": "http://169.254.169.254/"})
        if r.status == 200 and "instance-id" in r.body:
            self.file(
                title="Server-side request forgery (SSRF)", severity="high",
                endpoint="/fetch",
                evidence="The url parameter fetched an internal metadata endpoint.",
                remediation="Allowlist destination hosts; block link-local ranges.",
                cwe="CWE-918",
                poc='curl "$TARGET/fetch?url=http://169.254.169.254/"',
            )
```

Then register it in the `SPECIALISTS` list — name, class, and the skills it advertises
in the agent graph:

```python
SPECIALISTS = [
    ("Recon Scout", ReconAgent, ["reconnaissance", "security_headers"]),
    ("Injection Hunter", InjectionAgent, ["sql_injection", "xss"]),
    ("Access Auditor", AccessAgent, ["idor"]),
    ("SSRF Sentinel", SsrfAgent, ["ssrf"]),        # new
]
```

That is all the wiring: `RootAgent` spawns every entry in `SPECIALISTS` as its own
thread and waits on it. The helpers available inside `scripted()`:

| Call | Effect |
| --- | --- |
| `self.phase(msg)` / `self.think(msg)` | Emit a `phase` / `think` event to the live log. |
| `self.load_skill(name)` | Emit a `skill` event and return the playbook body. |
| `self.ctx.http(path, method="GET", params=None)` | Real, scope-checked HTTP; returns a `Response(status, headers, body, url)`. |
| `self.file(title=…, severity=…, endpoint=…, evidence=…, remediation=…, cwe="", poc="")` | Load `severity_calibration`, narrate the calibration, then file the finding. |
| `self.ctx.report(...)` | File a finding directly, without the calibration narration. |

**LLM mode comes for free.** `BaseAgent.work()` dispatches by mode: in scripted mode it
calls your `scripted()`; in LLM mode it hands the model your `focus` as the task and the
shared tool set. You do not write a separate LLM path.

**Optional UI polish.** The dashboard colors agents by `role` (`web/index.html`,
`AGENT_COLORS` plus the `--a-*` CSS variables). A new role renders in a neutral color
until you add an entry there.

## Add a new tool

A tool is a `name` + JSON schema + handler, registered in `tools.REGISTRY`. The handler
takes the `ToolContext` first and returns a string (the observation shown to the model
or the caller). Handlers should return errors as text rather than raise — `execute()`
guards, but returning a clear message is better.

```python
def tool_robots_diff(ctx: ToolContext, path: str = "/robots.txt") -> str:
    resp = ctx.http(path)
    disallowed = [ln.split(":", 1)[1].strip()
                  for ln in resp.body.splitlines() if ln.lower().startswith("disallow")]
    return f"Disallowed paths ({len(disallowed)}): {', '.join(disallowed) or 'none'}"

REGISTRY["robots_diff"] = Tool(
    "robots_diff",
    "Fetch robots.txt and list the paths it hides — often a map of sensitive areas.",
    {
        "type": "object",
        "properties": {"path": {"type": "string", "default": "/robots.txt"}},
    },
    tool_robots_diff,
)
```

- **Scripted agents** can invoke any tool by name with `execute(self.ctx, "robots_diff",
  {})`, or you can add a thin convenience method to `ToolContext`.
- **LLM agents** are only offered the tools named in `agents._TOOLS`. Add your tool's
  name there for the model to be able to call it:

  ```python
  _TOOLS = ["http_request", "load_skill", "list_skills", "report_finding",
            "robots_diff", "finish"]
  ```

Every tool inherits the safety guarantees automatically: `http_request` and anything
built on `ctx.http` is confined to the host allowlist, and all calls are logged as
`tool` events.

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

It is immediately visible via `list_skills` and loadable via `load_skill("ssrf")` — in
both scripted and LLM mode. Keep playbooks short and about *method*, not a specific
target.

## Plug in or swap the LLM

The model brain lives in `llm.py` (`run_agent_llm`), and its knobs are configuration:

| Knob | Where |
| --- | --- |
| Model id | `OPENOFFENSIVE_MODEL` / `--model` (default `claude-opus-5`). |
| Tokens per call | `OPENOFFENSIVE_MAX_TOKENS` (default 4096). |
| Per-agent step budget | `OPENOFFENSIVE_MAX_STEPS` (default 24). |
| System prompt & offered tools | `agents._COMMON_SYSTEM` and `agents._TOOLS`. |
| Cost-meter pricing | `llm._PRICES` (input/output USD per 1M tokens). |

**Swapping the model.** Set `--model` or `OPENOFFENSIVE_MODEL`. If it is a new id, add a
matching `_PRICES` entry so the run's cost meter is accurate (unknown ids fall back to
`claude-opus-5` pricing).

**Changing the loop.** `run_agent_llm` is a manual tool-use loop against the Anthropic
SDK: it constructs `anthropic.Anthropic()`, calls `client.messages.create(model,
max_tokens, system, tools, messages)`, turns text blocks into `think` events, executes
each `tool_use` block through the shared `execute(ctx, name, args)`, feeds the results
back as `tool_result` blocks, and stops when the model calls `finish` (or the step
budget is reached). To evolve it — for example to enable adaptive thinking
(`thinking={"type": "adaptive"}`) or set an effort level via `output_config` — add those
parameters to the `messages.create` call. The one invariant to preserve: **keep every
action flowing through the shared tool registry**, so scope-guarding, logging, and the
findings store work identically to scripted mode. The SDK is imported lazily, so the
package still installs and runs scripted with no dependencies.

**A different provider.** Replace the client construction and the `messages.create` call
with the other provider's SDK, keeping the same contract: emit `think` for reasoning
text, call `execute(ctx, name, args)` for each tool call, feed results back, and end when
`ctx.finished` is set. `llm_available()` gates whether LLM mode can run — update its SDK
import check to match.

## Add endpoints and vulnerabilities to the demo target

The demo target is "Juice-Box" in `demo_target.py`. Requests are dispatched in
`_Handler.do_GET` by path; each branch returns `self._send(code, body, ctype)`. To add a
practice vulnerability, add a branch and mark it with a `# VULN:` comment so it stays
obviously intentional:

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

- **Keep it localhost-only.** It binds to `127.0.0.1` and must never be deployed — it is
  vulnerable on purpose. See [SECURITY.md](SECURITY.md).
- Add the new endpoint to the home page listing if you want it discoverable by recon.
- Then close the loop: add a specialist or check that finds it, a skill if it needs one,
  and tests on both the target and the scan (see [TESTING.md](TESTING.md#adding-a-test-for-a-new-vuln-or-agent)).

## A complete example, end to end

Adding SSRF coverage touches exactly four files, each in the way shown above:

1. `skills.py` — add the `ssrf` playbook to `CATALOG`.
2. `demo_target.py` — add the vulnerable `/fetch` endpoint.
3. `agents.py` — add `SsrfAgent` and register it in `SPECIALISTS`.
4. `tests/` — pin the target behavior and assert the scan reports the finding.

No changes to the coordinator, runner, persistence, reporting, or server are needed —
the new specialist, skill, and finding flow through the existing machinery.
