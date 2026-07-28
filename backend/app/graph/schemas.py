"""Pydantic contracts for every structured LLM response.

Validation failures here are not errors to swallow - they drive the graph's
repair loop (`validate_extraction` routes back to the extractor with the
message below appended to the prompt).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.graph.state import COMPLAINT_FIELDS


class ExtractedField(BaseModel):
    """One field the model claims to have found."""

    value: Any = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    # Verbatim span from the source that justifies `value`. The UI shows this
    # on hover, which is what makes an AI-populated regulated form auditable.
    evidence: str | None = None

    @field_validator("value")
    @classmethod
    def blank_to_none(cls, v: Any) -> Any:
        if isinstance(v, str):
            cleaned = v.strip()
            # Small models like to answer "N/A" or "unknown" instead of null.
            if cleaned.lower() in {"", "n/a", "na", "none", "null", "unknown", "not specified"}:
                return None
            return cleaned
        return v


class ExtractionResult(BaseModel):
    """Whatever the extractor found this turn.

    Sparse by design: absent keys mean "not mentioned", which is what lets an
    edit patch a batch number without erasing the customer name.
    """

    fields: dict[str, ExtractedField] = Field(default_factory=dict)
    missing: list[str] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("fields")
    @classmethod
    def drop_unknown_fields(
        cls, v: dict[str, ExtractedField]
    ) -> dict[str, ExtractedField]:
        # Ignore hallucinated field names rather than failing the whole turn.
        return {k: fv for k, fv in v.items() if k in COMPLAINT_FIELDS}


class IntentResult(BaseModel):
    intent: Literal[
        "LOG_COMPLAINT", "EDIT_COMPLAINT", "EXTRACT_DOCUMENT", "ASK_QUESTION"
    ]
    reasoning: str | None = None


class RiskResult(BaseModel):
    """The AI Copilot Risk Assessment panel."""

    severity: Literal["Critical", "Major", "Minor"]
    priority: Literal["Urgent", "High", "Medium", "Low"]
    risk_score: int = Field(ge=0, le=100)
    justification: str
    next_actions: list[str] = Field(default_factory=list)
    regulatory_flags: list[str] = Field(default_factory=list)
    patient_safety_impact: str | None = None
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class MissingItem(BaseModel):
    field: str
    why_it_matters: str
    question_to_ask: str


class CompletenessResult(BaseModel):
    score: int = Field(ge=0, le=100)
    missing_required: list[MissingItem] = Field(default_factory=list)
    ready_to_submit: bool = False
    notes: str | None = None


class RootCause(BaseModel):
    cause: str
    # Ishikawa 6M - the standard cause categories in pharma investigations.
    category: Literal[
        "Man", "Machine", "Material", "Method", "Measurement", "Mother Nature"
    ]
    likelihood: Literal["High", "Medium", "Low"]
    rationale: str | None = None


class CapaResult(BaseModel):
    probable_root_causes: list[RootCause] = Field(default_factory=list)
    immediate_correction: str | None = None
    corrective_actions: list[str] = Field(default_factory=list)
    preventive_actions: list[str] = Field(default_factory=list)
    investigation_type: Literal["Phase I", "Phase II", "Not Required"] = "Phase I"


class DuplicateMatch(BaseModel):
    complaint_id: str
    reference_no: str
    similarity: float = Field(ge=0.0, le=1.0)
    reason: str
    product_name: str | None = None
    batch_lot_number: str | None = None
