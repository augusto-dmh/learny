"""Answer-provider factory — settings → adapter, misconfig → error (GEN-02).

``build_answer_adapter`` is the composition-root seam that chooses the answer
adapter from ``LEARNY_GENERATION_PROVIDER``. ``local`` (the offline default) yields
the deterministic adapter, ``anthropic`` the Claude adapter built from the
key/model/max-tokens settings, an empty key with the ``anthropic`` provider is a
loud fail-fast, and any other value is a loud configuration error rather than a
silent fall back. ``Settings`` is instantiated directly (bypassing the
``get_settings`` lru-cache) so each case is isolated.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.infrastructure.answering import (
    AnthropicAnswerAdapter,
    DeterministicAnswerAdapter,
    build_answer_adapter,
)


def test_local_provider_builds_deterministic_adapter() -> None:
    settings = Settings(_env_file=None, generation_provider="local")

    adapter = build_answer_adapter(settings)

    assert isinstance(adapter, DeterministicAnswerAdapter)


def test_anthropic_provider_builds_claude_adapter_from_settings() -> None:
    settings = Settings(
        _env_file=None,
        generation_provider="anthropic",
        anthropic_api_key="sk-ant-test",
        generation_model="claude-sonnet-4-6",
        generation_max_tokens=1024,
    )

    adapter = build_answer_adapter(settings)

    assert isinstance(adapter, AnthropicAnswerAdapter)
    # Identity reflects the settings-supplied model id (no network call).
    assert adapter.model == "claude-sonnet-4-6"


def test_anthropic_provider_with_empty_key_fails_fast() -> None:
    settings = Settings(
        _env_file=None, generation_provider="anthropic", anthropic_api_key=""
    )

    with pytest.raises(ValueError, match="LEARNY_ANTHROPIC_API_KEY is required"):
        build_answer_adapter(settings)


def test_unknown_provider_raises_value_error() -> None:
    settings = Settings(_env_file=None, generation_provider="gemini")

    with pytest.raises(ValueError, match="unknown generation provider: gemini"):
        build_answer_adapter(settings)
