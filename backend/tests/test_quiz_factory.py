"""B3 gate — quiz-provider factory (settings → adapter, misconfig → error).

``build_quiz_adapter`` is the composition-root seam that chooses the deck adapter from
``LEARNY_GENERATION_PROVIDER``: ``local`` (the offline default) yields the deterministic
adapter, ``anthropic`` the Message Batches adapter built from the key + ``quiz_model``, an
empty key with the ``anthropic`` provider is a loud fail-fast, and any other value is a
loud configuration error rather than a silent fall back. ``Settings`` is instantiated
directly (bypassing the ``get_settings`` lru-cache) so each case is isolated.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.infrastructure.quiz import (
    AnthropicQuizAdapter,
    DeterministicQuizAdapter,
    build_quiz_adapter,
)


def test_local_provider_builds_deterministic_adapter() -> None:
    settings = Settings(_env_file=None, generation_provider="local")

    adapter = build_quiz_adapter(settings)

    assert isinstance(adapter, DeterministicQuizAdapter)


def test_anthropic_provider_builds_batch_adapter_on_quiz_model() -> None:
    settings = Settings(
        _env_file=None,
        generation_provider="anthropic",
        anthropic_api_key="sk-ant-test",
        quiz_model="claude-haiku-4-5",
    )

    adapter = build_quiz_adapter(settings)

    assert isinstance(adapter, AnthropicQuizAdapter)
    # Identity reflects the settings-supplied quiz model id (no network call).
    assert adapter.model == "claude-haiku-4-5"


def test_anthropic_provider_with_empty_key_fails_fast() -> None:
    settings = Settings(
        _env_file=None, generation_provider="anthropic", anthropic_api_key=""
    )

    with pytest.raises(ValueError, match="LEARNY_ANTHROPIC_API_KEY is required"):
        build_quiz_adapter(settings)


def test_unknown_provider_raises_value_error() -> None:
    settings = Settings(_env_file=None, generation_provider="gemini")

    with pytest.raises(ValueError, match="unknown generation provider: gemini"):
        build_quiz_adapter(settings)
