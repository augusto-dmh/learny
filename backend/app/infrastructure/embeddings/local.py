"""Deterministic, network-free embedding adapter (implements ``EmbeddingPort``).

The default embedding provider (D-1): pure Python, no network, no provider SDK.
Text is tokenized into lowercase word tokens; each token is hashed with
``blake2b`` into an index of a ``LEARNY_EMBEDDING_DIM``-length accumulator with a
hashed ±1 sign, and the vector is L2-normalized. Same text → identical vector
(deterministic), and shared tokens raise cosine similarity (weakly meaningful),
which stabilizes golden-fixture semantic ordering. Empty/whitespace text → a
zero vector (the semantic arm stays safe; the lexical arm carries recall).

Swapping in a real cloud model later is an adapter + re-index change, never a
domain change (embeddings are derived and re-indexable, ADR-0001/0007).
"""

from __future__ import annotations

import hashlib
import math
import re

from app.core.config import get_settings

# Lowercase word tokens; unicode-aware so non-ASCII text still tokenizes.
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


class DeterministicEmbeddingAdapter:
    """``EmbeddingPort`` implementation — deterministic hashing bag-of-tokens.

    Needs no provider client: constructed with no arguments and makes no network
    call, so retrieval is testable offline (D-1).
    """

    def __init__(self) -> None:
        self._dim = get_settings().embedding_dim

    @property
    def model(self) -> str:
        """Stable identity — ``local-deterministic@{dim}`` (never a network call).

        Ignores ``LEARNY_EMBEDDING_MODEL`` (the provider model name) and reports its
        own hashing-adapter identity encoding the dimension, so a stamped chunk is
        never mistaken for a real provider's output (ADR-0019).
        """
        return f"local-deterministic@{self._dim}"

    def embed_query(self, text: str) -> list[float]:
        """Embed a single search query into one ``embedding_dim``-length vector."""
        return self._embed(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch, returning one vector per input text in input order."""
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        dim = self._dim
        vec = [0.0] * dim
        for token in _TOKEN_RE.findall(text.lower()):
            # Disjoint digest bytes for the index and the sign so they are
            # independent: first 8 bytes → bucket, next byte → ±1 sign.
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=9).digest()
            index = int.from_bytes(digest[:8], "big") % dim
            sign = 1.0 if digest[8] & 1 else -1.0
            vec[index] += sign
        norm = math.sqrt(sum(component * component for component in vec))
        if norm == 0.0:
            # Empty/whitespace text (no tokens) → zero vector; never divide by 0.
            return vec
        return [component / norm for component in vec]
