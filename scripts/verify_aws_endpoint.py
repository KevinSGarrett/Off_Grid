#!/usr/bin/env python3
"""Fail-closed protected endpoint smoke test for the AWS deploy workflow.

The application password is retrieved into this process only. It is never
printed, persisted, passed as a command argument, or placed in an environment
variable.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse


class SmokeError(RuntimeError):
    """A credential-safe smoke-test failure."""


def retrieve_secret(secret_id: str, region: str) -> str:
    result = subprocess.run(
        [
            "aws",
            "secretsmanager",
            "get-secret-value",
            "--secret-id",
            secret_id,
            "--query",
            "SecretString",
            "--output",
            "text",
            "--region",
            region,
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if result.returncode != 0:
        # Never reflect command output: it belongs to the only command that
        # can return the application password.
        raise SmokeError("access-secret retrieval failed")
    value = result.stdout.strip()
    if not value:
        raise SmokeError("access secret is empty")
    return value


def request(
    url: str,
    *,
    authorization: str | None = None,
    expect_json: bool = False,
) -> tuple[int, Any | None]:
    headers = {"User-Agent": "offgrid-deploy-smoke/1.0"}
    if authorization:
        headers["Authorization"] = authorization
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=headers, method="GET"), timeout=30
        ) as response:
            payload = response.read()
            return response.status, json.loads(payload) if expect_json else None
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (OSError, json.JSONDecodeError) as exc:
        raise SmokeError(f"public request failed: {type(exc).__name__}") from exc


def verify(endpoint: str, secret_id: str, region: str) -> dict[str, Any]:
    endpoint = endpoint.rstrip("/")
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.netloc:
        raise SmokeError("endpoint must be a public HTTPS URL")

    health_status, health = request(f"{endpoint}/api/v1/health", expect_json=True)
    unauthenticated_status, _ = request(endpoint)
    password = retrieve_secret(secret_id, region)
    token = base64.b64encode(f"offgrid:{password}".encode()).decode("ascii")
    password = ""
    authorization = f"Basic {token}"
    authenticated_status, _ = request(endpoint, authorization=authorization)
    readiness_status, readiness = request(
        f"{endpoint}/api/v1/readiness",
        authorization=authorization,
        expect_json=True,
    )
    token = ""
    authorization = ""

    checks = {
        "health_200_ok": health_status == 200
        and isinstance(health, dict)
        and health.get("status") == "ok",
        "unauthenticated_root_401": unauthenticated_status == 401,
        "authenticated_root_200": authenticated_status == 200,
        "readiness_200_ready": readiness_status == 200
        and isinstance(readiness, dict)
        and readiness.get("status") == "ready",
    }
    result = {
        "endpoint": endpoint,
        "checks": checks,
        "credentials_exposed": False,
        "result": "PASS" if all(checks.values()) else "FAIL",
    }
    if result["result"] != "PASS":
        raise SmokeError(f"protected endpoint smoke failed: {checks}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--secret-id", required=True)
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.endpoint, args.secret_id, args.region), indent=2))
    except SmokeError as exc:
        print(json.dumps({"result": "FAIL", "error": str(exc), "credentials_exposed": False}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
