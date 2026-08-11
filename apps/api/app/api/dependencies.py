from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import settings
from app.persistence.database import build_engine, build_session_factory

_default_engine = build_engine()
_default_session_factory = build_session_factory(_default_engine)


@dataclass(frozen=True, slots=True)
class RuntimePolicy:
    demo_mode: bool


def get_session_factory(request: Request) -> sessionmaker[Session]:
    return getattr(request.app.state, "session_factory", _default_session_factory)


def get_session(request: Request) -> Generator[Session, None, None]:
    factory = get_session_factory(request)
    with factory() as session:
        yield session


def get_runtime_policy(request: Request) -> RuntimePolicy:
    return RuntimePolicy(demo_mode=bool(getattr(request.app.state, "demo_mode", settings.demo_mode)))


def require_internal_mutation_allowed(
    policy: RuntimePolicy = Depends(get_runtime_policy),
) -> RuntimePolicy:
    if policy.demo_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "DEMO_MODE_READ_ONLY",
                "message": "Employer/demo mode is read-only; this command is blocked.",
            },
        )
    return policy
