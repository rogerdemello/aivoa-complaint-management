"""Development entrypoint.

    .venv/Scripts/python.exe run.py

Use this rather than `uvicorn app.main:app` on Windows.

`uvicorn.run()` installs its own event loop, which on Windows is the
ProactorEventLoop that psycopg's async mode refuses to use. Setting the policy
beforehand does not help, because uvicorn overrides it. So instead of letting
uvicorn own the loop, we build the Server ourselves and drive it with
`asyncio.run()` under the selector policy (see app/compat.py).
"""

from __future__ import annotations

import asyncio

from app.compat import configure_event_loop

configure_event_loop()


def main() -> None:
    import uvicorn

    config = uvicorn.Config(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        log_level="info",
        # Reload spawns a subprocess that would not inherit our loop policy.
        reload=False,
    )
    asyncio.run(uvicorn.Server(config).serve())


if __name__ == "__main__":
    main()
