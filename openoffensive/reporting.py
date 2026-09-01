"""Turn the findings store into a final report — the `finish_scan` moment."""

from __future__ import annotations

from .coordinator import Coordinator
from .models import SEVERITY_CVSS

_ORDER = ["critical", "high", "medium", "low", "info"]


def build_markdown(coord: Coordinator) -> str:
    findings = sorted(coord.findings, key=lambda f: -SEVERITY_CVSS.get(f.severity, 0))
    counts = coord.severity_counts()
    lines = [
        "# Penetration Test Report",
        "",
        f"**Target:** {coord.target}",
        f"**Findings:** {len(findings)}  "
        + "  ".join(f"{s}={counts[s]}" for s in _ORDER if counts[s]),
        f"**LLM turns (simulated):** {coord.turns}   **spend:** ${coord.cost:.2f}",
        "",
        "## Findings",
    ]
    for f in findings:
        lines += [
            "",
            f"### [{f.severity.upper()} · CVSS {f.cvss}] {f.title}",
            f"- **id:** {f.id}   **cwe:** {f.cwe or 'n/a'}   **by:** {f.agent}",
            f"- **endpoint:** `{f.endpoint}`",
            f"- **evidence:** {f.evidence}",
            f"- **poc:** `{f.poc}`" if f.poc else "",
            f"- **fix:** {f.remediation}",
        ]
    if not findings:
        lines.append("\n_No findings._")
    return "\n".join(l for l in lines if l is not None)


def summary(coord: Coordinator) -> dict:
    counts = coord.severity_counts()
    top = max((f for f in coord.findings), key=lambda f: f.cvss, default=None)
    return {
        "total": len(coord.findings),
        "counts": counts,
        "headline": (f"{top.severity.upper()} — {top.title}" if top else "no findings"),
    }
