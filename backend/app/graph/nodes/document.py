"""Document parsing.

The brief states production-grade OCR is not required, so this handles the
text-bearing formats a complaint actually arrives in: PDF, email and plain
text. Extraction quality is the LLM's job; this node only has to produce clean
text for it.
"""

from __future__ import annotations

import email
import io
import logging
from email import policy

from app.graph.nodes.common import Timer, trace
from app.graph.state import ComplaintState

log = logging.getLogger(__name__)

MAX_CHARS = 20_000


def parse_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    return "\n\n".join(p for p in pages if p)


def parse_eml(data: bytes) -> str:
    """Flatten an email to `Header: value` lines plus the plain-text body."""
    message = email.message_from_bytes(data, policy=policy.default)

    parts = [
        f"{label}: {message.get(header)}"
        for label, header in (
            ("From", "From"), ("To", "To"), ("Subject", "Subject"), ("Date", "Date"),
        )
        if message.get(header)
    ]

    body = ""
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_content()
                break
    else:
        body = message.get_content()

    return "\n".join(parts) + "\n\n" + (body or "").strip()


def extract_text(filename: str, content_type: str | None, data: bytes) -> str:
    """Dispatch on extension, falling back to a lenient text decode."""
    name = (filename or "").lower()

    if name.endswith(".pdf") or (content_type or "").endswith("pdf"):
        return parse_pdf(data)
    if name.endswith(".eml") or (content_type or "") == "message/rfc822":
        return parse_eml(data)

    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="replace")


async def parse_document(state: ComplaintState) -> dict:
    """Trim and trace text that the API layer already pulled out of the upload.

    File bytes never enter graph state - they would be checkpointed into
    Postgres on every turn. The upload route decodes to text first.
    """
    text = state.get("document_text") or ""
    name = state.get("document_name") or "document"

    with Timer() as timer:
        cleaned = text.strip()
        truncated = len(cleaned) > MAX_CHARS
        if truncated:
            cleaned = cleaned[:MAX_CHARS]

    if not cleaned:
        return {
            "trace": [trace("parse_document", status="error",
                            detail=f"no text recoverable from {name}")],
            "errors": [f"Could not read any text from {name}."],
        }

    return {
        "document_text": cleaned,
        "trace": [
            trace(
                "parse_document",
                detail=f"{name}: {len(cleaned):,} chars"
                       + (" (truncated)" if truncated else ""),
                duration_ms=timer.ms,
            )
        ],
    }
