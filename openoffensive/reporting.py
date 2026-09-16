"""Turn the findings store into deliverables: a markdown report, SARIF, and a
structured ScanResult record — the `finish_scan` moment."""

from __future__ import annotations

from typing import Any

from .coordinator import Coordinator
from .models import SEVERITY_CVSS, ScanResult, now

_ORDER = ["critical", "high", "medium", "low", "info"]
# SARIF severity levels: https://docs.oasis-open.org/sarif/sarif/v2.1.0
_SARIF_LEVEL = {"critical": "error", "high": "error", "medium": "warning",
                "low": "note", "info": "note"}


def build_markdown(coord: Coordinator) -> str:
    findings = sorted(coord.findings, key=lambda f: -SEVERITY_CVSS.get(f.severity, 0))
    counts = coord.severity_counts()
    lines = [
        "# OpenOffensive — Penetration Test Report",
        "",
        f"**Target:** {coord.target}",
        f"**Mode:** {coord.mode}",
        f"**Findings:** {len(findings)}  "
        + "  ".join(f"{s}={counts[s]}" for s in _ORDER if counts[s]),
        f"**Model turns:** {coord.turns}   **spend:** ${coord.cost:.2f}",
        "",
        "_Every finding carries the exact command run inside the sandbox container "
        "and the raw output it was drawn from — re-run the command in the same "
        "container to reproduce it. CVSS is a representative score mapped from "
        "severity, not a computed vector._",
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
            f"- **poc:** `{f.poc}`" if f.poc else "- **poc:** n/a",
            f"- **fix:** {f.remediation}",
        ]
        if f.command:
            lines.append(f"- **verified by running:** `{f.command}`")
        if f.output:
            lines += ["", "  Raw output this finding was drawn from:", "", "  ```",
                      *("  " + ln for ln in f.output.splitlines()), "  ```"]
    if not findings:
        lines.append("\n_No findings._")
    return "\n".join(lines)


def build_sarif(coord: Coordinator, version: str = "1.0.0") -> dict[str, Any]:
    rules: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    seen_rules: set[str] = set()
    for f in coord.findings:
        rule_id = f.cwe or f.title
        if rule_id not in seen_rules:
            seen_rules.add(rule_id)
            rules.append({
                "id": rule_id,
                "name": f.title.replace(" ", ""),
                "shortDescription": {"text": f.title},
                "properties": {"cwe": f.cwe, "security-severity": str(f.cvss)},
            })
        results.append({
            "ruleId": rule_id,
            "level": _SARIF_LEVEL.get(f.severity, "note"),
            "message": {"text": f"{f.title}: {f.evidence}"},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": f.endpoint.lstrip("/") or "/"},
                }
            }],
            "properties": {"severity": f.severity, "cvss": f.cvss,
                           "remediation": f.remediation, "agent": f.agent, "id": f.id,
                           "command": f.command, "output": f.output},
        })
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "OpenOffensive",
                "informationUri": "https://openoffensive.ai",
                "version": version,
                "rules": rules,
            }},
            "results": results,
        }],
    }


def summary(coord: Coordinator) -> dict[str, Any]:
    counts = coord.severity_counts()
    top = max((f for f in coord.findings), key=lambda f: f.cvss, default=None)
    return {
        "total": len(coord.findings),
        "counts": counts,
        "headline": (f"{top.severity.upper()} — {top.title}" if top else "no findings"),
    }


def to_result(coord: Coordinator, scan_id: str, status: str,
              started_at: float, finished_at: float | None = None) -> ScanResult:
    return ScanResult(
        scan_id=scan_id,
        target=coord.target,
        mode=coord.mode,
        status=status,
        findings=[f.to_dict() for f in coord.findings],
        counts=coord.severity_counts(),
        turns=coord.turns,
        cost=round(coord.cost, 4),
        started_at=started_at,
        finished_at=finished_at if finished_at is not None else now(),
        report_md=build_markdown(coord),
    )
