# MP4 Dataset Cutter for Create ML (Action Classifier)

A lightweight local web app to speed up dataset creation:

- Play MP4 videos, scrub the timeline, and use handy shortcuts.
- Press Space to cut a 2-second clip (configurable) around the current time.
- Prompt for a label (autocomplete from previous labels), then export into a Create ML Action Classifier folder structure: `DatasetRoot/Training/<Label>/<clip>.mp4`.
- Quick undo for the last exported clip.

Runs locally on macOS (or any OS with Python + ffmpeg). Default data lives in `~/DatasetCutter`.

## Features

- Video upload and playback with scrubbing.
- Keyboard shortcuts:
  - Space: Cut clip and prompt for label
  - Left/Right: Seek ±0.25s (hold Shift for ±1s)
  - J/K/L: 0.5x / 1x (toggle) / 1.5x speed
  - U: Undo last exported clip
  - C: Clip between in/out marks (if set)
  - I/O: Set mark-in / mark-out
- Clip mode: last N seconds or centered on current time
- Label autocomplete from previously used labels; quick-label buttons
- Create ML Action Classifier folder layout (video-based): `Training/<Label>/*.mp4`

## Requirements

- Python 3.9+
- ffmpeg. Recommended: a static ffmpeg at `~/DatasetCutter/bin/ffmpeg` (preferred automatically). Otherwise, ensure `ffmpeg` is on your PATH.

On macOS you can install ffmpeg via Homebrew:

```bash
brew install ffmpeg
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
3. Play/scrub. When you want to capture an action, press Space.
4. Enter/select a label. The clip is exported to `DatasetRoot/Training/<Label>/`.
5. Use Undo if needed.

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

### Bundling ffmpeg into the .app (optional)

If you want a single .app that runs without any system ffmpeg, you can bundle a binary into the app:

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

### App window in dev

You can show the same small window while developing by setting `SHOW_WINDOW=1` and running `python entry.py`.

## Troubleshooting

- If video scrubbing doesn’t work, ensure ffmpeg is installed and the video is fully uploaded to the app.
- Large videos may take time to upload on first import. After upload, playback streams locally from the app.
- If labeling dialog doesn’t pop, click inside the page once (to ensure the page has focus) and try Space again.
- On macOS, Homebrew ffmpeg can break due to missing dylibs (e.g., `libjxl`). Using a static ffmpeg in `~/DatasetCutter/bin/ffmpeg` avoids this.
- Check logs in `~/DatasetCutter/data/server.log` for ffmpeg path and errors.

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

## Privacy

Everything runs locally. Videos and clips are stored under `~/DatasetCutter` by default (unless you change paths).
