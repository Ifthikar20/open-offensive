"""An in-memory sandbox for tests — same interface as DockerSandbox, no Docker.

`exec()` answers from a rules map (substring of the command → (stdout, exit_code),
or a callable), else a default. Records every command in `.calls` so tests can
assert what the engine ran.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Union

from .docker import ExecResult

Rule = Union[tuple[str, int], Callable[[str], "tuple[str, int]"]]


class FakeSandbox:
    def __init__(self, responses: dict[str, Rule] | None = None,
                 default: tuple[str, int] = ("", 0), workspace: str = "/workspace") -> None:
        self.responses = responses or {}
        self.default = default
        self.workspace = workspace
        self.container = "oo-fake"
        self.calls: list[str] = []
        self.repos: list[tuple[str, str]] = []
        self.dirs: list[tuple[str, str]] = []
        self.started = False
        self.closed = False

    # no-ops for the docker-specific lifecycle
    def image_exists(self) -> bool:
        return True

    def ensure_image(self, dockerfile_dir: Path | None = None) -> None:
        return None

    def start(self) -> None:
        self.started = True

    def exec(self, command: str, *, timeout: float = 180, workdir: str | None = None) -> ExecResult:
        self.calls.append(command)
        for key, rule in self.responses.items():
            if key in command:
                out, code = rule(command) if callable(rule) else rule
                return ExecResult(command, out, "", code)
        out, code = self.default
        return ExecResult(command, out, "", code)

    def add_repo(self, url: str, name: str) -> str:
        self.repos.append((url, name))
        self.exec(f"git clone --depth 1 {url} {self.workspace}/{name}")
        return f"{self.workspace}/{name}"

    def add_dir(self, host_path: str, name: str) -> str:
        self.dirs.append((str(host_path), name))
        return f"{self.workspace}/{name}"

    def read_file(self, path: str) -> str:
        return self.exec(f"cat {path}").stdout

    def close(self) -> None:
        self.closed = True
