"""Quiz-provider factory pinning gate (settings → adapter, override → adapter).

Derived from the provider-pinning acceptance criteria at the factory seam: the
optional ``provider`` argument overrides ``settings.generation_provider`` — either
direction — so a poll can build exactly the adapter its deck handle names even
after the settings have named another provider; the default (no override) keeps
the settings-selected behavior byte-for-byte; an undeclared provider is a typed
``ValueError`` subclass naming the provider, so the poll task can map it to a
terminal failure while the retryable empty-key configuration error stays a plain
``ValueError``. ``Settings`` is instantiated directly (bypassing the
``get_settings`` lru-cache) so each case is isolated.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.infrastructure.quiz import (
    AnthropicQuizAdapter,
    DeterministicQuizAdapter,
    UndeclaredProviderError,
    build_quiz_adapter,
)


def test_the_override_selects_the_handle_provider_over_the_settings_provider() -> None:
    # Settings declare local; the handle says anthropic. The poll must get the
    # anthropic adapter — the batch id belongs to anthropic, whatever the current
    # default says.
    settings = Settings(
        _env_file=None,
        generation_provider="local",
        anthropic_api_key="sk-ant-test",
        quiz_model="claude-haiku-4-5",
    )

    adapter = build_quiz_adapter(settings, provider="anthropic")

    assert isinstance(adapter, AnthropicQuizAdapter)
    assert adapter.model == "claude-haiku-4-5"


def test_the_override_selects_local_while_settings_declare_anthropic() -> None:
    settings = Settings(
        _env_file=None,
        generation_provider="anthropic",
        anthropic_api_key="sk-ant-test",
    )

    adapter = build_quiz_adapter(settings, provider="local")

    assert isinstance(adapter, DeterministicQuizAdapter)


def test_no_override_keeps_the_settings_selected_provider() -> None:
    settings = Settings(_env_file=None, generation_provider="local")

    assert isinstance(build_quiz_adapter(settings), DeterministicQuizAdapter)
    assert isinstance(build_quiz_adapter(settings, provider=None), DeterministicQuizAdapter)


def test_an_undeclared_override_raises_the_typed_config_error() -> None:
    settings = Settings(_env_file=None, generation_provider="local")

    with pytest.raises(UndeclaredProviderError, match="gemini"):
        build_quiz_adapter(settings, provider="gemini")


def test_the_typed_config_error_is_still_a_value_error() -> None:
    # The pre-pinning contract — an unknown provider is a loud configuration
    # error, not a silent fall back — survives as the typed error's base class.
    settings = Settings(_env_file=None, generation_provider="gemini")

    with pytest.raises(ValueError, match="unknown generation provider: gemini"):
        build_quiz_adapter(settings)


def test_the_empty_key_error_stays_a_plain_value_error() -> None:
    # A missing key is a (possibly transient) configuration gap the worker may
    # retry; only an undeclared provider is terminal. The poll task tells the two
    # apart by type, so this one must not be the typed subclass.
    settings = Settings(_env_file=None, generation_provider="anthropic", anthropic_api_key="")

    with pytest.raises(ValueError) as excinfo:
        build_quiz_adapter(settings)

    assert not isinstance(excinfo.value, UndeclaredProviderError)
    assert "LEARNY_ANTHROPIC_API_KEY is required" in str(excinfo.value)
