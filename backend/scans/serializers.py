from __future__ import annotations

from rest_framework import serializers

from .models import Scan


class ScanListSerializer(serializers.ModelSerializer):
    """Lightweight row for the scans list (omits the heavy findings/report)."""

    finding_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Scan
        fields = (
            "id", "target", "mode", "status", "exit_code",
            "finding_count", "summary",
            "created_at", "started_at", "finished_at",
        )
        read_only_fields = fields


class ScanSerializer(serializers.ModelSerializer):
    """Full scan detail, including findings and the Markdown report."""

    finding_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Scan
        fields = (
            "id", "target", "mode", "status", "exit_code",
            "finding_count", "findings", "summary", "report_md", "error",
            "engine_scan_id",
            "created_at", "started_at", "finished_at",
        )
        # The client only supplies target + mode; everything else is engine-driven.
        read_only_fields = (
            "id", "status", "exit_code", "finding_count", "findings", "summary",
            "report_md", "error", "engine_scan_id",
            "created_at", "started_at", "finished_at",
        )

    def validate_target(self, value: str) -> str:
        return value.strip()
