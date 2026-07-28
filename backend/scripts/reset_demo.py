"""Clear complaints created by test runs, keeping the seeded history.

    .venv/Scripts/python.exe scripts/reset_demo.py

Run this before recording. Every demo run persists a real complaint, and those
accumulate as duplicate-detection noise ("87% similar to CMP-2026-0011") that
makes the recording confusing.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select, text  # noqa: E402

from app.compat import configure_event_loop  # noqa: E402
from app.db.models import Complaint, Document, Message  # noqa: E402
from app.db.session import dispose_engine, get_session_factory  # noqa: E402

configure_event_loop()

# Written by scripts/seed_complaints.py; these are the historical record that
# duplicate detection is supposed to search against.
KEEP = {
    "CMP-2026-0002",
    "CMP-2026-0003",
    "CMP-2026-0004",
    "CMP-2026-0005",
    "CMP-2026-0006",
}


async def main() -> None:
    async with get_session_factory()() as session:
        rows = await session.execute(
            select(Complaint.reference_no).where(Complaint.reference_no.notin_(KEEP))
        )
        doomed = [r[0] for r in rows]

        if not doomed:
            print("Nothing to clear - only seeded complaints present.")
        else:
            # Field history and risk assessments cascade from complaints.
            await session.execute(
                delete(Complaint).where(Complaint.reference_no.notin_(KEEP))
            )
            await session.execute(delete(Document).where(Document.session_id != "seed"))
            await session.execute(delete(Message))
            await session.commit()
            print(f"Cleared {len(doomed)} complaint(s): {', '.join(sorted(doomed))}")

    # LangGraph's own checkpoint tables, so old sessions don't resurface.
    # DELETE rather than TRUNCATE: TRUNCATE needs an ACCESS EXCLUSIVE lock, and
    # any lingering connection makes it block until Supabase's statement
    # timeout cancels it. DELETE only takes row locks. Child tables first.
    async with get_session_factory()() as session:
        for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
            try:
                await session.execute(text(f"DELETE FROM {table}"))
                await session.commit()
            except Exception as exc:
                await session.rollback()
                print(f"  could not clear {table}: {type(exc).__name__}")
        print("Checkpointer cleared.")

    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
