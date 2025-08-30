#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Create venv if missing
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

# Pick the venv python explicitly (works even if `python` isn’t on PATH)
VENV_PY=".venv/bin/python3"
if [ ! -x "$VENV_PY" ]; then
  VENV_PY=".venv/bin/python"
fi

"$VENV_PY" -m pip -q install -r requirements.txt
exec "$VENV_PY" -m uvicorn app.main:app --reload --port 8000
