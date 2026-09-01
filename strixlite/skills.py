"""Skills — pentesting know-how as data, loaded on demand.

In real Strix a skill is a Markdown knowledge pack injected into the agent's
prompt (a catalog is advertised, and the agent pulls the full text with a
`load_skill` tool). Here we keep the same shape at POC scale: a catalog of short
playbooks an agent 'loads' before it starts a specialised workflow, so the live
log shows the knowledge step that precedes the tool calls.
"""

from __future__ import annotations

# name -> (one-line catalog description, playbook body)
CATALOG: dict[str, tuple[str, str]] = {
    "reconnaissance": (
        "Map the attack surface before probing",
        "Enumerate endpoints and static assets, read robots.txt, fingerprint the "
        "server banner, and grep responses for leaked secrets/keys.",
    ),
    "security_headers": (
        "Check for missing hardening response headers",
        "Look for Content-Security-Policy, X-Frame-Options, X-Content-Type-Options, "
        "Strict-Transport-Security. Absence is a low-severity hardening gap.",
    ),
    "sql_injection": (
        "Union/blind/error-based SQLi",
        "Inject a single quote and watch for a raw DB error in the response — an "
        "error-based oracle confirms the input reaches a SQL string unsanitised.",
    ),
    "xss": (
        "Reflected / stored / DOM XSS",
        "Send a uniquely-marked script payload in each parameter; if it comes back "
        "un-encoded inside the HTML body, script executes in the victim's browser.",
    ),
    "idor": (
        "Broken object-level authorization (IDOR/BOLA)",
        "Walk sequential object ids on an API and check whether records you should "
        "not own are returned without an ownership or auth check.",
    ),
    "severity_calibration": (
        "Rank findings honestly by real impact",
        "Weigh confidentiality/integrity/availability and exploitability; do not "
        "inflate. A leaked live credential is critical; a missing header is low.",
    ),
}


def describe_catalog() -> list[dict[str, str]]:
    return [{"name": n, "description": d} for n, (d, _) in CATALOG.items()]


def load(name: str) -> str:
    """Return a skill's playbook body, or '' if unknown."""
    entry = CATALOG.get(name)
    return entry[1] if entry else ""
