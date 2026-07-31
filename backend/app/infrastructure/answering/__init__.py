"""Generation adapters (implement ``GenerationPort``, ADR-0007/0020).

The provider SDK, model name, and citation format live only inside these
adapters; callers depend on ``GenerationPort`` and receive a Learny-owned
``GeneratedAnswer``. The default is a deterministic, network-free extractive
adapter (AD-024) that makes the answer path testable offline;
``build_generation_adapter`` selects the concrete adapter from settings at the
composition root, so provider choice never leaks into application/domain code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.infrastructure.answering.anthropic import AnthropicGenerationAdapter
from app.infrastructure.answering.local import DeterministicGenerationAdapter

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.domain.ports import GenerationPort

__all__ = [
    "AnthropicGenerationAdapter",
    "DeterministicGenerationAdapter",
    "build_generation_adapter",
]


def build_generation_adapter(settings: Settings) -> GenerationPort:
    """Return the generation adapter named by ``settings.generation_provider``.

    One adapter serves both modes (D-2): the mode is a per-call argument, not a
    per-adapter choice, so one provider switch governs the whole turn path.

    ``local`` (default) → the deterministic, network-free adapter (CI/local needs
    no key); ``anthropic`` → the Claude adapter built from the key/model/max-tokens
    settings, which requires a non-empty ``anthropic_api_key`` so a misconfigured
    provider fails fast at composition rather than as a per-request 502. An
    unrecognized provider raises ``ValueError`` — a clear configuration error, not a
    silent fall back to the default (GEN-02).
    """
    provider = settings.generation_provider
    if provider == "local":
        return DeterministicGenerationAdapter()
    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError(
                "LEARNY_ANTHROPIC_API_KEY is required when the generation provider is 'anthropic'"
            )
        return AnthropicGenerationAdapter(
            api_key=settings.anthropic_api_key,
            model=settings.generation_model,
            max_tokens=settings.generation_max_tokens,
            effort=settings.generation_effort,
        )
    raise ValueError(f"unknown generation provider: {provider}")
