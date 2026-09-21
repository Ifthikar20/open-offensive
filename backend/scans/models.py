from __future__ import annotations

from django.conf import settings
from django.db import models


class Scan(models.Model):
    STATUS = (
        ("queued", "queued"),
        ("running", "running"),
        ("done", "done"),
        ("error", "error"),
    )
    MODE = (("llm", "llm"),)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="scans"
    )
    target = models.CharField(max_length=500, help_text="Repo URL, live URL/host, or a local dir.")
    mode = models.CharField(max_length=12, choices=MODE, default="llm")

    status = models.CharField(max_length=12, choices=STATUS, default="queued", db_index=True)
    engine_scan_id = models.CharField(max_length=64, blank=True)
    exit_code = models.IntegerField(null=True, blank=True)

    findings = models.JSONField(default=list, blank=True)
    summary = models.JSONField(default=dict, blank=True)
    report_md = models.TextField(blank=True)
    error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Scan #{self.pk} {self.target} [{self.status}]"

    @property
    def finding_count(self) -> int:
        return len(self.findings or [])
