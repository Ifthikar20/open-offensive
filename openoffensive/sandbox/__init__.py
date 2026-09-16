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
    "docker_available", "resolve_backend", "open_sandbox", "SANDBOX_DIR",
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
