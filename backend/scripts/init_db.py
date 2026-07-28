"""Create the schema and LangGraph's checkpoint tables.

Run once after filling in `.env`:

    .venv/Scripts/python.exe scripts/init_db.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.compat import configure_event_loop  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.db.session import get_engine, psycopg_dsn  # noqa: E402

configure_event_loop()


async def main() -> None:
    engine = get_engine()

    async with engine.begin() as conn:
        # Optional: trigram similarity for duplicate detection. The app falls
        # back to rapidfuzz when this is unavailable, so failure is not fatal.
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            print("  pg_trgm enabled")
        except Exception as exc:
            print(f"  pg_trgm unavailable ({type(exc).__name__}) - using rapidfuzz fallback")

        await conn.run_sync(Base.metadata.create_all)
        print(f"  tables created: {', '.join(sorted(Base.metadata.tables))}")

    await engine.dispose()

    # LangGraph manages its own checkpoint tables.
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    async with AsyncPostgresSaver.from_conn_string(psycopg_dsn()) as saver:
        await saver.setup()
        print("  langgraph checkpoint tables created")

    print("\nDatabase ready.")


if __name__ == "__main__":
    asyncio.run(main())
