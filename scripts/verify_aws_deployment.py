#!/usr/bin/env python3
"""Independently verify the authorized public Off Grid AWS demo deployment."""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CHICAGO = ZoneInfo("America/Chicago")
EXPECTED_ACCOUNT = "257851647752"
EXPECTED_REGION = "us-east-1"
FOUNDATION_STACK = "offgrid-commercial-intelligence-demo-foundation"
SERVICE_STACK = "offgrid-commercial-intelligence-demo-service"
EXPECTED_SERVICE = "offgrid-commercial-intelligence-demo"
EXPECTED_REPOSITORY = "offgrid-commercial-intelligence"
EXPECTED_WORKFLOW = "Deploy AWS Demo"
STABLE_STACK_STATUSES = {"CREATE_COMPLETE", "UPDATE_COMPLETE", "IMPORT_COMPLETE"}


class VerificationError(RuntimeError):
    """A fail-closed command or response error with no credential payload."""


def run_json(command: list[str], label: str) -> Any:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise VerificationError(f"{label} timed out") from exc
    if result.returncode != 0:
        detail = result.stderr.strip()[-1000:]
        raise VerificationError(f"{label} failed with exit {result.returncode}: {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise VerificationError(f"{label} returned invalid JSON") from exc


def aws_json(profile: str, region: str, args: list[str], label: str) -> Any:
    return run_json(
        ["aws", *args, "--profile", profile, "--region", region, "--output", "json"],
        label,
    )


def stack_outputs(stack: dict[str, Any]) -> dict[str, str]:
    outputs: dict[str, str] = {}
    for row in stack.get("Outputs") or []:
        if isinstance(row, dict) and isinstance(row.get("OutputKey"), str):
            value = row.get("OutputValue")
            if isinstance(value, str) and value:
                outputs[row["OutputKey"]] = value
    return outputs


def request_status(
    url: str,
    *,
    expect_json: bool = False,
) -> tuple[int, Any | None, dict[str, str]]:
    headers = {"User-Agent": "offgrid-release-verifier/1.0"}
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
            parsed = json.loads(payload) if expect_json else None
            return response.status, parsed, {
                key.lower(): value for key, value in response.headers.items()
            }
    except urllib.error.HTTPError as exc:
        # Do not include response bodies because an upstream error page may
        # echo request context. Status is sufficient for this smoke gate.
        return exc.code, None, {
            key.lower(): value for key, value in (exc.headers or {}).items()
        }
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"public request failed for {url}: {type(exc).__name__}") from exc


def verify(candidate: str, profile: str, region: str) -> dict[str, Any]:
    errors: list[str] = []
    result: dict[str, Any] = {
        "schema_version": "aws-deployment-verification-1.0",
        "verified_at": datetime.now(CHICAGO).isoformat(timespec="seconds"),
        "candidate_commit": candidate,
        "account": {"expected": EXPECTED_ACCOUNT, "actual": None},
        "region": region,
        "cloudformation": {},
        "ecr": {},
        "ecs": {},
        "github_deploy": {},
        "endpoint": {},
        "logs": {},
        "secrets": {"values_exposed": False},
        "errors": errors,
    }

    try:
        identity = aws_json(profile, region, ["sts", "get-caller-identity"], "AWS identity")
        actual_account = identity.get("Account") if isinstance(identity, dict) else None
        result["account"]["actual"] = actual_account
        if actual_account != EXPECTED_ACCOUNT:
            errors.append(f"AWS account mismatch: expected {EXPECTED_ACCOUNT}, got {actual_account}")
            result["result"] = "FAIL"
            return result

        foundation_data = aws_json(
            profile,
            region,
            ["cloudformation", "describe-stacks", "--stack-name", FOUNDATION_STACK],
            "foundation stack",
        )
        service_data = aws_json(
            profile,
            region,
            ["cloudformation", "describe-stacks", "--stack-name", SERVICE_STACK],
            "service stack",
        )
        foundation = foundation_data["Stacks"][0]
        service_stack = service_data["Stacks"][0]
        foundation_outputs = stack_outputs(foundation)
        service_outputs = stack_outputs(service_stack)
        result["cloudformation"] = {
            "foundation_stack": FOUNDATION_STACK,
            "foundation_status": foundation.get("StackStatus"),
            "service_stack": SERVICE_STACK,
            "service_status": service_stack.get("StackStatus"),
        }
        for name, status in (
            ("foundation", foundation.get("StackStatus")),
            ("service", service_stack.get("StackStatus")),
        ):
            if status not in STABLE_STACK_STATUSES:
                errors.append(f"{name} stack is not stable: {status}")

        repository_uri = foundation_outputs.get("RepositoryUri", "")
        cluster = foundation_outputs.get("ClusterName", "")
        access_secret = foundation_outputs.get("AccessSecretArn", "")
        openai_secret = foundation_outputs.get("OpenAISecretArn", "")
        log_group = foundation_outputs.get("LogGroupName", "")
        endpoint_value = service_outputs.get("Endpoint", "")
        endpoint = endpoint_value if endpoint_value.startswith("https://") else f"https://{endpoint_value}"

        if not repository_uri.endswith(f"/{EXPECTED_REPOSITORY}"):
            errors.append("foundation repository output is not the Off Grid ECR repository")
        if cluster != EXPECTED_SERVICE:
            errors.append("foundation cluster output is not the locked Off Grid cluster")
        parsed_endpoint = urlparse(endpoint)
        if parsed_endpoint.scheme != "https" or not parsed_endpoint.netloc:
            errors.append("service endpoint is not a valid public HTTPS URL")

        images = aws_json(
            profile,
            region,
            [
                "ecr",
                "describe-images",
                "--repository-name",
                EXPECTED_REPOSITORY,
                "--image-ids",
                f"imageTag={candidate}",
            ],
            "ECR candidate image",
        )
        image_details = images.get("imageDetails") if isinstance(images, dict) else None
        image = image_details[0] if isinstance(image_details, list) and image_details else {}
        digest = image.get("imageDigest")
        if not isinstance(digest, str) or not digest.startswith("sha256:"):
            errors.append("ECR candidate image lacks an immutable digest")

        scan = aws_json(
            profile,
            region,
            [
                "ecr",
                "describe-image-scan-findings",
                "--repository-name",
                EXPECTED_REPOSITORY,
                "--image-id",
                f"imageTag={candidate}",
            ],
            "ECR image scan",
        )
        scan_status = (scan.get("imageScanStatus") or {}).get("status")
        severity_counts = (scan.get("imageScanFindings") or {}).get("findingSeverityCounts") or {}
        finding_total = sum(
            value for value in severity_counts.values() if isinstance(value, int) and not isinstance(value, bool)
        )
        if scan_status != "COMPLETE":
            errors.append(f"ECR image scan is not complete: {scan_status}")
        if finding_total != 0:
            errors.append(f"ECR image scan reports {finding_total} findings")
        result["ecr"] = {
            "repository_uri": repository_uri,
            "tag": candidate,
            "digest": digest,
            "scan_status": scan_status,
            "finding_severity_counts": severity_counts,
            "finding_total": finding_total,
        }

        listed = aws_json(
            profile,
            region,
            [
                "ecs",
                "list-service-deployments",
                "--cluster",
                cluster,
                "--service",
                EXPECTED_SERVICE,
            ],
            "ECS service deployments",
        )
        deployments = listed.get("serviceDeployments") if isinstance(listed, dict) else None
        deployment_arn = (
            deployments[0].get("serviceDeploymentArn")
            if isinstance(deployments, list) and deployments and isinstance(deployments[0], dict)
            else None
        )
        described = aws_json(
            profile,
            region,
            [
                "ecs",
                "describe-service-deployments",
                "--service-deployment-arns",
                str(deployment_arn or "missing"),
            ],
            "ECS service deployment",
        )
        described_rows = described.get("serviceDeployments") if isinstance(described, dict) else None
        deployment = (
            described_rows[0]
            if isinstance(described_rows, list) and described_rows and isinstance(described_rows[0], dict)
            else {}
        )
        deployment_status = deployment.get("status")
        if deployment_status != "SUCCESSFUL":
            errors.append(f"ECS deployment is not successful: {deployment_status}")
        result["ecs"] = {
            "cluster": cluster,
            "service": EXPECTED_SERVICE,
            "deployment_arn": deployment.get("serviceDeploymentArn"),
            "deployment_status": deployment_status,
            "started_at": deployment.get("startedAt"),
            "finished_at": deployment.get("finishedAt"),
        }

        runs = run_json(
            [
                "gh",
                "run",
                "list",
                "--repo",
                "KevinSGarrett/Off_Grid",
                "--workflow",
                EXPECTED_WORKFLOW,
                "--commit",
                candidate,
                "--limit",
                "20",
                "--json",
                "databaseId,headSha,status,conclusion,event,workflowName,url",
            ],
            "GitHub AWS deployment run",
        )
        matching_runs = [
            row
            for row in runs
            if isinstance(row, dict)
            and row.get("headSha") == candidate
            and row.get("workflowName") == EXPECTED_WORKFLOW
            and row.get("status") == "completed"
            and row.get("conclusion") == "success"
        ] if isinstance(runs, list) else []
        github_run = matching_runs[0] if matching_runs else {}
        if not github_run:
            errors.append("no successful exact-candidate GitHub AWS deployment run was found")
        result["github_deploy"] = {
            "run_id": github_run.get("databaseId"),
            "head_sha": github_run.get("headSha"),
            "status": github_run.get("status"),
            "conclusion": github_run.get("conclusion"),
            "event": github_run.get("event"),
            "workflow_name": github_run.get("workflowName"),
            "url": github_run.get("url"),
        }

        log_data = aws_json(
            profile,
            region,
            ["logs", "describe-log-groups", "--log-group-name-prefix", log_group],
            "CloudWatch log group",
        )
        groups_value = log_data.get("logGroups") if isinstance(log_data, dict) else []
        groups = groups_value if isinstance(groups_value, list) else []
        log_exists = any(
            isinstance(row, dict) and row.get("logGroupName") == log_group for row in groups
        )
        if not log_exists:
            errors.append("Off Grid CloudWatch log group is missing")
        result["logs"] = {"log_group": log_group, "available": log_exists}

        if not openai_secret:
            errors.append("OpenAI secret ARN output is missing")
        else:
            aws_json(
                profile,
                region,
                ["secretsmanager", "describe-secret", "--secret-id", openai_secret],
                "OpenAI secret metadata",
            )
        result["secrets"].update(
            {
                "legacy_access_secret_present_unused": bool(access_secret),
                "openai_secret_reference_present": bool(openai_secret),
            }
        )

        health_status, health, health_headers = request_status(
            f"{endpoint}/api/v1/health", expect_json=True
        )
        root_status, _, root_headers = request_status(f"{endpoint}/")
        readiness_status, readiness, readiness_headers = request_status(
            f"{endpoint}/api/v1/readiness", expect_json=True
        )
        projects_status, projects, projects_headers = request_status(
            f"{endpoint}/api/v1/projects?limit=1", expect_json=True
        )
        if health_status != 200 or not isinstance(health, dict) or health.get("status") != "ok":
            errors.append("public health check did not return 200/ok")
        if root_status != 200:
            errors.append(f"public root did not return 200 without login: {root_status}")
        if (
            readiness_status != 200
            or not isinstance(readiness, dict)
            or readiness.get("status") != "ready"
        ):
            errors.append("public readiness did not return 200/ready without login")
        if projects_status != 200 or not isinstance(projects, dict):
            errors.append("public demo-safe projects API did not return 200/JSON without login")
        if any(
            "www-authenticate" in headers
            for headers in (health_headers, root_headers, readiness_headers, projects_headers)
        ):
            errors.append("public reviewer path returned a WWW-Authenticate header")
        result["endpoint"] = {
            "url": endpoint,
            "https": parsed_endpoint.scheme == "https",
            "health_status": health_status,
            "health": health.get("status") if isinstance(health, dict) else None,
            "root_status": root_status,
            "readiness_status": readiness_status,
            "readiness": readiness.get("status") if isinstance(readiness, dict) else None,
            "projects_status": projects_status,
            "www_authenticate_absent": not any(
                "www-authenticate" in headers
                for headers in (health_headers, root_headers, readiness_headers, projects_headers)
            ),
        }
    except (VerificationError, KeyError, IndexError, TypeError) as exc:
        errors.append(str(exc))

    result["result"] = "PASS" if not errors else "FAIL"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--profile", default="comfyui-bootstrap")
    parser.add_argument("--region", default=EXPECTED_REGION)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.candidate, args.profile, args.region)
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
