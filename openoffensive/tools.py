"""The tool layer — one registry, shared by scripted and LLM-driven agents.

A tool is a name + JSON-schema + handler. The same handlers back both execution
modes: the scripted specialists call them in a fixed methodology, and the LLM
loop calls them by name with the model's arguments. Every HTTP call is real and
goes through a host allowlist, so the agents can only reach the scan target (plus
any hosts an operator has explicitly authorised via scope).
"""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

from .coordinator import Coordinator
from .models import Finding, AgentState

_BODY_SNIPPET = 900          # chars of response body shown back to an agent
_HEADERS_SHOWN = ("server", "content-type", "location", "set-cookie",
                  "content-security-policy", "x-frame-options", "x-content-type-options")


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: str
    url: str


class ToolContext:
    """Per-agent handle the tool handlers act through."""

    def __init__(self, coord: Coordinator, agent: AgentState, settings: Any,
                 target: str | None = None) -> None:
        self.coord = coord
        self.agent = agent
        self.settings = settings
        self.target = (target or coord.target).rstrip("/")
        host = urlparse(self.target).hostname
        self.allowed_hosts = {h for h in (host, *getattr(settings, "scope_allow", ())) if h}
        self.finished = False
        self.finish_summary = ""

    # -- pacing (0 in tests, ~human speed in the dashboard) -------------------
    def pace(self, seconds: float) -> None:
        s = seconds * float(getattr(self.settings, "speed", 1.0))
        if s > 0:
            time.sleep(s)

    # -- narration ------------------------------------------------------------
    def think(self, msg: str) -> None:
        self.coord.emit("think", self.agent, msg)
        self.pace(0.3)

    def phase(self, msg: str) -> None:
        self.coord.emit("phase", self.agent, msg)
        self.pace(0.2)

    # -- real HTTP ------------------------------------------------------------
    def http(self, path: str, method: str = "GET",
             params: dict | None = None) -> Response:
        if not path.startswith("/"):
            path = "/" + path
        url = self.target + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        host = urlparse(url).hostname
        label = f"{method} {path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
        if host not in self.allowed_hosts:
            self.coord.emit("tool", self.agent, f"{label} → BLOCKED (out of scope: {host})",
                            ok=False)
            return Response(0, {}, f"blocked: host {host} is out of scope", url)
        self.coord.bill(self.agent)
        req = urllib.request.Request(url, method=method.upper(),
                                     headers={"User-Agent": "openoffensive/1.0"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                body = r.read().decode("utf-8", "replace")
                resp = Response(r.status, {k.lower(): v for k, v in r.headers.items()},
                                body, url)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            resp = Response(e.code, {k.lower(): v for k, v in (e.headers or {}).items()},
                            body, url)
        except Exception as e:  # noqa: BLE001 — a failed probe is a result, not a crash
            self.coord.emit("tool", self.agent, f"{label} → ERROR {e}", ok=False)
            return Response(0, {}, f"error: {e}", url)
        ms = int((time.time() - t0) * 1000)
        self.coord.emit("tool", self.agent, f"{label} → {resp.status} ({len(body)}b, {ms}ms)",
                        ok=True, status=resp.status)
        self.pace(0.35)
        return resp

    # -- findings -------------------------------------------------------------
    def report(self, *, title: str, severity: str, endpoint: str, evidence: str,
               remediation: str, cwe: str = "", poc: str = "") -> Finding:
        severity = severity.lower().strip()
        if severity not in ("critical", "high", "medium", "low", "info"):
            severity = "info"
        finding = Finding(id="", title=title, severity=severity, target=self.target,
                          endpoint=endpoint, evidence=evidence, remediation=remediation,
                          agent=self.agent.name, cwe=cwe, poc=poc)
        return self.coord.add_finding(self.agent, finding)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------
@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., str]

    def anthropic_schema(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description,
                "input_schema": self.input_schema}


def _fmt_response(resp: Response) -> str:
    hdrs = "\n".join(f"  {k}: {resp.headers[k]}" for k in _HEADERS_SHOWN if k in resp.headers)
    body = resp.body[:_BODY_SNIPPET]
    if len(resp.body) > _BODY_SNIPPET:
        body += f"\n… ({len(resp.body) - _BODY_SNIPPET} more bytes)"
    return (f"HTTP {resp.status} for {resp.url}\n"
            f"headers:\n{hdrs or '  (none of interest)'}\n"
            f"body:\n{body}")


def tool_http_request(ctx: ToolContext, path: str, method: str = "GET",
                      params: dict | None = None) -> str:
    resp = ctx.http(path, method=method, params=params or None)
    return _fmt_response(resp)


def tool_report_finding(ctx: ToolContext, title: str, severity: str, endpoint: str,
                        evidence: str, remediation: str, cwe: str = "",
                        poc: str = "") -> str:
    f = ctx.report(title=title, severity=severity, endpoint=endpoint, evidence=evidence,
                   remediation=remediation, cwe=cwe, poc=poc)
    return f"Filed {f.severity.upper()} finding {f.id}: {f.title} (CVSS {f.cvss})"


def tool_load_skill(ctx: ToolContext, name: str) -> str:
    from . import skills
    body = skills.load(name)
    if not body:
        return f"No skill named '{name}'. Available: {', '.join(s['name'] for s in skills.describe_catalog())}"
    ctx.coord.emit("skill", ctx.agent, f"load_skill({name})")
    ctx.pace(0.2)
    return f"# skill: {name}\n{body}"


def tool_list_skills(ctx: ToolContext) -> str:
    from . import skills
    return "\n".join(f"- {s['name']}: {s['description']}" for s in skills.describe_catalog())


def tool_finish(ctx: ToolContext, summary: str = "") -> str:
    ctx.finished = True
    ctx.finish_summary = summary
    return "acknowledged; agent work complete"


REGISTRY: dict[str, Tool] = {
    "http_request": Tool(
        "http_request",
        "Send a real HTTP request to an in-scope endpoint and get the status, "
        "selected headers, and response body back. Use this to probe the target: "
        "fetch pages, submit parameters, walk API ids, and inspect responses.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string",
                         "description": "Path on the target, e.g. '/login' or '/api/user/1'. "
                                        "Include a query string or pass 'params'."},
                "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE", "HEAD"],
                           "default": "GET"},
                "params": {"type": "object",
                           "description": "Query parameters as a flat object of strings.",
                           "additionalProperties": {"type": "string"}},
            },
            "required": ["path"],
        },
        tool_http_request,
    ),
    "report_finding": Tool(
        "report_finding",
        "File a validated vulnerability. Only report something you have evidence "
        "for from an actual response. Include a concrete proof-of-concept and fix.",
        {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "severity": {"type": "string", "enum": ["critical", "high", "medium", "low", "info"]},
                "endpoint": {"type": "string", "description": "Where it lives, e.g. '/search'."},
                "evidence": {"type": "string", "description": "What in the response proves it."},
                "remediation": {"type": "string", "description": "How to fix it."},
                "cwe": {"type": "string", "description": "CWE id, e.g. 'CWE-89'."},
                "poc": {"type": "string", "description": "A one-line reproduction, e.g. a curl."},
            },
            "required": ["title", "severity", "endpoint", "evidence", "remediation"],
        },
        tool_report_finding,
    ),
    "load_skill": Tool(
        "load_skill",
        "Load a knowledge pack (playbook) for a vulnerability class or technique "
        "before testing it. Call list_skills to see what is available.",
        {"type": "object",
         "properties": {"name": {"type": "string"}},
         "required": ["name"]},
        tool_load_skill,
    ),
    "list_skills": Tool(
        "list_skills",
        "List the available skill playbooks with one-line descriptions.",
        {"type": "object", "properties": {}},
        tool_list_skills,
    ),
    "finish": Tool(
        "finish",
        "Call when your assigned testing is complete. Provide a short summary of "
        "what you covered and found.",
        {"type": "object",
         "properties": {"summary": {"type": "string"}}},
        tool_finish,
    ),
}


def get_tools(names: list[str]) -> list[Tool]:
    return [REGISTRY[n] for n in names if n in REGISTRY]


def anthropic_schemas(names: list[str]) -> list[dict[str, Any]]:
    return [t.anthropic_schema() for t in get_tools(names)]


def execute(ctx: ToolContext, name: str, args: dict[str, Any]) -> str:
    """Dispatch a tool call by name; tool errors come back as text, never raise."""
    tool = REGISTRY.get(name)
    if tool is None:
        return f"error: unknown tool '{name}'"
    try:
        return tool.handler(ctx, **(args or {}))
    except TypeError as e:
        return f"error: bad arguments for {name}: {e}"
    except Exception as e:  # noqa: BLE001
        return f"error: {name} failed: {e}"
