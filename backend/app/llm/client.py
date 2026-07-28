"""Thin wrapper over Groq chat completions, addressed by role."""

from __future__ import annotations

import json
import logging
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


async def complete(
    role: ModelRole,
    system: str,
    user: str,
    *,
    temperature: float = 0.0,
    json_mode: bool = False,
    max_tokens: int | None = None,
) -> str:
    """Run one completion and return the raw text."""
    chat = get_chat(
        role, temperature=temperature, json_mode=json_mode, max_tokens=max_tokens
    )
    response = await chat.ainvoke(
        [SystemMessage(content=system), HumanMessage(content=user)]
    )
    return response.content if isinstance(response.content, str) else str(response.content)


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
