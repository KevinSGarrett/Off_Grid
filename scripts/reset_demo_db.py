#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED = ROOT / "data/demo_seed/offgrid_demo_seed.db"
DEFAULT_TARGET = ROOT / "data/private/offgrid.db"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="Reset a runtime demo DB to the immutable Wave 17 seed snapshot.")
    ap.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    ap.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    args = ap.parse_args()
    if not args.seed.is_file():
        raise SystemExit(f"Seed not found: {args.seed}")
    args.target.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.target.with_suffix(args.target.suffix + ".tmp")
    shutil.copyfile(args.seed, tmp)
    tmp.replace(args.target)
    print(f"reset={args.target}")
    print(f"sha256={digest(args.target)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
