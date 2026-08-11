from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_request_id: ContextVar[str | None] = ContextVar("offgrid_request_id", default=None)
_pipeline_run_id: ContextVar[str | None] = ContextVar("offgrid_pipeline_run_id", default=None)


def current_context() -> dict[str, str | None]:
    return {
        "request_id": _request_id.get(),
        "pipeline_run_id": _pipeline_run_id.get(),
    }


@contextmanager
def bind_request(request_id: str) -> Iterator[None]:
    token = _request_id.set(request_id)
    try:
        yield
    finally:
        _request_id.reset(token)


@contextmanager
def bind_pipeline_run(pipeline_run_id: str) -> Iterator[None]:
    token = _pipeline_run_id.set(pipeline_run_id)
    try:
        yield
    finally:
        _pipeline_run_id.reset(token)
