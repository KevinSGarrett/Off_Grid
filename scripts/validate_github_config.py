#!/usr/bin/env python3
"""Wave 15 repository-control validation.

This is intentionally dependency-light and checks the repository contracts we can validate locally
without a GitHub remote. It does not pretend to prove that a future remote ruleset is enabled.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_CI_JOB_NAMES = {
    "Repository Policy",
    "Backend Test Matrix",
    "Backend Static Quality",
    "Dependency and Secret Scan",
    "Golden Regression",
    "Frontend Typecheck and Build",
    "Docker Readiness",
}
REQUIRED_ECOSYSTEMS = {"pip", "npm", "github-actions"}
REQUIRED_PRIVATE_IGNORES = {
    "context/private_source_documents/",
    "context/original_chat_logs/",
    "data/private/",
}


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate() -> list[str]:
    errors: list[str] = []

    workflow_dir = ROOT / ".github" / "workflows"
    workflows = sorted(list(workflow_dir.glob("*.yml")) + list(workflow_dir.glob("*.yaml")))
    require(bool(workflows), "No GitHub Actions workflows found", errors)

    all_job_names: set[str] = set()
    for workflow in workflows:
        raw = workflow.read_text(encoding="utf-8")
        require(
            "pull_request_target" not in raw,
            f"Unsafe pull_request_target trigger in {workflow}",
            errors,
        )
        require("write-all" not in raw, f"Overbroad write-all permission in {workflow}", errors)
        require(
            re.search(r"(?m)^permissions:\s*\n\s+contents:\s*read\s*$", raw) is not None,
            f"{workflow} must declare top-level contents: read permissions",
            errors,
        )
        try:
            data = load_yaml(workflow) or {}
        except (OSError, yaml.YAMLError) as exc:  # pragma: no cover - defensive diagnostics
            errors.append(f"Invalid workflow YAML {workflow}: {exc}")
            continue
        jobs = data.get("jobs", {}) if isinstance(data, dict) else {}
        require(isinstance(jobs, dict) and bool(jobs), f"{workflow} has no jobs", errors)
        if isinstance(jobs, dict):
            for job_id, job in jobs.items():
                require(isinstance(job, dict), f"{workflow}:{job_id} must be a mapping", errors)
                if isinstance(job, dict):
                    name = job.get("name")
                    require(bool(name), f"{workflow}:{job_id} needs stable display name", errors)
                    if name:
                        if name in all_job_names:
                            errors.append(f"Duplicate workflow job display name: {name}")
                        all_job_names.add(str(name))

    missing_jobs = REQUIRED_CI_JOB_NAMES - all_job_names
    require(not missing_jobs, f"Missing required CI jobs: {sorted(missing_jobs)}", errors)

    dependabot = load_yaml(ROOT / ".github" / "dependabot.yml")
    require(
        isinstance(dependabot, dict) and dependabot.get("version") == 2,
        "dependabot.yml must use version: 2",
        errors,
    )
    updates = dependabot.get("updates", []) if isinstance(dependabot, dict) else []
    ecosystems = {item.get("package-ecosystem") for item in updates if isinstance(item, dict)}
    require(
        REQUIRED_ECOSYSTEMS <= ecosystems,
        f"Dependabot ecosystems missing: {sorted(REQUIRED_ECOSYSTEMS - ecosystems)}",
        errors,
    )

    codeowners = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    require("@KevinSGarrett" in codeowners, "CODEOWNERS lacks repository owner", errors)
    require(
        re.search(r"(?m)^/\.github/\s+@KevinSGarrett\s*$", codeowners) is not None,
        "CODEOWNERS must explicitly protect .github/",
        errors,
    )

    pr_template = ROOT / ".github" / "pull_request_template.md"
    require(pr_template.exists(), "PR template missing", errors)
    if pr_template.exists():
        pr_text = pr_template.read_text(encoding="utf-8").lower()
        for phrase in ("privacy", "golden", "external-write", "make test"):
            require(phrase in pr_text, f"PR template missing control phrase: {phrase}", errors)

    issue_dir = ROOT / ".github" / "ISSUE_TEMPLATE"
    issue_templates = sorted(issue_dir.glob("*.yml"))
    require(len(issue_templates) >= 4, "Expected at least four structured issue templates", errors)

    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for required in REQUIRED_PRIVATE_IGNORES:
        require(required in gitignore, f".gitignore missing private path: {required}", errors)

    for rel in ("CONTRIBUTING.md", "SECURITY.md"):
        require((ROOT / rel).exists(), f"Required Wave 15 artifact missing: {rel}", errors)

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("WAVE15_GITHUB_CONFIG_FAIL")
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("WAVE15_GITHUB_CONFIG_PASS")
    print(f"validated_ci_jobs={len(REQUIRED_CI_JOB_NAMES)}")
    print(f"validated_dependabot_ecosystems={len(REQUIRED_ECOSYSTEMS)}")
    print("private_source_gitignore=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
