"""LangGraph state for a complaint session.

The form on the left of the UI is a projection of `ComplaintState.complaint`.
Each entry is a `FieldValue`, so every populated field carries its own
provenance: what filled it, how confident the model was, and the exact source
text that justified it.
"""

from __future__ import annotations

import operator
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, TypedDict


class Intent(str, Enum):
    LOG_COMPLAINT = "LOG_COMPLAINT"
    EDIT_COMPLAINT = "EDIT_COMPLAINT"
    EXTRACT_DOCUMENT = "EXTRACT_DOCUMENT"
    ASK_QUESTION = "ASK_QUESTION"


class Source(str, Enum):
    PROMPT = "prompt"
    EDIT = "edit"
    DOCUMENT = "document"


# --- The form ---------------------------------------------------------------
# Mirrors the four sections of the reference UI, in display order.

COMPLAINT_FIELDS: tuple[str, ...] = (
    # 1. Origin & customer details
    "complaint_source",
    "customer_name",
    # 2. Product & batch identification
    "product_name",
    "product_strength_grade",
    "batch_lot_number",
    "manufacturing_date",
    "expiry_date",
    "quantity_affected",
    "quantity_unit",
    # 3. Complaint details
    "complaint_type",
    "complaint_date",
    "detailed_complaint_description",
    # 4. Initial assessment & priority
    "initial_severity",
    "priority",
)

FIELD_LABELS: dict[str, str] = {
    "complaint_source": "Complaint Source",
    "customer_name": "Customer Name",
    "product_name": "Product Name",
    "product_strength_grade": "Product Strength/Grade",
    "batch_lot_number": "Batch/Lot Number",
    "manufacturing_date": "Manufacturing Date",
    "expiry_date": "Expiry Date",
    "quantity_affected": "Quantity Affected",
    "quantity_unit": "Unit",
    "complaint_type": "Complaint Type",
    "complaint_date": "Complaint Date",
    "detailed_complaint_description": "Detailed Complaint Description",
    "initial_severity": "Initial Severity",
    "priority": "Priority",
}

# Fields a QMS will not accept a complaint record without. Drives the
# Completeness Checker.
REQUIRED_FIELDS: tuple[str, ...] = (
    "complaint_source",
    "customer_name",
    "product_name",
    "batch_lot_number",
    "complaint_type",
    "detailed_complaint_description",
    "complaint_date",
)

# Controlled vocabularies. Kept server-side so the model cannot invent values
# the form's dropdowns can't represent.
COMPLAINT_SOURCES = (
    "Email", "Phone", "Customer Portal", "Distributor", "Field Sales",
    "Regulatory Authority", "Customer Letter", "Other",
)
COMPLAINT_TYPES = (
    "Quality Defect", "Packaging Defect", "Labeling Error", "Foreign Matter",
    "Discoloration", "Contamination", "Damaged Goods", "Efficacy Complaint",
    "Adverse Event", "Documentation Error", "Shortage/Quantity Discrepancy",
    "Out of Specification", "Other",
)
SEVERITIES = ("Critical", "Major", "Minor")
PRIORITIES = ("Urgent", "High", "Medium", "Low")


class FieldValue(TypedDict, total=False):
    """One populated form field, with provenance."""

    value: Any
    confidence: float
    evidence: str | None   # verbatim source text that justified this value
    source: str            # prompt | edit | document
    turn_id: int
    updated_at: str


def make_field(
    value: Any,
    *,
    confidence: float = 0.0,
    evidence: str | None = None,
    source: str = Source.PROMPT.value,
    turn_id: int = 0,
) -> FieldValue:
    return FieldValue(
        value=value,
        confidence=confidence,
        evidence=evidence,
        source=source,
        turn_id=turn_id,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


class FieldDiff(TypedDict):
    """A single change, emitted by `merge_complaint` for the audit trail."""

    field: str
    old_value: Any
    new_value: Any
    source: str
    evidence: str | None
    confidence: float


class ComplaintState(TypedDict, total=False):
    """State threaded through the graph.

    Keys written by the parallel enrichment branches (`risk`, `completeness`,
    `duplicates`, `capa`) are deliberately disjoint so concurrent writes never
    collide. `trace` is the exception: every node appends to it, so it carries
    an `operator.add` reducer.
    """

    # Identity
    session_id: str
    complaint_id: str | None
    reference_no: str | None
    turn_id: int

    # This turn's input
    user_input: str
    document_text: str | None
    document_name: str | None
    intent: str
    source: str

    # The form
    complaint: dict[str, FieldValue]
    diffs: list[FieldDiff]

    # Extraction plumbing
    raw_extraction: dict[str, Any] | None
    validation_error: str | None
    repair_attempts: int
    missing_fields: list[str]

    # Enrichment (parallel branches, disjoint keys)
    risk: dict[str, Any] | None
    completeness: dict[str, Any] | None
    duplicates: list[dict[str, Any]] | None
    capa: dict[str, Any] | None
    summary: str | None

    # Output
    assistant_message: str
    trace: Annotated[list[dict[str, Any]], operator.add]
    errors: Annotated[list[str], operator.add]


def new_state(session_id: str, user_input: str = "", turn_id: int = 0) -> ComplaintState:
    return ComplaintState(
        session_id=session_id,
        complaint_id=None,
        reference_no=None,
        turn_id=turn_id,
        user_input=user_input,
        document_text=None,
        document_name=None,
        intent="",
        source=Source.PROMPT.value,
        complaint={},
        diffs=[],
        raw_extraction=None,
        validation_error=None,
        repair_attempts=0,
        missing_fields=[],
        risk=None,
        completeness=None,
        duplicates=None,
        capa=None,
        summary=None,
        assistant_message="",
        trace=[],
        errors=[],
    )


def filled_values(complaint: dict[str, FieldValue]) -> dict[str, Any]:
    """Flatten to `{field: value}`, dropping empties. For prompts and display."""
    out: dict[str, Any] = {}
    for name, entry in (complaint or {}).items():
        value = (entry or {}).get("value")
        if value not in (None, "", []):
            out[name] = value
    return out
