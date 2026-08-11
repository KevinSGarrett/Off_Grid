from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_session, require_internal_mutation_allowed
from app.api.serialization import jsonable
from app.pipeline.orchestrator import CommercialPipelineOrchestrator

router = APIRouter(tags=["ingestion"])


def _safe_filename(value: str | None) -> str:
    name = Path(value or "upload.pdf").name
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .") or "upload.pdf"
    return name[:240]


@router.post("/ingest", status_code=status.HTTP_201_CREATED)
async def ingest_document(
    request: Request,
    file: UploadFile = File(...),
    _policy=Depends(require_internal_mutation_allowed),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    filename = _safe_filename(file.filename)
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail={"code": "UNSUPPORTED_MEDIA", "message": "Wave 12 ingestion accepts PDF reports."})
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail={"code": "EMPTY_UPLOAD", "message": "Uploaded document is empty."})
    private_dir = Path(request.app.state.private_upload_dir) / str(uuid4())
    private_dir.mkdir(parents=True, exist_ok=True)
    path = private_dir / filename
    path.write_bytes(data)
    try:
        result = CommercialPipelineOrchestrator(session).ingest(path)
    except Exception as exc:
        raise HTTPException(status_code=422, detail={"code": "INGESTION_FAILED", "message": str(exc)}) from exc
    return {"status": "accepted", "private_source_retained": True, "result": jsonable(result)}
