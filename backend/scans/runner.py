"""Run the OpenOffensive engine as a subprocess and ingest its artifacts.

We shell out to the engine's CLI (`python -m openoffensive scan …`) into a
per-scan runs directory, then read the results back with the engine's own
``RunStore`` — so the backend stays decoupled from the engine's internals.
Kept deliberately simple: one background thread per scan, status polled by the
dashboard (no Celery / websockets).
"""

from __future__ import annotations

import subprocess
import threading

from django.conf import settings
from django.db import connections
from django.utils import timezone

_ENGINE_TIMEOUT = 1800  # seconds


def start_scan(scan) -> None:
    """Kick off ``scan`` in a background daemon thread and return immediately."""
    threading.Thread(target=_run, args=(scan.pk,), name=f"scan-{scan.pk}", daemon=True).start()


def _run(scan_pk: int) -> None:
    from .models import Scan  # local import; this runs off the request thread

    try:
        scan = Scan.objects.get(pk=scan_pk)
    except Scan.DoesNotExist:
        return

    runs_dir = settings.ENGINE_RUNS_DIR / str(scan_pk)
    runs_dir.mkdir(parents=True, exist_ok=True)

    cmd = [settings.ENGINE_PYTHON, "-m", "openoffensive", "scan", scan.target,
           "--runs-dir", str(runs_dir), "--sandbox", settings.ENGINE_SANDBOX]
    if settings.ENGINE_ALLOW_EXTERNAL:
        cmd.append("--authorized")

    scan.status = "running"
    scan.started_at = timezone.now()
    scan.save(update_fields=["status", "started_at"])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_ENGINE_TIMEOUT)
        scan.exit_code = proc.returncode
        _ingest(scan, runs_dir, stderr=proc.stderr)
    except subprocess.TimeoutExpired:
        scan.status = "error"
        scan.error = f"scan exceeded the {_ENGINE_TIMEOUT}s time budget"
    except Exception as e:  # noqa: BLE001
        scan.status = "error"
        scan.error = f"could not run the engine: {e}"
    finally:
        scan.finished_at = timezone.now()
        scan.save()
        connections.close_all()  # release this thread's DB connection


def _ingest(scan, runs_dir, stderr: str = "") -> None:
    """Read the engine's artifacts for this run and populate the Scan record."""
    from openoffensive.persistence import RunStore

    store = RunStore(str(runs_dir))
    runs = store.list_runs()
    if not runs:
        scan.status = "error"
        scan.error = (stderr or "the engine produced no run artifacts").strip()[-2000:]
        return

    summary = runs[0]
    scan_id = summary["scan_id"]
    rec = store.load_run(scan_id) or {}

    scan.engine_scan_id = scan_id
    scan.findings = rec.get("findings", [])
    scan.summary = {
        "counts": rec.get("counts", {}),
        "total": len(rec.get("findings", [])),
        "top_severity": rec.get("top_severity", "none"),
        "duration": rec.get("duration", 0),
    }
    scan.report_md = store.load_report(scan_id)
    # engine status is "done" or "error"; mirror it (exit code 1 is an engine error)
    engine_status = rec.get("status", "done")
    scan.status = "error" if engine_status == "error" else "done"
    if scan.status == "error" and not scan.error:
        scan.error = (stderr or "the scan ended in an error state").strip()[-2000:]
