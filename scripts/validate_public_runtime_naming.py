#!/usr/bin/env python3
"""Reject development chronology in shipped runtime and current public prose."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / ".github" / "repository-profile.json"
SEED = ROOT / "data" / "demo_seed" / "offgrid_demo_seed.db"

CHRONOLOGY = re.compile(r"\bwave(?:[ _-]?\d+)\b", re.IGNORECASE)
WAVE_WORD = re.compile(r"\bwave\b", re.IGNORECASE)
LEGACY_SYMBOLS = (
    "Wave07ResolutionService",
    "Wave07ResolutionResult",
    "Wave08ContactResolutionService",
    "Wave08ContactResolutionResult",
    "Wave09CommercialWorkflowService",
    "Wave09CommercialWorkflowResult",
    "Wave10IntegrationService",
    "Wave10IntegrationResult",
    "wave10-integration-service",
    "wave08_public_research",
)
APPROVED_TOPICS = [
    "applied-ai",
    "commercial-intelligence",
    "sales-intelligence",
    "revenue-intelligence",
    "lead-qualification",
    "crm-automation",
    "construction-tech",
    "llm-grounding",
    "data-provenance",
    "fastapi",
    "react",
    "typescript",
    "openai",
    "aws",
    "docker",
]
APPROVED_DESCRIPTION = (
    "Evidence-backed commercial intelligence engine that turns construction project data "
    "into qualified, CRM-ready sales opportunities for Off Grid Innovation."
)


def current_surface_paths() -> list[Path]:
    paths: list[Path] = [ROOT / "Dockerfile", ROOT / "README.md"]
    for relative in (
        "apps/api/app",
        "apps/web/src",
        "docker",
        "config",
        "prompts",
        "infra",
        ".github",
        "docs",
    ):
        base = ROOT / relative
        if not base.exists():
            continue
        paths.extend(
            path
            for path in base.rglob("*")
            if path.is_file() and path.suffix.lower() in {".py", ".ts", ".tsx", ".md", ".yml", ".yaml", ".json", ".sh"}
        )
    return sorted(set(paths))


def historical_path_reference(line: str) -> bool:
    """Allow chronology only when it is part of an immutable historical artifact path."""

    normalized = line.replace("\\", "/")
    return bool(
        re.search(
            r"(?:tests|scripts|research|release|docs)/[^\s`]*wave[_-]?\d+[^\s`]*",
            normalized,
            re.IGNORECASE,
        )
    )


def historical_document(relative: str) -> bool:
    """Identify governance/history documents that intentionally preserve chronology."""

    return relative.startswith("docs/adr/") or relative in {
        "docs/GLOSSARY.md",
        "docs/MASTER_PROJECT_PLAN.md",
        "docs/PACK_PROTOCOL.md",
        "docs/PROJECT_CHARTER.md",
        "docs/PROJECT_SCOPE.md",
        "docs/REQUIREMENTS.md",
        "docs/WAVE_17_FULL_APPLICATION_INTEGRATION.md",
        "docs/WAVE_20_FINAL_INTEGRATION_AND_HANDOFF.md",
    }


def validate_surfaces() -> list[str]:
    errors: list[str] = []
    for path in current_surface_paths():
        text = path.read_text(encoding="utf-8-sig")
        relative = path.relative_to(ROOT).as_posix()
        for legacy in LEGACY_SYMBOLS:
            if legacy in text:
                errors.append(f"legacy runtime identifier in {relative}: {legacy}")
        for number, line in enumerate(text.splitlines(), start=1):
            if CHRONOLOGY.search(line) and not historical_path_reference(line):
                errors.append(f"development chronology in {relative}:{number}")
            if (
                WAVE_WORD.search(line)
                and not historical_document(relative)
                and not historical_path_reference(line)
            ):
                errors.append(f"development chronology terminology in {relative}:{number}")

    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    if "Install the exact reviewed frontend dependency graph." not in dockerfile:
        errors.append("Dockerfile lacks durable npm-lockfile rationale")
    return errors


def validate_seed() -> list[str]:
    connection = sqlite3.connect(SEED)
    try:
        dump = "\n".join(connection.iterdump())
    finally:
        connection.close()
    errors = [f"legacy runtime identifier in demo seed: {value}" for value in LEGACY_SYMBOLS if value in dump]
    if CHRONOLOGY.search(dump):
        errors.append("development chronology remains in demo seed")
    return errors


def validate_profile() -> list[str]:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    errors: list[str] = []
    if profile.get("description") != APPROVED_DESCRIPTION:
        errors.append("repository description differs from approved employer wording")
    if profile.get("topics") != APPROVED_TOPICS:
        errors.append("repository topics differ from the exact approved ordered set")
    homepage = profile.get("homepage")
    if not isinstance(homepage, str) or not homepage.startswith("https://"):
        errors.append("repository homepage is not a verified HTTPS URL")
    preview = ROOT / str(profile.get("social_preview", ""))
    if not preview.is_file() or preview.suffix.lower() != ".png":
        errors.append("repository social preview PNG is missing")
    return errors


def main() -> int:
    errors = validate_surfaces() + validate_seed() + validate_profile()
    print(json.dumps({"status": "PASS" if not errors else "FAIL", "errors": errors}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
