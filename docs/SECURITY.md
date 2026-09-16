# Security and authorized use

> **Authorized testing only.** OpenOffensive runs real pentest tools against whatever target
> it is pointed at. Only use it against systems you **own** or have **explicit, written
> permission** to test. Unauthorized scanning of computer systems is illegal in most
> jurisdictions. Out of the box it tests only its own bundled demo app; pointing it at a live
> host anywhere else is a deliberate, accountable act.

This page describes the safety model that backs that warning — the mechanisms in the code, not
just good intentions.

## The isolation model

OpenOffensive is, by design, an engine that runs **arbitrary shell commands** — the whole
point is to drive a real toolset (`nmap`, `curl`, `sqlmap`, `nikto`, `gobuster`, `grep`, …)
the way a human tester would. It contains that power in two ways: it runs those commands
**inside a single-use container**, and it constrains **what** they are aimed at.

### 1. Every command runs inside an isolated, throwaway container

Each scan gets its own Kali container (`openoffensive-sandbox:kali`), started fresh and
`docker rm -f`'d when the run ends (in a `finally`, so a crash still tears it down). The core
tool, `run_command`, executes each command with `docker exec` inside that container — never on
the host. The target's source is cloned or copied into `/workspace` **inside the container**,
so source review happens there too. The blast radius of anything the agent (or the model
driving it) does is that disposable container, not your machine.

This is the primary boundary. There is no host-side HTTP tool and no host allowlist in the
container model — isolation comes from the container itself.

### 2. Scope is set by the target and reinforced by the prompt

Each agent is given exactly one in-scope target and is told, in its system prompt, to test
**only** that target and its cloned source and to never attempt to reach any other host.
Findings must be confirmed from real command output before they are filed. This is guidance
enforced by instruction, not a network jail: a container with `NET_ADMIN`/`NET_RAW` can in
principle reach other hosts, so the operator remains responsible for pointing the tool at an
authorized target and for the network the container sits on (see
`OPENOFFENSIVE_SANDBOX_NETWORK` in [USAGE.md](USAGE.md) to attach it to a constrained network).

### 3. The `--authorized` gate (the human checkpoint)

The CLI refuses to scan a **non-local URL** target unless you pass `--authorized`:

```
$ openoffensive scan https://example.com
Refusing to scan a non-local target without authorization.
Only scan systems you own or have explicit written permission to test.
Re-run with --authorized once you have confirmed you are in scope.
```

The check runs *before* the container is started and exits `1`. "Local" means `127.0.0.1`,
`localhost`, `::1`, `host.docker.internal`, or any `*.localhost` host; everything else is
treated as a real system that requires you to affirm authorization. The gate applies to
**live-URL targets**: a git repo URL is cloned into the container and reviewed rather than
attacked over the network, so it is not gated. `--authorized` is not a bypass — it is you going
on record that you have permission for that target. Use it only when that is true.

### 4. The scripted methodology sends only benign probes

The default scripted methodology runs real commands, but they are deliberately
non-destructive — minimal, confirmatory signals, not exploits:

| Check | Command in the container | Why it is safe |
| --- | --- | --- |
| Recon | `curl -s -i <target>/`, `curl` static assets, `grep` the cloned source | Ordinary reads; greps the source/response for a leaked key. |
| SQL injection | `curl` a login parameter containing a single quote | Triggers (or doesn't) an error message; extracts nothing. |
| Reflected XSS | `curl` a uniquely marked, inert string in a query parameter | Checks whether it comes back un-encoded; runs no script. |
| IDOR | `curl` sequential ids `1`, `2`, `3` on an API path | Reads whether records return without auth; changes nothing. |
| Headers | Inspects response headers | Read-only. |

OpenOffensive does not weaponize findings, pivot, escalate, persist, or attempt
denial-of-service in scripted mode. In LLM mode the model chooses the commands within the same
tool set and the same in-scope instruction; the container boundary and the `--authorized` gate
apply either way.

## The bundled demo target

The default target is **Juice-Box** (`demo_target.py`) — a deliberately vulnerable demo app
that exists only so the agents always have something safe to test. It ships textbook,
intentional weaknesses: reflected XSS on `/search`, a leaked SQL error on `/login`, an IDOR on
`/api/user/<id>`, a hardcoded live-style secret in `/static/app.js`, missing security headers,
and a version-disclosing server banner.

Because the scan runs inside a container, the demo has to be reachable **from** that container.
So when you run `openoffensive scan` (no target) or `openoffensive serve`, OpenOffensive binds
Juice-Box to `0.0.0.0` on the host and points the scan at `http://host.docker.internal:<port>`
so the container can reach it.

> **Never deploy Juice-Box.** It is vulnerable **on purpose**, and during a scan it is bound to
> all interfaces on the host so the container can reach it. Run it only on a machine you trust
> and control, as a throwaway practice target — never on anything reachable from an untrusted
> network. It is a practice target, not a component you run anywhere reachable.

## Trusting the Docker daemon

OpenOffensive shells out to the `docker` CLI to build the image, run the container, `docker cp`
a directory in, and `docker exec` every command. That means:

- It requires access to a working Docker daemon, and it inherits whatever that daemon can do.
  Access to the Docker socket is effectively root on the host — grant it only where you would
  grant that trust.
- The first run builds from `kalilinux/kali-rolling` and installs the toolset over the network
  (apt). Build the image somewhere you trust the network, or pull a pre-built, pinned image via
  `OPENOFFENSIVE_SANDBOX_IMAGE`.
- The container is started with `--cap-add NET_ADMIN --cap-add NET_RAW` (so tools like `nmap`
  work) and `--add-host host.docker.internal:host-gateway` (so it can reach a service on the
  host). Keep that in mind when choosing the network the container runs on.

## Handling run artifacts

Findings capture **evidence from real command output**, which can include sensitive material —
the demo's leaked API tokens and secret key are the obvious case, and a real authorized target
could yield credentials, tokens, or PII in the evidence and PoC fields. That evidence is
written to disk under the runs directory (`run.json`, `findings.json`, `findings.sarif`,
`report.md`, `events.jsonl`).

- Treat `runs/` as potentially sensitive. It is git-ignored by default; keep it that way.
- Rotate or revoke any real secret a scan surfaces, exactly as a finding's remediation says
  (the demo's critical finding literally advises revoking the key).
- Be deliberate about where you upload SARIF and reports in CI.

## Responsible use, in short

- Point it only at systems you own or are contracted/authorized in writing to test.
- Run it only where you trust the Docker daemon and the network the sandbox container sits on.
- Reserve `--authorized` for live targets you truly have permission to test.
- Do not deploy the demo target, and remember it binds to `0.0.0.0` during a scan.
- Handle findings and artifacts as the sensitive security data they are.

## Reporting a vulnerability in OpenOffensive itself

If you find a security issue in OpenOffensive (as opposed to in a target it scans), report it
privately to the maintainers via the project's repository rather than opening a public issue
with exploit details.
