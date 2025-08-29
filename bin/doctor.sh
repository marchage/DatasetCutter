#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "Python: $(python3 -V 2>&1)"
echo "Python which: $(which python3)"
if [ -d .venv ]; then
  echo "Venv Python: $(.venv/bin/python -V 2>&1)"
  echo "Venv pip: $(.venv/bin/pip -V 2>&1)"
fi
if command -v ffmpeg >/dev/null 2>&1; then
  echo "FFmpeg: $(command -v ffmpeg)"
  ffmpeg -hide_banner -loglevel error -version | head -n1 || true
else
  echo "FFmpeg: not found (brew install ffmpeg)"
fi
