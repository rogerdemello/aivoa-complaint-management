"""Role-based Groq model registry with live availability probing.

Why this exists
---------------
The assignment mandates two specific Groq models. Both are on Groq's deprecation
schedule:

    gemma2-9b-it            announced 2025-08-08, shut down 2025-10-08  (gone)
    llama-3.3-70b-versatile announced 2026-06-17, shuts down 2026-08-16 (soon)

    https://console.groq.com/docs/deprecations

Hard-coding either ID means the app throws `model_not_found` on the reviewer's
machine. So graph nodes never name a model: they ask for a *role*
(`router` / `extractor` / `reasoner`). At startup we probe Groq for the models
that actually exist and bind each role to the first live entry of its chain,
beginning with the assignment-mandated ID. The resolution is logged and served
at `GET /api/health/models`, so the substitution is always visible rather than
silent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"

# Models that exist on Groq but can never serve a chat role here.
_NON_CHAT_HINTS = ("whisper", "tts", "guard", "embed", "distil-whisper")


class ModelRole(str, Enum):
    """What a node needs from a model, decoupled from which model provides it."""

    ROUTER = "router"       # cheap intent classification
    EXTRACTOR = "extractor"  # structured field extraction with evidence spans
    REASONER = "reasoner"   # risk assessment, CAPA, root cause


# Ordered fallbacks, tried after the configured (assignment-mandated) ID.
# Sourced from Groq's own migration recommendations on the deprecations page.
FALLBACK_CHAINS: dict[ModelRole, tuple[str, ...]] = {
    ModelRole.ROUTER: (
        "openai/gpt-oss-20b",
        "qwen/qwen3.6-27b",
        "llama-3.3-70b-versatile",
    ),
    ModelRole.EXTRACTOR: (
        "openai/gpt-oss-20b",
        "qwen/qwen3.6-27b",
        "openai/gpt-oss-120b",
    ),
    ModelRole.REASONER: (
        "openai/gpt-oss-120b",
        "qwen/qwen3.6-27b",
        "openai/gpt-oss-20b",
    ),
}


@dataclass
class Resolution:
    """How one role ended up bound to one model."""

    role: ModelRole
    configured: str
    resolved: str
    substituted: bool
    reason: str


@dataclass
class ModelRegistry:
    available: set[str] = field(default_factory=set)
    resolutions: dict[ModelRole, Resolution] = field(default_factory=dict)
    probed: bool = False
    probe_error: str | None = None

    # -- probing ------------------------------------------------------------

    async def probe(self) -> None:
        """Ask Groq which models exist, then bind every role."""
        settings = get_settings()

        if not settings.groq_api_key:
            self.probe_error = "GROQ_API_KEY is not set"
            log.warning("No GROQ_API_KEY; binding roles to configured IDs unchecked.")
            self._bind_all_unchecked()
            return

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    GROQ_MODELS_URL,
                    headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                )
                response.raise_for_status()
                payload = response.json()
            self.available = {m["id"] for m in payload.get("data", [])}
            self.probed = True
            log.info("Groq probe found %d models.", len(self.available))
        except Exception as exc:  # network down, bad key, Groq outage
            self.probe_error = f"{type(exc).__name__}: {exc}"
            log.warning("Groq model probe failed (%s); using configured IDs.", exc)
            self._bind_all_unchecked()
            return

        for role in ModelRole:
            self.resolutions[role] = self._resolve(role)
            r = self.resolutions[role]
            if r.substituted:
                log.warning(
                    "Role %-9s: configured '%s' is unavailable -> using '%s' (%s)",
                    r.role.value, r.configured, r.resolved, r.reason,
                )
            else:
                log.info("Role %-9s -> %s", r.role.value, r.resolved)

    def _bind_all_unchecked(self) -> None:
        """Fall back to trusting configuration when the probe can't run."""
        for role in ModelRole:
            configured = self._configured(role)
            self.resolutions[role] = Resolution(
                role=role,
                configured=configured,
                resolved=configured,
                substituted=False,
                reason="availability not verified",
            )

    # -- resolution ---------------------------------------------------------

    @staticmethod
    def _configured(role: ModelRole) -> str:
        settings = get_settings()
        return {
            ModelRole.ROUTER: settings.aivoa_model_router,
            ModelRole.EXTRACTOR: settings.aivoa_model_extractor,
            ModelRole.REASONER: settings.aivoa_model_reasoner,
        }[role]

    def _resolve(self, role: ModelRole) -> Resolution:
        configured = self._configured(role)

        if configured in self.available:
            return Resolution(role, configured, configured, False, "available")

        settings = get_settings()
        if not settings.aivoa_model_auto_fallback:
            raise RuntimeError(
                f"Model '{configured}' for role '{role.value}' is not available on Groq "
                f"and AIVOA_MODEL_AUTO_FALLBACK is disabled."
            )

        for candidate in FALLBACK_CHAINS[role]:
            if candidate in self.available:
                return Resolution(
                    role, configured, candidate, True,
                    f"'{configured}' not offered by Groq; next live model in the "
                    f"{role.value} chain",
                )

        # Nothing in the curated chain survived. Rather than crash, take any
        # live chat-capable model so the app still demonstrates the workflow.
        last_resort = sorted(
            m for m in self.available
            if not any(hint in m.lower() for hint in _NON_CHAT_HINTS)
        )
        if last_resort:
            return Resolution(
                role, configured, last_resort[0], True,
                "entire fallback chain is unavailable; using first live chat model",
            )

        raise RuntimeError(
            f"No usable Groq chat model for role '{role.value}'. "
            f"Groq reported {len(self.available)} models."
        )

    # -- access -------------------------------------------------------------

    def get(self, role: ModelRole) -> str:
        """The model ID a node should call for this role."""
        if role not in self.resolutions:
            return self._configured(role)
        return self.resolutions[role].resolved

    def report(self) -> dict:
        """Payload for `GET /api/health/models`."""
        return {
            "probed": self.probed,
            "probe_error": self.probe_error,
            "available_count": len(self.available),
            "roles": [
                {
                    "role": r.role.value,
                    "configured": r.configured,
                    "resolved": r.resolved,
                    "substituted": r.substituted,
                    "reason": r.reason,
                }
                for r in self.resolutions.values()
            ],
        }


registry = ModelRegistry()
