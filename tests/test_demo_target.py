"""The bundled demo target must actually be vulnerable.

These tests hit the real demo server over HTTP and assert each intentional
weakness is present, so the rest of the suite is testing findings against a
target that genuinely exhibits them.
"""

from __future__ import annotations

from conftest import http_get


def test_reflected_xss_is_reflected(demo_target):
    marker = "<script>xss_marker_9f2b()</script>"
    status, _headers, body = http_get(f"{demo_target}/search?q={marker}")
    assert status == 200
    # The q parameter is echoed back into the HTML body un-encoded.
    assert marker in body


def test_sql_error_leaks_on_a_quote(demo_target):
    status, _headers, body = http_get(f"{demo_target}/login?user=admin%27&pass=x")
    assert status == 500
    assert "SQL" in body


def test_login_without_quote_is_not_a_server_error(demo_target):
    # Sanity: the SQL error is triggered by the quote, not by /login in general.
    status, _headers, body = http_get(f"{demo_target}/login?user=admin&pass=x")
    assert status == 401
    assert "SQL" not in body


def test_idor_returns_api_token_for_each_user(demo_target):
    for uid in ("1", "2", "3"):
        status, _headers, body = http_get(f"{demo_target}/api/user/{uid}")
        assert status == 200, f"user {uid} should be readable without auth"
        assert "api_token" in body, f"user {uid} record should leak an api_token"


def test_idor_unknown_user_is_404(demo_target):
    status, _headers, _body = http_get(f"{demo_target}/api/user/9999")
    assert status == 404


def test_secret_key_leaked_in_static_bundle(demo_target):
    status, _headers, body = http_get(f"{demo_target}/static/app.js")
    assert status == 200
    assert "sk_live_" in body


def test_security_headers_absent_on_home(demo_target):
    status, headers, _body = http_get(f"{demo_target}/")
    assert status == 200
    for hardening in ("content-security-policy", "x-frame-options",
                      "x-content-type-options", "strict-transport-security"):
        assert hardening not in headers, f"{hardening} should be missing on the demo"


def test_server_banner_discloses_version(demo_target):
    # Recon relies on the Server header advertising a version.
    _status, headers, _body = http_get(f"{demo_target}/")
    assert "server" in headers
    assert headers["server"].startswith("JuiceBox/")
