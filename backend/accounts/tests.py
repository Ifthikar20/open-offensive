"""Tests for editable profile + change-password endpoints under /api/auth/."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class ProfileEditTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="alice", password="Old-Pass-123", email="alice@example.com")
        self.client.force_login(self.user)

    def test_me_returns_extended_fields(self):
        resp = self.client.get("/api/auth/me/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for k in ("id", "username", "email", "first_name", "last_name",
                  "is_staff", "date_joined"):
            self.assertIn(k, data)

    def test_patch_me_updates_email_and_name(self):
        resp = self.client.patch(
            "/api/auth/me/",
            {"email": "new@example.com", "first_name": "Alice", "last_name": "A"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["email"], "new@example.com")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")
        self.assertEqual(self.user.first_name, "Alice")

    def test_patch_me_rejects_bad_email(self):
        resp = self.client.patch(
            "/api/auth/me/", {"email": "not-an-email"}, content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_patch_me_ignores_readonly_username(self):
        resp = self.client.patch(
            "/api/auth/me/", {"username": "hacker"}, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "alice")   # username is read-only

    def test_me_requires_auth(self):
        self.client.logout()
        resp = self.client.get("/api/auth/me/")
        self.assertIn(resp.status_code, (401, 403))


class ChangePasswordTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="bob", password="Old-Pass-123")
        self.client.force_login(self.user)

    def _post(self, current, new):
        return self.client.post(
            "/api/auth/change-password/",
            {"current_password": current, "new_password": new},
            content_type="application/json",
        )

    def test_success_and_session_survives(self):
        resp = self._post("Old-Pass-123", "New-Pass-456!")
        self.assertEqual(resp.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("New-Pass-456!"))
        # update_session_auth_hash keeps the session valid — a later authed call works.
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)

    def test_wrong_current_password_rejected(self):
        resp = self._post("wrong-password", "New-Pass-456!")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("current_password", resp.json())
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Old-Pass-123"))   # unchanged

    def test_weak_new_password_rejected(self):
        resp = self._post("Old-Pass-123", "123")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("new_password", resp.json())

    def test_requires_auth(self):
        self.client.logout()
        resp = self._post("Old-Pass-123", "New-Pass-456!")
        self.assertIn(resp.status_code, (401, 403))
