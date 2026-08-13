#!/usr/bin/env python3
"""Fail-closed no-login endpoint smoke test for the public employer demo."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse


class SmokeError(RuntimeError):
    """A response-safe smoke-test failure."""


def request(url: str, *, expect_json: bool = False) -> tuple[int, Any | None, dict[str, str]]:
    try:
        with urllib.request.urlopen(
            urllib.request.Request(
                url,
                headers={"User-Agent": "offgrid-deploy-smoke/2.0"},
                method="GET",
            ),
            timeout=30,
        ) as response:
            payload = response.read()
            parsed = json.loads(payload) if expect_json else None
            return response.status, parsed, {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        return exc.code, None, {
            key.lower(): value for key, value in (exc.headers or {}).items()
        }
    except (OSError, json.JSONDecodeError) as exc:
        raise SmokeError(f"public request failed: {type(exc).__name__}") from exc


def normalize_https_endpoint(endpoint: str) -> str:
    endpoint = endpoint.strip().rstrip("/")
    if "://" not in endpoint:
        endpoint = f"https://{endpoint}"
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.netloc:
        raise SmokeError("endpoint must be a public HTTPS URL or hostname")
    return endpoint


def verify(endpoint: str) -> dict[str, Any]:
    endpoint = normalize_https_endpoint(endpoint)
    health_status, health, health_headers = request(
        f"{endpoint}/api/v1/health", expect_json=True
    )
    root_status, _, root_headers = request(endpoint)
    readiness_status, readiness, readiness_headers = request(
        f"{endpoint}/api/v1/readiness", expect_json=True
    )
    projects_status, projects, projects_headers = request(
        f"{endpoint}/api/v1/projects?limit=1", expect_json=True
    )
    response_headers = (health_headers, root_headers, readiness_headers, projects_headers)
    checks = {
        "health_200_ok": health_status == 200
        and isinstance(health, dict)
        and health.get("status") == "ok",
        "root_200_public": root_status == 200,
        "readiness_200_ready": readiness_status == 200
        and isinstance(readiness, dict)
        and readiness.get("status") == "ready",
        "demo_api_200": projects_status == 200 and isinstance(projects, dict),
        "www_authenticate_absent": all("www-authenticate" not in headers for headers in response_headers),
    }
    result = {
        "endpoint": endpoint,
        "checks": checks,
        "credentials_exposed": False,
        "result": "PASS" if all(checks.values()) else "FAIL",
    }
    if result["result"] != "PASS":
        raise SmokeError(f"public endpoint smoke failed: {checks}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.endpoint), indent=2))
    except SmokeError as exc:
        print(json.dumps({"result": "FAIL", "error": str(exc), "credentials_exposed": False}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
