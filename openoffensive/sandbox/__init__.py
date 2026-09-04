"""Sandbox runtime — a real Docker container per scan (the Strix model).

Public surface: `docker_available()` to preflight, `open_sandbox()` to construct
the per-scan sandbox, and the `DockerSandbox` / `FakeSandbox` / `ExecResult`
types. Docker-only by design: if the daemon is missing, a run fails clearly.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from .docker import DockerSandbox, Emit, ExecResult, SandboxError
from .fake import FakeSandbox

SANDBOX_DIR = Path(__file__).resolve().parent  # holds the Dockerfile

__all__ = [
    "DockerSandbox", "FakeSandbox", "ExecResult", "SandboxError",
    "docker_available", "open_sandbox", "SANDBOX_DIR",
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


def open_sandbox(scan_id: str, settings: Any, *, emit: Emit = None) -> DockerSandbox:
    """Construct (but do not start) the per-scan Docker sandbox from settings."""
    return DockerSandbox(
        scan_id,
        image=getattr(settings, "sandbox_image", "openoffensive-sandbox:kali"),
        network=(getattr(settings, "sandbox_network", "") or None),
        emit=emit,
    )
