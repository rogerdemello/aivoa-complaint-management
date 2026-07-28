"""Owns the compiled graph and turns one user message into a stream of events."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from typing import Any

from app.db.session import psycopg_dsn
from app.graph.builder import build_graph
from app.graph.state import Intent, Source

log = logging.getLogger(__name__)

# State keys whose updates are worth pushing to the UI as they happen.
_STREAMED_KEYS = ("risk", "completeness", "duplicates", "capa", "summary")


class GraphRunner:
    def __init__(self) -> None:
        self._graph = None
        self._stack: AsyncExitStack | None = None
        self.checkpointed = False

    # -- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        """Compile the graph, with a Postgres checkpointer when one is reachable."""
        self._stack = AsyncExitStack()
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            saver = await self._stack.enter_async_context(
                AsyncPostgresSaver.from_conn_string(psycopg_dsn())
            )
            await saver.setup()
            self._graph = build_graph(checkpointer=saver)
            self.checkpointed = True
            log.info("Graph compiled with Postgres checkpointer.")
        except Exception as exc:
            # Without a checkpointer the graph still runs; sessions just don't
            # survive a restart. Better than refusing to boot.
            log.warning(
                "Postgres checkpointer unavailable (%s); running without durable "
                "session state.", exc,
            )
            await self._stack.aclose()
            self._stack = None
            self._graph = build_graph()
            self.checkpointed = False

    async def stop(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
        self._graph = None

    @property
    def graph(self):
        if self._graph is None:
            raise RuntimeError("Graph not started")
        return self._graph

    # -- state --------------------------------------------------------------

    @staticmethod
    def _config(session_id: str) -> dict:
        return {"configurable": {"thread_id": session_id}}

    async def get_state(self, session_id: str) -> dict[str, Any]:
        """Current state for a session, or empty when the thread is new."""
        if not self.checkpointed:
            return {}
        try:
            snapshot = await self.graph.aget_state(self._config(session_id))
            return dict(snapshot.values) if snapshot and snapshot.values else {}
        except Exception as exc:
            log.warning("Could not read state for %s: %s", session_id, exc)
            return {}

    # -- running ------------------------------------------------------------

    async def run(
        self,
        session_id: str,
        *,
        user_input: str = "",
        document_text: str | None = None,
        document_name: str | None = None,
    ) -> AsyncIterator[dict]:
        """Run one turn, yielding UI events as the graph progresses.

        Only this turn's inputs are passed in. Everything else - the complaint
        built up over previous turns - comes from the checkpointer, which is
        what makes "sorry, the batch number is..." work three turns later.
        """
        previous = await self.get_state(session_id)
        turn_id = int(previous.get("turn_id") or 0) + 1
        is_document = document_text is not None

        turn_input: dict[str, Any] = {
            "session_id": session_id,
            "turn_id": turn_id,
            "user_input": user_input,
            "document_text": document_text,
            "document_name": document_name,
            # Reset per-turn scratch space so a previous turn's failed
            # extraction can't leak into this one.
            "diffs": [],
            "raw_extraction": None,
            "validation_error": None,
            "repair_attempts": 0,
            "assistant_message": "",
        }
        if is_document:
            turn_input["intent"] = Intent.EXTRACT_DOCUMENT.value
            turn_input["source"] = Source.DOCUMENT.value
        else:
            turn_input["intent"] = ""

        yield {"event": "turn_start", "data": {"turn_id": turn_id, "session_id": session_id}}

        final: dict[str, Any] = {}
        # `diffs` accumulates across nodes (merge_complaint, then summarize's
        # severity sync) because persist needs the full list for the audit
        # trail. The UI only wants each change once.
        emitted: set[tuple] = set()
        try:
            async for update in self.graph.astream(
                turn_input, self._config(session_id), stream_mode="updates"
            ):
                for node, payload in (update or {}).items():
                    if not isinstance(payload, dict):
                        continue
                    final.update(payload)

                    for entry in payload.get("trace", []) or []:
                        yield {"event": "node", "data": entry}

                    # Fields land in the form as soon as the merge produces them.
                    for diff in payload.get("diffs", []) or []:
                        key = (diff.get("field"), str(diff.get("new_value")))
                        if key in emitted:
                            continue
                        emitted.add(key)
                        yield {"event": "field_patch", "data": diff}

                    if payload.get("complaint"):
                        yield {"event": "complaint", "data": payload["complaint"]}

                    for key in _STREAMED_KEYS:
                        if key in payload and payload[key] is not None:
                            yield {"event": key, "data": payload[key]}

                    for message in payload.get("errors", []) or []:
                        yield {"event": "error", "data": {"message": message}}
        except Exception as exc:
            log.exception("Graph run failed")
            yield {"event": "error", "data": {"message": f"{type(exc).__name__}: {exc}"}}
            yield {"event": "done", "data": {"turn_id": turn_id}}
            return

        yield {
            "event": "done",
            "data": {
                "turn_id": turn_id,
                "assistant_message": final.get("assistant_message", ""),
                "reference_no": final.get("reference_no"),
                "complaint_id": final.get("complaint_id"),
            },
        }


runner = GraphRunner()
