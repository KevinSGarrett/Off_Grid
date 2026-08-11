#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))

from app.pipeline.synthetic import generate_synthetic_projects, specs_as_jsonable  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate clearly labeled synthetic Off Grid scale fixtures.")
    parser.add_argument("--count", type=int, default=300)
    parser.add_argument("--seed", type=int, default=1401)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = {
        "dataset": "SYNTHETIC",
        "purpose": "Scale/load testing only; never employer factual evidence.",
        "count": args.count,
        "seed": args.seed,
        "projects": specs_as_jsonable(generate_synthetic_projects(count=args.count, seed=args.seed)),
    }
    text = json.dumps(payload, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        print(args.output)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
