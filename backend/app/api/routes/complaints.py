"""Complaint intake endpoints. Both AI entry points stream over SSE."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.config import get_settings
from app.db.models import Complaint, Document, FieldHistory, Message
from app.db.session import get_db
from app.graph.nodes.document import extract_text
from app.graph.state import COMPLAINT_FIELDS, FIELD_LABELS, REQUIRED_FIELDS
from app.services.runner import runner

log = logging.getLogger(__name__)
router = APIRouter()


class MessageIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=20_000)


def _sse(events: AsyncIterator[dict]) -> EventSourceResponse:
    async def stream():
        async for item in events:
            yield {"event": item["event"], "data": json.dumps(item["data"], default=str)}

    return EventSourceResponse(stream())


@router.post("/sessions")
async def create_session() -> dict:
    return {"session_id": str(uuid.uuid4())}


@router.get("/form-schema")
async def form_schema() -> dict:
    """Field order, labels and which fields are mandatory.

    The frontend renders the form from this rather than hard-coding it twice.
    """
    return {
        "fields": [
            {
                "name": name,
                "label": FIELD_LABELS[name],
                "required": name in REQUIRED_FIELDS,
            }
            for name in COMPLAINT_FIELDS
        ]
    }


@router.post("/complaint/message")
async def complaint_message(payload: MessageIn, db: AsyncSession = Depends(get_db)):
    """Log Complaint / Edit Complaint / question - the router decides which."""
    db.add(Message(session_id=payload.session_id, role="user", content=payload.text))
    await db.commit()

    return _sse(runner.run(payload.session_id, user_input=payload.text))


@router.post("/complaint/document")
async def complaint_document(
    session_id: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Document Extraction tool."""
    settings = get_settings()
    data = await file.read()

    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            413, f"File exceeds the {settings.aivoa_max_upload_mb} MB limit."
        )

    try:
        text = extract_text(file.filename or "", file.content_type, data)
    except Exception as exc:
        raise HTTPException(422, f"Could not read {file.filename}: {exc}") from exc

    if not text.strip():
        raise HTTPException(
            422,
            f"No text found in {file.filename}. Scanned images need OCR, which is "
            f"out of scope for this build.",
        )

    db.add(
        Document(
            session_id=session_id,
            filename=file.filename or "document",
            content_type=file.content_type,
            size_bytes=len(data),
            extracted_text=text,
        )
    )
    await db.commit()

    return _sse(
        runner.run(session_id, document_text=text, document_name=file.filename or "document")
    )


@router.get("/complaint/session/{session_id}")
async def get_session_state(session_id: str) -> dict:
    """Rehydrate the UI after a refresh."""
    state = await runner.get_state(session_id)
    return {
        "session_id": session_id,
        "complaint": state.get("complaint", {}),
        "risk": state.get("risk"),
        "completeness": state.get("completeness"),
        "capa": state.get("capa"),
        "duplicates": state.get("duplicates"),
        "summary": state.get("summary"),
        "reference_no": state.get("reference_no"),
        "complaint_id": state.get("complaint_id"),
        "turn_id": state.get("turn_id", 0),
    }


@router.get("/complaint/{complaint_id}/audit")
async def get_audit_trail(complaint_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    """Append-only field history - 21 CFR Part 11 §11.10(e)."""
    rows = await db.execute(
        select(FieldHistory)
        .where(FieldHistory.complaint_id == complaint_id)
        .order_by(desc(FieldHistory.created_at))
    )
    return {
        "entries": [
            {
                "id": str(r.id),
                "field": r.field,
                "label": FIELD_LABELS.get(r.field, r.field),
                "old_value": r.old_value,
                "new_value": r.new_value,
                "source": r.source,
                "actor": r.actor,
                "model": r.model,
                "evidence": r.evidence,
                "turn_id": r.turn_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows.scalars()
        ]
    }


@router.get("/complaints")
async def list_complaints(db: AsyncSession = Depends(get_db), limit: int = 50) -> dict:
    rows = await db.execute(
        select(Complaint).order_by(desc(Complaint.created_at)).limit(limit)
    )
    return {
        "complaints": [
            {
                "id": str(c.id),
                "reference_no": c.reference_no,
                "product_name": c.product_name,
                "batch_lot_number": c.batch_lot_number,
                "complaint_type": c.complaint_type,
                "status": c.status,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in rows.scalars()
        ]
    }
