"""Top-level scan runner — resolves the mode, runs the root agent, persists."""

from __future__ import annotations

import time
import uuid
from typing import Optional

from . import reporting
from .agents import RootAgent
from .config import Settings, load_settings
from .coordinator import Coordinator
from .llm import llm_available
from .models import ScanResult
from .persistence import RunStore


def resolve_mode(settings: Settings) -> tuple[str, str]:
    """Return (mode, note). 'note' is non-empty when LLM was wanted but unavailable."""
    if not settings.llm_enabled:
        return "scripted", ""
    ok, reason = llm_available(settings)
    if ok:
        return "llm", ""
    return "scripted", f"LLM mode requested but unavailable: {reason}"


def run_scan(coord: Coordinator, *, settings: Optional[Settings] = None,
             scan_id: Optional[str] = None, store: Optional[RunStore] = None) -> ScanResult:
    """Run one scan to completion. Blocks; intended to be called in a thread."""
    settings = settings or load_settings()
    scan_id = scan_id or f"scan-{uuid.uuid4().hex[:8]}"
    store = store if store is not None else RunStore(settings.runs_dir)

    mode, note = resolve_mode(settings)
    coord.mode = mode

    coord.status = "running"
    coord.started_at = time.time()
    coord.emit("system", None, f"scan started against {coord.target}  [mode: {mode}]")
    if note:
        coord.emit("system", None, note)
    if mode == "llm":
        coord.emit("system", None, f"agents reasoning with model {settings.model}")

    status = "done"
    try:
        RootAgent(coord, settings).run()
    except Exception as e:  # noqa: BLE001
        status = "error"
        coord.emit("error", None, f"scan error: {e}")

    result = reporting.to_result(coord, scan_id, status, coord.started_at)
    summ = reporting.summary(coord)
    coord.emit("report", None,
               f"finish_scan — {summ['total']} findings (top: {summ['headline']})",
               markdown=result.report_md, summary=summ)

    coord.status = status
    coord.finished_at = time.time()

    try:
        store.save(coord, result)
        coord.emit("system", None, f"artifacts written to {store.dir_for(scan_id)}")
    except Exception as e:  # noqa: BLE001 — persistence must not fail the scan
        coord.emit("error", None, f"could not persist run: {e}")

    coord.emit("system", None,
               f"scan complete in {result.duration:.1f}s · {coord.turns} turns · ${coord.cost:.2f}")
    return result
