"""Extraction, validation with a repair loop, and the sparse-patch merge.

`merge_complaint` is the most important function in the project. The demo
explicitly requires that correcting one field preserves every other field, and
the usual failure is an LLM re-emitting the whole object and nulling anything
it wasn't reminded of. Extraction here is sparse (absent key == not mentioned)
and the merge only ever touches keys the model actually returned.
"""

from __future__ import annotations

import logging

from app.graph.nodes.common import Timer, trace
from app.graph.prompts import (
    EXTRACT_NEW_SYSTEM,
    EXTRACT_PATCH_SYSTEM,
    extract_user,
)
from app.graph.schemas import ExtractionResult
from app.graph.state import (
    ComplaintState,
    FieldDiff,
    Source,
    filled_values,
    make_field,
)
from app.llm.client import complete, parse_json_object
from app.llm.registry import ModelRole, registry

log = logging.getLogger(__name__)

MAX_REPAIRS = 2


async def _run_extraction(state: ComplaintState, *, patch: bool) -> dict:
    system = EXTRACT_PATCH_SYSTEM if patch else EXTRACT_NEW_SYSTEM
    text = state.get("document_text") or state.get("user_input", "")
    current = filled_values(state.get("complaint", {})) if patch else None
    node = "extract_patch" if patch else "extract_complaint"

    with Timer() as timer:
        try:
            raw = await complete(
                ModelRole.EXTRACTOR,
                system,
                extract_user(text, current, state.get("validation_error")),
                json_mode=True,
                max_tokens=2000,
            )
            parsed = parse_json_object(raw)
        except Exception as exc:
            log.warning("%s failed: %s", node, exc)
            return {
                "raw_extraction": None,
                "validation_error": f"{type(exc).__name__}: {exc}",
                "trace": [
                    trace(
                        node, status="error", detail=str(exc)[:200],
                        role=ModelRole.EXTRACTOR, duration_ms=timer.ms,
                    )
                ],
            }

    attempt = state.get("repair_attempts", 0)
    return {
        "raw_extraction": parsed,
        "validation_error": None,
        "trace": [
            trace(
                node,
                detail=(
                    f"{len(parsed.get('fields', {}) or {})} field(s) returned"
                    + (f" (repair attempt {attempt})" if attempt else "")
                ),
                role=ModelRole.EXTRACTOR,
                duration_ms=timer.ms,
            )
        ],
    }


async def extract_complaint(state: ComplaintState) -> dict:
    """Full extraction for a new complaint (prompt or document)."""
    return await _run_extraction(state, patch=False)


async def extract_patch(state: ComplaintState) -> dict:
    """Sparse extraction: only the fields this correction actually changes."""
    return await _run_extraction(state, patch=True)


def validate_extraction(state: ComplaintState) -> dict:
    """Validate against the Pydantic contract.

    On failure the error text is put back into state so the extractor can see
    exactly what the validator rejected on its next attempt.
    """
    raw = state.get("raw_extraction")
    attempts = state.get("repair_attempts", 0)

    if raw is None:
        return {
            "repair_attempts": attempts + 1,
            "trace": [trace("validate_extraction", status="error",
                            detail="nothing to validate")],
        }

    try:
        ExtractionResult.model_validate(raw)
    except Exception as exc:
        message = str(exc)[:600]
        log.info("Validation failed (attempt %d): %s", attempts + 1, message[:200])
        return {
            "validation_error": message,
            "repair_attempts": attempts + 1,
            "trace": [
                trace(
                    "validate_extraction",
                    status="error",
                    detail=f"schema rejected (attempt {attempts + 1}/{MAX_REPAIRS})",
                )
            ],
        }

    return {
        "validation_error": None,
        "trace": [trace("validate_extraction", detail="schema OK")],
    }


def validation_branch(state: ComplaintState) -> str:
    """Retry the extractor, or move on."""
    if not state.get("validation_error") and state.get("raw_extraction") is not None:
        return "merge_complaint"
    if state.get("repair_attempts", 0) < MAX_REPAIRS:
        # Re-enter whichever extractor produced the bad output.
        return "extract_patch" if state.get("source") == Source.EDIT.value else "extract_complaint"
    # Out of retries: continue with whatever is already on file rather than
    # failing the turn outright.
    return "merge_complaint"


def merge_complaint(state: ComplaintState) -> dict:
    """Apply the extracted patch over existing state, emitting a diff per change.

    Only keys present in the extraction are touched. Everything else survives
    untouched - that is the whole contract of the Edit Complaint tool.
    """
    existing = dict(state.get("complaint", {}) or {})
    raw = state.get("raw_extraction") or {}
    turn_id = state.get("turn_id", 0)
    source = state.get("source", Source.PROMPT.value)

    try:
        result = ExtractionResult.model_validate(raw)
    except Exception:
        # Unrecoverable after the repair loop; keep the record as it stands.
        return {
            "diffs": [],
            "trace": [trace("merge_complaint", status="error",
                            detail="no valid extraction; record unchanged")],
        }

    diffs: list[FieldDiff] = []
    for name, extracted in result.fields.items():
        if extracted.value is None:
            # Sparse contract: a null means "not mentioned", never "clear it".
            continue

        previous = (existing.get(name) or {}).get("value")
        if previous == extracted.value:
            continue

        existing[name] = make_field(
            extracted.value,
            confidence=extracted.confidence,
            evidence=extracted.evidence,
            source=source,
            turn_id=turn_id,
        )
        diffs.append(
            FieldDiff(
                field=name,
                old_value=previous,
                new_value=extracted.value,
                source=source,
                evidence=extracted.evidence,
                confidence=extracted.confidence,
            )
        )

    detail = (
        f"{len(diffs)} field(s) changed: {', '.join(d['field'] for d in diffs)}"
        if diffs
        else "no changes"
    )
    return {
        "complaint": existing,
        "diffs": diffs,
        "missing_fields": result.missing,
        "raw_extraction": None,
        "repair_attempts": 0,
        "trace": [
            trace("merge_complaint", detail=detail, model=registry.get(ModelRole.EXTRACTOR))
        ],
    }
