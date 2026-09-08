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
    "UndeclaredProviderError",
    "build_quiz_adapter",
]


class UndeclaredProviderError(ValueError):
    """The factory was asked for a generation provider nothing declares.

    Raised by :func:`build_quiz_adapter` when the requested provider name (the
    explicit override, or ``settings.generation_provider`` when no override is
    given) matches no adapter branch. The deck poll maps this to a *terminal*
    job failure: retrying cannot make an undeclared provider exist, and falling
    back to the currently-configured one would poll a foreign vendor with the
    beginning provider's batch id.
    """


def build_quiz_adapter(settings: Settings, provider: str | None = None) -> QuizGenerationPort:
    """Return the quiz adapter for ``provider``, defaulting to the settings' provider.

    ``local`` (default) → the deterministic, network-free adapter (CI/local needs no key);
    ``anthropic`` → the Message Batches adapter built from the key + ``quiz_model``, which
    requires a non-empty ``anthropic_api_key`` so a misconfigured provider fails fast at
    composition rather than as a per-request 502. An unrecognized provider raises
    ``UndeclaredProviderError`` — a clear configuration error, not a silent fall back
    to the default.

    The explicit ``provider`` override pins a deck poll to the provider recorded on
    its handle: an in-flight batch must be collected by the provider that began it,
    even if the settings have since named a different one. The override changes only
    which branch is selected; the key requirement and the unknown-provider error
    apply exactly as they do for the settings-selected provider.
    """
    selected = settings.generation_provider if provider is None else provider
    if selected == "local":
        return DeterministicQuizAdapter()
    if selected == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError(
                "LEARNY_ANTHROPIC_API_KEY is required when the generation provider is 'anthropic'"
            )
        return AnthropicQuizAdapter(
            api_key=settings.anthropic_api_key,
            model=settings.quiz_model,
            max_tokens=settings.generation_max_tokens,
        )
    raise UndeclaredProviderError(f"unknown generation provider: {selected}")
