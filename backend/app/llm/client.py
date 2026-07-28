"""Thin wrapper over Groq chat completions, addressed by role."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from app.config import get_settings
from app.llm.registry import ModelRole, registry

log = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def get_chat(
    role: ModelRole,
    *,
    temperature: float = 0.0,
    json_mode: bool = False,
    max_tokens: int | None = None,
) -> ChatGroq:
    """Build a chat client bound to whichever model currently serves `role`."""
    settings = get_settings()
    kwargs: dict[str, Any] = {}
    if json_mode:
        # Groq's OpenAI-compatible JSON mode. Constrains output to a single
        # JSON object, which materially reduces parse failures on small models.
        kwargs["response_format"] = {"type": "json_object"}

    return ChatGroq(
        model=registry.get(role),
        api_key=settings.groq_api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        model_kwargs=kwargs,
    )


# The enrichment fan-out fires four reasoner calls at once, which trips Groq's
# tokens-per-minute limit on the free tier. Per-minute limits clear quickly, so
# a short wait recovers; per-day limits report a wait of many minutes and are
# not worth blocking a request for.
MAX_RETRIES = 2
MAX_RETRY_WAIT_SECONDS = 30.0
_RETRY_AFTER_RE = re.compile(r"try again in (?:(\d+(?:\.\d+)?)m)?(\d+(?:\.\d+)?)s")


def _retry_delay(message: str, attempt: int) -> float:
    """How long to wait, preferring Groq's own hint over backoff."""
    match = _RETRY_AFTER_RE.search(message)
    if match:
        minutes = float(match.group(1) or 0.0)
        seconds = float(match.group(2))
        return minutes * 60.0 + seconds + 0.5
    return min(2.0**attempt, 8.0) + random.random()


async def complete(
    role: ModelRole,
    system: str,
    user: str,
    *,
    temperature: float = 0.0,
    json_mode: bool = False,
    max_tokens: int | None = None,
) -> str:
    """Run one completion and return the raw text, retrying on rate limits."""
    chat = get_chat(
        role, temperature=temperature, json_mode=json_mode, max_tokens=max_tokens
    )
    messages = [SystemMessage(content=system), HumanMessage(content=user)]

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = await chat.ainvoke(messages)
            return (
                response.content
                if isinstance(response.content, str)
                else str(response.content)
            )
        except Exception as exc:
            text = str(exc)
            if "429" not in text and "rate_limit" not in text:
                raise
            if attempt == MAX_RETRIES:
                raise

            delay = _retry_delay(text, attempt)
            if delay > MAX_RETRY_WAIT_SECONDS:
                # A multi-minute wait means the daily budget is gone, not a
                # burst. Fail now so the node degrades instead of hanging.
                log.warning(
                    "%s rate limited for %.0fs (daily quota); not retrying.",
                    registry.get(role), delay,
                )
                raise

            log.info(
                "%s rate limited; retrying in %.1fs (attempt %d/%d).",
                registry.get(role), delay, attempt + 1, MAX_RETRIES,
            )
            await asyncio.sleep(delay)

    raise RuntimeError("unreachable")


def parse_json_object(text: str) -> dict:
    """Best-effort extraction of one JSON object from a model response.

    Small models wrap JSON in prose or code fences even under explicit
    instruction, so try progressively looser strategies before giving up. A
    `ValueError` here is what drives the graph's repair loop.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("empty model response")

    # 1. Clean JSON.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # 2. Fenced code block.
    fence = _FENCE_RE.search(text)
    if fence:
        try:
            parsed = json.loads(fence.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # 3. Outermost braces, scanned with a depth counter so nested objects and
    #    braces inside strings don't truncate the span.
    start = text.find("{")
    if start != -1:
        depth, in_string, escaped = 0, False, False
        for index in range(start, len(text)):
            char = text[index]
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start : index + 1])
                        if isinstance(parsed, dict):
                            return parsed
                    except json.JSONDecodeError:
                        break

    raise ValueError(f"no JSON object found in model response: {text[:200]!r}")
