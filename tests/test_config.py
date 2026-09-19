"""Configuration: environment variables → Settings, and .env auto-loading."""

from __future__ import annotations

import os

from openoffensive import Settings, load_settings
from openoffensive.config import _load_dotenv, reset_settings_cache


def _load(monkeypatch, **env) -> Settings:
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    reset_settings_cache()
    return load_settings()


def test_defaults_when_env_is_clean():
    # The autouse _clean_env fixture has stripped every relevant var.
    reset_settings_cache()
    s = load_settings()
    assert s.host == "127.0.0.1"
    assert s.port == 8777
    assert s.model == "claude-opus-5"
    assert s.runs_dir == "runs"
    assert s.speed == 1.0
    assert s.scope_allow == ()
    assert s.api_key_present is False
    # sandbox (Docker) defaults
    assert s.sandbox_image == "openoffensive-sandbox:kali"
    assert s.sandbox_network == ""


def test_env_maps_to_settings(monkeypatch):
    s = _load(
        monkeypatch,
        OPENOFFENSIVE_HOST="0.0.0.0",
        OPENOFFENSIVE_PORT="9001",
        OPENOFFENSIVE_MODEL="claude-sonnet-5",
        OPENOFFENSIVE_RUNS_DIR="/tmp/oo-runs",
        OPENOFFENSIVE_SPEED="0",
        OPENOFFENSIVE_MAX_TOKENS="2048",
        OPENOFFENSIVE_MAX_STEPS="7",
    )
    assert s.host == "0.0.0.0"
    assert s.port == 9001
    assert s.model == "claude-sonnet-5"
    assert s.runs_dir == "/tmp/oo-runs"
    assert s.speed == 0.0
    assert s.max_tokens == 2048
    assert s.max_steps == 7


def test_scope_env_is_split_and_stripped(monkeypatch):
    s = _load(monkeypatch, OPENOFFENSIVE_SCOPE="a.example, b.example ,,c.example")
    assert s.scope_allow == ("a.example", "b.example", "c.example")


def test_sandbox_env_maps_to_settings(monkeypatch):
    s = _load(
        monkeypatch,
        OPENOFFENSIVE_SANDBOX_IMAGE="ghcr.io/acme/kali:latest",
        OPENOFFENSIVE_SANDBOX_NETWORK="oo-net",
    )
    assert s.sandbox_image == "ghcr.io/acme/kali:latest"
    assert s.sandbox_network == "oo-net"


def test_api_key_presence_from_env(monkeypatch):
    with_key = _load(monkeypatch, ANTHROPIC_API_KEY="sk-test-123")
    assert with_key.api_key_present is True


def test_invalid_numeric_env_falls_back_to_default(monkeypatch):
    s = _load(monkeypatch, OPENOFFENSIVE_PORT="not-a-number",
              OPENOFFENSIVE_SPEED="fast")
    assert s.port == 8777
    assert s.speed == 1.0


def test_load_settings_is_cached(monkeypatch):
    monkeypatch.setenv("OPENOFFENSIVE_PORT", "1234")
    reset_settings_cache()
    first = load_settings()
    assert first.port == 1234
    # A later env change is NOT observed until the cache is reset.
    monkeypatch.setenv("OPENOFFENSIVE_PORT", "5678")
    assert load_settings().port == 1234
    reset_settings_cache()
    assert load_settings().port == 5678


# ---------------------------------------------------------------------------
# .env auto-loading (zero-dependency dotenv)
# ---------------------------------------------------------------------------
def test_dotenv_is_loaded_into_settings(tmp_path, monkeypatch):
    # A local .env supplies the key; load_settings() picks it up → llm turns on.
    monkeypatch.delenv("OPENOFFENSIVE_NO_DOTENV", raising=False)
    (tmp_path / ".env").write_text(
        '# local secrets\nexport ANTHROPIC_API_KEY="sk-ant-fromdotenv"\n'
        "OPENOFFENSIVE_MODEL=claude-sonnet-5\n")
    monkeypatch.chdir(tmp_path)
    try:
        reset_settings_cache()
        s = load_settings()
        assert s.api_key_present is True          # key came from the .env file
        assert s.model == "claude-sonnet-5"
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("OPENOFFENSIVE_MODEL", None)


def test_dotenv_never_overrides_real_env(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENOFFENSIVE_NO_DOTENV", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "real-shell-key")
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=dotenv-key\n")
    monkeypatch.chdir(tmp_path)
    _load_dotenv()
    assert os.environ["ANTHROPIC_API_KEY"] == "real-shell-key"   # the shell wins


def test_no_dotenv_flag_disables_loading(tmp_path, monkeypatch):
    # The flag the suite sets so a developer's real .env can't leak into tests.
    monkeypatch.setenv("OPENOFFENSIVE_NO_DOTENV", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=should-not-load\n")
    monkeypatch.chdir(tmp_path)
    _load_dotenv()
    assert "ANTHROPIC_API_KEY" not in os.environ
