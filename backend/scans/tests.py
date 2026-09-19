"""Tests for the scans API — focused on the PDF report export endpoint.

Runs against an isolated test database (``manage.py test``). No engine, Docker,
network, or model key is involved: a Scan row is created directly with real-shaped
finding data, and the endpoint is exercised through Django's test client.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Scan

_FINDINGS = [
    {"id": "VULN-0001", "title": "Hardcoded live secret key", "severity": "critical",
     "cvss": 9.4, "cwe": "CWE-798", "target": "https://staging.acme.com",
     "endpoint": "/static/app.js", "agent": "Recon Scout",
     "evidence": "Client JS embeds a live sk_live_ key.",
     "command": "curl -s https://staging.acme.com/static/app.js",
     "output": 'const CONFIG={stripeKey:"sk_live_...LEAKED"};',
     "poc": "curl -s $TARGET/static/app.js | grep sk_live_",
     "remediation": "Revoke the key; move secrets server-side."},
    {"id": "VULN-0002", "title": "Error-based SQL injection", "severity": "high",
     "cvss": 7.8, "cwe": "CWE-89", "target": "https://staging.acme.com",
     "endpoint": "/login", "agent": "Injection Hunter",
     "evidence": "A single quote triggers a raw SQL error.",
     "command": 'curl -s "https://staging.acme.com/login?user=admin%27"',
     "output": "SQLite3::SQLException", "poc": "",
     "remediation": "Use parameterised queries."},
]
_SUMMARY = {"counts": {"critical": 1, "high": 1, "medium": 0, "low": 0, "info": 0},
            "total": 2, "top_severity": "critical", "duration": 12.0}


class ReportPdfTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="alice", password="pw-not-secret")
        self.other = User.objects.create_user(username="bob", password="pw-not-secret")
        self.done = Scan.objects.create(
            owner=self.user, target="https://staging.acme.com", mode="llm",
            status="done", engine_scan_id="scan-abc123",
            findings=_FINDINGS, summary=_SUMMARY,
        )
        self.errored = Scan.objects.create(
            owner=self.user, target="https://staging.acme.com", mode="llm",
            status="error", error="the model is unreachable — ANTHROPIC_API_KEY is not set",
        )

    def _url(self, scan, template="technical"):
        return f"/api/scans/{scan.id}/report_pdf/?template={template}"

    def test_requires_authentication(self):
        resp = self.client.get(self._url(self.done))
        self.assertIn(resp.status_code, (401, 403))

    def test_done_scan_returns_pdf_for_each_template(self):
        self.client.force_login(self.user)
        for template in ("technical", "executive", "owasp"):
            resp = self.client.get(self._url(self.done, template))
            self.assertEqual(resp.status_code, 200, template)
            self.assertEqual(resp["Content-Type"], "application/pdf")
            body = b"".join(resp.streaming_content) if resp.streaming else resp.content
            self.assertTrue(body.startswith(b"%PDF-"), template)
            self.assertIn(f"report-{self.done.id}-{template}.pdf", resp["Content-Disposition"])

    def test_unknown_template_falls_back_to_default(self):
        self.client.force_login(self.user)
        resp = self.client.get(self._url(self.done, "bogus"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_errored_scan_returns_409_with_real_error(self):
        self.client.force_login(self.user)
        resp = self.client.get(self._url(self.errored))
        self.assertEqual(resp.status_code, 409)
        data = json.loads(resp.content)
        self.assertEqual(data["status"], "error")
        self.assertIn("ANTHROPIC_API_KEY", data["error"])   # the real error, not a fake report

    def test_owner_scoped_no_cross_user_access(self):
        self.client.force_login(self.other)
        resp = self.client.get(self._url(self.done))
        self.assertEqual(resp.status_code, 404)


class ListSerializerTests(TestCase):
    def test_list_row_exposes_error(self):
        User = get_user_model()
        user = User.objects.create_user(username="carol", password="pw-not-secret")
        Scan.objects.create(owner=user, target="https://x", mode="llm",
                            status="error", error="boom")
        self.client.force_login(user)
        resp = self.client.get("/api/scans/")
        self.assertEqual(resp.status_code, 200)
        row = resp.json()[0]
        self.assertEqual(row["error"], "boom")   # a failed scan reads as failed in the list

    def test_create_requires_target(self):
        User = get_user_model()
        user = User.objects.create_user(username="dave", password="pw-not-secret")
        self.client.force_login(user)
        resp = self.client.post("/api/scans/", {"target": "   "}, content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("target", resp.json())
