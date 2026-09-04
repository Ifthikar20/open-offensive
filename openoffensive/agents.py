"""The agents — a root orchestrator that delegates to specialist sub-agents, all
sharing ONE Kali sandbox container (the Strix model).

Each specialist runs in one of two ways, chosen per scan by the runner:

* **llm** — a real model drives the specialist: it decides which ``run_command``
  to issue inside the container, reads the output, and repeats until it calls
  ``finish``. This is the true agentic loop.
* **scripted** — a fixed playbook of real ``run_command``s in the container
  (no API key needed), so a run still spins a container and runs real tools.

Either way it's the same shared container, the same tools, the same findings
store, and the same live log.
"""

from __future__ import annotations

import threading
import uuid

from .coordinator import Coordinator
from .llm import LLMUnavailable, run_agent_llm
from .models import AgentState
from .tools import ToolContext

_TOOLS = ["run_command", "read_file", "load_skill", "list_skills", "report_finding", "finish"]

_COMMON_SYSTEM = (
    "You are OpenOffensive, an authorized penetration-testing agent working INSIDE an "
    "isolated Kali Linux sandbox container. A full toolset (nmap, curl, sqlmap, nikto, "
    "gobuster, whatweb, python3, git) is available through the run_command tool, which "
    "runs a shell command in the container and returns its output. "
    "You are authorized to test ONLY {scope}. Never attempt to reach any other host. "
    "Confirm every issue from real tool output before reporting it. Before testing a "
    "vulnerability class you're unsure about, call load_skill. File each validated issue "
    "with report_finding — evidence quoted from real output, a concrete proof-of-concept, "
    "a fix, and an honest severity; never invent findings. Work step by step, one tool "
    "call per step, and call finish with a short summary when your focus area is covered."
)


def _aid() -> str:
    return uuid.uuid4().hex[:8]


def _matching(text: str, *needles: str, limit: int = 4) -> str:
    """The real output lines that contain any needle — a finding's raw proof."""
    hits = [ln.rstrip() for ln in text.splitlines() if any(n in ln for n in needles)]
    return "\n".join(hits[:limit])


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
        return _COMMON_SYSTEM.format(scope=self._scope())

    def task_prompt(self) -> str:
        src = self.workspace_path or "none (black-box — test over the network)"
        return (f"Target: {self.target}\nSource in the container: {src}\n"
                f"Your focus: {self.focus}\n"
                "Orient yourself first (curl the target, or list/grep the source), then test "
                "thoroughly and report what you validate.")

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
        if self.coord.mode == "llm":
            try:
                run_agent_llm(self.ctx, system_prompt=self.system_prompt(),
                              task=self.task_prompt(), tool_names=_TOOLS, settings=self.settings)
                return
            except LLMUnavailable as e:
                self.coord.emit("error", self.state, f"LLM unavailable ({e}); using scripted mode")
        self.scripted()

    def scripted(self) -> None:  # overridden by specialists
        raise NotImplementedError

    # -- scripted helpers -----------------------------------------------------
    def _file(self, **kw) -> None:
        self.ctx.report(**kw)


# ---------------------------------------------------------------------------
# Specialists (scripted playbooks run REAL commands in the container)
# ---------------------------------------------------------------------------
class ReconAgent(BaseAgent):
    role = "recon"
    focus = ("Map the attack surface: fingerprint the server, fetch key endpoints and "
             "static assets, grep any source for leaked secrets, and check security headers.")

    def scripted(self) -> None:
        self.ctx.phase("Reconnaissance — mapping the attack surface")
        home_cmd = f"curl -s -i {self.target}/"
        home = self.ctx.run(home_cmd)
        banner = ""
        for line in home.stdout.splitlines():
            if line.lower().startswith("server:"):
                banner = line.strip()
        if banner:
            self._file(title="Server version disclosure", severity="info", endpoint="/",
                       evidence=f"Server header reveals '{banner.split(':', 1)[1].strip()}'.",
                       remediation="Suppress or genericise the Server header.", cwe="CWE-200",
                       command=home_cmd, output=banner)
        js_cmd = f"curl -s {self.target}/static/app.js"
        js = self.ctx.run(js_cmd)
        leak = _matching(js.stdout, "sk_live_")
        if leak:
            self._file(title="Hardcoded live secret key in client bundle", severity="critical",
                       endpoint="/static/app.js",
                       evidence="Client-served JS embeds a live sk_live_ key.",
                       remediation="Revoke the key; move secrets server-side.", cwe="CWE-798",
                       poc="curl -s $TARGET/static/app.js | grep sk_live_",
                       command=js_cmd, output=leak)
        if self.workspace_path:
            grep_cmd = f"grep -rEn 'sk_live_|api_key|password' {self.workspace_path} | head -20"
            grep = self.ctx.run(grep_cmd)
            if grep.stdout.strip():
                self._file(title="Secrets in source", severity="high", endpoint=self.workspace_path,
                           evidence="grep found credential-like strings in the source.",
                           remediation="Remove secrets from source; rotate them.", cwe="CWE-798",
                           command=grep_cmd, output=grep.stdout[:800])
        headers = home.stdout.lower()
        missing = [h for h in ("content-security-policy", "x-frame-options",
                               "x-content-type-options") if h not in headers]
        if missing:
            hdr_block = home.stdout.split("\r\n\r\n", 1)[0].split("\n\n", 1)[0]
            self._file(title="Missing security headers", severity="low", endpoint="/",
                       evidence="Absent: " + ", ".join(missing),
                       remediation="Add CSP, X-Frame-Options, X-Content-Type-Options.", cwe="CWE-693",
                       command=home_cmd, output=hdr_block[:600])


class InjectionAgent(BaseAgent):
    role = "injection"
    focus = "Test input handling: SQL injection on login-style endpoints and reflected XSS."

    def scripted(self) -> None:
        self.ctx.phase("Injection testing — SQLi & XSS")
        sqli_cmd = f"curl -s -i \"{self.target}/login?user=admin%27&pass=x\""
        sqli = self.ctx.run(sqli_cmd)
        err = _matching(sqli.stdout, "SQL", "SQLException", "SQLite", "syntax error")
        if err:
            self._file(title="Error-based SQL injection", severity="high", endpoint="/login",
                       evidence="A single quote triggers a raw SQL error in the response.",
                       remediation="Use parameterised queries; never concatenate input into SQL.",
                       cwe="CWE-89", poc="curl -s \"$TARGET/login?user=admin%27&pass=x\"",
                       command=sqli_cmd, output=err)
        xss_cmd = f"curl -s \"{self.target}/search?q=<script>xss1()</script>\""
        xss = self.ctx.run(xss_cmd)
        if "<script>xss1()</script>" in xss.stdout:
            self._file(title="Reflected cross-site scripting (XSS)", severity="medium",
                       endpoint="/search",
                       evidence="The q parameter is reflected un-encoded into the HTML body.",
                       remediation="Context-encode output; add a strict CSP.", cwe="CWE-79",
                       poc="open \"$TARGET/search?q=<script>alert(1)</script>\"",
                       command=xss_cmd,
                       output=_matching(xss.stdout, "<script>xss1()</script>") or xss.stdout[:200])


class AccessAgent(BaseAgent):
    role = "access"
    focus = "Test object-level authorization: walk sequential API ids without auth (IDOR/BOLA)."

    def scripted(self) -> None:
        self.ctx.phase("Access control — object-level authorization")
        walk_cmd = f"for i in 1 2 3; do curl -s {self.target}/api/user/$i; echo; done"
        walk = self.ctx.run(walk_cmd)
        if walk.stdout.count("api_token") > 1:
            self._file(title="IDOR — unauthenticated access to any user record", severity="high",
                       endpoint="/api/user/{id}",
                       evidence="Records for several ids returned without auth, each exposing "
                                "another user's email and api_token.",
                       remediation="Enforce authentication and an ownership check on every lookup.",
                       cwe="CWE-639", poc="for i in 1 2 3; do curl -s $TARGET/api/user/$i; done",
                       command=walk_cmd, output=walk.stdout[:400])


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
