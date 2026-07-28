"""Graph assembly.

    START -> route_intent -+-> parse_document -> extract_complaint -+
                           |                                        |
                           +-> extract_complaint -------------------+
                           |                                        |
                           +-> extract_patch -----------------------+--> validate_extraction
                           |                                             |    ^  (repair loop)
                           +-> answer_question -> END                    |    |
                                                                         v    |
                                                                 merge_complaint
                                                                         |
                        +--------------+--------------+-----------------+
                        v              v              v                 v
                  assess_risk  check_completeness  detect_duplicates  recommend_capa
                        +--------------+--------------+-----------------+
                                                 |
                                            summarize  (join: waits for all four)
                                                 |
                                              persist
                                                 |
                                           compose_reply -> END

The four enrichment nodes are independent, so they run as a parallel fan-out
and the turn costs roughly the slowest branch instead of their sum.
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from app.graph.nodes.document import parse_document
from app.graph.nodes.enrichment import (
    assess_risk,
    check_completeness,
    detect_duplicates,
    recommend_capa,
    summarize,
)
from app.graph.nodes.extraction import (
    extract_complaint,
    extract_patch,
    merge_complaint,
    validate_extraction,
    validation_branch,
)
from app.graph.nodes.persist import persist
from app.graph.nodes.qa import answer_question
from app.graph.nodes.reply import compose_reply
from app.graph.nodes.routing import intent_branch, route_intent
from app.graph.state import ComplaintState

log = logging.getLogger(__name__)

ENRICHMENT_NODES = (
    "assess_risk",
    "check_completeness",
    "detect_duplicates",
    "recommend_capa",
)


def build_graph(checkpointer=None):
    """Compile the complaint graph. Pass a checkpointer for durable sessions."""
    graph = StateGraph(ComplaintState)

    graph.add_node("route_intent", route_intent)
    graph.add_node("parse_document", parse_document)
    graph.add_node("extract_complaint", extract_complaint)
    graph.add_node("extract_patch", extract_patch)
    graph.add_node("validate_extraction", validate_extraction)
    graph.add_node("merge_complaint", merge_complaint)
    graph.add_node("assess_risk", assess_risk)
    graph.add_node("check_completeness", check_completeness)
    graph.add_node("detect_duplicates", detect_duplicates)
    graph.add_node("recommend_capa", recommend_capa)
    graph.add_node("summarize", summarize)
    graph.add_node("persist", persist)
    graph.add_node("compose_reply", compose_reply)
    graph.add_node("answer_question", answer_question)

    graph.add_edge(START, "route_intent")
    graph.add_conditional_edges(
        "route_intent",
        intent_branch,
        {
            "parse_document": "parse_document",
            "extract_complaint": "extract_complaint",
            "extract_patch": "extract_patch",
            "answer_question": "answer_question",
        },
    )

    graph.add_edge("parse_document", "extract_complaint")
    graph.add_edge("extract_complaint", "validate_extraction")
    graph.add_edge("extract_patch", "validate_extraction")

    # Repair loop: invalid JSON goes back to whichever extractor produced it.
    graph.add_conditional_edges(
        "validate_extraction",
        validation_branch,
        {
            "extract_complaint": "extract_complaint",
            "extract_patch": "extract_patch",
            "merge_complaint": "merge_complaint",
        },
    )

    # Fan out, then join on summarize.
    for node in ENRICHMENT_NODES:
        graph.add_edge("merge_complaint", node)
        graph.add_edge(node, "summarize")

    graph.add_edge("summarize", "persist")
    graph.add_edge("persist", "compose_reply")
    graph.add_edge("compose_reply", END)
    graph.add_edge("answer_question", END)

    return graph.compile(checkpointer=checkpointer)
