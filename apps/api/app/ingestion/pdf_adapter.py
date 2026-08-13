from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import fitz

from app.ingestion.errors import MalformedPDFError, UnsupportedReportError
from app.ingestion.types import ReportType

PARSER_VERSION = "constructconnect-pdf-0.5.0"


@dataclass(frozen=True)
class PDFPayload:
    path: Path
    content: bytes
    sha256: str
    page_text: tuple[str, ...]

    @property
    def first_page(self) -> str:
        return self.page_text[0] if self.page_text else ""


def load_pdf(path: str | Path) -> PDFPayload:
    source = Path(path)
    try:
        content = source.read_bytes()
    except OSError as exc:
        raise MalformedPDFError(f"unable to read PDF: {source}") from exc
    if not content.startswith(b"%PDF"):
        raise MalformedPDFError("payload does not have a PDF header")
    try:
        doc = fitz.open(stream=content, filetype="pdf")
        if len(doc) < 1:
            raise MalformedPDFError("PDF contains no pages")
        pages = tuple(page.get_text("text") for page in doc)
    except Exception as exc:  # PyMuPDF raises several concrete low-level exception types.
        if isinstance(exc, MalformedPDFError):
            raise
        raise MalformedPDFError("PDF could not be parsed") from exc
    return PDFPayload(source, content, sha256(content).hexdigest(), pages)


def detect_report_type(payload: PDFPayload) -> ReportType:
    first = payload.first_page
    if "Project ID #:" in first and "Project Description" in first and "Design Team" in first:
        return "PROJECT"
    if "Company ID#:" in first and "Planning Stage Projects" in first and "Bidding Role Projects" in "\n".join(payload.page_text):
        return "COMPANY"
    raise UnsupportedReportError(
        "Validated against the supplied Project and Company report formats; architecture supports additional adapters."
    )
