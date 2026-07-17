"""Quiz deck-generation adapters (implement ``QuizGenerationPort``, QUIZ-05).

The provider SDK, model name, and structured-output shapes live only inside these
adapters; callers depend on ``QuizGenerationPort`` and receive Learny-owned candidates.
The default is a deterministic, network-free adapter that makes the deck pipeline
testable offline; ``build_quiz_adapter`` selects the concrete adapter from settings at
the composition root, so provider choice never leaks into application/domain code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.infrastructure.quiz.anthropic import AnthropicQuizAdapter
from app.infrastructure.quiz.local import DeterministicQuizAdapter

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.domain.ports import QuizGenerationPort

__all__ = [
    "AnthropicQuizAdapter",
    "DeterministicQuizAdapter",
    "build_quiz_adapter",
]


def build_quiz_adapter(settings: Settings) -> QuizGenerationPort:
    """Return the quiz adapter named by ``settings.generation_provider``.

    ``local`` (default) → the deterministic, network-free adapter (CI/local needs no key);
    ``anthropic`` → the Message Batches adapter built from the key + ``quiz_model``, which
    requires a non-empty ``anthropic_api_key`` so a misconfigured provider fails fast at
    composition rather than as a per-request 502. An unrecognized provider raises
    ``ValueError`` — a clear configuration error, not a silent fall back to the default.
    """
    provider = settings.generation_provider
    if provider == "local":
        return DeterministicQuizAdapter()
    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError(
                "LEARNY_ANTHROPIC_API_KEY is required when the generation "
                "provider is 'anthropic'"
            )
        return AnthropicQuizAdapter(
            api_key=settings.anthropic_api_key,
            model=settings.quiz_model,
            max_tokens=settings.generation_max_tokens,
        )
    raise ValueError(f"unknown generation provider: {provider}")
