#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip -q install -r requirements.txt
exec uvicorn app.main:app --reload --port 8000
