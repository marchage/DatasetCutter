#!/usr/bin/env python3
"""
Dataset focus helper: list labels (folders) under a clip count threshold and suggest where to focus.

Defaults to the app's dataset path: ~/DatasetCutter/dataset/Training and threshold 50.

Examples:
  # Use defaults (~/DatasetCutter/dataset/Training, threshold 50)
  python bin/dataset_focus.py

  # Point at a specific dataset root and threshold
  python bin/dataset_focus.py --root /path/to/dataset/Training --threshold 100 --top 10
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Tuple
import sys


ALLOWED_EXTS = {".mp4", ".mov", ".m4v"}


def count_clips(label_dir: Path, allowed_exts: set[str]) -> int:
    if not label_dir.is_dir():
        return 0
    n = 0
    for p in label_dir.iterdir():
        if not p.is_file():
            continue
        name = p.name
        if name.startswith(".") or name.lower().startswith("._"):
            continue
        if p.suffix.lower() in allowed_exts:
            n += 1
    return n


def scan_dataset(root: Path, allowed_exts: set[str]) -> Dict[str, int]:
    if not root.exists():
        raise FileNotFoundError(f"Dataset path not found: {root}")
    counts: Dict[str, int] = {}
    for child in sorted(root.iterdir()):
        if child.is_dir():
            counts[child.name] = count_clips(child, allowed_exts)
    return counts


def summarize(counts: Dict[str, int]) -> Tuple[int, int, float, int, int]:
    if not counts:
        return (0, 0, 0.0, 0, 0)
    vals = list(counts.values())
    total = sum(vals)
    classes = len(vals)
    mean = total / classes if classes else 0.0
    return (classes, total, mean, min(vals), max(vals))


def main(argv: List[str] | None = None) -> int:
    home_default = Path.home() / "DatasetCutter" / "dataset" / "Training"
    parser = argparse.ArgumentParser(description="Report labels below a clip-count threshold.")
    parser.add_argument(
        "--root",
        type=Path,
        default=home_default,
        help=f"Dataset Training root (default: {home_default})",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=50,
        help="Minimum desired clips per label (default: 50)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=0,
        help="Only show the first N under-threshold labels (0 = all)",
    )
    parser.add_argument(
        "--ext",
        action="append",
        dest="exts",
        help="Extra file extension(s) to include (e.g., --ext .avi). Can repeat.",
    )
    args = parser.parse_args(argv)

    allowed_exts = set(ALLOWED_EXTS)
    if args.exts:
        for e in args.exts:
            if not e.startswith("."):
                e = "." + e
            allowed_exts.add(e.lower())

    try:
        counts = scan_dataset(args.root, allowed_exts)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2

    classes, total, mean, minv, maxv = summarize(counts)
    print(f"Dataset: {args.root}")
    print(f"Classes: {classes}  Total clips: {total}  Mean/cls: {mean:.1f}  Min: {minv}  Max: {maxv}")
    print("")

    under: List[Tuple[str, int, int]] = []  # (label, count, deficit)
    for label, n in counts.items():
        if n < args.threshold:
            under.append((label, n, args.threshold - n))

    under.sort(key=lambda t: (t[1], t[0]))  # by count asc, then name

    if not under:
        print(f"All labels meet the threshold (>= {args.threshold}). Nice!")
        return 0

    print(f"Labels below threshold (< {args.threshold}) — focus suggestions:")
    print("")
    header = f"{'label':30}  {'count':>6}  {'need':>6}"
    print(header)
    print("-" * len(header))

    shown = 0
    for label, n, deficit in under:
        print(f"{label:30}  {n:6d}  {deficit:6d}")
        shown += 1
        if args.top and shown >= args.top:
            break

    print("")
    total_needed = sum(d for _, _, d in under)
    print(f"Total clips needed to lift all under-threshold labels to {args.threshold}: {total_needed}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
