"""Candidate retrieval for duplicate complaint detection.

Prefers Postgres `pg_trgm` trigram similarity. Supabase ships the extension but
it is not enabled in a fresh project, and the app should not hard-fail if the
role lacks permission to create it - so there is a rapidfuzz fallback that does
the same job in Python over a bounded candidate set.
"""

from __future__ import annotations

import logging
import uuid

from rapidfuzz import fuzz
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Complaint

log = logging.getLogger(__name__)

CANDIDATE_LIMIT = 25
_PYTHON_FALLBACK_SCAN = 300


def _signature(product: str | None, batch: str | None, description: str | None) -> str:
    return " ".join(p for p in (product, batch, description) if p).strip()


async def _trigram_candidates(
    session: AsyncSession, signature: str, exclude_id: uuid.UUID | None
) -> list[dict] | None:
    """Trigram search. Returns None when pg_trgm is unavailable."""
    try:
        sql = text(
            """
            SELECT id, reference_no, product_name, batch_lot_number, description,
                   similarity(
                       coalesce(product_name,'') || ' ' ||
                       coalesce(batch_lot_number,'') || ' ' ||
                       coalesce(description,''),
                       :signature
                   ) AS score
            FROM complaints
            -- Cast explicitly: on the first turn there is no complaint to
            -- exclude, and psycopg cannot infer the type of an untyped NULL
            -- in `id <> $n`, which fails the whole query.
            WHERE (CAST(:exclude_id AS uuid) IS NULL OR id <> CAST(:exclude_id AS uuid))
              AND status <> 'draft'
            ORDER BY score DESC
            LIMIT :limit
            """
        )
        rows = await session.execute(
            sql,
            {
                "signature": signature,
                "exclude_id": exclude_id,
                "limit": CANDIDATE_LIMIT,
            },
        )
        return [
            {
                "complaint_id": str(r.id),
                "reference_no": r.reference_no,
                "product_name": r.product_name,
                "batch_lot_number": r.batch_lot_number,
                "description": r.description,
                "similarity": float(r.score or 0.0),
            }
            for r in rows
        ]
    except Exception as exc:
        log.info("pg_trgm unavailable (%s); using rapidfuzz fallback.", type(exc).__name__)
        await session.rollback()
        return None


async def _rapidfuzz_candidates(
    session: AsyncSession, signature: str, exclude_id: uuid.UUID | None
) -> list[dict]:
    stmt = select(Complaint).where(Complaint.status != "draft").limit(_PYTHON_FALLBACK_SCAN)
    if exclude_id is not None:
        stmt = stmt.where(Complaint.id != exclude_id)

    scored = []
    for complaint in (await session.execute(stmt)).scalars():
        other = _signature(
            complaint.product_name, complaint.batch_lot_number, complaint.description
        )
        if not other:
            continue
        scored.append(
            {
                "complaint_id": str(complaint.id),
                "reference_no": complaint.reference_no,
                "product_name": complaint.product_name,
                "batch_lot_number": complaint.batch_lot_number,
                "description": complaint.description,
                "similarity": fuzz.token_set_ratio(signature, other) / 100.0,
            }
        )

    scored.sort(key=lambda c: c["similarity"], reverse=True)
    return scored[:CANDIDATE_LIMIT]


async def find_candidates(
    session: AsyncSession,
    *,
    product_name: str | None,
    batch_lot_number: str | None,
    description: str | None,
    exclude_id: uuid.UUID | None = None,
    min_similarity: float = 0.25,
) -> list[dict]:
    """Prior complaints textually similar enough to be worth an LLM opinion."""
    signature = _signature(product_name, batch_lot_number, description)
    if not signature:
        return []

    candidates = await _trigram_candidates(session, signature, exclude_id)
    if candidates is None:
        candidates = await _rapidfuzz_candidates(session, signature, exclude_id)

    return [c for c in candidates if c["similarity"] >= min_similarity]
