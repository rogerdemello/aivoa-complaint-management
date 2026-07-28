"""Async engine and session factory (psycopg3 driver)."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

log = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is not set; copy .env.example to .env")

        connect_args: dict = {}
        # Supabase's transaction pooler (port 6543) does not support prepared
        # statements. psycopg3 prepares automatically after a few executions,
        # so disable it there or queries start failing intermittently.
        if ":6543" in settings.database_url:
            connect_args["prepare_threshold"] = None
            log.warning(
                "Transaction pooler (6543) detected: prepared statements disabled. "
                "The session pooler (5432) is preferred - LangGraph's checkpointer "
                "needs prepared statements."
            )

        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            connect_args=connect_args,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a session per request."""
    async with get_session_factory()() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine, _session_factory = None, None


def psycopg_dsn() -> str:
    """The plain psycopg DSN, for LangGraph's checkpointer.

    LangGraph's `AsyncPostgresSaver` takes a raw connection string and does not
    understand SQLAlchemy's `postgresql+psycopg://` dialect prefix.
    """
    return get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")
