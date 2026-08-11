from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.05
    max_delay_seconds: float = 0.5

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("retry delays must be non-negative")


def retry_call[T](
    operation: Callable[[], T],
    *,
    policy: RetryPolicy,
    is_retryable: Callable[[BaseException], bool],
    sleeper: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, BaseException, float], None] | None = None,
) -> T:
    """Execute a bounded retry loop for transient provider failures only."""

    attempt = 1
    while True:
        try:
            return operation()
        except BaseException as exc:
            if attempt >= policy.max_attempts or not is_retryable(exc):
                raise
            delay = min(policy.max_delay_seconds, policy.base_delay_seconds * (2 ** (attempt - 1)))
            if on_retry is not None:
                on_retry(attempt, exc, delay)
            sleeper(delay)
            attempt += 1
