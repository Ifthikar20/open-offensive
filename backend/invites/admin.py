from django.contrib import admin

from .models import AccessRequest, Invite


@admin.register(Invite)
class InviteAdmin(admin.ModelAdmin):
    list_display = ("code", "email", "used_by", "used_at", "expires_at", "created_at")
    list_filter = ("used_at", "expires_at", "created_at")
    search_fields = ("code", "email", "note")
    readonly_fields = ("used_by", "used_at", "created_at")


@admin.register(AccessRequest)
class AccessRequestAdmin(admin.ModelAdmin):
    list_display = ("email", "name", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("email", "name", "note")
    actions = ["mark_invited", "mark_declined"]

    @admin.action(description="Mark selected as invited")
    def mark_invited(self, request, queryset):
        queryset.update(status="invited")

    @admin.action(description="Mark selected as declined")
    def mark_declined(self, request, queryset):
        queryset.update(status="declined")
