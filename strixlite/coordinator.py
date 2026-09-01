"""The Coordinator — Strix-Lite's answer to Strix's AgentCoordinator.

It is the single owner of run state: the agent graph, the findings store, a
running event log, and the set of live subscribers (each an SSE client). Every
agent talks to the target and to each other only by emitting events here, so the
live log is a faithful trace of what the agents actually did.

Thread-safe: agents run in their own threads and the HTTP server reads from here
on request threads, so every mutation takes the lock and every subscriber gets a
thread-safe queue.
"""

from __future__ import annotations

import queue
import threading
from typing import Any

from .models import AgentState, Finding, LogEvent, now


class Coordinator:
    def __init__(self, target: str) -> None:
        self.target = target
        self._lock = threading.Lock()
        self._seq = 0
        self._finding_seq = 0
        self.events: list[LogEvent] = []
        self.agents: dict[str, AgentState] = {}
        self.findings: list[Finding] = []
        self._subscribers: list[queue.Queue] = []
        # A pretend spend meter, so the UI can show the budget idea Strix relies on.
        self.turns = 0
        self.cost = 0.0
        self.status = "idle"          # idle|running|done
        self.started_at: float | None = None
        self.finished_at: float | None = None

    # ---- pub/sub for the live log -------------------------------------------
    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            backlog = list(self.events)
            self._subscribers.append(q)
        # Replay what already happened so a late-joining browser is caught up.
        for ev in backlog:
            q.put(ev)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def _broadcast(self, ev: LogEvent) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(ev)
            except Exception:
                pass

    # ---- emitting events ----------------------------------------------------
    def emit(self, level: str, agent: AgentState | None, message: str,
             **data: Any) -> LogEvent:
        with self._lock:
            self._seq += 1
            ev = LogEvent(
                seq=self._seq,
                ts=now(),
                level=level,
                agent_id=agent.id if agent else "system",
                agent=agent.name if agent else "system",
                role=agent.role if agent else "system",
                message=message,
                data=data,
            )
            self.events.append(ev)
        self._broadcast(ev)
        return ev

    # ---- the agent graph ----------------------------------------------------
    def register(self, agent: AgentState) -> AgentState:
        with self._lock:
            self.agents[agent.id] = agent
        self.emit("graph", agent, f"spawned :: {agent.task}", status=agent.status,
                  parent=agent.parent, skills=agent.skills)
        return agent

    def set_status(self, agent: AgentState, status: str, note: str = "") -> None:
        agent.status = status
        self.emit("graph", agent, note or f"status → {status}", status=status)

    def bill(self, agent: AgentState, turns: int = 1, cost: float = 0.012) -> None:
        """Charge a little 'budget' so the run has a visible meter, like Strix."""
        with self._lock:
            self.turns += turns
            self.cost += cost

    # ---- findings -----------------------------------------------------------
    def add_finding(self, agent: AgentState, finding: Finding) -> Finding:
        with self._lock:
            # de-dupe on (title, endpoint), like Strix's ReportState
            for existing in self.findings:
                if existing.title == finding.title and existing.endpoint == finding.endpoint:
                    return existing
            if not finding.id:
                self._finding_seq += 1
                finding.id = f"VULN-{self._finding_seq:04d}"
            self.findings.append(finding)
        self.emit("finding", agent,
                  f"filed {finding.severity.upper()} — {finding.title}",
                  finding=finding.to_dict())
        return finding

    # ---- snapshot for a fresh page load ------------------------------------
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "target": self.target,
                "status": self.status,
                "turns": self.turns,
                "cost": round(self.cost, 3),
                "agents": [a.to_dict() for a in self.agents.values()],
                "findings": [f.to_dict() for f in self.findings],
                "last_seq": self._seq,
            }

    def severity_counts(self) -> dict[str, int]:
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        with self._lock:
            for f in self.findings:
                counts[f.severity] = counts.get(f.severity, 0) + 1
        return counts
