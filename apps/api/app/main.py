from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, sessionmaker

from app import __version__
from app.api.router import api_router
from app.core.settings import settings
from app.observability.logging import configure_structured_logging
from app.observability.middleware import install_request_observability
from app.persistence.database import build_engine, build_session_factory, create_schema


def create_app(
    *,
    session_factory: sessionmaker[Session] | None = None,
    demo_mode: bool | None = None,
    initialize_schema: bool | None = None,
    upload_dir: str | Path | None = None,
) -> FastAPI:
    configure_structured_logging(level=settings.log_level)
    app = FastAPI(
        title="Off Grid Commercial Intelligence Engine",
        version=__version__,
        description="Evidence-backed commercial intelligence for Off Grid Innovation USA.",
    )
    if session_factory is None:
        engine = build_engine()
        should_initialize = (
            settings.auto_create_schema if initialize_schema is None else initialize_schema
        )
        if should_initialize:
            create_schema(engine)
        session_factory = build_session_factory(engine)
    app.state.session_factory = session_factory
    app.state.demo_mode = settings.demo_mode if demo_mode is None else demo_mode
    app.state.private_upload_dir = Path(upload_dir or "data/private/inbox")
    install_request_observability(app)
    app.include_router(api_router)
    if settings.serve_web:
        web_dir = Path(settings.web_static_dir)
        if web_dir.exists():
            app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app


app = create_app()
