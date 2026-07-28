"""Intent routing.

Routing is an explicit graph node rather than an agentic tool-calling loop.
Two reasons: the assignment's mandated Groq models do not support native
function calling, and in a GxP context a deterministic, inspectable path
through the graph is easier to validate than a model deciding its own control
flow.
"""

from __future__ import annotations

import logging

from app.graph.nodes.common import Timer, trace
from app.graph.prompts import ROUTER_SYSTEM, router_user
from app.graph.schemas import IntentResult
from app.graph.state import ComplaintState, Intent, Source, filled_values
from app.llm.client import complete, parse_json_object
from app.llm.registry import ModelRole

log = logging.getLogger(__name__)


async def route_intent(state: ComplaintState) -> dict:
    """Classify this turn as log / edit / question.

    Document uploads bypass the model: the API layer sets the intent directly,
    because we already know a file arrived.
    """
    if state.get("intent") == Intent.EXTRACT_DOCUMENT.value:
        return {
            "source": Source.DOCUMENT.value,
            "trace": [trace("route_intent", detail="document upload (no model call)")],
        }

    current = filled_values(state.get("complaint", {}))
    has_complaint = bool(current)

    # A first message can only ever be a new complaint, so skip the call.
    if not has_complaint:
        return {
            "intent": Intent.LOG_COMPLAINT.value,
            "source": Source.PROMPT.value,
            "trace": [trace("route_intent", detail="no complaint on file -> LOG_COMPLAINT")],
        }

    with Timer() as timer:
        try:
            raw = await complete(
                ModelRole.ROUTER,
                ROUTER_SYSTEM,
                router_user(state.get("user_input", ""), current, has_complaint),
                json_mode=True,
                max_tokens=200,
            )
            result = IntentResult.model_validate(parse_json_object(raw))
            intent, reasoning = result.intent, result.reasoning
        except Exception as exc:
            # A complaint exists and the router failed, so an edit is the safe
            # assumption: it patches rather than replacing the record.
            log.warning("Router failed (%s); defaulting to EDIT_COMPLAINT.", exc)
            intent = Intent.EDIT_COMPLAINT.value
            reasoning = f"router error, defaulted to edit ({type(exc).__name__})"

    source = (
        Source.EDIT.value
        if intent == Intent.EDIT_COMPLAINT.value
        else Source.PROMPT.value
    )
    return {
        "intent": intent,
        "source": source,
        "trace": [
            trace(
                "route_intent",
                detail=f"{intent} - {reasoning}",
                role=ModelRole.ROUTER,
                duration_ms=timer.ms,
            )
        ],
    }


def intent_branch(state: ComplaintState) -> str:
    """Conditional edge target after routing."""
    intent = state.get("intent", Intent.LOG_COMPLAINT.value)
    if intent == Intent.EXTRACT_DOCUMENT.value:
        return "parse_document"
    if intent == Intent.EDIT_COMPLAINT.value:
        return "extract_patch"
    if intent == Intent.ASK_QUESTION.value:
        return "answer_question"
    return "extract_complaint"
