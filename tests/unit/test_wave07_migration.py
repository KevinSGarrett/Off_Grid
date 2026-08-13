from pathlib import Path
import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def test_wave07_migration_adds_phase_and_relationship_resolution_fields(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "wave07.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    inspector = sa.inspect(sa.create_engine(url))
    project_cols = {c["name"] for c in inspector.get_columns("projects")}
    rel_cols = {c["name"] for c in inspector.get_columns("project_relationships")}
    assert {"phase_label", "phase_start_number", "phase_end_number"} <= project_cols
    assert {"confidence_score", "rationale"} <= rel_cols
