"""Shared data types for the OpenOffensive engine.

These mirror, in miniature, the records a real pentest engine keeps: a stream of log
events, an agent graph, and validated findings with a severity/CVSS score.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Any

# Severity → representative CVSS base score. A production engine computes a full CVSS
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


@dataclass
class ScanConfig:
    """Everything needed to launch one scan."""
    target: str
    scan_id: str
    mode: str = "scripted"        # "scripted" | "llm"
    model: str | None = None      # resolved model id when mode == "llm"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScanResult:
    """The outcome of a finished (or in-progress) scan — the persisted record."""
    scan_id: str
    target: str
    mode: str
    status: str                   # running | done | error
    findings: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    turns: int = 0
    cost: float = 0.0
    started_at: float = 0.0
    finished_at: float | None = None
    report_md: str = ""

    @property
    def duration(self) -> float:
        return (self.finished_at or now()) - self.started_at

    @property
    def top_severity(self) -> str:
        for sev in ("critical", "high", "medium", "low", "info"):
            if self.counts.get(sev):
                return sev
        return "none"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["duration"] = round(self.duration, 2)
        d["top_severity"] = self.top_severity
        return d


def now() -> float:
    return time.time()
