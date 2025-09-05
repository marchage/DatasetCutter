#!/usr/bin/env python3
"""
Repair DatasetCutter Training set videos for Create ML compatibility.

It scans a dataset root (default: ~/DatasetCutter/dataset/Training) and for each
*.mp4/*.mov/*.m4v it will:
  - Ensure H.264 video, yuv420p, even dimensions (no odd size), and moov at start (+faststart)
  - Optionally enforce constant frame rate (e.g., 30 fps)
  - Convert audio to AAC if present (or preserve, or drop on failure)

Heuristics:
  - If codec != h264 or pix_fmt != yuv420p or odd width/height -> re-encode video
  - Otherwise just remux with -c copy and +faststart

On macOS, if libx264 isn’t available, falls back to h264_videotoolbox.

Usage:
  python bin/repair_dataset.py --root ~/DatasetCutter/dataset/Training --cfr 30
  python bin/repair_dataset.py --root /path/to/Training --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple


ALLOWED_EXTS = {".mp4", ".mov", ".m4v"}


def find_ffmpeg() -> str:
    env = os.environ.get("FFMPEG_BINARY")
    if env and shutil.which(env):
        return env
    # prefer user-local
    user_local = Path.home() / "DatasetCutter" / "bin" / "ffmpeg"
    if user_local.exists() and os.access(user_local, os.X_OK):
        return str(user_local)
    # common macOS locations, then PATH
    for p in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return shutil.which("ffmpeg") or "ffmpeg"


def run(cmd: list[str]) -> Tuple[int, str, str]:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.returncode, p.stdout.decode(errors="replace"), p.stderr.decode(errors="replace")


def ffprobe_json(ffmpeg_bin: str, path: Path) -> Optional[dict]:
    ffprobe = ffmpeg_bin.replace("ffmpeg", "ffprobe")
    if ffprobe == ffmpeg_bin:
        ffprobe = "ffprobe"
    cmd = [
        ffprobe, "-v", "error",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        str(path),
    ]
    rc, out, err = run(cmd)
    if rc != 0:
        return None
    try:
        return json.loads(out or "{}")
    except Exception:
        return None


def needs_reencode(meta: dict) -> Tuple[bool, bool, dict]:
    """Return (reencode_video, reencode_audio, video_info)."""
    vinfo = {}
    re_v = False
    re_a = False
    streams = meta.get("streams") or []
    vstreams = [s for s in streams if s.get("codec_type") == "video"]
    astreams = [s for s in streams if s.get("codec_type") == "audio"]
    if vstreams:
        v = vstreams[0]
        vinfo = v
        codec = (v.get("codec_name") or "").lower()
        pix = (v.get("pix_fmt") or "").lower()
        w = int(v.get("width") or 0)
        h = int(v.get("height") or 0)
        if codec != "h264" or pix != "yuv420p" or (w % 2 != 0) or (h % 2 != 0):
            re_v = True
    else:
        # no video stream? definitely needs work
        re_v = True
    if astreams:
        a = astreams[0]
        acodec = (a.get("codec_name") or "").lower()
        if acodec != "aac":
            re_a = True
    # if no audio, that's ok; we won't force add audio
    return re_v, re_a, vinfo


def repair_file(ffbin: str, path: Path, *, cfr: Optional[int], dry_run: bool, backup_ext: str) -> bool:
    meta = ffprobe_json(ffbin, path) or {}
    re_v, re_a, vinfo = needs_reencode(meta)

    tmp = path.with_suffix(path.suffix + ".tmp.mp4")
    backup = path.with_suffix(path.suffix + backup_ext)

    # Build command
    if not re_v and not re_a:
        # remux with +faststart
        cmd = [
            ffbin, "-hide_banner", "-nostdin",
            "-i", str(path),
            "-map", "0:v:0",
        ]
        # keep first audio if exists
        has_audio = any(s.get("codec_type") == "audio" for s in (meta.get("streams") or []))
        if has_audio:
            cmd += ["-map", "0:a:0"]
        cmd += [
            "-c", "copy",
            "-movflags", "+faststart",
            "-y", str(tmp)
        ]
    else:
        # re-encode video (libx264 -> fallback to videotoolbox if needed)
        vf = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
        vcodec_primary = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-profile:v", "main", "-level", "4.1", "-pix_fmt", "yuv420p"]
        if cfr and cfr > 0:
            vcodec_primary += ["-r", str(cfr)]
        acodec = ["-c:a", "aac", "-b:a", "128k"] if re_a else ["-c:a", "copy"]
        cmd = [
            ffbin, "-hide_banner", "-nostdin",
            "-i", str(path),
            "-vf", vf,
            *vcodec_primary,
            *acodec,
            "-movflags", "+faststart",
            "-y", str(tmp)
        ]

    def try_run(cmd) -> Tuple[bool, str]:
        rc, out, err = run(cmd)
        return rc == 0, err or out

    if dry_run:
        print(f"[DRY] Would {'re-encode' if (re_v or re_a) else 'remux'}: {path}")
        return True

    ok, log = try_run(cmd)
    if not ok and (re_v or re_a):
        # try VideoToolbox fallback
        vf = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
        vcodec_fallback = ["-c:v", "h264_videotoolbox", "-b:v", "2M", "-pix_fmt", "yuv420p"]
        if cfr and cfr > 0:
            vcodec_fallback += ["-r", str(cfr)]
        acodec = ["-c:a", "aac", "-b:a", "128k"] if re_a else ["-c:a", "copy"]
        cmd2 = [
            ffbin, "-hide_banner", "-nostdin",
            "-i", str(path),
            "-vf", vf,
            *vcodec_fallback,
            *acodec,
            "-movflags", "+faststart",
            "-y", str(tmp)
        ]
        ok, log2 = try_run(cmd2)
        if not ok:
            print(f"[ERR] Failed to repair {path}\n{log}\n{log2}")
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass
            return False

    # Verify decode pass (smoke test)
    check = [ffbin, "-v", "error", "-i", str(tmp), "-f", "null", "-"]
    rc, out, err = run(check)
    if rc != 0:
        print(f"[ERR] Post-repair decode check failed for {path}:\n{err}")
        try:
            tmp.unlink()
        except Exception:
            pass
        return False

    # Replace original (backup)
    try:
        if not backup_ext:
            path.unlink()
        else:
            if backup.exists():
                backup.unlink()
            path.rename(backup)
        tmp.rename(path)
    except Exception as e:
        print(f"[ERR] Could not replace {path}: {e}")
        return False

    print(f"[OK] Repaired {path}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Repair DatasetCutter Training videos for Create ML.")
    default_root = Path.home() / "DatasetCutter" / "dataset" / "Training"
    parser.add_argument("--root", type=Path, default=default_root, help="Path to Training directory (contains class subfolders)")
    parser.add_argument("--exts", default=",".join(sorted(ALLOWED_EXTS)), help="Comma-separated list of extensions to include")
    parser.add_argument("--cfr", type=int, default=30, help="Force constant frame rate (e.g., 30). Set 0 to keep source VFR")
    parser.add_argument("--dry-run", action="store_true", help="Only print actions; don’t modify files")
    parser.add_argument("--backup-ext", default=".bak", help="Backup extension for originals (set empty string to delete originals)")
    args = parser.parse_args()

    root: Path = args.root
    if not root.exists() or not root.is_dir():
        print(f"[ERR] Root not found or not a directory: {root}")
        raise SystemExit(2)
    exts = {e if e.startswith(".") else "." + e for e in (args.exts.split(",") if args.exts else [])}
    exts = exts or set(ALLOWED_EXTS)

    ffbin = find_ffmpeg()
    print(f"Using ffmpeg: {ffbin}")

    total = 0
    repaired = 0
    skipped = 0
    for cls in sorted([p for p in root.iterdir() if p.is_dir()]):
        for vid in sorted(cls.iterdir()):
            if not vid.is_file() or vid.suffix.lower() not in exts:
                continue
            total += 1
            ok = repair_file(ffbin, vid, cfr=(args.cfr if args.cfr and args.cfr > 0 else None), dry_run=args.dry_run, backup_ext=args.backup_ext)
            if ok:
                repaired += 1
            else:
                skipped += 1

    print(f"\nDone. processed={total} repaired={repaired} failed={skipped}")


if __name__ == "__main__":
    main()
