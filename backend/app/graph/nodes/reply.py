"""Composing the Copilot's chat reply.

Deterministic on purpose. The reply narrates what the graph just did, and that
is knowledge the code already has - spending another model call (and another
chance to hallucinate) to restate it would be worse on every axis.
"""

from __future__ import annotations

from app.graph.nodes.common import trace
from app.graph.state import FIELD_LABELS, ComplaintState, Intent


def _humanise(field: str) -> str:
    return FIELD_LABELS.get(field, field.replace("_", " ").title())


def compose_reply(state: ComplaintState) -> dict:
    if state.get("assistant_message"):
        return {}  # answer_question already replied

    diffs = state.get("diffs", []) or []
    intent = state.get("intent")
    lines: list[str] = []

    if not diffs:
        lines.append(
            "I couldn't find any new complaint details in that. Could you include "
            "the product, batch number and what went wrong?"
        )
    elif intent == Intent.EDIT_COMPLAINT.value:
        changed = ", ".join(f"**{_humanise(d['field'])}**" for d in diffs)
        lines.append(f"Updated {changed}. Everything else on the record is unchanged.")
    else:
        source = "the document" if state.get("document_name") else "your description"
        lines.append(
            f"I've extracted {len(diffs)} field(s) from {source} and filled in the "
            f"complaint form."
        )
        if reference := state.get("reference_no"):
            lines.append(f"Logged as **{reference}**.")

    if risk := state.get("risk"):
        lines.append(
            f"Risk assessment: **{risk.get('severity')}** severity, "
            f"**{risk.get('priority')}** priority (score {risk.get('risk_score')}/100)."
        )
        if flags := risk.get("regulatory_flags"):
            lines.append(f"⚠️ Regulatory: {flags[0]}")

    completeness = state.get("completeness") or {}
    if missing := completeness.get("missing_required"):
        first = missing[0]
        lines.append(
            f"Still missing {len(missing)} mandatory field(s). "
            f"{first.get('question_to_ask', '')}"
        )

    if duplicates := state.get("duplicates"):
        top = duplicates[0]
        lines.append(
            f"🔁 Possible duplicate of **{top.get('reference_no')}** "
            f"({int(top.get('similarity', 0) * 100)}% similar) - {top.get('reason', '')}"
        )

    return {
        "assistant_message": "\n\n".join(lines),
        "trace": [trace("compose_reply", detail="reply composed")],
    }
