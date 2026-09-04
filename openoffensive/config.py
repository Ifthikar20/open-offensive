"""Runtime configuration, resolved from environment variables.

Everything is optional: with no configuration at all, OpenOffensive runs in
scripted mode against its bundled demo target. Set ``ANTHROPIC_API_KEY`` (and
install the ``llm`` extra) to let the agents reason with a real model.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_bool(name: str, default: bool) -> bool:
    val = _env(name).lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name) or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name) or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # --- dashboard / server ---
    host: str = "127.0.0.1"
    port: int = 8777

    # --- LLM brain (optional) ---
    # mode: "auto" (LLM when a key is available, else scripted), "llm", or "scripted".
    llm_mode: str = "auto"
    model: str = "claude-opus-5"
    max_tokens: int = 4096
    max_steps: int = 24          # per-agent tool-call budget in LLM mode
    api_key_present: bool = False

    # --- sandbox (Docker) ---
    sandbox_image: str = "openoffensive-sandbox:kali"
    sandbox_network: str = ""     # empty = docker default bridge

    # --- run persistence ---
    runs_dir: str = "runs"

    # --- scope / safety ---
    # Extra hostnames the tool layer is allowed to reach, beyond the scan target.
    # The bundled demo target is always allowed; this only widens scope when a
    # user deliberately points the app at something they are authorized to test.
    scope_allow: tuple[str, ...] = field(default_factory=tuple)

    # --- pacing (scripted mode) ---
    # Multiplier on the small sleeps that make the live log readable. 0 = instant
    # (used by tests); 1.0 = human-watchable default.
    speed: float = 1.0

    @property
    def llm_enabled(self) -> bool:
        """Whether this run should actually use a model."""
        if self.llm_mode == "scripted":
            return False
        if self.llm_mode == "llm":
            return True
        return self.api_key_present  # "auto"


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    return Settings(
        host=_env("OPENOFFENSIVE_HOST") or "127.0.0.1",
        port=_env_int("OPENOFFENSIVE_PORT", 8777),
        llm_mode=(_env("OPENOFFENSIVE_LLM_MODE") or "auto").lower(),
        model=_env("OPENOFFENSIVE_MODEL") or "claude-opus-5",
        max_tokens=_env_int("OPENOFFENSIVE_MAX_TOKENS", 4096),
        max_steps=_env_int("OPENOFFENSIVE_MAX_STEPS", 24),
        api_key_present=bool(_env("ANTHROPIC_API_KEY")),
        sandbox_image=_env("OPENOFFENSIVE_SANDBOX_IMAGE") or "openoffensive-sandbox:kali",
        sandbox_network=_env("OPENOFFENSIVE_SANDBOX_NETWORK"),
        runs_dir=_env("OPENOFFENSIVE_RUNS_DIR") or "runs",
        scope_allow=tuple(
            h for h in (s.strip() for s in _env("OPENOFFENSIVE_SCOPE").split(",")) if h
        ),
        speed=_env_float("OPENOFFENSIVE_SPEED", 1.0),
    )


def reset_settings_cache() -> None:
    """Drop the memoized settings (used by tests that tweak the environment)."""
    load_settings.cache_clear()
