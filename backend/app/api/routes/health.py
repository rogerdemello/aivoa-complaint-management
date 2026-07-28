"""Health and diagnostics endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.db.session import get_session_factory
from app.llm.registry import registry

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/health/models")
async def health_models() -> dict:
    """Which Groq model is actually serving each graph role.

    Surfaced in the UI so a substituted model is visible rather than silent.
    """
    return registry.report()


@router.get("/health/db")
async def health_db() -> dict:
    try:
        async with get_session_factory()() as session:
            result = await session.execute(text("select version()"))
            return {"status": "ok", "server": result.scalar_one()}
    except Exception as exc:
        return {"status": "error", "detail": f"{type(exc).__name__}: {exc}"}
