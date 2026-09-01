"""Top-level scan runner — brings up a coordinator, runs the root agent, reports."""

from __future__ import annotations

import time

from . import reporting
from .agents import RootAgent
from .coordinator import Coordinator


def run_scan(coord: Coordinator) -> None:
    """Run one scan to completion. Blocks; intended to be called in a thread."""
    coord.status = "running"
    coord.started_at = time.time()
    coord.emit("system", None, f"scan started against {coord.target}")

    root = RootAgent(coord)
    root.run()  # spawns specialists, waits, aggregates

    md = reporting.build_markdown(coord)
    summ = reporting.summary(coord)
    coord.emit("report", None, f"finish_scan — {summ['total']} findings "
               f"(top: {summ['headline']})", markdown=md, summary=summ)

    coord.status = "done"
    coord.finished_at = time.time()
    coord.emit("system", None,
               f"scan complete in {coord.finished_at - coord.started_at:.1f}s "
               f"· {coord.turns} turns · ${coord.cost:.2f}")
