#!/usr/bin/env bash
# OpenOffensive — launch the live multi-agent pentest dashboard for a target.
#
# Starts the dashboard server for the target you pass, then opens your browser.
# A scan needs an ANTHROPIC_API_KEY (the agents reason with a real model).
#
#   ./run.sh <target>        # e.g. ./run.sh https://example.com
#
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  if command -v python3 >/dev/null 2>&1; then PY=python3
  elif command -v python >/dev/null 2>&1; then PY=python
  else
    echo "error: Python 3 not found. Install Python 3.9+ and re-run." >&2
    exit 1
  fi
fi

if [ "$#" -lt 1 ]; then
  echo "usage: ./run.sh <target>   (git repo URL, live URL/host, or local dir)" >&2
  exit 2
fi

echo "OpenOffensive — starting the dashboard (Ctrl-C to stop)…"
exec "$PY" -m openoffensive serve "$@"
