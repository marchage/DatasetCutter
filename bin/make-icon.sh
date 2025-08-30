#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PNG="assets/DatasetCutter.png"
ICNS="assets/DatasetCutter.icns"
ICONSET_DIR="build/icon.iconset"

if [ ! -f "$PNG" ]; then
  echo "Missing $PNG (expected 1024x1024 PNG)." >&2
  exit 1
fi

rm -rf "$ICONSET_DIR"
mkdir -p "$ICONSET_DIR"

# Generate required sizes
# macOS iconset requires both 1x and 2x for listed base sizes
sizes=(16 32 64 128 256 512)
for sz in "${sizes[@]}"; do
  sips -z "$sz" "$sz"     "$PNG" --out "$ICONSET_DIR/icon_${sz}x${sz}.png" >/dev/null
  if [ "$sz" -lt 512 ]; then
    d=$((sz*2))
    sips -z "$d" "$d" "$PNG" --out "$ICONSET_DIR/icon_${sz}x${sz}@2x.png" >/dev/null
  else
    # 512x512@2x is 1024x1024
    sips -z 1024 1024 "$PNG" --out "$ICONSET_DIR/icon_512x512@2x.png" >/dev/null
  fi

done

# Also include 1024 standalone for reference (optional)
cp -f "$PNG" "$ICONSET_DIR/icon_1024x1024.png"

# Build .icns
iconutil -c icns "$ICONSET_DIR" -o "$ICNS"

echo "Wrote $ICNS"
