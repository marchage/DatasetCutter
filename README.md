# MP4 Dataset Cutter for Create ML (Action Classifier)

A lightweight local web app to speed up dataset creation:

- Play MP4 videos, scrub the timeline, and use handy shortcuts.
- Press Enter to export a 5-second clip (configurable) around the current time.
- Press Space to play/pause like QuickTime.
- Prompt for a label (autocomplete from previous labels), then export into a Create ML Action Classifier folder structure: `DatasetRoot/Training/<Label>/<clip>.mp4`.
- Quick-label hotkeys with digits (multi-digit supported, e.g. 10, 11).
- Color-coded labels and a mini bar chart to guide dataset balancing.
- Multi-level undo (up to 10 clips).

Runs locally on macOS (or any OS with Python + ffmpeg). Default data lives in `~/DatasetCutter`.

## Features

- Video upload and playback with scrubbing.
- Keyboard shortcuts:
  - Space: Play/Pause
  - Enter: Export clip and prompt for label
  - Digits: Quick-label export (supports multi-digit like 10, 11). Type the number; it auto-commits. If a number is buffered, Enter commits it.
  - Left/Right: Seek ±0.25s (hold Shift for ±1s)
  - J/K/L: 0.5x / 1.0x / 1.5x speed
  - U: Undo (multi-level stack up to 10)
  - C: Clip between in/out marks (if set)
  - I/O: Set mark-in / mark-out
- Clip mode: last N seconds or centered on current time
- Label autocomplete from previously used labels; quick-label buttons with counts
- Create ML Action Classifier folder layout (video-based): `Training/<Label>/*.mp4`

### Label balancing helpers

- Quick-label buttons are color-coded based on per-label counts and your target threshold ± margin:
  - Good (green): count ≥ threshold + margin
  - Warn (yellow): threshold − margin ≤ count < threshold + margin
  - Bad (red): count < threshold − margin
- Configure Threshold and Margin in Settings. Click “Refresh Stats” to recompute.
- A compact mini bar chart (25px tall) near the Label header shows per-label counts by height with the same colors.

## Download (macOS)

Grab a prebuilt app from GitHub Releases (ffmpeg 8 bundled for both Intel and Apple Silicon):

- DatasetCutter-macOS-app-arm64.zip → Apple Silicon (M1/M2/M3)
- DatasetCutter-macOS-app-x86_64.zip → Intel (or Apple Silicon via Rosetta)

Unzip and run “Dataset Cutter.app”. On first launch macOS may warn because it’s unsigned; right-click → Open to proceed.

CLI bundles are also attached (…-cli-<arch>.zip) if you prefer the onedir build.

## Requirements

- Using the prebuilt macOS app from Releases: no extra install needed. ffmpeg v8 is bundled for both Intel and Apple Silicon and is auto-selected at runtime.
- Running from source (dev): Python 3.9+ and ffmpeg available locally.

ffmpeg discovery order at runtime:
1) Bundled app binary: `app/bin/<arch>/ffmpeg` (inside the .app)
2) User-local: `~/DatasetCutter/bin/ffmpeg`
3) System: `/opt/homebrew/bin/ffmpeg`, `/usr/local/bin/ffmpeg`, or `ffmpeg` on PATH

macOS (dev) install options:

```bash
brew install ffmpeg
```

Or drop a static ffmpeg at `~/DatasetCutter/bin/ffmpeg` and make it executable.
There’s also a helper script:

```bash
./bin/install-ffmpeg.sh
```

## Setup (dev)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Dev options:

- Quick dev server (reload):
```bash
python -m uvicorn app.main:app --reload --port 8000
```

- Full launcher (same as the .app): picks a free port, opens your browser, supports graceful quit; you can also show the native window in dev:
```bash
export SHOW_WINDOW=1   # optional; shows the small macOS window in dev
python entry.py
```

Then open http://127.0.0.1:8000 in your browser.

Data & logs:
- App data root: `~/DatasetCutter`
  - Videos: `~/DatasetCutter/data/videos`
  - Server log: `~/DatasetCutter/data/server.log`
  - Dataset root (default): `~/DatasetCutter/dataset`

## Usage

1. Optionally set the Dataset Root (defaults to `~/DatasetCutter/dataset/`). The app will create `Training/` inside it.
2. Upload an MP4 via the “Open Video” button (local file is copied to `data/videos/`).
3. Play/scrub. When you want to capture an action, press Space (or press digits to choose a quick label).
4. Enter/select a label or use a quick label. The clip is exported to `DatasetRoot/Training/<Label>/`.
5. Use Undo if needed (up to 10 steps).

## Create ML Notes

Create ML Action Classifier (video-based) expects a directory with class subfolders inside `Training/` (and optionally `Validation/` / `Testing/`). This tool writes to `Training/` by default. You can reorganize or split later if needed.

## Packaging (.app)

Build a macOS app bundle (opens your browser UI on launch):

```bash
./bin/build-app.sh
open "dist/Dataset Cutter.app"
```

Notes:
- The .app shows a small macOS window with two buttons:
  - Open UI: opens the browser to the local server URL
  - Quit Server: gracefully shuts down the server and closes the app
- The window displays the exact URL (port may differ if 8000 is in use).
- The launcher prefers `~/DatasetCutter/bin/ffmpeg` when present.
- Release builds bundle ffmpeg v8 for both arm64 and x86_64 and pick the right one at runtime.

### Bundling ffmpeg into the .app (optional)

If you build locally and want the .app to run without system ffmpeg, bundle binaries like so:

1) Place a platform-appropriate ffmpeg binary at:

  - macOS Intel:  `assets/ffmpeg/mac/x86_64/ffmpeg`
  - macOS Apple:  `assets/ffmpeg/mac/arm64/ffmpeg`

  Make sure it’s executable:

  ```bash
  chmod +x assets/ffmpeg/mac/*/ffmpeg
  ```

2) Rebuild:

```bash
./bin/build-app.sh
```

At runtime, the app will prefer the bundled ffmpeg. If missing, it falls back to `~/DatasetCutter/bin/ffmpeg`, then PATH.

## Releases (CI)

Pushing a tag like `v1.0.0` triggers GitHub Actions to:

1) Build native .apps on Intel and Apple Silicon runners
2) Bundle ffmpeg v8 for both architectures
3) Publish a GitHub Release with four assets:
  - DatasetCutter-macOS-app-arm64.zip
  - DatasetCutter-macOS-app-x86_64.zip
  - DatasetCutter-macOS-cli-arm64.zip
  - DatasetCutter-macOS-cli-x86_64.zip

Create and push a tag:

```bash
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin v1.0.0
```

Recent tags will automatically publish an updated app with UI improvements like the shortcuts banner, label mini chart, and color-coded quick labels.

### App window in dev

You can show the same small window while developing by setting `SHOW_WINDOW=1` and running `python entry.py`.

## Troubleshooting

- If video scrubbing doesn’t work, ensure ffmpeg is installed and the video is fully uploaded to the app.
- Large videos may take time to upload on first import. After upload, playback streams locally from the app.
- If labeling dialog doesn’t pop, click inside the page once (to ensure the page has focus) and try Space again.
- On macOS, Homebrew ffmpeg can break due to missing dylibs (e.g., `libjxl`). Using a static ffmpeg in `~/DatasetCutter/bin/ffmpeg` avoids this.
- Check logs in `~/DatasetCutter/data/server.log` for ffmpeg path and errors.

#### Export normalization controls

New clips are normalized for Create ML by default. You can tweak via env vars before launching:

```bash
# Always re-encode (safe). Set to 0 to try a fast stream copy first.
export DC_ALWAYS_REENCODE=1

# Force constant frame rate (set 0 to keep source VFR)
export DC_EXPORT_CFR=30

# Drop audio tracks on export (helps if audio codecs cause issues)
export DC_EXPORT_DROP_AUDIO=0
```

### Port already in use

- The dev command `uvicorn ... --port 8000` will fail if 8000 is used. Either kill the other process or pick a different port.
- The launcher `python entry.py` automatically finds the next free port starting at 8000 and shows it in the window.

### Graceful quit

- The native window’s “Quit Server” requests a graceful shutdown; the process exits cleanly.
- From the browser UI, the “Quit Server” button does the same via `/api/quit`.

### Virtualenv mismatch (bad interpreter)

- If you moved/renamed folders after creating `.venv`, recreate it:
```bash
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### Diagnostics

Run the helper script:
```bash
./bin/doctor.sh
```
It reports Python/venv, ffmpeg availability, and the last server log lines.

### Dataset analysis helper

From the repo root, a helper script surfaces labels that need attention (defaults to `~/DatasetCutter/dataset/Training`):

```bash
python bin/dataset_focus.py
```

Options include extra file extensions and a top-N view. This mirrors the in-app label stats/colouring logic.

### Repair training videos for Create ML

If Create ML reports “Failed to complete video decoding”, normalize your clips using the repair script. It remuxes or re-encodes to H.264 (yuv420p), even dimensions, +faststart, and optional constant frame rate.

```bash
# Dry run first
python bin/repair_dataset.py --root ~/DatasetCutter/dataset/Training --dry-run

# Then actually repair (defaults to 30 fps CFR, creates .bak backups)
python bin/repair_dataset.py --root ~/DatasetCutter/dataset/Training --cfr 30
```

Notes:
- Falls back to h264_videotoolbox on macOS if libx264 is unavailable.
- Keeps audio if possible; converts to AAC when needed.
- Use `--backup-ext ""` to skip backups (replace originals in place).

## Privacy

Everything runs locally. Videos and clips are stored under `~/DatasetCutter` by default (unless you change paths).
