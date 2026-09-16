"""Invite-only access: invite codes and public access requests (waitlist).

No real codes are stored in source — they are minted at runtime via the Django
admin or the ``makeinvite`` management command.
"""

from __future__ import annotations

import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


def _generate_code() -> str:
    """A short, URL-safe, unguessable invite code."""
    return secrets.token_urlsafe(9)


class Invite(models.Model):
    code = models.CharField(max_length=64, unique=True, default=_generate_code, db_index=True)
    email = models.EmailField(blank=True, help_text="Optional: restrict this code to one email.")
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="invites_created",
    )
    used_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="invites_used",
    )
    used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        state = "used" if self.used_by_id else ("expired" if self.is_expired else "open")
        return f"{self.code} ({state})"

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at < timezone.now())

    def is_valid_for(self, email: str = "") -> tuple[bool, str]:
        """(ok, reason) — whether this code may be redeemed now (optionally by ``email``)."""
        if self.used_by_id:
            return False, "This invite has already been used."
        if self.is_expired:
            return False, "This invite has expired."
        if self.email and email and self.email.lower() != email.lower():
            return False, "This invite is for a different email address."
        return True, ""

    def redeem(self, user) -> None:
        self.used_by = user
        self.used_at = timezone.now()
        self.save(update_fields=["used_by", "used_at"])


class AccessRequest(models.Model):
    """A 'Request access' submission from the landing page (waitlist)."""

    STATUS = (("pending", "pending"), ("invited", "invited"), ("declined", "declined"))

    email = models.EmailField()
    name = models.CharField(max_length=120, blank=True)
    note = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.email} ({self.status})"
