from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class CfnLoader(yaml.SafeLoader):
    pass


def _cfn(loader: CfnLoader, tag_suffix: str, node: yaml.Node):
    if isinstance(node, yaml.ScalarNode):
        return {f"!{tag_suffix}": loader.construct_scalar(node)}
    if isinstance(node, yaml.SequenceNode):
        return {f"!{tag_suffix}": loader.construct_sequence(node)}
    return {f"!{tag_suffix}": loader.construct_mapping(node)}


CfnLoader.add_multi_constructor("!", _cfn)


def load(path: str) -> dict:
    return yaml.load((ROOT / path).read_text(), Loader=CfnLoader)


def main() -> int:
    errors: list[str] = []
    foundation = load("infra/aws/foundation.yaml")
    service = load("infra/aws/service.yaml")
    oidc = load("infra/aws/github-deploy-role.yaml")

    fres = foundation.get("Resources", {})
    sres = service.get("Resources", {})
    ores = oidc.get("Resources", {})

    required_foundation = {
        "AWS::ECR::Repository",
        "AWS::SecretsManager::Secret",
        "AWS::Logs::LogGroup",
        "AWS::ECS::Cluster",
        "AWS::IAM::Role",
    }
    types = {r.get("Type") for r in fres.values()}
    missing = required_foundation - types
    if missing:
        errors.append(f"foundation missing resource types: {sorted(missing)}")

    repo = fres.get("ContainerRepository", {}).get("Properties", {})
    if repo.get("ImageTagMutability") != "IMMUTABLE":
        errors.append("ECR repository must use immutable tags")
    if repo.get("ImageScanningConfiguration", {}).get("ScanOnPush") is not True:
        errors.append("ECR scan-on-push must be true")
    if fres.get("DemoLogGroup", {}).get("Properties", {}).get("RetentionInDays") != 7:
        errors.append("demo log group must retain only 7 days")

    infra_role = fres.get("ExpressInfrastructureRole", {}).get("Properties", {})
    managed = infra_role.get("ManagedPolicyArns", [])
    if not any("AmazonECSInfrastructureRoleforExpressGatewayServices" in str(v) for v in managed):
        errors.append("Express infrastructure managed policy missing")

    demo = sres.get("DemoService", {})
    if demo.get("Type") != "AWS::ECS::ExpressGatewayService":
        errors.append("service template must use AWS::ECS::ExpressGatewayService")
    props = demo.get("Properties", {})
    if props.get("Cpu") != "256" or props.get("Memory") != "512":
        errors.append("service must explicitly pin 256 CPU / 512 MiB")
    if props.get("HealthCheckPath") != "/api/v1/health":
        errors.append("health check must use /api/v1/health")
    scaling = props.get("ScalingTarget", {})
    if scaling.get("MinTaskCount") != 1 or scaling.get("MaxTaskCount") != 1:
        errors.append("interview service must stay at exactly one task")
    primary = props.get("PrimaryContainer", {})
    if primary.get("ContainerPort") != 8000:
        errors.append("container must expose port 8000")
    env = {item["Name"]: item["Value"] for item in primary.get("Environment", [])}
    expected_env = {
        "DEMO_MODE": "true",
        "OPENAI_ENABLED": "true",
        "OPENAI_RESEARCH_ENABLED": "false",
        "OPENAI_RAW_DOCUMENTS": "false",
        "APOLLO_MODE": "off",
        "PIPEDRIVE_MODE": "dry_run",
        "TRELLO_MODE": "off",
        "GOOGLE_INTEGRATION_MODE": "off",
        "DEMO_RESET_ON_START": "true",
    }
    for name, value in expected_env.items():
        if env.get(name) != value:
            errors.append(f"unsafe/missing demo env {name}={value}")
    secrets = primary.get("Secrets", [])
    for forbidden in ("REQUIRE_ACCESS_CONTROL", "APP_ACCESS_PASSWORD"):
        if forbidden in env or any(s.get("Name") == forbidden for s in secrets):
            errors.append(f"viewer authentication setting must be absent: {forbidden}")
    if not any(s.get("Name") == "OPENAI_API_KEY" for s in secrets):
        errors.append("OPENAI_API_KEY must come through ECS secret injection")

    openai_secret = fres.get("OpenAIApiKeySecret", {}).get("Properties", {})
    if openai_secret.get("Name") != "offgrid-commercial-intelligence/demo/openai-api-key":
        errors.append("dedicated OpenAI Secrets Manager entry is missing")
    execution_policy = str(fres.get("TaskExecutionRole", {}).get("Properties", {}).get("Policies", []))
    if "OpenAIApiKeySecret" not in execution_policy:
        errors.append("task execution role cannot read the OpenAI secret")
    if "DemoAccessSecret" in execution_policy:
        errors.append("task execution role must not read the legacy dashboard access secret")

    tags = props.get("Tags", [])
    tag_map = {t["Key"]: t["Value"] for t in tags}
    for key, value in {"Project":"OffGridCommercialIntelligence","Environment":"demo","Purpose":"Interview"}.items():
        if tag_map.get(key) != value:
            errors.append(f"missing required service tag {key}={value}")

    provider = ores.get("GitHubOidcProvider", {})
    if provider.get("Type") != "AWS::IAM::OIDCProvider":
        errors.append("GitHub OIDC provider must be managed by the deployment-role stack")
    provider_props = provider.get("Properties", {})
    if provider_props.get("Url") != "https://token.actions.githubusercontent.com":
        errors.append("GitHub OIDC provider URL is missing or incorrect")
    if "sts.amazonaws.com" not in provider_props.get("ClientIdList", []):
        errors.append("GitHub OIDC provider must trust the AWS STS audience")

    role = ores.get("GitHubDeployRole", {}).get("Properties", {})
    trust = str(role.get("AssumeRolePolicyDocument", {}))
    if (
        "token.actions.githubusercontent.com:sub" not in trust
        or "GitHubOwnerId" not in trust
        or "GitHubRepositoryId" not in trust
        or "environment:${DeploymentEnvironment}" not in trust
    ):
        errors.append("GitHub OIDC trust is not restricted to repository environment")
    policies_text = str(role.get("Policies", []))
    if "FoundationStackRead" not in policies_text or "offgrid-commercial-intelligence-demo-foundation" not in policies_text:
        errors.append("GitHub deploy role cannot read the prepared foundation stack outputs")
    if "ReadDemoAccessPasswordForPostDeploySmoke" in policies_text or "secretsmanager:GetSecretValue" in policies_text:
        errors.append("GitHub deploy role must not retrieve viewer or provider secrets")
    if "offgrid-commercial-intelligence/demo/openai-api-key-*" in policies_text:
        errors.append("GitHub deploy role must not read the OpenAI API key secret")
    for action in (
        "ecs:RegisterTaskDefinition",
        "ecs:DeregisterTaskDefinition",
        "ecs:ListServiceDeployments",
        "ecs:DescribeServiceDeployments",
        "ecs:DescribeServiceRevisions",
    ):
        if action not in policies_text:
            errors.append(f"GitHub deploy role missing Express task-definition action {action}")

    workflow = (ROOT / ".github/workflows/deploy-aws-demo.yml").read_text()
    for needle in (
        "workflow_dispatch:",
        "id-token: write",
        "environment: aws-demo",
        'confirm_deploy }}" == "DEPLOY"',
        "aws-actions/configure-aws-credentials@v6.2.3",
        "aws-actions/amazon-ecr-login@v2",
        "python scripts/run_public_test_matrix.py",
    ):
        if needle not in workflow:
            errors.append(f"deployment workflow missing {needle!r}")
    if re.search(r"on:\s*\n\s*(push|pull_request):", workflow):
        errors.append("AWS deployment workflow must not auto-run on push/PR")
    if "run_wave16_test_matrix.sh" in workflow:
        errors.append("AWS deployment workflow references a private-only test script")
    if "Foundation output $1 is missing" not in workflow:
        errors.append("AWS deployment workflow does not fail closed on missing foundation outputs")
    for needle in ("OpenAISecretArn", "openai_secret_arn"):
        if needle not in workflow:
            errors.append(f"deployment workflow missing OpenAI secret wiring {needle!r}")
    for needle in ("access_secret_arn", "AccessSecretArn=", "--secret-id"):
        if needle in workflow:
            errors.append(f"deployment workflow still depends on dashboard access secret {needle!r}")

    dockerignore = (ROOT / ".dockerignore").read_text()
    for private in ("context/private_source_documents", "context/original_chat_logs", "data/private"):
        if private not in dockerignore:
            errors.append(f"Docker context does not exclude {private}")

    dockerfile = (ROOT / "Dockerfile").read_text()
    for needle in ("FROM node:22-alpine AS web-build", "USER appuser", "HEALTHCHECK", "apps/web/dist", "npm ci", "requirements.lock", "data/demo_seed/offgrid_demo_seed.db"):
        if needle not in dockerfile:
            errors.append(f"Dockerfile missing {needle!r}")

    if errors:
        print("AWS INFRA VALIDATION: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("AWS INFRA VALIDATION: PASS")
    print("- ECS Express Mode / 256 CPU / 512 MiB / one task")
    print("- publicly viewable employer demo with server-only OpenAI key")
    print("- read-only fail-closed integration modes")
    print("- OIDC/manual GitHub deployment without secret retrieval")
    print("- private source files excluded from Docker context")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
