# Security and authorized use

> **Authorized testing only.** OpenOffensive sends real HTTP requests to whatever target
> it is pointed at. Only use it against systems you **own** or have **explicit, written
> permission** to test. Unauthorized scanning of computer systems is illegal in most
> jurisdictions. Out of the box it tests only its own bundled demo app on localhost;
> pointing it anywhere else is a deliberate, accountable act.

This page describes the safety model that backs that warning — the mechanisms in the
code, not just good intentions.

## The layers of scope control

### 1. The host allowlist (the real enforcement)

Every HTTP request goes through `ToolContext` in `tools.py`, which is constructed with
an **allowlist**:

```
allowed_hosts = { host(target) } ∪ OPENOFFENSIVE_SCOPE
```

Before any request is sent, the destination host is checked against that set. A request
to any host not on it is **blocked, logged as a failed tool call, and never leaves the
process** — the handler returns `"blocked: host … is out of scope"`. The agents
therefore cannot reach anything but the scan target, plus any hosts an operator has
*explicitly* added via `OPENOFFENSIVE_SCOPE` (a comma-separated list) because they are
in scope for an authorized engagement.

This is defense in depth: in LLM mode the system prompt also instructs the model to test
only the target and never reach another host, but the allowlist enforces it regardless
of what the model attempts. Prompt text is guidance; the allowlist is the boundary.

### 2. The `--authorized` gate (the human checkpoint)

The CLI refuses to scan a **non-loopback** target unless you pass `--authorized`:

```
$ openoffensive scan https://example.com
Refusing to scan a non-loopback target without authorization.
Only scan systems you own or have explicit written permission to test.
Re-run with --authorized once you have confirmed you are in scope.
```

The check runs *before* any request is sent and exits `1`. "Loopback" means
`127.0.0.1`, `localhost`, `::1`, or any `*.localhost` host; everything else is treated as
a real system that requires you to affirm authorization. `--authorized` is not a
bypass — it is you going on record that you have permission for that target. Use it
only when that is true.

### 3. Scripted mode sends only benign probes

The default scripted methodology is deliberately non-destructive. Its "attacks" are
minimal, confirmatory signals, not exploits:

| Check | Probe | Why it is safe |
| --- | --- | --- |
| Recon | `GET /`, `/robots.txt`, `/static/app.js` | Ordinary reads; greps responses locally for a leaked key. |
| SQL injection | A single quote in a login parameter | Triggers (or doesn't) an error message; extracts nothing. |
| Reflected XSS | A uniquely marked, inert string in a query parameter | Checks whether it comes back un-encoded; runs no script. |
| IDOR | Fetches sequential IDs `1`, `2`, `3` on an API path | Reads whether records return without auth; changes nothing. |
| Headers | Inspects response headers | Read-only. |

OpenOffensive does not weaponize findings, pivot, escalate, persist, or attempt
denial-of-service. It probes, observes, and reports.

## The bundled demo target

The default target is **Juice-Box** (`demo_target.py`) — a deliberately vulnerable demo
app that exists only so the agents always have something safe and local to test. It
ships textbook, intentional weaknesses: reflected XSS on `/search`, a leaked SQL error on
`/login`, an IDOR on `/api/user/<id>`, a hardcoded live-style secret in
`/static/app.js`, missing security headers, and a version-disclosing server banner.

> **Never deploy Juice-Box.** It binds to `127.0.0.1` only and is vulnerable **on
> purpose**. It is a practice target, not a component you run anywhere reachable.

When you run the dashboard, it starts Juice-Box on a random localhost port and points the
agents at it; no external hosts are contacted.

## Handling run artifacts

Findings capture **evidence from real responses**, which can include sensitive material —
the demo's leaked API tokens and secret key are the obvious case, and a real authorized
target could yield credentials, tokens, or PII in the evidence and PoC fields. That
evidence is written to disk under the runs directory (`run.json`, `findings.json`,
`findings.sarif`, `report.md`, `events.jsonl`).

- Treat `runs/` as potentially sensitive. It is git-ignored by default; keep it that way.
- Rotate or revoke any real secret a scan surfaces, exactly as a finding's remediation
  says (the demo's critical finding literally advises revoking the key).
- Be deliberate about where you upload SARIF and reports in CI.

## Responsible use, in short

- Point it only at systems you own or are contracted/authorized in writing to test.
- Keep scope tight: rely on the target host allowlist, and widen it with
  `OPENOFFENSIVE_SCOPE` only for hosts genuinely in scope.
- Reserve `--authorized` for targets you truly have permission to test.
- Do not deploy the demo target.
- Handle findings and artifacts as the sensitive security data they are.

## Reporting a vulnerability in OpenOffensive itself

If you find a security issue in OpenOffensive (as opposed to in a target it scans),
report it privately to the maintainers via the project's repository rather than opening a
public issue with exploit details.
