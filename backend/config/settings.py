"""Django settings for the OpenOffensive backend.

Everything sensitive comes from the environment (or a git-ignored backend/.env).
Nothing secret is hard-coded, and no default SECRET_KEY ships for production.
"""

from __future__ import annotations

import os
from pathlib import Path

from django.core.management.utils import get_random_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# minimal, dependency-free .env loader (git-ignored file, never committed)
# ---------------------------------------------------------------------------
def _load_dotenv(path: Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, sep, val = line.partition("=")
        if not sep:
            continue
        key, val = key.strip(), val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_bool(name: str, default: bool) -> bool:
    v = _env(name).lower()
    return v in ("1", "true", "yes", "on") if v else default


def _csv(name: str) -> list[str]:
    return [x.strip() for x in _env(name).split(",") if x.strip()]


# ---------------------------------------------------------------------------
# core
# ---------------------------------------------------------------------------
DEBUG = _env_bool("DJANGO_DEBUG", True)

# SECRET_KEY: from the environment. In DEBUG we generate an ephemeral key so the
# dev server runs with zero setup; in production a real key is REQUIRED and the
# app refuses to boot without one (never ship a hard-coded secret).
SECRET_KEY = _env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = get_random_secret_key()  # ephemeral, per-process, not persisted
    else:
        raise RuntimeError(
            "DJANGO_SECRET_KEY is required in production. Set it in the environment "
            "(never commit it)."
        )

ALLOWED_HOSTS = _csv("DJANGO_ALLOWED_HOSTS") or (["*"] if DEBUG else [])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third-party
    "rest_framework",
    "corsheaders",
    # local
    "accounts",
    "invites",
    "scans",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# database — SQLite by default; point at Postgres via env in production
# ---------------------------------------------------------------------------
if _env("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _env("POSTGRES_DB"),
            "USER": _env("POSTGRES_USER"),
            "PASSWORD": _env("POSTGRES_PASSWORD"),
            "HOST": _env("POSTGRES_HOST") or "localhost",
            "PORT": _env("POSTGRES_PORT") or "5432",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# DRF — session auth, authenticated by default (this is an invite-only app)
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

# CORS / CSRF — the React dashboard dev server talks to this API with credentials.
CORS_ALLOWED_ORIGINS = _csv("CORS_ALLOWED_ORIGINS") or [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = _csv("CSRF_TRUSTED_ORIGINS") or list(CORS_ALLOWED_ORIGINS)

# ---------------------------------------------------------------------------
# engine integration — how the backend runs the OpenOffensive scanner
# ---------------------------------------------------------------------------
# The engine is invoked as a subprocess: `<ENGINE_PYTHON> -m openoffensive scan ...`.
ENGINE_PYTHON = _env("OPENOFFENSIVE_ENGINE_PYTHON") or os.sys.executable
ENGINE_RUNS_DIR = Path(_env("OPENOFFENSIVE_ENGINE_RUNS_DIR") or (BASE_DIR / "runs"))
# Allow scanning non-local URL targets (adds the engine's --authorized flag).
ENGINE_ALLOW_EXTERNAL = _env_bool("OPENOFFENSIVE_ALLOW_EXTERNAL", False)
# Execution backend for the engine: auto (try Docker, fall back to host), docker, or local.
ENGINE_SANDBOX = _env("OPENOFFENSIVE_ENGINE_SANDBOX") or "auto"
