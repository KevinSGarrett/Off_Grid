from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load_validator():
    path = ROOT / "scripts" / "validate_github_config.py"
    spec = importlib.util.spec_from_file_location("wave15_validator", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_wave15_repository_configuration_validator_passes() -> None:
    validator = _load_validator()
    assert validator.validate() == []


def test_private_continuity_paths_are_explicitly_ignored() -> None:
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for path in (
        "/Chat_Logs/",
        "context/private_source_documents/",
        "context/original_chat_logs/",
        "data/private/",
    ):
        assert path in text


def test_top_level_chat_logs_are_excluded_from_docker_and_git_validation() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    validator = (ROOT / "scripts" / "validate_git_privacy.py").read_text(encoding="utf-8")

    assert dockerignore.startswith("# Send only the files consumed by Dockerfile")
    assert "**\n" in dockerignore
    assert '"chat_logs/",' in validator
    assert '"/Chat_Logs/",' in validator


def test_public_repository_excludes_local_control_and_design_reference_material() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "/CURRENT_TASK.md" in gitignore
    assert "/template/" in gitignore


def test_public_repository_includes_only_the_sanitized_deployment_seed() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "/data/demo_seed/*" in gitignore
    assert "!/data/demo_seed/offgrid_demo_seed.db" in gitignore


def test_ci_uses_read_only_default_permissions_and_safe_pr_trigger() -> None:
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "permissions:\n  contents: read" in text
    assert "pull_request_target" not in text
    assert "write-all" not in text
    assert "name: Repository Policy" in text
    assert "name: Backend Test Matrix" in text
    assert "name: Frontend Typecheck and Build" in text
    assert "name: Record static-analysis tool versions" in text
    assert "continue-on-error: true" not in text


def test_public_ci_does_not_depend_on_ignored_continuity_or_private_source_artifacts() -> None:
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    for forbidden in (
        "scripts/run_wave",
        "scripts/build_wave",
        "scripts/verify_wave",
        "tests/golden\n",
        "context/private_source_documents",
        "research/WAVE_",
        "release/WAVE_",
    ):
        assert forbidden not in text


def test_dependabot_covers_python_web_and_actions() -> None:
    data = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8"))
    assert data["version"] == 2
    ecosystems = {item["package-ecosystem"] for item in data["updates"]}
    assert ecosystems == {"pip", "npm", "github-actions"}


def test_codeowners_protects_github_control_plane() -> None:
    text = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    assert "* @KevinSGarrett" in text
    assert "/.github/ @KevinSGarrett" in text
