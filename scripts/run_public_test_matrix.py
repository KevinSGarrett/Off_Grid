#!/usr/bin/env python3
"""Run the reproducible test boundary available in the public repository.

The canonical private workspace has additional licensed-source tests. Those
tests remain in the repository for transparency, but their PDF inputs are
intentionally excluded from Git. This matrix exercises the public-safe
equivalents and is also the required GitHub Actions backend test job.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_NODES = (
    "tests/contract/test_wave14_observability_contract.py::test_structured_log_is_json_correlated_and_redacted",
    "tests/contract/test_wave14_observability_contract.py::test_sanitizer_masks_nested_secret_and_contact_values",
    "tests/load/test_wave14_synthetic_scale.py",
    "tests/unit/test_wave03_state_machines.py",
    "tests/unit/test_wave03_write_policy.py",
    "tests/unit/test_wave04_migration.py",
    "tests/unit/test_wave04_models.py",
    "tests/unit/test_wave04_privacy.py",
    "tests/unit/test_wave04_provenance.py",
    "tests/unit/test_wave05_sanitized_fixtures.py",
    "tests/unit/test_wave05_ingestion.py::test_later_material_project_change_creates_history_and_pipeline_event",
    "tests/unit/test_wave06_configuration.py",
    "tests/unit/test_wave06_migration.py",
    "tests/unit/test_wave07_migration.py",
    "tests/unit/test_wave08_apollo.py",
    "tests/unit/test_wave08_configuration.py",
    "tests/unit/test_wave11_openai.py",
    "tests/unit/test_wave13_frontend_contract.py",
    "tests/unit/test_wave14_resilience.py",
    "tests/unit/test_wave15_github.py",
    "tests/unit/test_wave16_aws.py",
    "tests/unit/test_wave17_integration.py",
)
DESELECTED_PRIVATE_EVIDENCE_NODES = (
    "tests/unit/test_wave08_configuration.py::test_public_research_snapshot_records_no_prospect_outreach_or_live_apollo",
    "tests/unit/test_wave11_openai.py::test_wave11_official_api_verification_record_exists",
    "tests/unit/test_wave16_aws.py::test_cost_model_matches_documented_fixed_subtotal",
)


def main() -> int:
    env = dict(os.environ)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    command = [sys.executable, "-m", "pytest", "-q", *TEST_NODES]
    command.extend(f"--deselect={node}" for node in DESELECTED_PRIVATE_EVIDENCE_NODES)
    return subprocess.run(command, cwd=ROOT, env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
