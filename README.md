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
uvicorn app.main:app --reload --port 8000
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
- The .app runs headless (server + browser). A Dock icon may appear briefly and close; this is expected.
- A “Quit Server” button is in the UI header to stop the background server.
- The launcher prefers `~/DatasetCutter/bin/ffmpeg` when present.

## Troubleshooting

- If video scrubbing doesn’t work, ensure ffmpeg is installed and the video is fully uploaded to the app.
- Large videos may take time to upload on first import. After upload, playback streams locally from the app.
- If labeling dialog doesn’t pop, click inside the page once (to ensure the page has focus) and try Space again.
- On macOS, Homebrew ffmpeg can break due to missing dylibs (e.g., `libjxl`). Using a static ffmpeg in `~/DatasetCutter/bin/ffmpeg` avoids this.
- Check logs in `~/DatasetCutter/data/server.log` for ffmpeg path and errors.

## Privacy

Everything runs locally. Videos and clips are stored under `~/DatasetCutter` by default (unless you change paths).
