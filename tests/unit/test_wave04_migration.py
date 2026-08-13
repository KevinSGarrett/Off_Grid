from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
import sqlalchemy as sa

from app.models import Base


def test_alembic_baseline_upgrade_and_downgrade(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "wave04.db"
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    cfg = Config("alembic.ini")

    command.upgrade(cfg, "head")
    engine = sa.create_engine(database_url)
    inspector = sa.inspect(engine)
    assert set(Base.metadata.tables).issubset(set(inspector.get_table_names()))
    assert "alembic_version" in inspector.get_table_names()

    command.downgrade(cfg, "base")
    remaining = set(sa.inspect(engine).get_table_names())
    assert not (set(Base.metadata.tables) & remaining)
