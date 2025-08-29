from __future__ import annotations

import os
import shutil
import time
import sys
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import ffmpeg
import subprocess

# --- Ensure ffmpeg binary is discoverable even in bundled app (limited PATH) ---
FFMPEG_BIN_PATH: Optional[str] = None

def _ensure_ffmpeg_in_path() -> None:
    candidates = []
    # Env override
    env_bin = os.environ.get("FFMPEG_BINARY")
    if env_bin:
        candidates.append(env_bin)
    # User-local static ffmpeg (preferred fallback)
    try:
        candidates.append(str(Path.home() / "DatasetCutter" / "bin" / "ffmpeg"))
    except Exception:
        pass
    # Common macOS locations
    candidates += [
        "/usr/local/bin/ffmpeg",
        "/opt/homebrew/bin/ffmpeg",
        shutil.which("ffmpeg") or "",
    ]
    # Deduplicate and filter
    seen = set()
    paths = [p for p in candidates if p and (p not in seen and not seen.add(p))]
    global FFMPEG_BIN_PATH
    for p in paths:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            # Add containing dir to PATH if missing
            d = os.path.dirname(p)
            path_env = os.environ.get("PATH", "")
            if d not in path_env.split(":"):
                os.environ["PATH"] = f"{d}:{path_env}" if path_env else d
            try:
                # Hint ffmpeg-python to use this binary
                import ffmpeg as _ff
                from ffmpeg import _run as _fr
                _fr.FFMPEG_BIN = p  # type: ignore[attr-defined]
            except Exception:
                pass
            FFMPEG_BIN_PATH = p
            break

_ensure_ffmpeg_in_path()

# Resolve app root for templates/static (read-only in bundle)
if getattr(sys, "_MEIPASS", None):
    APP_ROOT = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    IN_BUNDLE = True
else:
    APP_ROOT = Path(__file__).resolve().parent.parent
    IN_BUNDLE = False

# Use a user-writable base for data/dataset for both dev and bundled
BASE_DIR = Path.home() / "DatasetCutter"

DATA_DIR = BASE_DIR / "data"
VIDEOS_DIR = DATA_DIR / "videos"
CLIPS_DIR = DATA_DIR / "clips"
DEFAULT_DATASET_ROOT = BASE_DIR / "dataset"

VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
CLIPS_DIR.mkdir(parents=True, exist_ok=True)
(DEFAULT_DATASET_ROOT / "Training").mkdir(parents=True, exist_ok=True)

# Filenames to exclude from listings (case-insensitive)
EXCLUDED_META_NAMES = {
    ".ds_store",  # macOS Finder metadata
    "thumbs.db",  # Windows thumbnail cache
    "ehthumbs.db",  # Windows enhanced thumbnail cache
    "desktop.ini",  # Windows folder config
}

# Only list these video extensions in the dropdown
ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".m4v"}

def _is_listable_video(p: Path) -> bool:
    """Return True if path is a normal user video file (not OS metadata)."""
    if not p.is_file():
        return False
    name = p.name
    low = name.lower()
    # Exclude dotfiles, AppleDouble resource forks, and known OS metadata names
    if name.startswith(".") or low in EXCLUDED_META_NAMES or low.startswith("._"):
        return False
    # Restrict by known video extensions (matches upload allow-list)
    return p.suffix.lower() in ALLOWED_VIDEO_EXTS

# Basic startup diagnostics
try:
    with (DATA_DIR / "server.log").open("a", encoding="utf-8") as f:
        f.write(f"START: IN_BUNDLE={IN_BUNDLE} APP_ROOT={APP_ROOT}\n")
        f.write(f"BASE_DIR={BASE_DIR} DATA_DIR={DATA_DIR} VIDEOS_DIR={VIDEOS_DIR}\n")
        f.write(f"PATH={os.environ.get('PATH','')}\n")
        f.write(f"FFMPEG_BIN_PATH={FFMPEG_BIN_PATH}\n")
        try:
            ffbin = FFMPEG_BIN_PATH or shutil.which('ffmpeg') or 'ffmpeg'
            ver = subprocess.run([ffbin, '-version'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=3)
            f.write("ffmpeg -version:\n" + ver.stdout.decode(errors='replace') + "\n")
        except Exception as _e:
            f.write(f"ffmpeg -version failed: {_e}\n")
except Exception:
    pass

app = FastAPI(title="MP4 Dataset Cutter")

# Static mounts (from app resources)
app.mount("/static", StaticFiles(directory=str(APP_ROOT / "app" / "static")), name="static")
app.mount("/videos", StaticFiles(directory=str(VIDEOS_DIR)), name="videos")

templates = Jinja2Templates(directory=str(APP_ROOT / "app" / "templates"))


# Ensure Accept-Ranges for video to enable seeking on some clients
@app.middleware("http")
async def ensure_ranges(req: Request, call_next):
    resp = await call_next(req)
    if req.url.path.startswith("/videos/"):
        if "accept-ranges" not in (k.lower() for k in resp.headers.keys()):
            resp.headers["Accept-Ranges"] = "bytes"
        resp.headers.setdefault("Cache-Control", "no-cache")
    return resp


class Settings(BaseModel):
    dataset_root: str = str(DEFAULT_DATASET_ROOT)
    clip_duration: float = 2.0  # seconds
    clip_mode: str = "backward"  # "backward" or "centered" or "range" (I/O marks)


class ClipRequest(BaseModel):
    video_filename: str
    current_time: float
    label: str
    in_mark: Optional[float] = None
    out_mark: Optional[float] = None


class UndoState(BaseModel):
    path: Optional[str] = None


SETTINGS_PATH = DATA_DIR / "settings.json"
LABELS_PATH = DATA_DIR / "labels.txt"
UNDO_PATH = DATA_DIR / "undo.txt"

_current_settings = Settings()
_undo_state = UndoState()


# util

def load_labels() -> List[str]:
    if LABELS_PATH.exists():
        return [l.strip() for l in LABELS_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    return []


def save_label(label: str) -> None:
    labels = list(dict.fromkeys(load_labels() + [label]))
    LABELS_PATH.write_text("\n".join(labels) + "\n", encoding="utf-8")


def sanitize_filename(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in name)
    return safe.strip("._") or "clip"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "settings": _current_settings.model_dump()})


@app.get("/api/settings")
async def get_settings():
    return _current_settings


@app.post("/api/settings")
async def update_settings(dataset_root: str = Form(None), clip_duration: float = Form(None), clip_mode: str = Form(None)):
    global _current_settings
    if dataset_root:
        _current_settings.dataset_root = dataset_root
        Path(dataset_root, "Training").mkdir(parents=True, exist_ok=True)
    if clip_duration:
        _current_settings.clip_duration = float(clip_duration)
    if clip_mode in {"backward", "centered", "range"}:
        _current_settings.clip_mode = clip_mode
    return _current_settings


@app.get("/api/labels")
async def get_labels():
    return {"labels": load_labels()}


@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".mp4", ".mov", ".m4v")):
        raise HTTPException(400, "Only MP4/MOV allowed")
    dest = VIDEOS_DIR / sanitize_filename(file.filename)
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"filename": dest.name}


@app.get("/api/videos")
async def list_videos():
    files = sorted([p.name for p in VIDEOS_DIR.iterdir() if _is_listable_video(p)])
    return {"videos": files}


# Keeping this for compatibility; frontend uses /videos/{filename}
@app.get("/api/video/{filename}")
async def get_video(filename: str):
    path = VIDEOS_DIR / filename
    if not path.exists():
        raise HTTPException(404, "Video not found")
    return FileResponse(str(path), media_type="video/mp4")


@app.post("/api/clip")
async def make_clip(req: ClipRequest):
    src = VIDEOS_DIR / req.video_filename
    if not src.exists():
        raise HTTPException(404, "Source video not found")

    # Determine start/end
    duration = _current_settings.clip_duration
    start: float
    end: float
    if _current_settings.clip_mode == "range" and req.in_mark is not None and req.out_mark is not None and req.out_mark > req.in_mark:
        start = max(0.0, req.in_mark)
        end = req.out_mark
    elif _current_settings.clip_mode == "centered":
        half = duration / 2.0
        start = max(0.0, req.current_time - half)
        end = start + duration
    else:  # backward
        start = max(0.0, req.current_time - duration)
        end = req.current_time

    label = sanitize_filename(req.label) or "unknown"
    save_label(label)

    dataset_root = Path(_current_settings.dataset_root)
    out_dir = dataset_root / "Training" / label
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = int(time.time() * 1000)
    base = src.stem
    out_name = f"{base}_{int(start*1000)}_{int(end*1000)}_{ts}.mp4"
    out_path = out_dir / out_name

    # Compute segment duration
    seg_dur = max(0.0, end - start)
    if seg_dur <= 0.0:
        raise HTTPException(400, "Invalid segment duration")

    # Try using system ffmpeg with explicit flags and capture stderr
    def _run(cmd: list[str]) -> tuple[int, str]:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return p.returncode, p.stderr.decode(errors='replace')

    ffbin = FFMPEG_BIN_PATH or shutil.which('ffmpeg') or 'ffmpeg'
    # Attempt 1: fast stream copy (may fail if cut is not at keyframe)
    cmd1 = [
        ffbin, '-hide_banner', '-nostdin',
        '-ss', f'{start:.3f}', '-i', str(src),
        '-t', f'{seg_dur:.3f}',
        '-c', 'copy', '-movflags', '+faststart',
        '-y', str(out_path)
    ]
    rc1, err1 = _run(cmd1)
    if rc1 != 0:
        # Attempt 2: re-encode with sane defaults and even-dimension safeguard
        cmd2 = [
            ffbin, '-hide_banner', '-nostdin',
            '-ss', f'{start:.3f}', '-i', str(src),
            '-t', f'{seg_dur:.3f}',
            '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
            '-c:a', 'aac', '-movflags', '+faststart',
            '-y', str(out_path)
        ]
        rc2, err2 = _run(cmd2)
        if rc2 != 0:
            # Attempt 3 (macOS-friendly): use VideoToolbox hardware encoder to avoid missing libx264
            cmd3 = [
                ffbin, '-hide_banner', '-nostdin',
                '-ss', f'{start:.3f}', '-i', str(src),
                '-t', f'{seg_dur:.3f}',
                '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
                '-c:v', 'h264_videotoolbox', '-b:v', '2M',
                '-c:a', 'aac', '-movflags', '+faststart',
                '-y', str(out_path)
            ]
            rc3, err3 = _run(cmd3)
            if rc3 != 0:
                errlog = DATA_DIR / "server.log"
                with errlog.open("a", encoding="utf-8") as f:
                    f.write("ffmpeg copy cmd: " + " ".join(cmd1) + "\n")
                    f.write("stderr1:\n" + err1 + "\n")
                    f.write("ffmpeg reencode cmd: " + " ".join(cmd2) + "\n")
                    f.write("stderr2:\n" + err2 + "\n")
                    f.write("ffmpeg vt hw cmd: " + " ".join(cmd3) + "\n")
                    f.write("stderr3:\n" + err3 + "\n")
                raise HTTPException(500, "ffmpeg failed to export clip")

    # Verify output exists and is non-empty
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise HTTPException(500, "Clip export produced no file")

    # Record undo path
    UNDO_PATH.write_text(str(out_path), encoding="utf-8")
    return {"ok": True, "path": str(out_path)}


@app.post("/api/undo")
async def undo_last():
    if not UNDO_PATH.exists():
        return {"ok": False}
    p = Path(UNDO_PATH.read_text(encoding="utf-8").strip())
    if p.exists():
        p.unlink()
    UNDO_PATH.unlink(missing_ok=True)
    return {"ok": True}


@app.get("/api/ping")
async def ping():
    return {"ok": True}


@app.post("/api/quit")
async def quit_server(background_tasks: BackgroundTasks):
    # Respond immediately, then request a graceful shutdown via SIGTERM
    def _shutdown():
        try:
            import signal
            time.sleep(0.2)
            os.kill(os.getpid(), signal.SIGTERM)
        except Exception:
            # As a last resort, hard-exit to avoid hanging
            os._exit(0)

    background_tasks.add_task(_shutdown)
    return {"ok": True}
