"""Render a completed scan as a professional vulnerability-assessment PDF.

This lives in the backend (not the stdlib-only engine): it reads the Scan row's
real findings + summary + metadata, renders one of several Django HTML templates,
and turns it into a PDF with WeasyPrint. It never fabricates data — a scan with no
findings produces a legitimate "no findings" report, and an unfinished or errored
scan is refused by the view (the real status/error is returned instead).
"""

from __future__ import annotations

from django.template.loader import render_to_string
from django.utils import timezone

_SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]

# Selectable report templates. Each is a full Django template under templates/reports/.
TEMPLATES = {
    "executive": "reports/executive.html",
    "technical": "reports/technical.html",
    "owasp": "reports/owasp.html",
}
DEFAULT_TEMPLATE = "technical"

TEMPLATE_TITLES = {
    "executive": "Executive Summary",
    "technical": "Technical Assessment Report",
    "owasp": "OWASP Top 10 Coverage Report",
}

# A compact CWE → OWASP Top 10 (2021) mapping for the compliance view. Findings
# whose CWE isn't mapped fall under "Uncategorized".
_OWASP_2021 = [
    ("A01:2021 – Broken Access Control",
     {"CWE-22", "CWE-200", "CWE-201", "CWE-284", "CWE-285", "CWE-538", "CWE-639",
      "CWE-862", "CWE-863"}),
    ("A02:2021 – Cryptographic Failures",
     {"CWE-259", "CWE-319", "CWE-321", "CWE-327", "CWE-331", "CWE-798"}),
    ("A03:2021 – Injection",
     {"CWE-77", "CWE-78", "CWE-79", "CWE-89", "CWE-90", "CWE-91", "CWE-94", "CWE-564"}),
    ("A04:2021 – Insecure Design", {"CWE-209", "CWE-256", "CWE-501", "CWE-522"}),
    ("A05:2021 – Security Misconfiguration",
     {"CWE-16", "CWE-611", "CWE-693", "CWE-1021"}),
    ("A06:2021 – Vulnerable and Outdated Components", {"CWE-937", "CWE-1104"}),
    ("A07:2021 – Identification and Authentication Failures",
     {"CWE-287", "CWE-306", "CWE-307", "CWE-384", "CWE-620"}),
    ("A08:2021 – Software and Data Integrity Failures",
     {"CWE-345", "CWE-502", "CWE-829"}),
    ("A09:2021 – Security Logging and Monitoring Failures",
     {"CWE-117", "CWE-223", "CWE-532", "CWE-778"}),
    ("A10:2021 – Server-Side Request Forgery (SSRF)", {"CWE-918"}),
]


def _owasp_category(cwe: str) -> str:
    cwe = (cwe or "").strip().upper()
    if cwe:
        for name, cwes in _OWASP_2021:
            if cwe in cwes:
                return name
    return "Uncategorized"


def _sorted_findings(findings: list[dict]) -> list[dict]:
    """Most severe first, then highest CVSS within a severity."""
    def key(f: dict):
        sev = (f.get("severity") or "info").lower()
        order = _SEVERITY_ORDER.index(sev) if sev in _SEVERITY_ORDER else len(_SEVERITY_ORDER)
        try:
            cvss = float(f.get("cvss") or 0)
        except (TypeError, ValueError):
            cvss = 0.0
        return (order, -cvss)
    return sorted(findings or [], key=key)


def build_context(scan, template: str) -> dict:
    findings = _sorted_findings(scan.findings or [])
    summary = scan.summary or {}
    raw_counts = summary.get("counts") or {}
    counts = {s: int(raw_counts.get(s, 0) or 0) for s in _SEVERITY_ORDER}
    total = summary.get("total", len(findings))

    # Group by OWASP category in Top-10 order, dropping empty categories.
    owasp_groups = []
    for name, _ in _OWASP_2021:
        group = [f for f in findings if _owasp_category(f.get("cwe")) == name]
        if group:
            owasp_groups.append({"name": name, "findings": group})
    uncategorized = [f for f in findings if _owasp_category(f.get("cwe")) == "Uncategorized"]
    if uncategorized:
        owasp_groups.append({"name": "Uncategorized", "findings": uncategorized})

    # A short, data-derived risk line — only ever the real counts, never invented.
    if total == 0:
        headline = "No findings were reported for this assessment."
    else:
        parts = [f"{counts[s]} {s}" for s in _SEVERITY_ORDER if counts[s]]
        noun = "finding" if total == 1 else "findings"
        headline = f"{total} {noun}: " + ", ".join(parts) + "."

    max_count = max(counts.values()) or 1
    severities = [
        {"key": s, "count": counts[s], "pct": round(100 * counts[s] / max_count)}
        for s in _SEVERITY_ORDER
    ]

    return {
        "scan": scan,
        "template": template,
        "report_title": TEMPLATE_TITLES.get(template, "Assessment Report"),
        "findings": findings,
        "counts": counts,
        "severities": severities,
        "severity_order": _SEVERITY_ORDER,
        "total": total,
        "top": findings[0] if findings else None,
        "headline": headline,
        "owasp_groups": owasp_groups,
        "generated_at": timezone.now(),
    }


def render_pdf(scan, template: str = DEFAULT_TEMPLATE) -> bytes:
    """Render ``scan`` to PDF bytes using the named template (falls back to the
    default for an unknown name). No network/remote resources are fetched."""
    template = template if template in TEMPLATES else DEFAULT_TEMPLATE
    html = render_to_string(TEMPLATES[template], build_context(scan, template))
    from weasyprint import HTML
    return HTML(string=html).write_pdf()
