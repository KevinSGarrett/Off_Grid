from __future__ import annotations

import importlib.util
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _verifier():
    path = ROOT / "scripts/verify_aws_deployment.py"
    spec = importlib.util.spec_from_file_location("aws_deployment_verifier", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _endpoint_verifier():
    path = ROOT / "scripts/verify_aws_endpoint.py"
    spec = importlib.util.spec_from_file_location("aws_endpoint_verifier", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_aws_stack_output_parser_ignores_malformed_rows() -> None:
    verifier = _verifier()
    assert verifier.ROOT == ROOT
    assert verifier.stack_outputs(
        {
            "Outputs": [
                {"OutputKey": "Endpoint", "OutputValue": "example.test"},
                {"OutputKey": "Empty", "OutputValue": ""},
                {"OutputValue": "missing-key"},
                "malformed",
            ]
        }
    ) == {"Endpoint": "example.test"}


def test_wrong_aws_account_fails_closed_before_resource_checks(monkeypatch) -> None:
    verifier = _verifier()
    calls: list[list[str]] = []

    def fake_aws_json(profile: str, region: str, args: list[str], label: str):
        calls.append(args)
        assert profile == "test-profile"
        assert region == "us-east-1"
        assert label == "AWS identity"
        return {"Account": "000000000000"}

    monkeypatch.setattr(verifier, "aws_json", fake_aws_json)
    result = verifier.verify("a" * 40, "test-profile", "us-east-1")
    assert result["result"] == "FAIL"
    assert result["account"] == {
        "expected": "257851647752",
        "actual": "000000000000",
    }
    assert result["errors"] == [
        "AWS account mismatch: expected 257851647752, got 000000000000"
    ]
    assert calls == [["sts", "get-caller-identity"]]


def test_http_error_returns_only_status_and_never_reads_body(monkeypatch) -> None:
    verifier = _verifier()
    error = urllib.error.HTTPError(
        "https://example.test/",
        503,
        "Unavailable",
        hdrs=None,
        fp=None,
    )

    def fail_request(*args, **kwargs):
        raise error

    monkeypatch.setattr(verifier.urllib.request, "urlopen", fail_request)
    assert verifier.request_status("https://example.test/") == (503, None, {})


def test_endpoint_smoke_accepts_public_reviewer_path_without_auth(monkeypatch) -> None:
    verifier = _endpoint_verifier()
    revision = "b" * 40

    def fake_request(url: str, *, expect_json=False):
        if url.endswith("/health"):
            return 200, {"status": "ok", "build_revision": revision}, {}
        if url.endswith("/readiness"):
            return 200, {"status": "ready", "build_revision": revision}, {}
        if "/projects?limit=1" in url:
            return 200, {"items": []}, {}
        return 200, None, {}

    monkeypatch.setattr(verifier, "request", fake_request)
    result = verifier.verify("https://example.test", expected_build_revision=revision)
    assert result["result"] == "PASS"
    assert result["credentials_exposed"] is False
    assert result["checks"]["www_authenticate_absent"] is True
    assert result["checks"]["health_build_revision_matches"] is True
    assert result["checks"]["readiness_build_revision_matches"] is True


def test_endpoint_smoke_rejects_runtime_build_revision_drift(monkeypatch) -> None:
    verifier = _endpoint_verifier()

    def fake_request(url: str, *, expect_json=False):
        if url.endswith("/health"):
            return 200, {"status": "ok", "build_revision": "a" * 40}, {}
        if url.endswith("/readiness"):
            return 200, {"status": "ready", "build_revision": "a" * 40}, {}
        if "/projects?limit=1" in url:
            return 200, {"items": []}, {}
        return 200, None, {}

    monkeypatch.setattr(verifier, "request", fake_request)
    with pytest.raises(verifier.SmokeError, match="build_revision_matches"):
        verifier.verify("https://example.test", expected_build_revision="b" * 40)


def test_endpoint_smoke_rejects_http() -> None:
    verifier = _endpoint_verifier()
    with pytest.raises(verifier.SmokeError, match="HTTPS"):
        verifier.verify("http://example.test")


def test_endpoint_smoke_normalizes_aws_generated_hostname(monkeypatch) -> None:
    verifier = _endpoint_verifier()
    seen: list[str] = []

    def fake_request(url: str, *, expect_json=False):
        seen.append(url)
        if url.endswith("/health"):
            return 200, {"status": "ok"}, {}
        if url.endswith("/readiness"):
            return 200, {"status": "ready"}, {}
        if "/projects?limit=1" in url:
            return 200, {"items": []}, {}
        return 200, None, {}

    monkeypatch.setattr(verifier, "request", fake_request)
    result = verifier.verify("service.ecs.us-east-1.on.aws")
    assert result["endpoint"] == "https://service.ecs.us-east-1.on.aws"
    assert all(url.startswith("https://") for url in seen)


def test_endpoint_smoke_rejects_www_authenticate(monkeypatch) -> None:
    verifier = _endpoint_verifier()
    def fake_request(url: str, *, expect_json=False):
        if url.endswith("/health"):
            return 200, {"status": "ok"}, {}
        if url.endswith("/readiness"):
            return 200, {"status": "ready"}, {}
        if "/projects?limit=1" in url:
            return 200, {"items": []}, {}
        return 200, None, {"www-authenticate": "Basic"}
    monkeypatch.setattr(verifier, "request", fake_request)
    with pytest.raises(verifier.SmokeError, match="www_authenticate_absent"):
        verifier.verify("https://example.test")


def test_deploy_workflow_runs_public_endpoint_smoke() -> None:
    workflow = (ROOT / ".github/workflows/deploy-aws-demo.yml").read_text(encoding="utf-8")
    assert "name: Verify public employer-demo endpoint" in workflow
    assert "python scripts/verify_aws_endpoint.py" in workflow
    assert '--expected-build-revision "$GITHUB_SHA"' in workflow
    assert "--secret-id" not in workflow
    assert "access_secret_arn" not in workflow


def test_deploy_role_cannot_read_dashboard_or_provider_secrets() -> None:
    role = (ROOT / "infra/aws/github-deploy-role.yaml").read_text(encoding="utf-8")
    assert "ReadDemoAccessPasswordForPostDeploySmoke" not in role
    assert "secretsmanager:GetSecretValue" not in role
    assert "secret:offgrid-commercial-intelligence/demo/access-password-*" not in role
    assert "secret:offgrid-commercial-intelligence/demo/openai-api-key-*" not in role
