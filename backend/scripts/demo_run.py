"""Drive the three demo scenarios end-to-end, without the HTTP layer.

    .venv/Scripts/python.exe scripts/demo_run.py

Exercises exactly what the demo video asks for: log from a prompt, correct via
natural language while preserving the rest of the record, then extract from a
PDF and correct that too.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.compat import configure_event_loop  # noqa: E402

configure_event_loop()

# The assistant's replies contain emoji; the Windows console defaults to cp1252.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.graph.nodes.document import extract_text  # noqa: E402
from app.graph.state import filled_values  # noqa: E402
from app.llm.registry import registry  # noqa: E402
from app.services.runner import runner  # noqa: E402

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


async def turn(session_id: str, *, text: str = "", document: Path | None = None) -> dict:
    kwargs = {}
    if document is not None:
        kwargs["document_text"] = extract_text(document.name, None, document.read_bytes())
        kwargs["document_name"] = document.name
        print(f"\n>>> UPLOAD {document.name}")
    else:
        kwargs["user_input"] = text
        print(f"\n>>> {text}")

    patched, nodes = [], []
    async for event in runner.run(session_id, **kwargs):
        if event["event"] == "node":
            d = event["data"]
            nodes.append(d["node"])
            ms = f" {d['duration_ms']}ms" if d.get("duration_ms") else ""
            print(f"    [{d['node']:<20}] {d.get('detail', '')}{ms}")
        elif event["event"] == "field_patch":
            patched.append(event["data"]["field"])
        elif event["event"] == "done":
            print(f"\n    REPLY: {event['data']['assistant_message'][:400]}")

    print(f"\n    fields changed this turn: {patched or 'none'}")
    return await runner.get_state(session_id)


def show_record(state: dict) -> None:
    values = filled_values(state.get("complaint", {}))
    print("\n    --- FORM ---")
    for key, value in values.items():
        print(f"      {key:32} {str(value)[:70]}")
    if risk := state.get("risk"):
        print(f"\n    --- RISK: {risk['severity']} / {risk['priority']} "
              f"({risk['risk_score']}/100) ---")
        print(f"      {risk['justification'][:220]}")
        for action in (risk.get("next_actions") or [])[:3]:
            print(f"      - {action[:100]}")
        for flag in risk.get("regulatory_flags") or []:
            print(f"      ! {flag[:110]}")
    if comp := state.get("completeness"):
        print(f"\n    --- COMPLETENESS: {comp['score']}% "
              f"({len(comp.get('missing_required') or [])} missing) ---")
    if capa := state.get("capa"):
        causes = ", ".join(
            f"{c['cause'][:40]} [{c['category']}]" for c in (capa.get("probable_root_causes") or [])[:2]
        )
        print(f"\n    --- CAPA ({capa.get('investigation_type')}): {causes} ---")
    if dupes := state.get("duplicates"):
        for d in dupes:
            print(f"\n    --- DUPLICATE: {d['reference_no']} "
                  f"({int(d['similarity'] * 100)}%) {d['reason'][:90]} ---")


async def main() -> None:
    await registry.probe()
    await runner.start()
    print(f"checkpointer: {'postgres' if runner.checkpointed else 'in-memory'}")

    # -- Scenario 1 & 2: log from a prompt, then correct it -----------------
    rule("SCENARIO 1 - Log Complaint (natural language prompt)")
    session_a = str(uuid.uuid4())
    state = await turn(
        session_a,
        text="Apollo Pharmacy reported discolored capsules in Amoxicillin Capsules 500mg.",
    )
    show_record(state)
    before = filled_values(state.get("complaint", {}))

    rule("SCENARIO 2 - Edit Complaint (must preserve everything else)")
    state = await turn(
        session_a,
        text="Sorry, the batch number is BMX240602 and the affected quantity is 48 capsules.",
    )
    show_record(state)

    after = filled_values(state.get("complaint", {}))
    lost = [k for k, v in before.items() if after.get(k) != v]
    print(f"\n    PRESERVATION CHECK: {len(before)} field(s) before, {len(after)} after")
    print(f"    fields altered from turn 1: {lost or 'NONE - all preserved'}")

    # -- Scenario 3: document extraction, then correct it -------------------
    rule("SCENARIO 3 - Document Extraction (PDF) then natural-language correction")
    session_b = str(uuid.uuid4())
    state = await turn(session_b, document=SAMPLES / "metformin_api_complaint.pdf")
    show_record(state)
    before_doc = filled_values(state.get("complaint", {}))

    state = await turn(
        session_b,
        text="Sorry, the batch number is CHG260712A and the affected quantity is 50 kg, 2 HDPE drums.",
    )
    show_record(state)

    after_doc = filled_values(state.get("complaint", {}))
    lost_doc = [k for k, v in before_doc.items() if after_doc.get(k) != v]
    print(f"\n    fields altered from the PDF extraction: {lost_doc}")

    await runner.stop()


if __name__ == "__main__":
    asyncio.run(main())
