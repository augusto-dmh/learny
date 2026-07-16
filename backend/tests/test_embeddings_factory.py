"""Provider-selection factory — settings → adapter, unknown → error (EMB-03).

``build_embedding_adapter`` is the single composition-root seam that chooses the
embedding adapter from ``LEARNY_EMBEDDING_PROVIDER``. ``local`` (the offline
default) yields the deterministic adapter, ``openai`` the OpenAI adapter built from
the key/model/dims settings, and any other value is a loud configuration error
rather than a silent fall back.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.infrastructure.embeddings import (
    DeterministicEmbeddingAdapter,
    OpenAIEmbeddingAdapter,
    build_embedding_adapter,
)


def test_local_provider_builds_deterministic_adapter() -> None:
    settings = Settings(_env_file=None, embedding_provider="local")

    adapter = build_embedding_adapter(settings)

    assert isinstance(adapter, DeterministicEmbeddingAdapter)


def test_openai_provider_builds_openai_adapter_from_settings() -> None:
    settings = Settings(
        _env_file=None,
        embedding_provider="openai",
        openai_api_key="sk-test",
        embedding_model="text-embedding-3-large",
        embedding_dim=1536,
    )

    adapter = build_embedding_adapter(settings)

    assert isinstance(adapter, OpenAIEmbeddingAdapter)
    # Identity reflects the settings-supplied model + dims (no network call).
    assert adapter.model == "text-embedding-3-large@1536"


def test_unknown_provider_raises_value_error() -> None:
    settings = Settings(_env_file=None, embedding_provider="voyage")

    with pytest.raises(ValueError, match="unknown embedding provider: voyage"):
        build_embedding_adapter(settings)
