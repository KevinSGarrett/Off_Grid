#!/usr/bin/env python3
"""Fail if Git tracks files that belong only in private cumulative continuity packs."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PREFIXES = (
    "chat_logs/",
    "context/private_source_documents/",
    "context/original_chat_logs/",
    "data/private/",
    "data/raw/",
    "inbox/",
    "archive/",
)
FORBIDDEN_EXACT = {".env", ".env.local", ".env.production", ".env.development"}
FORBIDDEN_SUFFIXES = (".pem", ".key")


def git_files() -> list[str] | None:
    if not (ROOT / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-git", action="store_true")
    args = parser.parse_args()

    tracked = git_files()
    if tracked is None:
        if args.require_git:
            print("GIT_PRIVACY_FAIL: .git directory unavailable")
            return 1
        print("GIT_PRIVACY_SKIP_TRACKED_CHECK: cumulative archives intentionally exclude .git")
        tracked = []

    violations: list[str] = []
    for path in tracked:
        lower = path.lower()
        if lower in FORBIDDEN_EXACT or lower.startswith(FORBIDDEN_PREFIXES):
            violations.append(path)
        if lower.endswith(FORBIDDEN_SUFFIXES):
            violations.append(path)

    required_ignore = [
        "/Chat_Logs/",
        "context/private_source_documents/",
        "context/original_chat_logs/",
        "data/private/",
    ]
    ignore_text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for item in required_ignore:
        if item not in ignore_text:
            violations.append(f".gitignore missing {item}")

    if violations:
        print("GIT_PRIVACY_FAIL")
        for violation in sorted(set(violations)):
            print(f"FORBIDDEN: {violation}")
        return 1

    print("GIT_PRIVACY_PASS")
    print(f"tracked_files_checked={len(tracked)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
