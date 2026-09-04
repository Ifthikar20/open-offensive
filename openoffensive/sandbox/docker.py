"""The Docker sandbox — one Kali container per scan, driven via the `docker` CLI.

This is the piece that makes OpenOffensive behave like Strix: a real, isolated
container with a pentest toolset, into which the target's source is cloned, and
inside which every agent tool call runs (`docker exec`). We shell out to the
`docker` CLI rather than take a docker-py dependency, so the package stays
dependency-free.

Lifecycle: ``ensure_image()`` (build or pull) → ``start()`` (run a keep-alive
container) → ``add_repo()`` / ``add_dir()`` (get the target in) → ``exec()`` (run
tools) → ``close()`` (remove the container).
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

_BUILD_TIMEOUT = 1800   # image build/pull can be slow (multi-GB Kali base)
_START_TIMEOUT = 120
_DEFAULT_EXEC_TIMEOUT = 180

# Emit callback: (level, message) — lets the runtime stream build/exec progress
# into the live log without the sandbox knowing about the coordinator.
Emit = Optional[Callable[[str, str], None]]


class SandboxError(RuntimeError):
    """A container operation (build/pull/run/exec/clone) failed."""


@dataclass
class ExecResult:
    command: str
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def combined(self, limit: int = 6000) -> str:
        """stdout + stderr, trimmed — what an agent sees back from a tool call."""
        parts = []
        if self.stdout:
            parts.append(self.stdout)
        if self.stderr.strip():
            parts.append("[stderr]\n" + self.stderr)
        text = "\n".join(parts) if parts else "(no output)"
        if self.timed_out:
            text = f"[timed out after the command budget]\n{text}"
        if len(text) > limit:
            text = text[:limit] + f"\n… (truncated, {len(text) - limit} more bytes)"
        return text


class DockerSandbox:
    def __init__(self, scan_id: str, *, image: str, network: str | None = None,
                 workspace: str = "/workspace", emit: Emit = None) -> None:
        self.scan_id = scan_id
        self.image = image
        self.network = network
        self.workspace = workspace
        self.container = f"oo-{scan_id}"
        self._emit = emit
        self._started = False

    # -- low-level docker CLI -------------------------------------------------
    def _docker(self, args: list[str], *, timeout: float | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)

    def _log(self, level: str, msg: str) -> None:
        if self._emit is not None:
            try:
                self._emit(level, msg)
            except Exception:
                pass

    # -- image ----------------------------------------------------------------
    def image_exists(self) -> bool:
        return self._docker(["image", "inspect", self.image]).returncode == 0

    def ensure_image(self, dockerfile_dir: Path | None = None) -> None:
        """Make the image available: build our bundled Dockerfile for the default
        local tag, or pull an overridden remote tag."""
        if self.image_exists():
            self._log("system", f"sandbox image present: {self.image}")
            return
        is_local = self.image.startswith("openoffensive-sandbox") and dockerfile_dir is not None
        if is_local:
            self._log("system", f"building sandbox image {self.image} (first run — pulls Kali, slow)…")
            cp = self._docker(
                ["build", "-t", self.image, "-f", str(dockerfile_dir / "Dockerfile"),
                 str(dockerfile_dir)],
                timeout=_BUILD_TIMEOUT,
            )
            if cp.returncode != 0:
                raise SandboxError(f"image build failed:\n{cp.stderr[-800:]}")
            self._log("system", "sandbox image built")
        else:
            self._log("system", f"pulling sandbox image {self.image}…")
            cp = self._docker(["pull", self.image], timeout=_BUILD_TIMEOUT)
            if cp.returncode != 0:
                raise SandboxError(f"image pull failed:\n{cp.stderr[-800:]}")
            self._log("system", "sandbox image pulled")

    # -- lifecycle ------------------------------------------------------------
    def start(self) -> None:
        # Remove any stale container from a crashed prior run with this id.
        self._docker(["rm", "-f", self.container])
        args = ["run", "-d", "--name", self.container,
                "--add-host", "host.docker.internal:host-gateway",
                "--cap-add", "NET_ADMIN", "--cap-add", "NET_RAW"]
        if self.network:
            args += ["--network", self.network]
        args += [self.image, "tail", "-f", "/dev/null"]
        cp = self._docker(args, timeout=_START_TIMEOUT)
        if cp.returncode != 0:
            raise SandboxError(f"container start failed:\n{cp.stderr[-800:]}")
        self._started = True
        self.exec(f"mkdir -p {shlex.quote(self.workspace)}", timeout=30)
        self._log("system", f"sandbox container up: {self.container}")

    def exec(self, command: str, *, timeout: float = _DEFAULT_EXEC_TIMEOUT,
             workdir: str | None = None) -> ExecResult:
        wd = workdir or self.workspace
        try:
            cp = self._docker(["exec", "-w", wd, self.container, "sh", "-lc", command],
                              timeout=timeout)
            return ExecResult(command, cp.stdout, cp.stderr, cp.returncode)
        except subprocess.TimeoutExpired as e:
            out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            err = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
            return ExecResult(command, out, err, 124, timed_out=True)

    # -- getting the target in ------------------------------------------------
    def add_repo(self, url: str, name: str) -> str:
        dest = f"{self.workspace}/{name}"
        self._log("system", f"cloning {url} → {dest}")
        r = self.exec(f"git clone --depth 1 {shlex.quote(url)} {shlex.quote(dest)}", timeout=600)
        if not r.ok:
            raise SandboxError(f"git clone failed:\n{(r.stderr or r.stdout)[-800:]}")
        return dest

    def add_dir(self, host_path: str | Path, name: str) -> str:
        dest = f"{self.workspace}/{name}"
        self.exec(f"mkdir -p {shlex.quote(dest)}", timeout=30)
        cp = self._docker(["cp", f"{Path(host_path)}/.", f"{self.container}:{dest}"], timeout=300)
        if cp.returncode != 0:
            raise SandboxError(f"docker cp failed:\n{cp.stderr[-800:]}")
        return dest

    def read_file(self, path: str) -> str:
        return self.exec(f"cat {shlex.quote(path)}").stdout

    def close(self) -> None:
        if self._started:
            self._docker(["rm", "-f", self.container], timeout=60)
            self._started = False
            self._log("system", f"sandbox container removed: {self.container}")
