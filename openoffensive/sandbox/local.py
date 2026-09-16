"""The local sandbox — run the agents' tool calls directly on the HOST.

This is the fallback for environments where Docker cannot be used: no daemon, a
locked-down egress policy that can't pull the Kali base image, CI runners without
docker-in-docker, and so on. It implements the exact same surface as
:class:`~openoffensive.sandbox.docker.DockerSandbox` (``ensure_image`` / ``start``
/ ``exec`` / ``add_repo`` / ``add_dir`` / ``read_file`` / ``close``) so the runner,
tools, and agents don't know the difference — a tool call is still a shell command
whose stdout/exit code come back as the next observation.

The important tradeoff: there is NO container isolation here. Commands run as the
host user in a per-scan temporary workspace directory. It is therefore opt-in
(``OPENOFFENSIVE_SANDBOX=local`` / ``--sandbox local``), Docker stays the default
where a daemon is available, and the existing scope guardrails still apply.

Only the tools already installed on the host are available. ``available_tools()``
reports which of the expected pentest toolset are present so the agents can probe
with what they actually have (curl/python) instead of leaning on a missing nmap.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from .docker import Emit, ExecResult, SandboxError

_DEFAULT_EXEC_TIMEOUT = 180

# The toolset the Kali sandbox image bundles; on the host, whichever are present.
EXPECTED_TOOLS = (
    "curl", "wget", "git", "jq", "python3", "nc",
    "nmap", "sqlmap", "nikto", "whatweb", "dirb", "gobuster", "wafw00f", "dig",
)


class LocalSandbox:
    """Host-execution sandbox: same interface as DockerSandbox, no container."""

    def __init__(self, scan_id: str, *, workspace: str | None = None,
                 emit: Emit = None) -> None:
        self.scan_id = scan_id
        self._emit = emit
        self._started = False
        # A dedicated per-scan workspace so a run can't scribble over the cwd, and
        # cleanup is a single rmtree. Created lazily on start().
        self._explicit_workspace = workspace
        self.workspace = workspace or ""

    # -- logging --------------------------------------------------------------
    def _log(self, level: str, msg: str) -> None:
        if self._emit is not None:
            try:
                self._emit(level, msg)
            except Exception:
                pass

    # -- image (no-ops: nothing to build for host execution) ------------------
    def image_exists(self) -> bool:
        return True

    def ensure_image(self, dockerfile_dir: Path | None = None) -> None:
        self._log("system", "local backend: no image to build — tools run on the host")

    # -- capability -----------------------------------------------------------
    def available_tools(self) -> list[str]:
        """Which of the expected pentest tools are actually on the host PATH."""
        return [t for t in EXPECTED_TOOLS if shutil.which(t) is not None]

    def missing_tools(self) -> list[str]:
        return [t for t in EXPECTED_TOOLS if shutil.which(t) is None]

    # -- lifecycle ------------------------------------------------------------
    def start(self) -> None:
        if not self.workspace:
            self.workspace = tempfile.mkdtemp(prefix=f"oo-{self.scan_id}-")
        else:
            Path(self.workspace).mkdir(parents=True, exist_ok=True)
        self._started = True
        present = self.available_tools()
        missing = self.missing_tools()
        self._log("system",
                  f"local sandbox ready at {self.workspace} — running tools on the "
                  "host (no container isolation)")
        self._log("system", "tools present: " + (", ".join(present) or "none"))
        if missing:
            self._log("system", "tools NOT installed here: " + ", ".join(missing))

    def exec(self, command: str, *, timeout: float = _DEFAULT_EXEC_TIMEOUT,
             workdir: str | None = None) -> ExecResult:
        wd = workdir or self.workspace or None
        try:
            # Non-login shell: on the host we already inherit a configured environment,
            # and a login shell would source profile files that print banners into the
            # tool output the agents parse.
            cp = subprocess.run(["sh", "-c", command], capture_output=True,
                                text=True, timeout=timeout, cwd=wd)
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
        dest = Path(self.workspace) / name
        src = Path(host_path)
        try:
            shutil.copytree(src, dest, dirs_exist_ok=True)
        except OSError as e:
            raise SandboxError(f"copying target source failed: {e}") from e
        return str(dest)

    def read_file(self, path: str) -> str:
        return self.exec(f"cat {shlex.quote(path)}").stdout

    def close(self) -> None:
        if self._started:
            # Only remove a workspace we created ourselves (a temp dir).
            if not self._explicit_workspace and self.workspace:
                shutil.rmtree(self.workspace, ignore_errors=True)
            self._started = False
            self._log("system", "local sandbox cleaned up")
