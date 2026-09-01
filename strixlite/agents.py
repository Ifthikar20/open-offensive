"""The agents — a root orchestrator that delegates to specialist sub-agents.

This is the miniature of Strix's "graph of agents": the root does no hands-on
testing itself; it plans, spawns specialists (each in its own thread, running in
parallel), waits for them, then compiles the report. Each specialist loads the
skills for its niche, drives the tool layer against the target, calibrates
severity, and files findings — every step narrated to the live log.
"""

from __future__ import annotations

import threading
import time
import uuid

from . import skills
from .coordinator import Coordinator
from .models import AgentState, Finding
from .tools import Toolbox


def _aid() -> str:
    return uuid.uuid4().hex[:8]


class BaseAgent:
    role = "agent"

    def __init__(self, coord: Coordinator, name: str, task: str,
                 parent: str | None, skill_names: list[str]) -> None:
        self.coord = coord
        self.state = AgentState(id=_aid(), name=name, role=self.role, parent=parent,
                                task=task, skills=list(skill_names))
        coord.register(self.state)
        self.tools = Toolbox(coord, self.state)

    # --- narration helpers (each is a kind of live-log line) -----------------
    def think(self, msg: str, pause: float = 0.35) -> None:
        self.coord.emit("think", self.state, msg)
        time.sleep(pause)

    def phase(self, msg: str) -> None:
        self.coord.emit("phase", self.state, msg)
        time.sleep(0.2)

    def load_skill(self, name: str) -> str:
        body = skills.load(name)
        self.coord.emit("skill", self.state, f"load_skill({name}) — {body}")
        time.sleep(0.3)
        return body

    def file(self, title: str, severity: str, endpoint: str, evidence: str,
             remediation: str, cwe: str = "", poc: str = "") -> Finding:
        self.load_skill("severity_calibration")
        self.think(f"calibrating severity for '{title}' → {severity.upper()}")
        f = Finding(id="", title=title, severity=severity, target=self.coord.target,
                    endpoint=endpoint, evidence=evidence, remediation=remediation,
                    agent=self.state.name, cwe=cwe, poc=poc)
        return self.coord.add_finding(self.state, f)

    # --- lifecycle -----------------------------------------------------------
    def run(self) -> None:
        self.coord.set_status(self.state, "running")
        try:
            self.work()
            done_note = ("finish_scan → report written" if self.state.parent is None
                         else "agent_finish → reporting to root")
            self.coord.set_status(self.state, "done", done_note)
        except Exception as e:  # noqa: BLE001 — a dead child must not take down the run
            self.coord.emit("error", self.state, f"crashed: {e}")
            self.coord.set_status(self.state, "stopped", "stopped after error")

    def work(self) -> None:  # overridden by specialists
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Specialists
# ---------------------------------------------------------------------------
class ReconAgent(BaseAgent):
    role = "recon"

    def work(self) -> None:
        self.phase("Reconnaissance — mapping the attack surface")
        self.load_skill("reconnaissance")

        home = self.tools.http_get("/", note="fetch homepage")
        banner = home.headers.get("server", "")
        if banner:
            self.think(f"server banner discloses software/version: '{banner}'")
            self.file(
                title="Server version disclosure",
                severity="info",
                endpoint="/",
                evidence=f"Server header reveals '{banner}', aiding fingerprinting.",
                remediation="Suppress or genericise the Server response header.",
                cwe="CWE-200",
            )

        self.tools.http_get("/robots.txt", note="read robots.txt")

        self.think("pulling static assets to grep for leaked secrets")
        js = self.tools.http_get("/static/app.js", note="fetch client bundle")
        if "sk_live_" in js.body:
            token = next((w for w in js.body.replace('"', " ").split()
                          if w.startswith("sk_live_")), "sk_live_…")
            self.file(
                title="Hardcoded live secret key in client bundle",
                severity="critical",
                endpoint="/static/app.js",
                evidence=f"Client-served JS embeds a live key: {token}",
                remediation="Revoke the key immediately; move secrets server-side and "
                            "out of any client-delivered asset.",
                cwe="CWE-798",
                poc="curl -s $TARGET/static/app.js | grep sk_live_",
            )

        self.phase("Hardening review — response headers")
        self.load_skill("security_headers")
        missing = [h for h in ("content-security-policy", "x-frame-options",
                               "x-content-type-options")
                   if h not in home.headers]
        if missing:
            self.file(
                title="Missing security headers",
                severity="low",
                endpoint="/",
                evidence="Absent: " + ", ".join(missing),
                remediation="Add CSP, X-Frame-Options, and X-Content-Type-Options.",
                cwe="CWE-693",
            )


class InjectionAgent(BaseAgent):
    role = "injection"

    def work(self) -> None:
        self.phase("Injection testing — SQLi & XSS")

        self.load_skill("sql_injection")
        self.think("probing /login with a single-quote error oracle")
        r = self.tools.http_get("/login", {"user": "admin'", "pass": "x"},
                                note="SQLi probe: user=admin'")
        if r.status >= 500 and ("SQL" in r.body or "SQLException" in r.body):
            self.file(
                title="Error-based SQL injection",
                severity="high",
                endpoint="/login",
                evidence="A single quote triggers a raw SQL error: "
                         + r.body.split("\n")[0][:140],
                remediation="Use parameterised queries/prepared statements; never "
                            "concatenate input into SQL. Stop leaking DB errors.",
                cwe="CWE-89",
                poc="curl -s \"$TARGET/login?user=admin%27&pass=x\"",
            )

        self.load_skill("xss")
        marker = "<script>st1x()</script>"
        self.think(f"spraying a marked XSS payload into /search?q= ({marker})")
        r = self.tools.http_get("/search", {"q": marker}, note="XSS probe on q=")
        if marker in r.body:
            self.file(
                title="Reflected cross-site scripting (XSS)",
                severity="medium",
                endpoint="/search",
                evidence="The q parameter is reflected un-encoded into the HTML body, "
                         "so injected script executes.",
                remediation="Context-encode all user input on output; add a strict CSP.",
                cwe="CWE-79",
                poc="open \"$TARGET/search?q=<script>alert(1)</script>\"",
            )


class AccessAgent(BaseAgent):
    role = "access"

    def work(self) -> None:
        self.phase("Access control — object-level authorization")
        self.load_skill("idor")
        self.think("walking sequential ids on /api/user/<id> with no auth")

        leaked = []
        for uid in ("1", "2", "3"):
            r = self.tools.http_get(f"/api/user/{uid}", note=f"IDOR walk id={uid}")
            if r.status == 200 and "api_token" in r.body:
                leaked.append(uid)

        if len(leaked) > 1:
            self.file(
                title="IDOR — unauthenticated access to any user record",
                severity="high",
                endpoint="/api/user/{id}",
                evidence=f"Records for ids {', '.join(leaked)} returned without auth, "
                         "each exposing another user's email and live api_token.",
                remediation="Enforce authentication and an ownership check on every "
                            "object lookup; do not return secrets in user objects.",
                cwe="CWE-639",
                poc="for i in 1 2 3; do curl -s $TARGET/api/user/$i; done",
            )


SPECIALISTS = [
    ("Recon Scout", ReconAgent, "map surface, fingerprint, hunt secrets",
     ["reconnaissance", "security_headers"]),
    ("Injection Hunter", InjectionAgent, "test SQLi and XSS on inputs",
     ["sql_injection", "xss"]),
    ("Access Auditor", AccessAgent, "test object-level authorization",
     ["idor"]),
]


class RootAgent(BaseAgent):
    role = "root"

    def __init__(self, coord: Coordinator) -> None:
        super().__init__(coord, "Root Orchestrator",
                         task=f"pentest {coord.target}", parent=None,
                         skill_names=["reconnaissance", "severity_calibration"])

    def work(self) -> None:
        self.phase("Orchestration — planning the engagement")
        self.think(f"target in scope: {self.coord.target}")
        self.think("my job is delegation, not hands-on testing — decomposing into "
                   "specialist subagents", pause=0.5)

        threads = []
        for name, cls, task, skill_names in SPECIALISTS:
            child = cls(self.coord, name, task, self.state.id, skill_names)
            self.coord.emit("think", self.state, f"create_agent → {name} ({task})")
            t = threading.Thread(target=child.run, name=name, daemon=True)
            t.start()
            threads.append(t)
            time.sleep(0.6)  # stagger spawns so the graph fills in visibly

        self.coord.set_status(self.state, "waiting", "wait_for_agents — specialists running")
        for t in threads:
            t.join()

        self.coord.set_status(self.state, "running", "all subagents reported back")
        self.phase("Aggregation — compiling the final report")
        self.think("de-duplicating findings and ranking by CVSS")
