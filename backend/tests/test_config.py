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
    assert settings.embedding_dimensions == 1536
    assert settings.embedding_dim == 1536


def test_embedding_settings_env_override(monkeypatch) -> None:
    # LEARNY_-prefixed env vars override every embedding knob.
    monkeypatch.setenv("LEARNY_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("LEARNY_OPENAI_API_KEY", "sk-test-123")
    monkeypatch.setenv("LEARNY_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("LEARNY_EMBEDDING_DIMENSIONS", "512")

    settings = Settings(_env_file=None)

    assert settings.embedding_provider == "openai"
    assert settings.openai_api_key == "sk-test-123"
    assert settings.embedding_model == "text-embedding-3-small"
    assert settings.embedding_dimensions == 512
