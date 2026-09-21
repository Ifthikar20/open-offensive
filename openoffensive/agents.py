"""The agents — a root orchestrator that delegates to specialist sub-agents, all
sharing ONE Kali sandbox container.

Each specialist is driven by a real model: it decides which ``run_command`` to
issue inside the container, reads the real output, and repeats until it calls
``finish`` — the true agentic loop. They share the same container, the same
tools, the same findings store, and the same live log.
"""

from __future__ import annotations

import threading
import uuid

from .coordinator import Coordinator
from .llm import run_agent_llm
from .models import AgentState
from .tools import ToolContext

_TOOLS = ["run_command", "read_file", "load_skill", "list_skills", "report_finding", "finish"]

_COMMON_SYSTEM = (
    "You are OpenOffensive, an authorized penetration-testing agent working INSIDE an "
    "isolated Kali Linux sandbox container. A full toolset (nmap, curl, sqlmap, nikto, "
    "whatweb, gobuster, dirb, wafw00f, python3, git) is available through the run_command "
    "tool, which runs ONE shell command in the container and returns its real output. "
    "You are testing a REAL, UNKNOWN application: do not assume any endpoint exists — "
    "discover the attack surface from evidence. "
    "Work as a loop: run a command, READ its output, decide the next command from what you "
    "actually saw, and repeat — one tool call per step. Start broad to map the app "
    "(fingerprint the server/tech, fetch the homepage and read it, check robots.txt and "
    "sitemap.xml, follow links, enumerate paths with gobuster/dirb) to find its real pages "
    "— especially any auth or business-logic page — THEN probe those for issues. "
    "You are authorized to test ONLY {scope}. Never attempt to reach any other host. "
    "Confirm every issue from real output before reporting it; call load_skill before a "
    "class you're unsure about. File each validated issue with report_finding — evidence "
    "quoted from real output, a concrete proof-of-concept, a fix, and an honest severity; "
    "never invent findings. Call finish with a short summary when your focus area is covered."
)


def _aid() -> str:
    return uuid.uuid4().hex[:8]


class BaseAgent:
    role = "agent"
    focus = ""

    def __init__(self, coord: Coordinator, settings, sandbox, name: str, task: str,
                 parent: str | None, skills: list[str], target: str,
                 workspace_path: str | None) -> None:
        self.coord = coord
        self.settings = settings
        self.sandbox = sandbox
        self.target = target
        self.workspace_path = workspace_path
        self.state = AgentState(id=_aid(), name=name, role=self.role, parent=parent,
                                task=task, skills=list(skills))
        coord.register(self.state)
        self.ctx = ToolContext(coord, self.state, settings, sandbox, target)

    # -- prompts --------------------------------------------------------------
    def _scope(self) -> str:
        if self.workspace_path:
            return f"the target {self.target} and its source cloned at {self.workspace_path}"
        return f"the target {self.target}"

    def system_prompt(self) -> str:
        return _COMMON_SYSTEM.format(scope=self._scope()) + self._toolset_note()

    def _toolset_note(self) -> str:
        """Tell the model which tools are ACTUALLY available in this sandbox.

        The Docker (Kali) backend has the full suite; the local host-execution
        backend only has whatever is installed on the host. Reporting the real
        set stops the model from leaning on a missing nmap/sqlmap and steers it to
        curl/python and source review instead. Backends that don't expose the
        capability (e.g. Docker) add nothing here."""
        fn = getattr(self.sandbox, "available_tools", None)
        if not callable(fn):
            return ""
        present = fn()
        missing = getattr(self.sandbox, "missing_tools", lambda: [])()
        if not present and not missing:
            return ""
        note = "\n\nSandbox tools actually installed: " + (", ".join(present) or "none") + "."
        if missing:
            note += (" NOT installed here: " + ", ".join(missing) + " — do not call them; "
                     "probe with curl/python3 and read source with grep/cat.")
        return note

    def task_prompt(self) -> str:
        src = self.workspace_path or "none (black-box — probe over the network)"
        return (f"Target: {self.target}\nSource in the container: {src}\n"
                f"Your focus: {self.focus}\n"
                "First ENUMERATE to learn what this app actually is and where its "
                "interesting pages live — fingerprint it, fetch and read the homepage, check "
                "robots.txt / sitemap and any linked paths, and discover routes (gobuster / "
                "dirb) as needed. Only once you've found real endpoints, test them for your "
                "focus area. Base each next command on the output you just saw, and report "
                "only what you validate from real responses.")

    # -- lifecycle ------------------------------------------------------------
    def run(self) -> None:
        self.coord.set_status(self.state, "running")
        try:
            self.work()
            done_note = ("finish_scan → report written" if self.state.parent is None
                         else "agent_finish → reporting to root")
            self.coord.set_status(self.state, "done", done_note)
        except Exception as e:  # noqa: BLE001 — a dead child must not kill the run
            self.coord.emit("error", self.state, f"crashed: {e}")
            self.coord.set_status(self.state, "stopped", "stopped after error")

    def work(self) -> None:
        # A real model drives every specialist. If the model becomes unreachable
        # mid-run, LLMUnavailable propagates out of run() and the agent is marked
        # "stopped" (a crash) — it never falls back to canned or scripted output.
        run_agent_llm(self.ctx, system_prompt=self.system_prompt(),
                      task=self.task_prompt(), tool_names=_TOOLS, settings=self.settings)


# ---------------------------------------------------------------------------
# Specialists — each a model-driven agent with a focused mandate. The role/focus
# shape the agent graph and the model's system + task prompts.
# ---------------------------------------------------------------------------
class ReconAgent(BaseAgent):
    role = "recon"
    focus = ("Map the attack surface: fingerprint the server, fetch key endpoints and "
             "static assets, grep any source for leaked secrets, and check security headers.")


class InjectionAgent(BaseAgent):
    role = "injection"
    focus = "Test input handling: SQL injection on login-style endpoints and reflected XSS."


class AccessAgent(BaseAgent):
    role = "access"
    focus = "Test object-level authorization: walk sequential API ids without auth (IDOR/BOLA)."


SPECIALISTS: list[tuple[str, type[BaseAgent], list[str]]] = [
    ("Recon Scout", ReconAgent, ["reconnaissance", "security_headers"]),
    ("Injection Hunter", InjectionAgent, ["sql_injection", "xss"]),
    ("Access Auditor", AccessAgent, ["idor"]),
]


class RootAgent(BaseAgent):
    role = "root"

    def __init__(self, coord: Coordinator, settings, sandbox, target: str,
                 workspace_path: str | None) -> None:
        super().__init__(coord, settings, sandbox, "Root Orchestrator",
                         task=f"pentest {target}", parent=None,
                         skills=["reconnaissance", "severity_calibration"],
                         target=target, workspace_path=workspace_path)

    def work(self) -> None:
        # The root always orchestrates (it never tests hands-on), regardless of mode.
        self.ctx.phase("Orchestration — planning the engagement")
        self.ctx.think(f"target in scope: {self.target}"
                       + (f"; source at {self.workspace_path}" if self.workspace_path else ""))
        self.ctx.think("delegating to specialist subagents that share the sandbox container")

        threads = []
        for name, cls, skills in SPECIALISTS:
            child = cls(self.coord, self.settings, self.sandbox, name, cls.focus,
                        self.state.id, skills, self.target, self.workspace_path)
            self.coord.emit("think", self.state, f"create_agent → {name}")
            t = threading.Thread(target=child.run, name=name, daemon=True)
            t.start()
            threads.append(t)

        self.coord.set_status(self.state, "waiting", "wait_for_agents — specialists running")
        for t in threads:
            t.join()

        self.coord.set_status(self.state, "running", "all subagents reported back")
        self.ctx.phase("Aggregation — compiling the final report")
        self.ctx.think("de-duplicating findings and ranking by CVSS")
