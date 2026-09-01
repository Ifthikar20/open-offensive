"""The agents — a root orchestrator that delegates to specialist sub-agents.

Each specialist can run in two modes, chosen once per scan by the runner:

* **scripted** (default, no API key needed): a fixed, auditable methodology that
  drives the shared tool layer step by step.
* **llm**: the specialist is handed a system prompt + its focus and a set of
  tools, and a real model decides what to probe and what to report.

Either way it's the *same* tools, the same findings store, and the same live
log — so the two modes are directly comparable.
"""

from __future__ import annotations

import threading
import time
import uuid

from .coordinator import Coordinator
from .llm import LLMUnavailable, run_agent_llm
from .models import AgentState
from .tools import ToolContext

_COMMON_SYSTEM = (
    "You are OpenOffensive, an authorized penetration-testing agent operating "
    "under explicit written authorization. You are testing ONLY the target {target} "
    "and must never attempt to reach any other host. Probe with the http_request "
    "tool and confirm issues from real responses. Before testing a vulnerability "
    "class you are unsure about, call load_skill (use list_skills to discover them). "
    "File each validated issue with report_finding, quoting the evidence from a real "
    "response and giving a concrete proof-of-concept, a fix, and an honest severity — "
    "never invent findings. Make one tool call per step, keep going until your focus "
    "area is thoroughly covered, then call finish with a short summary."
)

_TOOLS = ["http_request", "load_skill", "list_skills", "report_finding", "finish"]


def _aid() -> str:
    return uuid.uuid4().hex[:8]


class BaseAgent:
    role = "agent"
    focus = ""

    def __init__(self, coord: Coordinator, settings, name: str, task: str,
                 parent: str | None, skills: list[str]) -> None:
        self.coord = coord
        self.settings = settings
        self.state = AgentState(id=_aid(), name=name, role=self.role, parent=parent,
                                task=task, skills=list(skills))
        coord.register(self.state)
        self.ctx = ToolContext(coord, self.state, settings)

    # -- narration helpers (scripted mode) ------------------------------------
    def think(self, msg: str) -> None:
        self.ctx.think(msg)

    def phase(self, msg: str) -> None:
        self.ctx.phase(msg)

    def load_skill(self, name: str) -> str:
        from . import skills
        body = skills.load(name)
        self.coord.emit("skill", self.state, f"load_skill({name}) — {body}")
        self.ctx.pace(0.25)
        return body

    def file(self, *, title: str, severity: str, endpoint: str, evidence: str,
             remediation: str, cwe: str = "", poc: str = "") -> None:
        self.load_skill("severity_calibration")
        self.think(f"calibrating severity for '{title}' → {severity.upper()}")
        self.ctx.report(title=title, severity=severity, endpoint=endpoint,
                        evidence=evidence, remediation=remediation, cwe=cwe, poc=poc)

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
        """Dispatch to the LLM loop or the scripted methodology."""
        if self.coord.mode == "llm":
            try:
                run_agent_llm(
                    self.ctx,
                    system_prompt=_COMMON_SYSTEM.format(target=self.coord.target),
                    task=f"Target: {self.coord.target}\nYour focus: {self.focus}\nBegin.",
                    tool_names=_TOOLS,
                    settings=self.settings,
                )
                return
            except LLMUnavailable as e:
                self.coord.emit("error", self.state, f"LLM unavailable ({e}); using scripted mode")
        self.scripted()

    def scripted(self) -> None:  # overridden by specialists
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Specialists
# ---------------------------------------------------------------------------
class ReconAgent(BaseAgent):
    role = "recon"
    focus = ("Map the attack surface. Fetch the homepage and static assets, read "
             "robots.txt, note the server banner, grep responses for leaked "
             "secrets/keys, and check for missing security headers.")

    def scripted(self) -> None:
        self.phase("Reconnaissance — mapping the attack surface")
        self.load_skill("reconnaissance")
        home = self.ctx.http("/")
        banner = home.headers.get("server", "")
        if banner:
            self.think(f"server banner discloses software/version: '{banner}'")
            self.file(title="Server version disclosure", severity="info", endpoint="/",
                      evidence=f"Server header reveals '{banner}', aiding fingerprinting.",
                      remediation="Suppress or genericise the Server response header.",
                      cwe="CWE-200")
        self.ctx.http("/robots.txt")
        self.think("pulling static assets to grep for leaked secrets")
        js = self.ctx.http("/static/app.js")
        if "sk_live_" in js.body:
            token = next((w for w in js.body.replace('"', " ").split()
                          if w.startswith("sk_live_")), "sk_live_…")
            self.file(title="Hardcoded live secret key in client bundle", severity="critical",
                      endpoint="/static/app.js",
                      evidence=f"Client-served JS embeds a live key: {token}",
                      remediation="Revoke the key immediately; move secrets server-side.",
                      cwe="CWE-798", poc="curl -s $TARGET/static/app.js | grep sk_live_")
        self.phase("Hardening review — response headers")
        self.load_skill("security_headers")
        missing = [h for h in ("content-security-policy", "x-frame-options",
                               "x-content-type-options") if h not in home.headers]
        if missing:
            self.file(title="Missing security headers", severity="low", endpoint="/",
                      evidence="Absent: " + ", ".join(missing),
                      remediation="Add CSP, X-Frame-Options, and X-Content-Type-Options.",
                      cwe="CWE-693")


class InjectionAgent(BaseAgent):
    role = "injection"
    focus = ("Test input-handling flaws: SQL injection on login-style endpoints "
             "(a single-quote error oracle) and reflected XSS on search/query params.")

    def scripted(self) -> None:
        self.phase("Injection testing — SQLi & XSS")
        self.load_skill("sql_injection")
        self.think("probing /login with a single-quote error oracle")
        r = self.ctx.http("/login", params={"user": "admin'", "pass": "x"})
        if r.status >= 500 and ("SQL" in r.body or "SQLException" in r.body):
            self.file(title="Error-based SQL injection", severity="high", endpoint="/login",
                      evidence="A single quote triggers a raw SQL error: "
                               + r.body.split("\n")[0][:140],
                      remediation="Use parameterised queries; never concatenate input into SQL.",
                      cwe="CWE-89", poc="curl -s \"$TARGET/login?user=admin%27&pass=x\"")
        self.load_skill("xss")
        marker = "<script>xss1()</script>"
        self.think(f"spraying a marked XSS payload into /search?q= ({marker})")
        r = self.ctx.http("/search", params={"q": marker})
        if marker in r.body:
            self.file(title="Reflected cross-site scripting (XSS)", severity="medium",
                      endpoint="/search",
                      evidence="The q parameter is reflected un-encoded into the HTML body.",
                      remediation="Context-encode all user input on output; add a strict CSP.",
                      cwe="CWE-79", poc="open \"$TARGET/search?q=<script>alert(1)</script>\"")


class AccessAgent(BaseAgent):
    role = "access"
    focus = ("Test object-level authorization: walk sequential ids on any /api/... "
             "resource and check whether records are returned without auth (IDOR/BOLA).")

    def scripted(self) -> None:
        self.phase("Access control — object-level authorization")
        self.load_skill("idor")
        self.think("walking sequential ids on /api/user/<id> with no auth")
        leaked = []
        for uid in ("1", "2", "3"):
            r = self.ctx.http(f"/api/user/{uid}")
            if r.status == 200 and "api_token" in r.body:
                leaked.append(uid)
        if len(leaked) > 1:
            self.file(title="IDOR — unauthenticated access to any user record", severity="high",
                      endpoint="/api/user/{id}",
                      evidence=f"Records for ids {', '.join(leaked)} returned without auth, "
                               "each exposing another user's email and live api_token.",
                      remediation="Enforce authentication and an ownership check on every lookup.",
                      cwe="CWE-639", poc="for i in 1 2 3; do curl -s $TARGET/api/user/$i; done")


SPECIALISTS: list[tuple[str, type[BaseAgent], list[str]]] = [
    ("Recon Scout", ReconAgent, ["reconnaissance", "security_headers"]),
    ("Injection Hunter", InjectionAgent, ["sql_injection", "xss"]),
    ("Access Auditor", AccessAgent, ["idor"]),
]


class RootAgent(BaseAgent):
    role = "root"

    def __init__(self, coord: Coordinator, settings) -> None:
        super().__init__(coord, settings, "Root Orchestrator",
                         task=f"pentest {coord.target}", parent=None,
                         skills=["reconnaissance", "severity_calibration"])

    def work(self) -> None:
        # The root always orchestrates (it never tests hands-on), regardless of mode.
        self.phase("Orchestration — planning the engagement")
        self.think(f"target in scope: {self.coord.target}")
        self.think("my job is delegation, not hands-on testing — decomposing into "
                   "specialist subagents")

        threads = []
        for name, cls, skills in SPECIALISTS:
            child = cls(self.coord, self.settings, name, cls.focus, self.state.id, skills)
            self.coord.emit("think", self.state, f"create_agent → {name}")
            t = threading.Thread(target=child.run, name=name, daemon=True)
            t.start()
            threads.append(t)
            self.ctx.pace(0.6)

        self.coord.set_status(self.state, "waiting", "wait_for_agents — specialists running")
        for t in threads:
            t.join()

        self.coord.set_status(self.state, "running", "all subagents reported back")
        self.phase("Aggregation — compiling the final report")
        self.think("de-duplicating findings and ranking by CVSS")
