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
        "REQUIRE_ACCESS_CONTROL": "true",
        "OPENAI_ENABLED": "false",
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
    if not any(s.get("Name") == "APP_ACCESS_PASSWORD" for s in secrets):
        errors.append("APP_ACCESS_PASSWORD must come through ECS secret injection")

    tags = props.get("Tags", [])
    tag_map = {t["Key"]: t["Value"] for t in tags}
    for key, value in {"Project":"OffGridCommercialIntelligence","Environment":"demo","Purpose":"Interview"}.items():
        if tag_map.get(key) != value:
            errors.append(f"missing required service tag {key}={value}")

    role = ores.get("GitHubDeployRole", {}).get("Properties", {})
    trust = str(role.get("AssumeRolePolicyDocument", {}))
    if "token.actions.githubusercontent.com:sub" not in trust or "environment:${DeploymentEnvironment}" not in trust:
        errors.append("GitHub OIDC trust is not restricted to repository environment")

    workflow = (ROOT / ".github/workflows/deploy-aws-demo.yml").read_text()
    for needle in (
        "workflow_dispatch:",
        "id-token: write",
        "environment: aws-demo",
        'confirm_deploy }}" == "DEPLOY"',
        "aws-actions/configure-aws-credentials@v6.2.3",
        "aws-actions/amazon-ecr-login@v2",
    ):
        if needle not in workflow:
            errors.append(f"deployment workflow missing {needle!r}")
    if re.search(r"on:\s*\n\s*(push|pull_request):", workflow):
        errors.append("AWS deployment workflow must not auto-run on push/PR")

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
    print("- generated Secrets Manager access password")
    print("- read-only fail-closed integration modes")
    print("- OIDC/manual protected GitHub deployment")
    print("- private source files excluded from Docker context")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
