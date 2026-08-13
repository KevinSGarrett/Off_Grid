from __future__ import annotations

import importlib.util
import json
from pathlib import Path

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
        ("OPENAI_ENABLED", "'true'"),
        ("OPENAI_RESEARCH_ENABLED", "'false'"),
        ("OPENAI_RAW_DOCUMENTS", "'false'"),
        ("APOLLO_MODE", "'off'"),
        ("PIPEDRIVE_MODE", "'dry_run'"),
        ("TRELLO_MODE", "'off'"),
        ("GOOGLE_INTEGRATION_MODE", "'off'"),
    ):
        assert f"Name: {pair[0]}" in text
        assert f"Value: {pair[1]}" in text
    assert "REQUIRE_ACCESS_CONTROL" not in text
    assert "APP_ACCESS_PASSWORD" not in text


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
    assert "Type: AWS::IAM::OIDCProvider" in text
    assert "Url: https://token.actions.githubusercontent.com" in text
    assert "ClientIdList:" in text and "sts.amazonaws.com" in text
    assert "token.actions.githubusercontent.com:aud: sts.amazonaws.com" in text
    assert "GitHubOwnerId:" in text and "GitHubRepositoryId:" in text
    assert "repo:${GitHubOwner}@${GitHubOwnerId}/${GitHubRepository}@${GitHubRepositoryId}:environment:${DeploymentEnvironment}" in text
    assert "iam:PassRole" in text
    assert "offgrid-commercial-intelligence-demo-execution" in text
    assert "ecs:RegisterTaskDefinition" in text
    assert "ecs:DeregisterTaskDefinition" in text
    assert "ecs:ListServiceDeployments" in text
    assert "ecs:DescribeServiceRevisions" in text
    assert "FoundationStackRead" in text
    assert "offgrid-commercial-intelligence-demo-foundation" in text


def test_deploy_workflow_fails_closed_on_missing_foundation_outputs() -> None:
    text = (ROOT / ".github" / "workflows" / "deploy-aws-demo.yml").read_text()
    assert '[[ -n "$value" && "$value" != "None" ]]' in text
    assert "Foundation output $1 is missing" in text
    assert "OpenAISecretArn" in text
    assert "openai_secret_arn" in text


def test_openai_key_is_a_dedicated_server_side_secret() -> None:
    foundation = (ROOT / "infra" / "aws" / "foundation.yaml").read_text()
    service = (ROOT / "infra" / "aws" / "service.yaml").read_text()
    assert "offgrid-commercial-intelligence/demo/openai-api-key" in foundation
    assert "OpenAIApiKeySecret" in foundation
    assert "Name: OPENAI_API_KEY" in service
    assert "ValueFrom: !Ref OpenAISecretArn" in service


def test_cost_model_matches_documented_fixed_subtotal() -> None:
    data = json.loads((ROOT / "research" / "WAVE_16_AWS_COST_MODEL.json").read_text())
    assert data["configuration"] == {"vCPU": 0.25, "memory_gb": 0.5, "min_tasks": 1, "max_tasks": 1}
    assert data["assumptions"]["secrets_manager_secrets"] == 2
    assert data["assumptions"]["observed_public_ipv4_total"] == 7
    assert data["monthly_estimate"]["fixed_subtotal_before_alb_lcu_data_transfer"] == 51.84
    assert data["monthly_estimate"]["openai_application_guard_usd_per_day"] == 2.0
    assert data["monthly_estimate"]["budget_template_default_usd"] == 50
    assert data["monthly_estimate"]["deployed_budget_resource_present"] is False


def test_dashboard_view_authentication_is_absent_from_runtime_and_service() -> None:
    assert not (ROOT / "apps" / "api" / "app" / "security" / "basic_auth.py").exists()
    runtime = (ROOT / "apps" / "api" / "app" / "main.py").read_text()
    settings = (ROOT / "apps" / "api" / "app" / "core" / "settings.py").read_text()
    service = (ROOT / "infra" / "aws" / "service.yaml").read_text()
    combined = runtime + settings + service
    for forbidden in ("basic_auth", "REQUIRE_ACCESS_CONTROL", "APP_ACCESS_PASSWORD"):
        assert forbidden not in combined
