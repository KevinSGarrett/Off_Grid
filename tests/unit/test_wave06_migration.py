from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def test_wave06_migration_adds_decision_eligibility_columns(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "wave06.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    inspector = sa.inspect(sa.create_engine(url))
    cols = {c["name"] for c in inspector.get_columns("source_observations")}
    assert {"decision_eligible", "decision_eligibility_reason"} <= cols
