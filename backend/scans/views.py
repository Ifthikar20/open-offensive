from __future__ import annotations

from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from . import runner
from .models import Scan
from .serializers import ScanListSerializer, ScanSerializer


class ScanViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Owner-scoped scans: list / create / retrieve, plus a `report` view.

    Creating a scan launches the engine as a background subprocess; the client
    polls the detail endpoint for status until it is ``done`` or ``error``.
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
