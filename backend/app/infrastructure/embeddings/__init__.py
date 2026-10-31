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
    no key); ``openai`` → the OpenAI adapter built from the key/model/dims settings;
    ``openai-compatible`` → the same adapter pointed at a self-hosted
    OpenAI-compatible runtime (Ollama/LM Studio) via ``LEARNY_EMBEDDING_BASE_URL``
    (ADR-0019 amendment: self-host only). The compat kind never sends the
    OpenAI-only ``dimensions`` parameter — the runtime's native dimension is
    validated against ``embedding_dim`` on every response — so the adapter's
    identity stamps the corpus with the width the responses are proven to have.
    An unrecognized provider, or the compat kind without its base URL, raises
    ``ValueError`` — a clear configuration error, not a silent fall back (EMB-03).
    """
    provider = settings.embedding_provider
    if provider == "local":
        return DeterministicEmbeddingAdapter()
    if provider == "openai":
        return OpenAIEmbeddingAdapter(
            api_key=settings.openai_api_key,
            model=settings.embedding_model,
            dimensions=settings.embedding_dim,
        )
    if provider == "openai-compatible":
        if not settings.embedding_base_url:
            raise ValueError(
                "LEARNY_EMBEDDING_PROVIDER=openai-compatible requires "
                "LEARNY_EMBEDDING_BASE_URL to name the local runtime's "
                "OpenAI-compatible endpoint (e.g. http://localhost:11434/v1 for "
                "Ollama, http://localhost:1234/v1 for LM Studio)"
            )
        # A local runtime ignores the key but the OpenAI SDK requires a non-empty
        # one: the operator's OpenAI key when set, else a fixed placeholder.
        return OpenAIEmbeddingAdapter(
            api_key=settings.openai_api_key or "local-embedding-runtime",
            model=settings.embedding_model,
            dimensions=None,
            expected_dim=settings.embedding_dim,
            base_url=settings.embedding_base_url,
        )
    raise ValueError(f"unknown embedding provider: {provider}")
