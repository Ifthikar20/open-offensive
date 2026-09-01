"""Shared data types for the Strix-Lite engine.

These mirror, in miniature, the records real Strix keeps: a stream of log
events, an agent graph, and validated findings with a severity/CVSS score.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Any

# Severity → representative CVSS base score. Real Strix computes a full CVSS
# vector; the POC keeps a simple, honest mapping so the UI can rank findings.
SEVERITY_CVSS = {
    "critical": 9.4,
    "high": 7.8,
    "medium": 5.6,
    "low": 3.3,
    "info": 0.0,
}

# Event levels drive the colour/'glyph' the live-log console renders.
LEVELS = ("system", "phase", "think", "skill", "tool", "finding", "graph", "report", "error")


@dataclass
class LogEvent:
    """One line in the live log / one graph update."""
    seq: int
    ts: float
    level: str
    agent_id: str
    agent: str
    role: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentState:
    """A node in the agent graph."""
    id: str
    name: str
    role: str
    parent: str | None
    status: str = "spawning"      # spawning|running|waiting|done|stopped
    skills: list[str] = field(default_factory=list)
    task: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Finding:
    """A validated vulnerability report."""
    id: str
    title: str
    severity: str
    target: str
    endpoint: str
    evidence: str
    remediation: str
    agent: str
    cwe: str = ""
    poc: str = ""

    @property
    def cvss(self) -> float:
        return SEVERITY_CVSS.get(self.severity, 0.0)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["cvss"] = self.cvss
        return d


def now() -> float:
    return time.time()
