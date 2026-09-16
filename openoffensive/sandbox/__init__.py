"""Sandbox runtime — where an agent's tool calls actually execute.

Two real backends share one interface: :class:`DockerSandbox` (a Kali container
per scan — the default where a daemon is available) and
:class:`LocalSandbox` (tool calls run directly on the host — the fallback for
environments without usable Docker). Public surface: `docker_available()` to
preflight, `resolve_backend()` to pick, `open_sandbox()` to construct the per-scan
sandbox, and the `DockerSandbox` / `LocalSandbox` / `FakeSandbox` / `ExecResult`
types.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from .docker import DockerSandbox, Emit, ExecResult, SandboxError
from .fake import FakeSandbox
from .local import LocalSandbox

SANDBOX_DIR = Path(__file__).resolve().parent  # holds the Dockerfile

__all__ = [
    "DockerSandbox", "LocalSandbox", "FakeSandbox", "ExecResult", "SandboxError",
    "docker_available", "try_start_docker_daemon", "resolve_backend", "open_sandbox",
    "SANDBOX_DIR",
]


def docker_available() -> tuple[bool, str]:
    """(usable, reason) — whether a container can actually be started right now."""
    if shutil.which("docker") is None:
        return False, "the 'docker' CLI is not installed"
    try:
        cp = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=15)
    except Exception as e:  # noqa: BLE001
        return False, f"could not run docker: {e}"
    if cp.returncode != 0:
        return False, "the Docker daemon is not running or not reachable"
    return True, ""


def try_start_docker_daemon(emit: Emit = None, timeout: float = 30.0) -> tuple[bool, str]:
    """Best-effort: bring up a Docker daemon that isn't running.

    Tries a service manager first (``service`` / ``systemctl``), then launches
    ``dockerd`` directly when we have the privileges. Never raises; returns
    ``(up, message)``. It can only work where this process may actually start a
    daemon (root, or passwordless sudo / a service manager) — otherwise it reports
    why it couldn't, and the caller falls back to local execution.
    """
    import os
    import subprocess
    import time

    def _log(msg: str) -> None:
        if emit is not None:
            try:
                emit("system", msg)
            except Exception:  # noqa: BLE001
                pass

    if docker_available()[0]:
        return True, "already running"
    if shutil.which("docker") is None:
        return False, "the 'docker' CLI is not installed"

    def _wait(secs: float) -> bool:
        end = time.time() + secs
        while time.time() < end:
            if docker_available()[0]:
                return True
            time.sleep(0.5)
        return False

    is_root = hasattr(os, "geteuid") and os.geteuid() == 0
    sudo = [] if is_root else (["sudo", "-n"] if shutil.which("sudo") else None)

    # 1) a managed service, if a service manager is present and we can invoke it
    for svc in (["service", "docker", "start"], ["systemctl", "start", "docker"]):
        if shutil.which(svc[0]) is None or sudo is None:
            continue
        try:
            subprocess.run([*sudo, *svc], capture_output=True, timeout=20)
        except Exception:  # noqa: BLE001
            continue
        if _wait(min(timeout, 12)):
            _log(f"Docker daemon started via {svc[0]}")
            return True, f"started via {svc[0]}"

    # 2) launch dockerd directly (needs root)
    if shutil.which("dockerd") is not None and is_root:
        try:
            subprocess.Popen(["dockerd"], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        except Exception as e:  # noqa: BLE001
            return False, f"could not launch dockerd: {e}"
        if _wait(timeout):
            return True, "launched dockerd"
        return False, "dockerd was launched but did not become ready in time"

    if not is_root and sudo is None:
        return False, "insufficient privileges (need root or passwordless sudo)"
    return False, "no available method to start the Docker daemon"


def resolve_backend(settings: Any) -> str:
    """Return the concrete execution backend to use: "docker" or "local".

    "auto" (the default) picks Docker when a daemon is reachable, and otherwise
    falls back to local host execution so a scan can still run where Docker is
    unavailable (no daemon, a locked-down network that can't pull the image, CI).
    An explicit "docker" or "local" is honored as-is.
    """
    backend = (getattr(settings, "sandbox_backend", "auto") or "auto").lower()
    if backend in ("docker", "local"):
        return backend
    # "auto" (or anything unrecognized): prefer Docker, fall back to local.
    return "docker" if docker_available()[0] else "local"


def open_sandbox(scan_id: str, settings: Any, *, emit: Emit = None):
    """Construct (but do not start) the per-scan sandbox chosen by settings.

    Returns a :class:`DockerSandbox` or a :class:`LocalSandbox`; both share the
    same interface, so the runner and tools treat them identically.
    """
    if resolve_backend(settings) == "local":
        return LocalSandbox(scan_id, emit=emit)
    return DockerSandbox(
        scan_id,
        image=getattr(settings, "sandbox_image", "openoffensive-sandbox:kali"),
        network=(getattr(settings, "sandbox_network", "") or None),
        emit=emit,
    )
