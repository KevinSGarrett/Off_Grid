from __future__ import annotations


class IngestionError(ValueError):
    """Base class for source-ingestion failures."""


class MalformedPDFError(IngestionError):
    """Raised when a payload is not a readable PDF."""


class UnsupportedReportError(IngestionError):
    """Raised when a readable PDF is not one of the validated report formats."""


class ParserReconciliationError(IngestionError):
    """Raised when a company report cannot reconcile its own advertised row counts."""
