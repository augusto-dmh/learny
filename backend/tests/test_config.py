"""Embedding-provider settings — defaults and environment overrides (EMB-06).

The composition-root factory reads these four knobs to select and build the
embedding adapter, so their defaults (offline ``local`` provider, no key required)
and ``LEARNY_``-prefixed overrides are pinned here. ``Settings`` is instantiated
directly (bypassing the ``get_settings`` lru-cache) so each case is isolated.
"""

from __future__ import annotations

from app.core.config import Settings


def test_embedding_settings_defaults() -> None:
    # Default provider is the offline deterministic adapter — CI needs no key.
    settings = Settings(_env_file=None)

    assert settings.embedding_provider == "local"
    assert settings.openai_api_key == ""
    assert settings.embedding_model == "text-embedding-3-large"
    assert settings.embedding_dim == 1536


def test_embedding_settings_env_override(monkeypatch) -> None:
    # LEARNY_-prefixed env vars override every embedding knob.
    monkeypatch.setenv("LEARNY_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("LEARNY_OPENAI_API_KEY", "sk-test-123")
    monkeypatch.setenv("LEARNY_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("LEARNY_EMBEDDING_DIM", "512")

    settings = Settings(_env_file=None)

    assert settings.embedding_provider == "openai"
    assert settings.openai_api_key == "sk-test-123"
    assert settings.embedding_model == "text-embedding-3-small"
    assert settings.embedding_dim == 512


def test_generation_settings_defaults() -> None:
    # Default provider is the offline deterministic adapter — CI needs no key.
    settings = Settings(_env_file=None)

    assert settings.generation_provider == "local"
    assert settings.anthropic_api_key == ""
    assert settings.generation_model == "claude-sonnet-4-6"
    assert settings.generation_max_tokens == 1024
    assert settings.judge_model == "claude-haiku-4-5"
    assert settings.eval_max_cases == 50


def test_generation_settings_env_override(monkeypatch) -> None:
    # LEARNY_-prefixed env vars override every generation knob.
    monkeypatch.setenv("LEARNY_GENERATION_PROVIDER", "anthropic")
    monkeypatch.setenv("LEARNY_ANTHROPIC_API_KEY", "sk-ant-123")
    monkeypatch.setenv("LEARNY_GENERATION_MODEL", "claude-opus-4-8")
    monkeypatch.setenv("LEARNY_GENERATION_MAX_TOKENS", "2048")
    monkeypatch.setenv("LEARNY_JUDGE_MODEL", "claude-sonnet-4-6")
    monkeypatch.setenv("LEARNY_EVAL_MAX_CASES", "10")

    settings = Settings(_env_file=None)

    assert settings.generation_provider == "anthropic"
    assert settings.anthropic_api_key == "sk-ant-123"
    assert settings.generation_model == "claude-opus-4-8"
    assert settings.generation_max_tokens == 2048
    assert settings.judge_model == "claude-sonnet-4-6"
    assert settings.eval_max_cases == 10
