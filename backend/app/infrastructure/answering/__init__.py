"""Answer-generation adapters (implement ``AnswerGenerationPort``, ADR-0007/0020).

The provider SDK, model name, and citation format live only inside these
adapters; callers depend on ``AnswerGenerationPort`` and receive a Learny-owned
``GeneratedAnswer``. The default is a deterministic, network-free extractive
adapter (AD-024) that makes the answer path testable offline;
``build_answer_adapter`` selects the concrete adapter from settings at the
composition root, so provider choice never leaks into application/domain code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.infrastructure.answering.anthropic import (
    AnthropicAnswerAdapter,
    AnthropicTeachingAdapter,
)
from app.infrastructure.answering.local import (
    DeterministicAnswerAdapter,
    DeterministicTeachingAdapter,
)

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.domain.ports import AnswerGenerationPort, TeachingGenerationPort

__all__ = [
    "AnthropicAnswerAdapter",
    "AnthropicTeachingAdapter",
    "DeterministicAnswerAdapter",
    "DeterministicTeachingAdapter",
    "build_answer_adapter",
    "build_teaching_adapter",
]


def build_answer_adapter(settings: Settings) -> AnswerGenerationPort:
    """Return the answer adapter named by ``settings.generation_provider``.

    ``local`` (default) → the deterministic, network-free adapter (CI/local needs
    no key); ``anthropic`` → the Claude adapter built from the key/model/max-tokens
    settings, which requires a non-empty ``anthropic_api_key`` so a misconfigured
    provider fails fast at composition rather than as a per-request 502. An
    unrecognized provider raises ``ValueError`` — a clear configuration error, not a
    silent fall back to the default (GEN-02).
    """
    provider = settings.generation_provider
    if provider == "local":
        return DeterministicAnswerAdapter()
    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError(
                "LEARNY_ANTHROPIC_API_KEY is required when the generation "
                "provider is 'anthropic'"
            )
        return AnthropicAnswerAdapter(
            api_key=settings.anthropic_api_key,
            model=settings.generation_model,
            max_tokens=settings.generation_max_tokens,
        )
    raise ValueError(f"unknown generation provider: {provider}")


def build_teaching_adapter(settings: Settings) -> TeachingGenerationPort:
    """Return the teaching adapter named by ``settings.generation_provider``.

    The teaching sibling of :func:`build_answer_adapter` — one provider switch
    governs both ports (D-2): ``local`` (default) → the deterministic, network-free
    teaching adapter; ``anthropic`` → the Claude teaching adapter built from the
    key/model/max-tokens settings, requiring a non-empty ``anthropic_api_key`` so a
    misconfigured provider fails fast at composition rather than as a per-request
    502. An unrecognized provider raises ``ValueError`` (GEN-02).
    """
    provider = settings.generation_provider
    if provider == "local":
        return DeterministicTeachingAdapter()
    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError(
                "LEARNY_ANTHROPIC_API_KEY is required when the generation "
                "provider is 'anthropic'"
            )
        return AnthropicTeachingAdapter(
            api_key=settings.anthropic_api_key,
            model=settings.generation_model,
            max_tokens=settings.generation_max_tokens,
        )
    raise ValueError(f"unknown generation provider: {provider}")
