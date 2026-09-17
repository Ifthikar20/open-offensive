"""Top-level URL routing for the OpenOffensive backend.

    /admin/       Django admin (mint invites, review access requests, inspect scans)
    /api/auth/    session auth: csrf, register (invite-gated), login, logout, me, request-access
    /api/         scans API (owner-scoped): list / create / retrieve / report
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/", include("scans.urls")),
]
