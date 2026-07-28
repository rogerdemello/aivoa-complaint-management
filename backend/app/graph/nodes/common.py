"""Helpers shared by graph nodes."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.llm.registry import ModelRole, registry

log = logging.getLogger(__name__)


def trace(
    node: str,
    status: str = "end",
    detail: str | None = None,
    role: ModelRole | None = None,
    duration_ms: int | None = None,
    **extra: Any,
) -> dict:
    """One entry for the live agent-trace panel in the UI."""
    event: dict[str, Any] = {
        "node": node,
        "status": status,
        "detail": detail,
        "ts": time.time(),
    }
    if role is not None:
        event["model"] = registry.get(role)
        event["role"] = role.value
    if duration_ms is not None:
        event["duration_ms"] = duration_ms
    event.update(extra)
    return event


class Timer:
    """Wall-clock timing for trace events."""

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_: object) -> None:
        self.ms = int((time.perf_counter() - self._start) * 1000)

    ms: int = 0
