from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence


class SourceBlobStore(Protocol):
    def put_private(self, source_id: str, source_path: Path) -> str:
        """Persist/refer to private source bytes and return an opaque reference."""
        ...

    def exists(self, blob_ref: str) -> bool: ...


class SourceParser(Protocol):
    report_type: str

    def can_parse(self, *, filename: str, extracted_text: str) -> bool: ...

    def parse(self, source_ref: str) -> Mapping[str, Any]: ...


class UnitOfWork(Protocol):
    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class AIIntelligencePort(Protocol):
    def analyze(self, *, task: str, evidence: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        """Return a structured proposal; caller remains responsible for grounding/acceptance."""
        ...


class ContactResearchPort(Protocol):
    def search_candidates(self, criteria: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]: ...


class CRMPort(Protocol):
    def preview(self, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def execute(self, payload: Mapping[str, Any], *, idempotency_key: str) -> Mapping[str, Any]: ...


class ReportingPort(Protocol):
    def preview_report(self, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...


class TaskPort(Protocol):
    def preview_task(self, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...
