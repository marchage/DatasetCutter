from __future__ import annotations

import os
import shutil
import time
import sys
from pathlib import Path
import json
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import ffmpeg
import subprocess
from datetime import datetime

# --- Ensure ffmpeg binary is discoverable even in bundled app (limited PATH) ---
FFMPEG_BIN_PATH: Optional[str] = None

def _ensure_ffmpeg_in_path() -> None:
    candidates = []
    # Env override
    env_bin = os.environ.get("FFMPEG_BINARY")
    if env_bin:
        candidates.append(env_bin)
    # Bundled ffmpeg inside the app (PyInstaller)
    try:
        # Compute a local app root (works before APP_ROOT global is set)
        from pathlib import Path as _Path
        _bundle_root = getattr(sys, "_MEIPASS", None)
        app_root_local = _Path(_bundle_root) if _bundle_root else _Path(__file__).resolve().parent.parent
        # Prefer arch-specific dirs when bundled
        import platform as _plat
        arch = _plat.machine()
        appbin = app_root_local / "app" / "bin"
        if arch:
            # Prefer ffmpeg in app/bin/<arch>/ffmpeg and set its lib path
            ff = appbin / arch / "ffmpeg"
            lib = appbin / arch / "lib"
            if ff.exists():
                # Prepend lib dir to DYLD_LIBRARY_PATH for child processes
                if lib.exists():
                    os.environ["DYLD_LIBRARY_PATH"] = f"{lib}:{os.environ.get('DYLD_LIBRARY_PATH','')}"
                candidates.append(str(ff))
        # Fallbacks
        candidates.append(str(appbin / "ffmpeg"))
    except Exception:
        pass
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

# Export normalization controls (can be overridden by env vars)
EXPORT_ALWAYS_REENCODE = os.environ.get("DC_ALWAYS_REENCODE", "1") not in {"0", "false", "False"}
try:
    _cfr_env = os.environ.get("DC_EXPORT_CFR", "30")
    EXPORT_CFR = int(_cfr_env) if _cfr_env else 30
except Exception:
    EXPORT_CFR = 30
EXPORT_DROP_AUDIO = os.environ.get("DC_EXPORT_DROP_AUDIO", "0") in {"1", "true", "True"}

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

def _log(msg: str) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with (DATA_DIR / "server.log").open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass

# Basic startup diagnostics (with a clear run separator)
try:
    _log("===== START =====")
    _log(f"IN_BUNDLE={IN_BUNDLE} APP_ROOT={APP_ROOT}")
    _log(f"BASE_DIR={BASE_DIR} DATA_DIR={DATA_DIR} VIDEOS_DIR={VIDEOS_DIR}")
    _log(f"PATH={os.environ.get('PATH','')}")
    _log(f"FFMPEG_BIN_PATH={FFMPEG_BIN_PATH}")
    try:
        ffbin = FFMPEG_BIN_PATH or shutil.which('ffmpeg') or 'ffmpeg'
        ver = subprocess.run([ffbin, '-version'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=3)
        _log("ffmpeg -version:\n" + ver.stdout.decode(errors='replace'))
    except Exception as _e:
        _log(f"ffmpeg -version failed: {_e}")
except Exception:
    pass

app = FastAPI(title="MP4 Dataset Cutter")

# Static mounts (from app resources)
app.mount("/static", StaticFiles(directory=str(APP_ROOT / "app" / "static")), name="static")
app.mount("/videos", StaticFiles(directory=str(VIDEOS_DIR)), name="videos")
# Optionally serve repository assets (icons) if present
try:
    assets_dir = APP_ROOT / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
except Exception:
    pass

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
    clip_duration: float = 5.0  # seconds
    clip_mode: str = "backward"  # "backward" or "centered" or "range" (I/O marks)
    # Optional: target clips per label (used by UI coloring; not persisted via POST yet)
    target_per_label: int = 50
    margin_per_label: int = 5


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
UNDO_PATH = DATA_DIR / "undo.txt"  # newline-delimited stack (last line = most recent)

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


# --- Undo stack helpers (max depth 10) ---
MAX_UNDO = 10

def _read_undo_stack() -> List[Path]:
    if not UNDO_PATH.exists():
        return []
    try:
        lines = [l.strip() for l in UNDO_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
        return [Path(l) for l in lines]
    except Exception:
        return []

def _write_undo_stack(items: List[Path]) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        text = "\n".join(str(p) for p in items[-MAX_UNDO:]) + ("\n" if items else "")
        UNDO_PATH.write_text(text, encoding="utf-8")
    except Exception:
        pass

def _push_undo(p: Path) -> None:
    items = _read_undo_stack()
    items.append(p)
    if len(items) > MAX_UNDO:
        items = items[-MAX_UNDO:]
    _write_undo_stack(items)

def _pop_undo() -> Optional[Path]:
    items = _read_undo_stack()
    if not items:
        return None
    last = items[-1]
    _write_undo_stack(items[:-1])
    return last


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "settings": _current_settings.model_dump()})


@app.get("/api/settings")
async def get_settings():
    return _current_settings


@app.post("/api/settings")
async def update_settings(
    dataset_root: str = Form(None),
    clip_duration: float = Form(None),
    clip_mode: str = Form(None),
    label_threshold: int = Form(None),
    label_margin: int = Form(None),
):
    global _current_settings
    if dataset_root:
        _current_settings.dataset_root = dataset_root
        Path(dataset_root, "Training").mkdir(parents=True, exist_ok=True)
    if clip_duration:
        _current_settings.clip_duration = float(clip_duration)
    if clip_mode in {"backward", "centered", "range"}:
        _current_settings.clip_mode = clip_mode
    if label_threshold is not None:
        try:
            _current_settings.target_per_label = int(label_threshold)
        except Exception:
            pass
    if label_margin is not None:
        try:
            _current_settings.margin_per_label = int(label_margin)
        except Exception:
            pass
    return _current_settings


@app.get("/api/labels")
async def get_labels():
    return {"labels": load_labels()}


def _count_clips_in_dir(d: Path) -> int:
    if not d.is_dir():
        return 0
    n = 0
    for p in d.iterdir():
        if not p.is_file():
            continue
        name = p.name
        if name.startswith(".") or name.lower().startswith("._"):
            continue
        if p.suffix.lower() in ALLOWED_VIDEO_EXTS:
            n += 1
    return n


# --- Media compatibility helpers ---
def _ffprobe_json(path: Path) -> Optional[dict]:
    try:
        ffprobe = (FFMPEG_BIN_PATH or shutil.which('ffmpeg') or 'ffmpeg').replace('ffmpeg', 'ffprobe')
        if not ffprobe:
            ffprobe = 'ffprobe'
        cmd = [ffprobe, '-v', 'error', '-print_format', 'json', '-show_streams', '-show_format', str(path)]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.returncode != 0:
            return None
        return json.loads(p.stdout.decode(errors='replace') or '{}')
    except Exception:
        return None


def _is_create_ml_friendly(meta: Optional[dict]) -> bool:
    if not meta:
        return False
    streams = meta.get('streams') or []
    vstreams = [s for s in streams if s.get('codec_type') == 'video']
    if not vstreams:
        return False
    v = vstreams[0]
    codec = (v.get('codec_name') or '').lower()
    pix = (v.get('pix_fmt') or '').lower()
    try:
        w = int(v.get('width') or 0); h = int(v.get('height') or 0)
    except Exception:
        w = h = 0
    # Create ML-friendly baseline: H.264 + yuv420p + even dimensions
    if codec != 'h264':
        return False
    if pix and pix != 'yuv420p':
        return False
    if (w % 2 != 0) or (h % 2 != 0):
        return False
    return True


@app.get("/api/label_stats")
async def label_stats(threshold: Optional[int] = None, margin: Optional[int] = None):
    """Return per-label counts and a status for UI coloring.

    Status rules (with given threshold and margin):
      - count >= threshold + margin: "good"
      - threshold - margin <= count < threshold + margin: "warn"
      - count < threshold - margin: "bad"
    """
    labels = load_labels()
    thr = int(threshold if threshold is not None else _current_settings.target_per_label)
    mar = int(margin if margin is not None else _current_settings.margin_per_label)
    items = []
    root = Path(_current_settings.dataset_root) / "Training"
    total = 0
    minv = None
    maxv = None
    for label in labels:
        s = sanitize_filename(label)
        count = _count_clips_in_dir(root / s)
        total += count
        minv = count if minv is None else min(minv, count)
        maxv = count if maxv is None else max(maxv, count)
        status = "good" if count >= thr + mar else ("warn" if count >= thr - mar else "bad")
        items.append({"label": label, "sanitized": s, "count": count, "status": status})
    classes = len(labels)
    mean = (total / classes) if classes else 0.0
    return {
        "threshold": thr,
        "margin": mar,
        "summary": {"classes": classes, "total": total, "mean": mean, "min": (minv or 0), "max": (maxv or 0)},
        "items": items,
    }


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
    rc1 = -1
    err1 = ''
    if not EXPORT_ALWAYS_REENCODE:
        # Attempt 1: fast stream copy (may fail if cut is not at keyframe or incompatible pixel format)
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
            '-profile:v', 'main', '-level', '4.1', '-pix_fmt', 'yuv420p',
            *(['-r', str(EXPORT_CFR)] if EXPORT_CFR and EXPORT_CFR > 0 else []),
            *( ['-an'] if EXPORT_DROP_AUDIO else ['-c:a', 'aac'] ),
            '-movflags', '+faststart',
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
                '-c:v', 'h264_videotoolbox', '-b:v', '2M', '-pix_fmt', 'yuv420p',
                *(['-r', str(EXPORT_CFR)] if EXPORT_CFR and EXPORT_CFR > 0 else []),
                *( ['-an'] if EXPORT_DROP_AUDIO else ['-c:a', 'aac'] ),
                '-movflags', '+faststart',
                '-y', str(out_path)
            ]
            rc3, err3 = _run(cmd3)
            if rc3 != 0:
                _log("ffmpeg copy cmd: " + " ".join(cmd1))
                _log("stderr1:\n" + err1)
                _log("ffmpeg reencode cmd: " + " ".join(cmd2))
                _log("stderr2:\n" + err2)
                _log("ffmpeg vt hw cmd: " + " ".join(cmd3))
                _log("stderr3:\n" + err3)
                raise HTTPException(500, "ffmpeg failed to export clip")
    else:
        # Copy succeeded. Verify compatibility; re-encode if not Create ML-friendly.
        try:
            meta = _ffprobe_json(out_path)
            if not _is_create_ml_friendly(meta):
                _log(f"Post-copy not friendly; re-encoding {out_path}")
                tmp = out_path.with_suffix(out_path.suffix + '.tmp')
                cmd2 = [
                    ffbin, '-hide_banner', '-nostdin',
                    '-i', str(out_path),
                    '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
                    '-profile:v', 'main', '-level', '4.1', '-pix_fmt', 'yuv420p',
                    *(['-r', str(EXPORT_CFR)] if EXPORT_CFR and EXPORT_CFR > 0 else []),
                    *( ['-an'] if EXPORT_DROP_AUDIO else ['-c:a', 'aac'] ),
                    '-movflags', '+faststart',
                    '-y', str(tmp)
                ]
                rc2, err2 = _run(cmd2)
                if rc2 != 0:
                    cmd3 = [
                        ffbin, '-hide_banner', '-nostdin',
                        '-i', str(out_path),
                        '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
                        '-c:v', 'h264_videotoolbox', '-b:v', '2M', '-pix_fmt', 'yuv420p',
                        *(['-r', str(EXPORT_CFR)] if EXPORT_CFR and EXPORT_CFR > 0 else []),
                        *( ['-an'] if EXPORT_DROP_AUDIO else ['-c:a', 'aac'] ),
                        '-movflags', '+faststart',
                        '-y', str(tmp)
                    ]
                    rc3, err3 = _run(cmd3)
                    if rc3 != 0:
                        _log("post-copy reencode stderr2:\n" + err2)
                        _log("post-copy vt stderr3:\n" + err3)
                        raise HTTPException(500, "ffmpeg failed to normalize clip")
                # replace original
                try:
                    out_path.unlink(missing_ok=True)
                except TypeError:
                    # Python <3.8 fallback
                    if out_path.exists():
                        out_path.unlink()
                tmp.rename(out_path)
        except HTTPException:
            raise
        except Exception as e:
            _log(f"compat check error: {e}")

    # Verify output exists and is non-empty
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise HTTPException(500, "Clip export produced no file")

    # Record undo (stack, max depth) and log success
    _push_undo(out_path)
    _log(f"Clip OK: {out_path}")
    return {"ok": True, "path": str(out_path)}


@app.post("/api/undo")
async def undo_last():
    p = _pop_undo()
    if not p:
        return {"ok": False}
    try:
        if p.exists():
            p.unlink()
        _log(f"Undo OK: deleted {p}")
    except Exception as e:
        _log(f"Undo error for {p}: {e}")
        return {"ok": False}
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
