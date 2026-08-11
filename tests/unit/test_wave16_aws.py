from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.security.basic_auth import install_basic_access_control

ROOT = Path(__file__).resolve().parents[2]


def _validator_module():
    path = ROOT / "scripts" / "validate_aws_infra.py"
    spec = importlib.util.spec_from_file_location("wave16_aws_validator", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_wave16_aws_infrastructure_validator_passes() -> None:
    assert _validator_module().main() == 0


def test_service_is_pinned_to_small_express_mode_task_and_health_path() -> None:
    text = (ROOT / "infra" / "aws" / "service.yaml").read_text()
    assert "Type: AWS::ECS::ExpressGatewayService" in text
    assert "Cpu: '256'" in text
    assert "Memory: '512'" in text
    assert "HealthCheckPath: /api/v1/health" in text
    assert "MinTaskCount: 1" in text
    assert "MaxTaskCount: 1" in text


def test_aws_demo_modes_are_fail_closed() -> None:
    text = (ROOT / "infra" / "aws" / "service.yaml").read_text()
    for pair in (
        ("DEMO_MODE", "'true'"),
        ("REQUIRE_ACCESS_CONTROL", "'true'"),
        ("OPENAI_ENABLED", "'false'"),
        ("OPENAI_RAW_DOCUMENTS", "'false'"),
        ("APOLLO_MODE", "'off'"),
        ("PIPEDRIVE_MODE", "'dry_run'"),
        ("TRELLO_MODE", "'off'"),
        ("GOOGLE_INTEGRATION_MODE", "'off'"),
    ):
        assert f"Name: {pair[0]}" in text
        assert f"Value: {pair[1]}" in text


def test_private_source_material_cannot_enter_container_context() -> None:
    text = (ROOT / ".dockerignore").read_text()
    for path in (
        "context/private_source_documents",
        "context/original_chat_logs",
        "data/private",
        "data/raw",
    ):
        assert path in text


def test_deploy_workflow_is_manual_oidc_and_acknowledged() -> None:
    text = (ROOT / ".github" / "workflows" / "deploy-aws-demo.yml").read_text()
    assert "workflow_dispatch:" in text
    assert "id-token: write" in text
    assert "environment: aws-demo" in text
    assert 'confirm_deploy }}" == "DEPLOY"' in text
    assert "aws-actions/configure-aws-credentials@v6.2.3" in text
    assert "aws-actions/amazon-ecr-login@v2" in text
    assert "python scripts/run_public_test_matrix.py" in text
    assert "run_wave16_test_matrix.sh" not in text
    assert "on:\n  push:" not in text


def test_github_oidc_role_is_repository_environment_scoped() -> None:
    text = (ROOT / "infra" / "aws" / "github-deploy-role.yaml").read_text()
    assert "token.actions.githubusercontent.com:aud: sts.amazonaws.com" in text
    assert "repo:${GitHubOwner}/${GitHubRepository}:environment:${DeploymentEnvironment}" in text
    assert "iam:PassRole" in text
    assert "offgrid-commercial-intelligence-demo-execution" in text


def test_cost_model_matches_documented_fixed_subtotal() -> None:
    data = json.loads((ROOT / "research" / "WAVE_16_AWS_COST_MODEL.json").read_text())
    assert data["configuration"] == {"vCPU": 0.25, "memory_gb": 0.5, "min_tasks": 1, "max_tasks": 1}
    assert data["monthly_estimate"]["fixed_subtotal_before_alb_lcu_ipv4_data_transfer"] == 25.89
    assert data["monthly_estimate"]["budget_guardrail_usd"] == 50


def test_basic_access_gate_protects_app_but_exempts_health() -> None:
    app = FastAPI()

    @app.get("/")
    def root() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/v1/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    install_basic_access_control(app, password="correct-horse", required=True)
    client = TestClient(app)
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/").status_code == 401
    token = base64.b64encode(b"offgrid:correct-horse").decode()
    assert client.get("/", headers={"Authorization": f"Basic {token}"}).status_code == 200


def test_access_gate_fails_startup_when_required_without_password() -> None:
    app = FastAPI()
    try:
        install_basic_access_control(app, password=None, required=True)
    except RuntimeError as exc:
        assert "APP_ACCESS_PASSWORD" in str(exc)
    else:
        raise AssertionError("required access control must fail closed without a password")
