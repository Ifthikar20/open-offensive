"""The tool layer — one registry, executed INSIDE the per-scan container.

The core tool is ``run_command``: the model (or a scripted playbook) runs shell
commands in the Kali sandbox — nmap, curl, sqlmap, nikto, gobuster, or grepping
the target's source under ``/workspace`` — and the stdout/exit code come back as
the next observation. ``report_finding`` files a validated issue; ``finish`` ends
the agent. The same registry backs both the LLM loop and the scripted playbook.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Any, Callable

from .coordinator import Coordinator
from .models import AgentState, Finding

_MAX_EXEC_TIMEOUT = 600


class ToolContext:
    """Per-agent handle: the shared sandbox, the in-scope target, and logging."""

    def __init__(self, coord: Coordinator, agent: AgentState, settings: Any,
                 sandbox: Any, target: str) -> None:
        self.coord = coord
        self.agent = agent
        self.settings = settings
        self.sandbox = sandbox
        self.target = target
        self.finished = False
        self.finish_summary = ""

    # -- narration ------------------------------------------------------------
    def think(self, msg: str) -> None:
        self.coord.emit("think", self.agent, msg)

    def phase(self, msg: str) -> None:
        self.coord.emit("phase", self.agent, msg)

    # -- the sandbox ----------------------------------------------------------
    def run(self, command: str, timeout: float = 180) -> Any:
        """Run a command in the container; log it and its result. Returns ExecResult."""
        self.coord.emit("tool", self.agent, f"$ {command}")
        res = self.sandbox.exec(command, timeout=min(int(timeout or 180), _MAX_EXEC_TIMEOUT))
        tag = "timeout" if res.timed_out else f"exit {res.exit_code}"
        self.coord.emit("tool", self.agent, f"  → {tag}, {len(res.stdout)}b", ok=res.ok)
        return res

    # -- findings -------------------------------------------------------------
    def report(self, *, title: str, severity: str, endpoint: str, evidence: str,
               remediation: str, cwe: str = "", poc: str = "") -> Finding:
        severity = (severity or "info").lower().strip()
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


def tool_run_command(ctx: ToolContext, command: str, timeout: int = 180) -> str:
    if not command or not command.strip():
        return "error: command must be a non-empty string"
    return ctx.run(command, timeout=timeout).combined()


def tool_read_file(ctx: ToolContext, path: str) -> str:
    res = ctx.run(f"cat {shlex.quote(path)}")
    return res.combined()


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
        catalog = ", ".join(s["name"] for s in skills.describe_catalog())
        return f"No skill named '{name}'. Available: {catalog}"
    ctx.coord.emit("skill", ctx.agent, f"load_skill({name})")
    return f"# skill: {name}\n{body}"


def tool_list_skills(ctx: ToolContext) -> str:
    from . import skills
    return "\n".join(f"- {s['name']}: {s['description']}" for s in skills.describe_catalog())


def tool_finish(ctx: ToolContext, summary: str = "") -> str:
    ctx.finished = True
    ctx.finish_summary = summary
    return "acknowledged; agent work complete"


REGISTRY: dict[str, Tool] = {
    "run_command": Tool(
        "run_command",
        "Run a shell command INSIDE the sandbox container (a Kali box with a pentest "
        "toolset). Use it to run tools (nmap, curl, sqlmap, nikto, gobuster, whatweb, "
        "python3) against the in-scope target, and to read/grep the target's source "
        "under /workspace. Returns combined stdout+stderr and the exit code. One command "
        "per call; chain with && or pipes as needed.",
        {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to run."},
                "timeout": {"type": "integer",
                            "description": "Seconds before the command is killed (default 180, max 600)."},
            },
            "required": ["command"],
        },
        tool_run_command,
    ),
    "read_file": Tool(
        "read_file",
        "Read a file inside the sandbox (e.g. source under /workspace). Convenience "
        "wrapper over `cat`.",
        {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        tool_read_file,
    ),
    "report_finding": Tool(
        "report_finding",
        "File a validated vulnerability. Only report something you proved from real tool "
        "output. Include a concrete proof-of-concept and a fix.",
        {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "severity": {"type": "string", "enum": ["critical", "high", "medium", "low", "info"]},
                "endpoint": {"type": "string", "description": "Where it lives, e.g. '/login' or a file path."},
                "evidence": {"type": "string", "description": "What in the output proves it."},
                "remediation": {"type": "string", "description": "How to fix it."},
                "cwe": {"type": "string", "description": "CWE id, e.g. 'CWE-89'."},
                "poc": {"type": "string", "description": "A one-line reproduction."},
            },
            "required": ["title", "severity", "endpoint", "evidence", "remediation"],
        },
        tool_report_finding,
    ),
    "load_skill": Tool(
        "load_skill",
        "Load a knowledge pack (playbook) for a vulnerability class before testing it. "
        "Call list_skills to see what is available.",
        {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
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
        "Call when your assigned testing is complete. Provide a short summary of what you "
        "covered and found.",
        {"type": "object", "properties": {"summary": {"type": "string"}}},
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
