from __future__ import annotations

import importlib.util
import subprocess
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _verifier():
    path = ROOT / "scripts/verify_aws_deployment.py"
    spec = importlib.util.spec_from_file_location("aws_deployment_verifier", path)
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


def test_secret_retrieval_failure_never_reflects_process_output(monkeypatch) -> None:
    verifier = _verifier()
    fake_result = SimpleNamespace(
        returncode=1,
        stdout="do-not-reflect-secret",
        stderr="do-not-reflect-secret-error",
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: fake_result)
    with pytest.raises(verifier.VerificationError) as exc:
        verifier.retrieve_secret("test-profile", "us-east-1", "secret-id")
    message = str(exc.value)
    assert message == "access-secret retrieval failed"
    assert "do-not-reflect" not in message


def test_http_error_returns_only_status_and_never_reads_body(monkeypatch) -> None:
    verifier = _verifier()
    error = urllib.error.HTTPError(
        "https://example.test/",
        401,
        "Unauthorized",
        hdrs=None,
        fp=None,
    )

    def fail_request(*args, **kwargs):
        raise error

    monkeypatch.setattr(verifier.urllib.request, "urlopen", fail_request)
    assert verifier.request_status("https://example.test/") == (401, None)
