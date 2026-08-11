"""Fail-closed consistency rules for current-state handoff documents."""

from __future__ import annotations

from pathlib import Path

CURRENT_CLAIM_SOURCES = {
    "engineering/README.md": "README.md",
    "operator/FINAL_READINESS_REPORT.md": "release/FINAL_READINESS_REPORT.md",
    "operator/FINAL_GAP_REPORT.md": "release/FINAL_GAP_REPORT.md",
    "operator/CLEAN_ROOM_VERIFICATION.md": "release/CLEAN_ROOM_VERIFICATION.md",
    "operator/WAVE_20_REQUIREMENT_COVERAGE.md": "project/WAVE_20_REQUIREMENT_COVERAGE.md",
    "codex/README.md": "codex/README.md",
}

CURRENT_CLAIM_RULES = {
    "engineering/README.md": {
        "required": (
            "Windows PowerShell",
            "py -3.12 -m venv .venv",
            ".\\.venv\\Scripts\\python.exe scripts\\run_public_test_matrix.py",
            "python3.12 -m venv .venv",
            ".venv/bin/python scripts/run_public_test_matrix.py",
        ),
        "forbidden": ("\npython -m venv .venv",),
    },
    "operator/FINAL_READINESS_REPORT.md": {
        "required": (
            "RELEASE CANDIDATE",
            "Canonical Python suite: `223 passed`",
            "all seven required checks passed",
            "OGCI-TASK-035",
        ),
        "forbidden": (
            "Canonical Python suite: `217 passed`",
            "Canonical Python suite: `218 passed`",
            "Canonical Python suite: `220 passed`",
            "Canonical Python suite: `221 passed`",
            "Canonical Python suite: `222 passed`",
        ),
    },
    "operator/FINAL_GAP_REPORT.md": {
        "required": (
            "| Python regression | PASS | 223 canonical tests",
            "Seven strict protected checks green",
            "RELEASE CANDIDATE",
            "OGCI-TASK-035",
        ),
        "forbidden": (
            "217 canonical tests",
            "218 canonical tests",
            "220 canonical tests",
            "221 canonical tests",
            "222 canonical tests",
        ),
    },
    "operator/CLEAN_ROOM_VERIFICATION.md": {
        "required": (
            "At the Wave 17 clean-room baseline",
            "complete `223`-test collection",
            "historical clean-room result remains tied to commit",
            "On Windows PowerShell",
            "py -3.12 -m venv .venv",
            "python3.12 -m venv .venv",
        ),
        "forbidden": (
            "\npython -m venv .venv",
            "complete `221`-test collection",
            "complete `222`-test collection",
        ),
    },
    "operator/WAVE_20_REQUIREMENT_COVERAGE.md": {
        "required": (
            "| Install proof | **PASS** |",
            "| Frontend build proof | **PASS** |",
            "| Container build/run proof | **PASS** |",
            "| Browser-on-image proof | **PASS** |",
            "| Secret/privacy scan controls | **PASS** |",
            "release state remains `RELEASE CANDIDATE`",
            "time-gated Task 035 is pending",
        ),
        "forbidden": (
            "BLOCKED: npm",
            "BLOCKED: Docker",
            "| Frontend build proof | **BLOCKED** |",
            "| Browser-on-image proof | **BLOCKED** |",
            "image scan BLOCKED",
            "release state remains BLOCKED",
        ),
    },
    "codex/README.md": {
        "required": (
            "last contiguous completed wave is **20**",
            "Wave 17 release proof is **PASS**",
            "application is a **RELEASE CANDIDATE**",
            "`OGCI-TASK-035`",
            "Historical prompts and manifests preserve the state observed",
        ),
        "forbidden": (
            "last contiguous completed wave is 16",
            "Wave 17 is blocked only",
        ),
    },
}


def load_current_claim_entries(root: Path) -> dict[str, bytes]:
    """Load the current-state sources using their handoff archive names."""
    return {
        archive_name: (root / source_path).read_bytes()
        for archive_name, source_path in CURRENT_CLAIM_SOURCES.items()
    }


def validate_current_claims(entries: dict[str, bytes]) -> list[str]:
    """Return exact current-claim violations; an empty list is PASS."""
    errors: list[str] = []
    for name, rules in CURRENT_CLAIM_RULES.items():
        data = entries.get(name)
        if data is None:
            errors.append(f"current-claim document missing: {name}")
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            errors.append(f"current-claim document is not UTF-8: {name}")
            continue
        folded = text.casefold()
        for phrase in rules["required"]:
            if phrase.casefold() not in folded:
                errors.append(f"current claim missing in {name}: {phrase}")
        for phrase in rules["forbidden"]:
            if phrase.casefold() in folded:
                errors.append(f"stale current claim in {name}: {phrase}")
    return errors
