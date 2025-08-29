#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "System Python: $(python3 -V 2>&1) ($(which python3))"

if [ -d .venv ]; then
  echo "Project venv exists: $(realpath .venv)"
  if [ -x .venv/bin/python ]; then
    echo "Venv Python: $(.venv/bin/python -V 2>&1)"
    echo "Venv pip: $(.venv/bin/python -m pip -V 2>&1)"
  fi
else
  echo "No .venv found. Create one with: python3 -m venv .venv && source .venv/bin/activate && python -m pip install -r requirements.txt"
fi

if command -v ffmpeg >/dev/null 2>&1; then
  echo "FFmpeg (PATH): $(command -v ffmpeg)"
  ffmpeg -hide_banner -loglevel error -version | head -n1 || true
else
  echo "FFmpeg: not found in PATH"
fi

if [ -x "$HOME/DatasetCutter/bin/ffmpeg" ]; then
  echo "FFmpeg (preferred static): $HOME/DatasetCutter/bin/ffmpeg"
  "$HOME/DatasetCutter/bin/ffmpeg" -hide_banner -loglevel error -version | head -n1 || true
fi

echo "Server log (tail):"
LOG="$HOME/DatasetCutter/data/server.log"
[ -f "$LOG" ] && tail -n 20 "$LOG" || echo "No log yet ($LOG)"
