from __future__ import annotations

import base64
import hmac

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def install_basic_access_control(
    app: FastAPI,
    *,
    password: str | None,
    required: bool,
    exempt_paths: tuple[str, ...] = ("/api/v1/health",),
) -> None:
    """Install a deliberately small HTTP Basic gate for the interview demo.

    The gate is only a transport-level access control. It is not a user/account system.
    It relies on HTTPS at the deployment edge. The health endpoint stays unauthenticated so
    load-balancer probes do not need a secret.
    """
    if required and not password:
        raise RuntimeError("REQUIRE_ACCESS_CONTROL=true requires APP_ACCESS_PASSWORD")
    if not password:
        return

    expected = password.encode("utf-8")

    @app.middleware("http")
    async def basic_access_control(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.url.path in exempt_paths:
            return await call_next(request)

        header = request.headers.get("authorization", "")
        if not header.startswith("Basic "):
            return _unauthorized()
        try:
            decoded = base64.b64decode(header[6:], validate=True).decode("utf-8")
            _username, supplied = decoded.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            return _unauthorized()
        if not hmac.compare_digest(supplied.encode("utf-8"), expected):
            return _unauthorized()
        return await call_next(request)


def _unauthorized() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": "Authentication required"},
        headers={"WWW-Authenticate": 'Basic realm="Off Grid Interview Demo"'},
    )
