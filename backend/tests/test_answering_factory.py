"""Generation-provider factory — settings → adapter, misconfig → error (GEN-02).

``build_generation_adapter`` is the composition-root seam that chooses the one
generation adapter — it serves both modes — from ``LEARNY_GENERATION_PROVIDER``.
``local`` (the offline default) yields the deterministic adapter, ``anthropic`` the
Claude adapter built from the key/model/max-tokens settings, an empty key with the
``anthropic`` provider is a loud fail-fast, and any other value is a loud
configuration error rather than a silent fall back. ``Settings`` is instantiated
directly (bypassing the ``get_settings`` lru-cache) so each case is isolated.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.infrastructure.answering import (
    AnthropicGenerationAdapter,
    DeterministicGenerationAdapter,
    build_generation_adapter,
)


def test_local_provider_builds_deterministic_adapter() -> None:
    settings = Settings(_env_file=None, generation_provider="local")

    adapter = build_generation_adapter(settings)

    assert isinstance(adapter, DeterministicGenerationAdapter)


def test_anthropic_provider_builds_claude_adapter_from_settings() -> None:
    settings = Settings(
        _env_file=None,
        generation_provider="anthropic",
        anthropic_api_key="sk-ant-test",
        generation_model="claude-sonnet-4-6",
        generation_effort="xhigh",
        generation_max_tokens=2048,
    )

    adapter = build_generation_adapter(settings)

    assert isinstance(adapter, AnthropicGenerationAdapter)
    # Identity reflects the settings-supplied model id (no network call).
    assert adapter.model == "claude-sonnet-4-6"
    # The thinking budget and effort the operator configured are the ones this
    # adapter will spend — a factory that dropped either would leave the knobs inert.
    assert adapter._max_tokens == 2048
    assert adapter._effort == "xhigh"


def test_anthropic_provider_with_empty_key_fails_fast() -> None:
    settings = Settings(_env_file=None, generation_provider="anthropic", anthropic_api_key="")

    with pytest.raises(ValueError, match="LEARNY_ANTHROPIC_API_KEY is required"):
        build_generation_adapter(settings)


def test_unknown_provider_raises_value_error() -> None:
    settings = Settings(_env_file=None, generation_provider="gemini")

    with pytest.raises(ValueError, match="unknown generation provider: gemini"):
        build_generation_adapter(settings)
