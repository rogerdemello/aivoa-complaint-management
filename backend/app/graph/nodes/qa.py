"""Answering questions about the complaint on file (the ASK_QUESTION branch)."""

from __future__ import annotations

import json
import logging

from app.graph.nodes.common import Timer, trace
from app.graph.prompts import QA_SYSTEM
from app.graph.state import ComplaintState, filled_values
from app.llm.client import complete, parse_json_object
from app.llm.registry import ModelRole

log = logging.getLogger(__name__)


async def answer_question(state: ComplaintState) -> dict:
    values = filled_values(state.get("complaint", {}))

    with Timer() as timer:
        try:
            raw = await complete(
                ModelRole.REASONER,
                QA_SYSTEM,
                "Complaint record:\n"
                + json.dumps(values, indent=2, default=str)
                + "\n\nRisk assessment:\n"
                + json.dumps(state.get("risk") or {}, indent=2, default=str)
                + f"\n\nQuestion:\n\"\"\"{state.get('user_input', '')}\"\"\"",
                json_mode=True,
                max_tokens=600,
            )
            answer = parse_json_object(raw).get("answer") or "I don't have an answer for that."
        except Exception as exc:
            log.warning("answer_question failed: %s", exc)
            answer = "I couldn't process that question just now. Please try rephrasing it."

    return {
        "assistant_message": answer,
        "trace": [trace("answer_question", detail="answered from the record",
                        role=ModelRole.REASONER, duration_ms=timer.ms)],
    }
