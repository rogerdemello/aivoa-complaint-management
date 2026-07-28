"""The four enrichment branches, plus the summary that joins them.

`assess_risk`, `check_completeness`, `detect_duplicates` and `recommend_capa`
are independent, so the graph runs them as a parallel fan-out. Each writes to
a distinct state key, which is what makes concurrent writes safe without a
custom reducer.
"""

from __future__ import annotations

import json
import logging
import uuid

from app.graph.nodes.common import Timer, trace
from app.graph.prompts import (
    CAPA_SYSTEM,
    COMPLETENESS_SYSTEM,
    DUPLICATE_SYSTEM,
    RISK_SYSTEM,
    SUMMARY_SYSTEM,
)
from app.graph.schemas import CapaResult, CompletenessResult, RiskResult
from app.graph.state import (
    REQUIRED_FIELDS,
    ComplaintState,
    FieldDiff,
    Source,
    filled_values,
    make_field,
)
from app.llm.client import complete, parse_json_object
from app.llm.registry import ModelRole
from app.services.duplicates import find_candidates

log = logging.getLogger(__name__)


def _record(state: ComplaintState) -> str:
    values = filled_values(state.get("complaint", {}))
    if not values:
        return "(no fields captured yet)"
    return json.dumps(values, indent=2, default=str)


# --- Risk --------------------------------------------------------------------

async def assess_risk(state: ComplaintState) -> dict:
    values = filled_values(state.get("complaint", {}))
    if not values:
        return {"trace": [trace("assess_risk", detail="skipped - empty record")]}

    with Timer() as timer:
        try:
            raw = await complete(
                ModelRole.REASONER,
                RISK_SYSTEM,
                f"Complaint record:\n{_record(state)}",
                json_mode=True,
                temperature=0.1,
                max_tokens=1200,
            )
            result = RiskResult.model_validate(parse_json_object(raw))
        except Exception as exc:
            log.warning("assess_risk failed: %s", exc)
            return {
                "trace": [trace("assess_risk", status="error", detail=str(exc)[:200],
                                role=ModelRole.REASONER, duration_ms=timer.ms)],
                "errors": [f"risk assessment unavailable: {type(exc).__name__}"],
            }

    return {
        "risk": result.model_dump(),
        "trace": [
            trace(
                "assess_risk",
                detail=f"{result.severity} / {result.priority} (score {result.risk_score})",
                role=ModelRole.REASONER,
                duration_ms=timer.ms,
            )
        ],
    }


# --- Completeness ------------------------------------------------------------

async def check_completeness(state: ComplaintState) -> dict:
    """Deterministic gap detection, with the model supplying only the rationale.

    Which fields are missing is a fact, not a judgement, so it is computed in
    Python. The model is asked why each one matters and what to ask the
    customer - the part that genuinely needs language.
    """
    values = filled_values(state.get("complaint", {}))
    missing = [f for f in REQUIRED_FIELDS if f not in values]
    score = round(100 * (len(REQUIRED_FIELDS) - len(missing)) / len(REQUIRED_FIELDS))

    if not missing:
        return {
            "completeness": CompletenessResult(
                score=100, missing_required=[], ready_to_submit=True,
                notes="All mandatory fields captured.",
            ).model_dump(),
            "trace": [trace("check_completeness", detail="100% - ready to submit")],
        }

    with Timer() as timer:
        try:
            raw = await complete(
                ModelRole.REASONER,
                COMPLETENESS_SYSTEM,
                f"Complaint record:\n{_record(state)}\n\n"
                f"Mandatory fields missing: {', '.join(missing)}\n"
                f"Computed score: {score}",
                json_mode=True,
                max_tokens=1200,
            )
            result = CompletenessResult.model_validate(parse_json_object(raw))
            # Trust arithmetic over the model.
            result.score = score
            result.ready_to_submit = False
            payload = result.model_dump()
        except Exception as exc:
            log.warning("check_completeness degraded: %s", exc)
            payload = CompletenessResult(
                score=score,
                missing_required=[
                    {
                        "field": f,
                        "why_it_matters": "Mandatory for a complete complaint record.",
                        "question_to_ask": f"Could you provide the {f.replace('_', ' ')}?",
                    }
                    for f in missing
                ],
                ready_to_submit=False,
            ).model_dump()

    return {
        "completeness": payload,
        "trace": [
            trace("check_completeness", detail=f"{score}% - missing {len(missing)}",
                  role=ModelRole.REASONER, duration_ms=timer.ms)
        ],
    }


# --- CAPA --------------------------------------------------------------------

async def recommend_capa(state: ComplaintState) -> dict:
    values = filled_values(state.get("complaint", {}))
    if not values.get("detailed_complaint_description"):
        return {"trace": [trace("recommend_capa", detail="skipped - no defect described")]}

    with Timer() as timer:
        try:
            raw = await complete(
                ModelRole.REASONER,
                CAPA_SYSTEM,
                f"Complaint record:\n{_record(state)}",
                json_mode=True,
                temperature=0.2,
                max_tokens=1500,
            )
            result = CapaResult.model_validate(parse_json_object(raw))
        except Exception as exc:
            log.warning("recommend_capa failed: %s", exc)
            return {
                "trace": [trace("recommend_capa", status="error", detail=str(exc)[:200],
                                role=ModelRole.REASONER, duration_ms=timer.ms)]
            }

    return {
        "capa": result.model_dump(),
        "trace": [
            trace(
                "recommend_capa",
                detail=f"{len(result.probable_root_causes)} root cause(s), "
                       f"{result.investigation_type}",
                role=ModelRole.REASONER,
                duration_ms=timer.ms,
            )
        ],
    }


# --- Duplicates --------------------------------------------------------------

async def detect_duplicates(state: ComplaintState) -> dict:
    """Retrieve similar prior complaints, then have the model confirm them.

    Retrieval alone over-reports (any two amoxicillin complaints look alike),
    so SQL similarity proposes and the model disposes.
    """
    from app.db.session import get_session_factory

    values = filled_values(state.get("complaint", {}))
    if not values.get("product_name"):
        return {"trace": [trace("detect_duplicates", detail="skipped - no product yet")]}

    complaint_id = state.get("complaint_id")
    with Timer() as timer:
        try:
            async with get_session_factory()() as session:
                candidates = await find_candidates(
                    session,
                    product_name=values.get("product_name"),
                    batch_lot_number=values.get("batch_lot_number"),
                    description=values.get("detailed_complaint_description"),
                    exclude_id=uuid.UUID(complaint_id) if complaint_id else None,
                )
        except Exception as exc:
            log.warning("Duplicate retrieval failed: %s", exc)
            return {
                "trace": [trace("detect_duplicates", status="error", detail=str(exc)[:200],
                                duration_ms=timer.ms)]
            }

        if not candidates:
            return {
                "duplicates": [],
                "trace": [trace("detect_duplicates", detail="no similar complaints on file",
                                duration_ms=timer.ms)],
            }

        try:
            raw = await complete(
                ModelRole.REASONER,
                DUPLICATE_SYSTEM,
                "New complaint:\n" + _record(state) + "\n\nCandidates:\n"
                + json.dumps(
                    [
                        {
                            "reference_no": c["reference_no"],
                            "product_name": c["product_name"],
                            "batch_lot_number": c["batch_lot_number"],
                            "description": (c["description"] or "")[:300],
                            "text_similarity": round(c["similarity"], 2),
                        }
                        for c in candidates
                    ],
                    indent=2,
                ),
                json_mode=True,
                max_tokens=1000,
            )
            confirmed = parse_json_object(raw).get("matches", []) or []
        except Exception as exc:
            log.warning("Duplicate confirmation failed (%s); returning raw candidates.", exc)
            confirmed = [
                {"reference_no": c["reference_no"], "similarity": c["similarity"],
                 "reason": "text similarity only - model confirmation unavailable"}
                for c in candidates[:3]
            ]

    by_ref = {c["reference_no"]: c for c in candidates}
    matches = [
        {
            "complaint_id": by_ref.get(m.get("reference_no"), {}).get("complaint_id"),
            "reference_no": m.get("reference_no"),
            "similarity": float(m.get("similarity", 0.0) or 0.0),
            "reason": m.get("reason", ""),
            "product_name": by_ref.get(m.get("reference_no"), {}).get("product_name"),
            "batch_lot_number": by_ref.get(m.get("reference_no"), {}).get("batch_lot_number"),
        }
        for m in confirmed
        if m.get("reference_no") in by_ref
    ]

    return {
        "duplicates": matches,
        "trace": [
            trace(
                "detect_duplicates",
                detail=f"{len(candidates)} candidate(s) -> {len(matches)} confirmed",
                role=ModelRole.REASONER,
                duration_ms=timer.ms,
            )
        ],
    }


# --- Summary (join point) ----------------------------------------------------

def _sync_assessment_fields(state: ComplaintState) -> tuple[dict, list]:
    """Copy the risk verdict into the form's Initial Assessment section.

    `assess_risk` is the single source of truth for severity and priority. The
    extractor is told not to guess them, so without this the two fields would
    stay empty - and if both stages set them independently, the form and the
    risk panel could contradict each other in front of a reviewer.
    """
    risk = state.get("risk") or {}
    complaint = dict(state.get("complaint", {}) or {})
    diffs: list[FieldDiff] = []

    for field, value in (
        ("initial_severity", risk.get("severity")),
        ("priority", risk.get("priority")),
    ):
        if not value:
            continue
        previous = (complaint.get(field) or {}).get("value")
        if previous == value:
            continue

        complaint[field] = make_field(
            value,
            confidence=float(risk.get("confidence") or 0.7),
            evidence=(risk.get("justification") or "")[:200] or None,
            source=state.get("source", Source.PROMPT.value),
            turn_id=state.get("turn_id", 0),
        )
        diffs.append(
            FieldDiff(
                field=field,
                old_value=previous,
                new_value=value,
                source=state.get("source", Source.PROMPT.value),
                evidence="AI risk assessment",
                confidence=float(risk.get("confidence") or 0.7),
            )
        )

    return complaint, diffs


async def summarize(state: ComplaintState) -> dict:
    """Join node: runs once all four enrichment branches have completed."""
    values = filled_values(state.get("complaint", {}))
    if not values:
        return {"trace": [trace("summarize", detail="skipped - empty record")]}

    # Safe to write `complaint` here: the fan-out has joined, so this is the
    # only writer at this point in the graph.
    complaint, assessment_diffs = _sync_assessment_fields(state)

    with Timer() as timer:
        try:
            raw = await complete(
                ModelRole.REASONER,
                SUMMARY_SYSTEM,
                f"Complaint record:\n{_record(state)}\n\n"
                f"Risk assessment:\n{json.dumps(state.get('risk') or {}, default=str)}",
                json_mode=True,
                max_tokens=400,
            )
            summary = parse_json_object(raw).get("summary")
        except Exception as exc:
            log.warning("summarize failed: %s", exc)
            summary = None

    detail = "QA summary written"
    if assessment_diffs:
        detail += f"; synced {', '.join(d['field'] for d in assessment_diffs)} from risk"

    return {
        "summary": summary,
        "complaint": complaint,
        # Appended, not replaced: merge_complaint's diffs still need to reach
        # the audit trail.
        "diffs": (state.get("diffs") or []) + assessment_diffs,
        "trace": [trace("summarize", detail=detail,
                        role=ModelRole.REASONER, duration_ms=timer.ms)],
    }
