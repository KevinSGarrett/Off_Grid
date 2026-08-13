from __future__ import annotations

import re
import time
from uuid import uuid4

from fastapi import FastAPI, Request

from app.observability.context import bind_request
from app.observability.logging import get_logger

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
logger = get_logger("http")


def _request_id_from(request: Request) -> str:
    supplied = (request.headers.get("x-request-id") or "").strip()
    if supplied and _REQUEST_ID.fullmatch(supplied):
        return supplied
    return f"req-{uuid4()}"


def install_request_observability(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_observability(request: Request, call_next):
        request_id = _request_id_from(request)
        started = time.perf_counter()
        with bind_request(request_id):
            try:
                response = await call_next(request)
            except Exception:
                logger.exception(
                    "http.request.failed",
                    extra={
                        "safe_extra": {
                            "method": request.method,
                            "path": request.url.path,
                            "duration_ms": int((time.perf_counter() - started) * 1000),
                        }
                    },
                )
                raise
            duration_ms = int((time.perf_counter() - started) * 1000)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "http.request.completed",
                extra={
                    "safe_extra": {
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                    }
                },
            )
            return response
