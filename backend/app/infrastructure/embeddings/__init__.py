"""Embedding adapters (implement ``EmbeddingPort``, ADR-0007).

The provider SDK and model name live only inside these adapters; callers depend
on ``EmbeddingPort`` and receive plain ``list[float]`` vectors. The default is a
deterministic, network-free adapter (D-1) that makes retrieval testable offline.
"""

from app.infrastructure.embeddings.local import DeterministicEmbeddingAdapter

__all__ = ["DeterministicEmbeddingAdapter"]
