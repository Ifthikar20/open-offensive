"""Run persistence — every scan is written to ``runs/<scan_id>/`` so results
survive the process and the dashboard can browse history.

Artifacts per run:
  run.json         the ScanResult record (status, counts, cost, report)
  findings.json    the findings array
  findings.sarif   SARIF 2.1.0 for code-scanning / CI ingestion
  report.md        the human-readable report
  events.jsonl     the full live-log event stream (one JSON object per line)
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from . import reporting
from .coordinator import Coordinator
from .models import ScanResult


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class RunStore:
    def __init__(self, runs_dir: str | Path = "runs") -> None:
        self.root = Path(runs_dir)

    def dir_for(self, scan_id: str) -> Path:
        return self.root / scan_id

    # -- write ----------------------------------------------------------------
    def save(self, coord: Coordinator, result: ScanResult) -> Path:
        d = self.dir_for(result.scan_id)
        _atomic_write(d / "run.json", json.dumps(result.to_dict(), indent=2))
        _atomic_write(d / "findings.json", json.dumps(result.findings, indent=2))
        _atomic_write(d / "findings.sarif",
                      json.dumps(reporting.build_sarif(coord), indent=2))
        _atomic_write(d / "report.md", result.report_md)
        _atomic_write(d / "events.jsonl",
                      "\n".join(json.dumps(e.to_dict()) for e in coord.events))
        return d

    # -- read -----------------------------------------------------------------
    def load_run(self, scan_id: str) -> dict[str, Any] | None:
        p = self.dir_for(scan_id) / "run.json"
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def load_events(self, scan_id: str) -> list[dict[str, Any]]:
        p = self.dir_for(scan_id) / "events.jsonl"
        if not p.exists():
            return []
        out: list[dict[str, Any]] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def load_report(self, scan_id: str) -> str:
        p = self.dir_for(scan_id) / "report.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def list_runs(self) -> list[dict[str, Any]]:
        """Summaries of all persisted runs, newest first."""
        if not self.root.exists():
            return []
        runs: list[dict[str, Any]] = []
        for child in self.root.iterdir():
            if not child.is_dir():
                continue
            rec = self.load_run(child.name)
            if rec is None:
                continue
            runs.append({
                "scan_id": rec.get("scan_id", child.name),
                "target": rec.get("target", ""),
                "mode": rec.get("mode", ""),
                "status": rec.get("status", ""),
                "counts": rec.get("counts", {}),
                "total": len(rec.get("findings", [])),
                "top_severity": rec.get("top_severity", "none"),
                "started_at": rec.get("started_at", 0),
                "finished_at": rec.get("finished_at"),
                "duration": rec.get("duration", 0),
            })
        runs.sort(key=lambda r: r.get("started_at", 0), reverse=True)
        return runs
