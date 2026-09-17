# OpenOffensive backend

A Django + Django REST Framework API for the invite-only OpenOffensive web app.
It runs the OpenOffensive engine as a managed subprocess and stores each scan's
findings and report for the dashboard to read.

- **accounts** — session auth. Registration is **invite-gated** (no open signup).
- **invites** — `Invite` codes + a public `AccessRequest` waitlist; minted via the
  admin or the `makeinvite` command.
- **scans** — `Scan` model + an owner-scoped API; a background runner launches
  `python -m openoffensive scan …` and ingests the artifacts it writes.

## Quick start

```bash
# from the repo root: install the engine so `python -m openoffensive` resolves
pip install -e .

cd backend
pip install -r requirements.txt
cp .env.example .env          # then edit .env (it is git-ignored)

python manage.py migrate
python manage.py createsuperuser
python manage.py makeinvite --count 1     # prints an invite code
python manage.py runserver
```

The API is now at `http://localhost:8000/`. Sign in to the admin at `/admin/`
to mint invites and review access requests.

## Configuration

All configuration comes from the environment (or a git-ignored `backend/.env`).
See [`.env.example`](.env.example) for the full list. Nothing secret is
hard-coded, and no default `SECRET_KEY` ships — in production the app refuses to
start without `DJANGO_SECRET_KEY`.

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Django secret. Required in production; auto-generated (ephemeral) in `DEBUG`. |
| `DJANGO_DEBUG` | `true`/`false` (default `true`). |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hostnames (production). |
| `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` | Where the React dashboard runs. |
| `POSTGRES_*` | Set `POSTGRES_DB` to use PostgreSQL instead of SQLite. |
| `ANTHROPIC_API_KEY` | Passed through to the engine subprocess for LLM mode. |
| `OPENOFFENSIVE_ENGINE_PYTHON` | Interpreter used to launch the engine (default: this one). |
| `OPENOFFENSIVE_ENGINE_RUNS_DIR` | Where per-scan artifacts are written (default `backend/runs`). |
| `OPENOFFENSIVE_ENGINE_SANDBOX` | `auto` / `docker` / `local`. |
| `OPENOFFENSIVE_ALLOW_EXTERNAL` | Allow non-local URL targets (adds `--authorized`). |

## API

Base path `/api/`. Session auth; every endpoint except the three public ones
requires an authenticated session.

| Method & path | Auth | Purpose |
| --- | --- | --- |
| `GET  /api/auth/csrf/` | public | Set the CSRF cookie the SPA echoes as `X-CSRFToken`. |
| `POST /api/auth/register/` | public | Invite-gated signup (`username`, `password`, `invite_code`, `email?`). |
| `POST /api/auth/login/` | public | `username` + `password`. |
| `POST /api/auth/logout/` | user | End the session. |
| `GET  /api/auth/me/` | user | The current user. |
| `POST /api/auth/request-access/` | public | Landing-page waitlist (`email`, `name?`, `note?`). |
| `GET  /api/scans/` | user | List the caller's scans (lightweight rows). |
| `POST /api/scans/` | user | Start a scan (`target?`, `mode` = `auto`/`llm`/`scripted`). |
| `GET  /api/scans/{id}/` | user | Full scan detail — poll this for `status`, findings, report. |
| `GET  /api/scans/{id}/report/` | user | Just the Markdown report. |

A created scan starts as `queued`, moves to `running`, then settles at `done`
or `error`. The dashboard polls the detail endpoint until it is terminal.

## How a scan runs

1. `POST /api/scans/` creates a `Scan` and returns immediately (`status: queued`).
2. A background daemon thread runs
   `python -m openoffensive scan <target> --mode <mode> --runs-dir backend/runs/<scan_pk> --sandbox <backend>`.
3. On completion the runner reads the engine's own artifacts with `RunStore`
   (`run.json`, `findings.json`, `report.md`) and populates the `Scan` row.

No Celery, no websockets — one subprocess per scan, status by polling.

## Notes

- **Never commit secrets.** `.env`, `db.sqlite3`, and `runs/` are git-ignored;
  only `.env.example` (placeholders) is tracked. Invite codes are minted at
  runtime, never stored in source.
- Non-local URL targets require `OPENOFFENSIVE_ALLOW_EXTERNAL=true` and are only
  scanned with explicit authorization — you must be permitted to test them.
