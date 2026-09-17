"""Top-level scan runner — spins the sandbox, acquires the target, runs the agents."""

from __future__ import annotations

import json
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
from .sandbox import (SANDBOX_DIR, LocalSandbox, SandboxError, docker_available,
                       open_sandbox, resolve_backend, try_start_docker_daemon)

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


def _open_event_log(store: RunStore, scan_id: str):
    """Open a per-scan events.jsonl for live appending. Best-effort: returns None
    if the file can't be opened, so streaming never blocks a scan."""
    try:
        d = store.dir_for(scan_id)
        d.mkdir(parents=True, exist_ok=True)
        return open(d / "events.jsonl", "a", encoding="utf-8")
    except Exception:
        return None


def _append_event(fh, ev) -> None:
    try:
        fh.write(json.dumps(ev.to_dict()) + "\n")
        fh.flush()
    except Exception:
        pass


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

    # Stream events to disk as they're emitted so an out-of-process reader (the
    # web backend) can tail the live log while the scan is still running.
    _event_log = _open_event_log(store, scan_id)
    if _event_log is not None:
        coord.on_event = lambda ev: _append_event(_event_log, ev)

    created_sandbox = sandbox is None
    mode, note = resolve_mode(settings)
    coord.mode = mode
    coord.status = "running"
    coord.started_at = time.time()
    backend = (settings.sandbox_backend or "auto") if created_sandbox else "injected"
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
            desired = (settings.sandbox_backend or "auto").lower()
            if desired not in ("docker", "local"):
                desired = "auto"

            # If Docker is wanted (explicitly or via auto) but the daemon is down,
            # optionally try to start it before deciding the backend.
            if (desired in ("docker", "auto") and settings.docker_autostart
                    and not docker_available()[0]):
                coord.emit("system", None, "Docker daemon not running — attempting to start it…")
                started, why = try_start_docker_daemon(emit=_emit)
                coord.emit("system", None,
                           "Docker daemon is up" if started
                           else f"could not start the Docker daemon: {why}")

            resolved = resolve_backend(settings)   # reflects a just-started daemon
            if resolved == "docker":
                ok, reason = docker_available()
                if not ok:
                    raise SandboxError(
                        f"Docker is required to run a scan but is unavailable: {reason}. "
                        "Start the Docker daemon (see `openoffensive doctor`), or set "
                        "OPENOFFENSIVE_SANDBOX=local to run the tools on the host.")
                sandbox = open_sandbox(scan_id, settings, emit=_emit)
                try:
                    sandbox.ensure_image(dockerfile_dir=SANDBOX_DIR)
                    sandbox.start()
                except SandboxError as e:
                    if desired != "auto":
                        raise
                    # auto: the daemon is up but the image/container cannot be made
                    # available here (e.g. the image can't be pulled or built) — fall
                    # back to host execution rather than failing the scan.
                    coord.emit("system", None,
                               f"Docker image/container unavailable ({e}); falling back to "
                               "local host execution (no container isolation)")
                    try:
                        sandbox.close()
                    except Exception:  # noqa: BLE001
                        pass
                    sandbox = LocalSandbox(scan_id, emit=_emit)
                    sandbox.start()
            else:
                coord.emit("system", None,
                           "running tools on the host (local sandbox — no container "
                           "isolation); set OPENOFFENSIVE_SANDBOX=docker to require a container")
                sandbox = open_sandbox(scan_id, settings, emit=_emit)
                sandbox.ensure_image(dockerfile_dir=SANDBOX_DIR)
                sandbox.start()
        else:
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

    # Stop live-streaming before the authoritative artifacts are written.
    coord.on_event = None
    if _event_log is not None:
        try:
            _event_log.close()
        except Exception:
            pass

    try:
        store.save(coord, result)
        coord.emit("system", None, f"artifacts written to {store.dir_for(scan_id)}")
    except Exception as e:  # noqa: BLE001
        coord.emit("error", None, f"could not persist run: {e}")

    coord.emit("system", None,
               f"scan complete in {result.duration:.1f}s · {coord.turns} turns · ${coord.cost:.2f}")
    return result
