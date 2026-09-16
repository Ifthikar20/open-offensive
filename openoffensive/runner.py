"""Top-level scan runner — spins the sandbox, acquires the target, runs the agents."""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, Optional
from urllib.parse import urlparse

from . import reporting
from .agents import RootAgent
from .config import Settings, load_settings
from .coordinator import Coordinator
from .llm import llm_available, preflight_model
from .models import ScanResult
from .persistence import RunStore
from .sandbox import (SANDBOX_DIR, SandboxError, docker_available, open_sandbox,
                       resolve_backend)

_REPO_HOSTS = ("github.com", "gitlab.com", "bitbucket.org")


class PreflightError(RuntimeError):
    """The model is unreachable, so LLM-mode agents can't run — fail before the
    container is built rather than after three opaque per-agent crashes."""


def _first_crash_reason(coord: Coordinator) -> str:
    """The reason from the first agent-crash event, e.g. 'Connection error.'."""
    for ev in coord.events:
        if ev.level == "error" and ev.message.startswith("crashed:"):
            return ev.message[len("crashed:"):].strip()
    return ""


def _failed_from_crashes(coord: Coordinator) -> tuple[bool, str]:
    """True (+reason) when every specialist that ran crashed and nothing was found —
    a failed run that would otherwise masquerade as a clean 0-finding scan."""
    crashed = coord.crashed_agents()
    if crashed and not coord.findings:
        return True, _first_crash_reason(coord) or "all agents stopped after errors"
    return False, ""


def resolve_mode(settings: Settings) -> tuple[str, str]:
    """Return (mode, note). LLM is the operating mode unless scripted is explicitly
    requested (``--mode scripted`` / ``OPENOFFENSIVE_LLM_MODE=scripted``). In every
    other case the mode is "llm"; if a key or the SDK is missing, or the model is
    unreachable, the scan fails LOUDLY at preflight rather than silently degrading
    to a scripted playbook."""
    if settings.llm_mode == "scripted":
        return "scripted", ""
    return "llm", ""


def classify_target(target: str) -> str:
    """'dir' (local source), 'repo' (git URL), or 'url' (live app to probe)."""
    if os.path.isdir(target):
        return "dir"
    t = target.strip()
    low = t.lower()
    if low.endswith(".git") or low.startswith("git@"):
        return "repo"
    parsed = urlparse(t if "//" in t else "https://" + t)
    if (parsed.hostname or "") in _REPO_HOSTS and parsed.path.strip("/").count("/") >= 1:
        return "repo"
    return "url"


def _repo_url_and_name(target: str) -> tuple[str, str]:
    t = target.strip()
    if not ("//" in t or t.startswith("git@")):
        t = "https://" + t
    name = t.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return t, (name or "repo")


def run_scan(coord: Coordinator, *, settings: Optional[Settings] = None,
             scan_id: Optional[str] = None, store: Optional[RunStore] = None,
             sandbox: Optional[Any] = None) -> ScanResult:
    """Run one scan to completion. Blocks; intended to be called in a thread.

    ``sandbox`` may be injected (a FakeSandbox in tests); otherwise a real Docker
    sandbox is created, which requires a running daemon.
    """
    settings = settings or load_settings()
    scan_id = scan_id or f"scan-{uuid.uuid4().hex[:8]}"
    store = store if store is not None else RunStore(settings.runs_dir)

    created_sandbox = sandbox is None
    mode, note = resolve_mode(settings)
    coord.mode = mode
    coord.status = "running"
    coord.started_at = time.time()
    backend = resolve_backend(settings) if created_sandbox else "injected"
    coord.emit("system", None,
               f"scan started against {coord.target}  [mode: {mode} · sandbox: {backend}]")
    if note:
        coord.emit("system", None, note)
    if mode == "llm":
        coord.emit("system", None, f"agents reasoning with model {settings.model}")

    status = "done"

    def _emit(level: str, msg: str) -> None:
        coord.emit(level, None, msg)

    try:
        # In LLM mode the agents call the model from the host on their first step;
        # verify it's reachable now, before spending time building the container.
        if mode == "llm":
            ok, msg = preflight_model(settings)
            if not ok:
                raise PreflightError(
                    "the model is unreachable, so the agents can't reason — "
                    f"{msg}. Set ANTHROPIC_API_KEY (and `pip install 'openoffensive[llm]'`) "
                    "and run `openoffensive doctor`, or pass --mode scripted to run the "
                    "no-key demo playbook.")
        if created_sandbox:
            if backend == "docker":
                ok, reason = docker_available()
                if not ok:
                    raise SandboxError(
                        f"Docker is required to run a scan but is unavailable: {reason}. "
                        "Start the Docker daemon (see `openoffensive doctor`), or set "
                        "OPENOFFENSIVE_SANDBOX=local to run the tools on the host.")
            else:
                coord.emit("system", None,
                           "running tools on the host (local sandbox — no container "
                           "isolation); set OPENOFFENSIVE_SANDBOX=docker to require a container")
            sandbox = open_sandbox(scan_id, settings, emit=_emit)
        sandbox.ensure_image(dockerfile_dir=SANDBOX_DIR)
        sandbox.start()

        workspace_path = None
        kind = classify_target(coord.target)
        if kind == "repo":
            url, name = _repo_url_and_name(coord.target)
            workspace_path = sandbox.add_repo(url, name)
            coord.emit("system", None, f"cloned target source → {workspace_path}")
        elif kind == "dir":
            name = os.path.basename(os.path.abspath(coord.target)) or "src"
            workspace_path = sandbox.add_dir(coord.target, name)
            coord.emit("system", None, f"copied target source → {workspace_path}")

        RootAgent(coord, settings, sandbox, coord.target, workspace_path).run()

        # A run where every specialist crashed and nothing was found is a failure,
        # not a clean scan — surface it so status/exit code reflect reality.
        failed, reason = _failed_from_crashes(coord)
        if failed:
            status = "error"
            coord.emit("error", None, f"no findings — every specialist crashed: {reason}")
    except Exception as e:  # noqa: BLE001
        status = "error"
        coord.emit("error", None, f"scan error: {e}")
    finally:
        if created_sandbox and sandbox is not None:
            try:
                sandbox.close()
            except Exception:  # noqa: BLE001
                pass

    result = reporting.to_result(coord, scan_id, status, coord.started_at)
    summ = reporting.summary(coord)
    coord.emit("report", None,
               f"finish_scan — {summ['total']} findings (top: {summ['headline']})",
               markdown=result.report_md, summary=summ)

    coord.status = status
    coord.finished_at = time.time()

    try:
        store.save(coord, result)
        coord.emit("system", None, f"artifacts written to {store.dir_for(scan_id)}")
    except Exception as e:  # noqa: BLE001
        coord.emit("error", None, f"could not persist run: {e}")

    coord.emit("system", None,
               f"scan complete in {result.duration:.1f}s · {coord.turns} turns · ${coord.cost:.2f}")
    return result
