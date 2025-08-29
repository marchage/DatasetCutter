#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip -q install -r requirements.txt pyinstaller==6.10.0
# Clean previous builds to avoid name collisions (e.g., dist/DatasetCutter dir vs exe)
rm -rf build dist || true
# Build the app bundle
pyinstaller -y --clean pyinstaller.spec

cat <<'TXT'
Built application in dist/DatasetCutter
You can now launch either the CLI bundle or the .app:

CLI bundle:
  cd dist/DatasetCutter
  ./DatasetCutter

macOS app bundle:
  open "dist/Dataset Cutter.app"

On start it opens your browser automatically; if not, visit the printed URL e.g. http://127.0.0.1:8000
TXT
