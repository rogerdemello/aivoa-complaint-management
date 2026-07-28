"""SQLAlchemy models.

`complaints.fields` holds the live form state as JSONB, one entry per form
field, shaped like `FieldValue` in `app.graph.state`:

    {"value": ..., "confidence": 0.9, "evidence": "...", "source": "prompt",
     "turn_id": 3, "updated_at": "..."}

A few of those values are also mirrored into flat columns so duplicate
detection can run a real SQL similarity query rather than scanning JSON.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class Complaint(Base):
    """The system of record for one complaint."""

    __tablename__ = "complaints"

    id: Mapped[uuid.UUID] = _uuid_pk()
    reference_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")

    # Full form state, including per-field provenance.
    fields: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Mirrored for similarity search (see services/duplicates.py).
    product_name: Mapped[str | None] = mapped_column(String(255), index=True)
    batch_lot_number: Mapped[str | None] = mapped_column(String(128), index=True)
    complaint_type: Mapped[str | None] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)

    turn_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    history: Mapped[list["FieldHistory"]] = relationship(
        back_populates="complaint", cascade="all, delete-orphan"
    )
    risk_assessments: Mapped[list["RiskAssessment"]] = relationship(
        back_populates="complaint", cascade="all, delete-orphan"
    )


class FieldHistory(Base):
    """Append-only audit trail of every field mutation.

    Never updated or deleted. This is the 21 CFR Part 11 §11.10(e) requirement
    for a computer-generated, time-stamped audit trail that records changes
    without obscuring previously recorded values.
    """

    __tablename__ = "complaint_field_history"

    id: Mapped[uuid.UUID] = _uuid_pk()
    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), index=True
    )

    field: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)

    # How the value arrived: prompt | edit | document
    source: Mapped[str] = mapped_column(String(32))
    # Who/what made the change. Always an AI actor in this build, but the
    # column exists because a real QMS records a human identity here.
    actor: Mapped[str] = mapped_column(String(64), default="ai-copilot")
    model: Mapped[str | None] = mapped_column(String(128))
    evidence: Mapped[str | None] = mapped_column(Text)
    turn_id: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    complaint: Mapped[Complaint] = relationship(back_populates="history")


class RiskAssessment(Base):
    """One AI risk assessment. Versioned: a new row per mutating turn."""

    __tablename__ = "risk_assessments"

    id: Mapped[uuid.UUID] = _uuid_pk()
    complaint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), index=True
    )
    turn_id: Mapped[int] = mapped_column(Integer, default=0)

    severity: Mapped[str | None] = mapped_column(String(32))
    priority: Mapped[str | None] = mapped_column(String(32))
    risk_score: Mapped[int | None] = mapped_column(Integer)
    justification: Mapped[str | None] = mapped_column(Text)
    next_actions: Mapped[list | None] = mapped_column(JSONB)
    regulatory_flags: Mapped[list | None] = mapped_column(JSONB)

    # Enrichment branches, stored alongside the assessment they belong to.
    completeness: Mapped[dict | None] = mapped_column(JSONB)
    capa: Mapped[dict | None] = mapped_column(JSONB)
    duplicates: Mapped[list | None] = mapped_column(JSONB)
    summary: Mapped[str | None] = mapped_column(Text)

    model: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    complaint: Mapped[Complaint] = relationship(back_populates="risk_assessments")


class Document(Base):
    """An uploaded complaint document and the text pulled out of it."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    complaint_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), index=True, nullable=True
    )
    session_id: Mapped[str] = mapped_column(String(64), index=True)

    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    extracted_text: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Message(Base):
    """Copilot conversation history, kept for replay and for the demo video."""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    complaint_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), nullable=True
    )

    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(32))
    turn_id: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
