#!/usr/bin/env python3
from __future__ import annotations

import argparse
import dataclasses
import json
from decimal import Decimal
from enum import Enum
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.ingestion.service import ConstructConnectIngestionService
from app.models import Base, Project
from app.persistence.database import build_engine
from app.scoring.qualification import QualificationService

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "context/private_source_documents/Stafford-Technology-Campus-Phases-3-4.pdf"


def jsonable(value):
    if dataclasses.is_dataclass(value):
        return {field.name: jsonable(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, (list, tuple)):
        return [jsonable(x) for x in value]
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


def main() -> int:
    ap = argparse.ArgumentParser(description="Run Wave 6 computed qualification on the real Stafford source.")
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ConstructConnectIngestionService(session).ingest(args.source)
        project = session.scalar(sa.select(Project).where(Project.source_system == "constructconnect", Project.external_id.is_not(None)))
        if project is None:
            raise RuntimeError("No ConstructConnect project was produced")
        result = QualificationService(session).evaluate(project.id, persist=True)
        payload = jsonable(result)

    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
