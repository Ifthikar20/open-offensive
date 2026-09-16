from django.contrib import admin

from .models import Scan


@admin.register(Scan)
class ScanAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "target", "mode", "status", "exit_code",
                    "finding_count", "created_at", "finished_at")
    list_filter = ("status", "mode", "created_at")
    search_fields = ("target", "engine_scan_id", "owner__username")
    readonly_fields = (
        "owner", "engine_scan_id", "exit_code", "status",
        "findings", "summary", "report_md", "error",
        "created_at", "started_at", "finished_at",
    )

    @admin.display(description="findings")
    def finding_count(self, obj):
        return obj.finding_count
