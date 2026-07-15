"""Embedding adapters (implement ``EmbeddingPort``, ADR-0007/0019).

The provider SDK and model name live only inside these adapters; callers depend
on ``EmbeddingPort`` and receive plain ``list[float]`` vectors. The default is a
deterministic, network-free adapter (D-1) that makes retrieval testable offline;
``build_embedding_adapter`` selects the concrete adapter from settings at the
composition root, so provider choice never leaks into query/repository code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.infrastructure.embeddings.local import DeterministicEmbeddingAdapter
from app.infrastructure.embeddings.openai import OpenAIEmbeddingAdapter

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.domain.ports import EmbeddingPort

__all__ = [
    "DeterministicEmbeddingAdapter",
    "OpenAIEmbeddingAdapter",
    "build_embedding_adapter",
]


def build_embedding_adapter(settings: Settings) -> EmbeddingPort:
    """Return the embedding adapter named by ``settings.embedding_provider``.

    ``local`` (default) → the deterministic, network-free adapter (CI/local needs
    no key); ``openai`` → the OpenAI adapter built from the key/model/dims settings.
    An unrecognized provider raises ``ValueError`` — a clear configuration error, not
    a silent fall back to the default (EMB-03).
    """
    provider = settings.embedding_provider
    if provider == "local":
        return DeterministicEmbeddingAdapter()
    if provider == "openai":
        return OpenAIEmbeddingAdapter(
            api_key=settings.openai_api_key,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    raise ValueError(f"unknown embedding provider: {provider}")
