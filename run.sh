#!/usr/bin/env bash
# OpenOffensive — launch the live multi-agent pentest dashboard.
#
# Starts the bundled vulnerable demo target + the dashboard server, then opens
# your browser. Pure Python standard library — no install, no dependencies.
#
#   ./run.sh
#
set -euo pipefail
cd "$(dirname "$0")"

# Pick an available Python 3 interpreter.
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  if command -v python3 >/dev/null 2>&1; then PY=python3
  elif command -v python >/dev/null 2>&1; then PY=python
  else
    echo "error: Python 3 not found. Install Python 3.8+ and re-run." >&2
    exit 1
  fi
fi

echo "OpenOffensive — starting the dashboard (Ctrl-C to stop)…"
exec "$PY" server.py "$@"
