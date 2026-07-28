"""Platform compatibility shims.

psycopg's async mode cannot run on Windows' default ProactorEventLoop; it
raises `InterfaceError: Psycopg cannot use the 'ProactorEventLoop'`. Python has
defaulted to Proactor on Windows since 3.8, so anything that opens an async
connection has to switch the policy *before* the first event loop is created.
"""

from __future__ import annotations

import asyncio
import sys


def configure_event_loop() -> None:
    """Select an event loop policy psycopg can use. No-op off Windows."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
