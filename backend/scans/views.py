from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from . import runner
from .models import Scan
from .serializers import ScanListSerializer, ScanSerializer

# Cap a single events response so a huge run can't blow up a poll.
_MAX_EVENTS = 2000
# Heavy per-event payloads that don't belong in the live log stream.
_HEAVY_DATA_KEYS = ("markdown", "summary")


def _read_events(scan: Scan, after: int = 0):
    """Return ``(events, last_seq)`` from a scan's ``events.jsonl``.

    Reads the engine's live event stream straight off disk (the engine appends
    to it as the scan runs), tolerating a partial trailing line mid-write and
    dropping heavy fields like the embedded report markdown.
    """
    runs_dir = Path(settings.ENGINE_RUNS_DIR) / str(scan.pk)
    if not runs_dir.exists():
        return [], after
    # The engine writes into a single scan-xxxx subdir; newest wins.
    candidates = sorted(
        runs_dir.glob("*/events.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if not candidates:
        return [], after

    out, last = [], after
    try:
        with open(candidates[0], encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a partial line while the engine is mid-write
                seq = ev.get("seq", 0)
                if seq <= after:
                    continue
                data = ev.get("data") or {}
                if isinstance(data, dict):
                    data = {k: v for k, v in data.items() if k not in _HEAVY_DATA_KEYS}
                out.append({
                    "seq": seq,
                    "ts": ev.get("ts"),
                    "level": ev.get("level", "system"),
                    "agent": ev.get("agent", "system"),
                    "agent_id": ev.get("agent_id", "system"),
                    "role": ev.get("role", "system"),
                    "message": ev.get("message", ""),
                    "data": data,
                })
                if seq > last:
                    last = seq
    except OSError:
        return [], after
    return out[:_MAX_EVENTS], last


class ScanViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Owner-scoped scans: list / create / retrieve, plus `report` and `events`.

    Creating a scan launches the engine as a background subprocess; the client
    polls the detail and events endpoints until the scan is ``done`` or ``error``.
    """

    def get_queryset(self):
        # Never leak other users' scans — always scope to the caller.
        return Scan.objects.filter(owner=self.request.user)

    def get_serializer_class(self):
        return ScanListSerializer if self.action == "list" else ScanSerializer

    def perform_create(self, serializer):
        scan = serializer.save(owner=self.request.user, status="queued")
        runner.start_scan(scan)

    @action(detail=True, methods=["get"])
    def report(self, request, pk=None):
        """Return just the Markdown report for a scan (handy for the dashboard)."""
        scan = self.get_object()
        return Response({"id": scan.id, "status": scan.status, "report_md": scan.report_md})

    @action(detail=True, methods=["get"], url_path="report_pdf")
    def report_pdf(self, request, pk=None):
        """Render this scan as a professional vulnerability-assessment PDF.

        ``?template=executive|technical|owasp`` (default technical). A scan that is
        not finished (still running, or ended in error) yields no PDF — the real
        status and error are returned instead, never a report of fabricated data.
        """
        from . import reporting

        scan = self.get_object()
        if scan.status != "done":
            return Response(
                {"detail": f"No report available: the scan is '{scan.status}'.",
                 "status": scan.status, "error": scan.error},
                status=status.HTTP_409_CONFLICT,
            )
        template = (request.query_params.get("template") or reporting.DEFAULT_TEMPLATE).lower()
        if template not in reporting.TEMPLATES:
            template = reporting.DEFAULT_TEMPLATE
        pdf = reporting.render_pdf(scan, template)
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = (
            f'attachment; filename="openoffensive-report-{scan.id}-{template}.pdf"'
        )
        return resp

    @action(detail=True, methods=["get"])
    def events(self, request, pk=None):
        """The live agent-activity log — tail-able while the scan runs.

        `?after=<seq>` returns only events newer than that sequence number, so
        the dashboard can poll cheaply and append.
        """
        scan = self.get_object()
        try:
            after = int(request.query_params.get("after", 0))
        except (TypeError, ValueError):
            after = 0
        events, last_seq = _read_events(scan, after)
        return Response(
            {"id": scan.id, "status": scan.status, "last_seq": last_seq, "events": events}
        )
