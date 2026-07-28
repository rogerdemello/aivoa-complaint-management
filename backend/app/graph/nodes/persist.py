"""Writing the turn to Postgres: the record, its audit trail, its assessment."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models import Complaint, FieldHistory, RiskAssessment
from app.db.session import get_session_factory
from app.graph.nodes.common import trace
from app.graph.state import ComplaintState, filled_values
from app.llm.registry import ModelRole, registry

log = logging.getLogger(__name__)


async def _next_reference_no(session) -> str:
    """Allocate the next CMP-YYYY-NNNN.

    Derived from the highest existing suffix, not from a row count: seeded or
    manually inserted records leave gaps, and counting collides with numbers
    already issued.
    """
    year = datetime.now(timezone.utc).year
    prefix = f"CMP-{year}-"

    rows = await session.execute(
        select(Complaint.reference_no).where(Complaint.reference_no.like(f"{prefix}%"))
    )
    highest = 0
    for (reference,) in rows:
        suffix = (reference or "")[len(prefix):]
        if suffix.isdigit():
            highest = max(highest, int(suffix))

    return f"{prefix}{highest + 1:04d}"


async def persist(state: ComplaintState) -> dict:
    """Upsert the complaint, append audit rows, and version the assessment.

    Audit rows are written from `diffs`, which `merge_complaint` produced, so
    the trail records exactly what changed rather than a snapshot of the record.
    """
    values = filled_values(state.get("complaint", {}))
    diffs = state.get("diffs", []) or []
    risk = state.get("risk")

    if not values and not risk:
        return {"trace": [trace("persist", detail="nothing to write")]}

    # Reference numbers are allocated read-then-write, so two sessions logging
    # their first complaint at the same moment can pick the same number. The
    # unique index catches it; this retries with a freshly read number.
    for attempt in range(3):
        try:
            return await _write_turn(state, values, diffs, risk)
        except IntegrityError:
            log.warning("Reference number collision (attempt %d/3); retrying.", attempt + 1)
        except Exception as exc:
            log.exception("persist failed")
            return {
                "trace": [trace("persist", status="error", detail=str(exc)[:200])],
                "errors": [f"Could not save the complaint: {type(exc).__name__}"],
            }

    return {
        "trace": [trace("persist", status="error", detail="reference number collision")],
        "errors": ["Could not allocate a complaint reference number."],
    }


async def _write_turn(
    state: ComplaintState, values: dict, diffs: list, risk: dict | None
) -> dict:
    async with get_session_factory()() as session:
        complaint_id = state.get("complaint_id")
        complaint: Complaint | None = None

        if complaint_id:
            complaint = await session.get(Complaint, uuid.UUID(complaint_id))

        if complaint is None:
            complaint = Complaint(
                id=uuid.uuid4(),
                reference_no=await _next_reference_no(session),
                session_id=state.get("session_id", ""),
                status="open",
            )
            session.add(complaint)

        complaint.fields = state.get("complaint", {})
        complaint.product_name = values.get("product_name")
        complaint.batch_lot_number = values.get("batch_lot_number")
        complaint.complaint_type = values.get("complaint_type")
        complaint.description = values.get("detailed_complaint_description")
        complaint.turn_count = state.get("turn_id", 0)

        for diff in diffs:
            session.add(
                FieldHistory(
                    complaint_id=complaint.id,
                    field=diff["field"],
                    old_value=None if diff["old_value"] is None else str(diff["old_value"]),
                    new_value=None if diff["new_value"] is None else str(diff["new_value"]),
                    source=diff["source"],
                    actor="ai-copilot",
                    model=registry.get(ModelRole.EXTRACTOR),
                    evidence=diff.get("evidence"),
                    turn_id=state.get("turn_id", 0),
                )
            )

        if risk:
            session.add(
                RiskAssessment(
                    complaint_id=complaint.id,
                    turn_id=state.get("turn_id", 0),
                    severity=risk.get("severity"),
                    priority=risk.get("priority"),
                    risk_score=risk.get("risk_score"),
                    justification=risk.get("justification"),
                    next_actions=risk.get("next_actions"),
                    regulatory_flags=risk.get("regulatory_flags"),
                    completeness=state.get("completeness"),
                    capa=state.get("capa"),
                    duplicates=state.get("duplicates"),
                    summary=state.get("summary"),
                    model=registry.get(ModelRole.REASONER),
                )
            )

        await session.commit()
        reference_no = complaint.reference_no
        new_id = str(complaint.id)

    return {
        "complaint_id": new_id,
        "reference_no": reference_no,
        "trace": [
            trace("persist", detail=f"{reference_no} saved, {len(diffs)} audit row(s)")
        ],
    }
