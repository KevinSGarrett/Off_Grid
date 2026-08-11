from __future__ import annotations

import pytest

from app.resilience import RetryPolicy, retry_call


def test_retry_call_recovers_after_transient_failures_without_sleep() -> None:
    attempts = []

    def operation() -> str:
        attempts.append(len(attempts) + 1)
        if len(attempts) < 3:
            raise TimeoutError("transient")
        return "ok"

    retries = []
    result = retry_call(
        operation,
        policy=RetryPolicy(max_attempts=3, base_delay_seconds=0, max_delay_seconds=0),
        is_retryable=lambda exc: isinstance(exc, TimeoutError),
        sleeper=lambda _delay: None,
        on_retry=lambda attempt, exc, delay: retries.append((attempt, type(exc).__name__, delay)),
    )
    assert result == "ok"
    assert attempts == [1, 2, 3]
    assert retries == [(1, "TimeoutError", 0), (2, "TimeoutError", 0)]


def test_retry_call_stops_on_non_retryable_failure() -> None:
    attempts = 0

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise ValueError("permanent")

    with pytest.raises(ValueError, match="permanent"):
        retry_call(
            operation,
            policy=RetryPolicy(max_attempts=5, base_delay_seconds=0),
            is_retryable=lambda exc: isinstance(exc, TimeoutError),
            sleeper=lambda _delay: None,
        )
    assert attempts == 1
