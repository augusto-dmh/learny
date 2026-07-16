"""OpenAI embedding adapter (implements ``EmbeddingPort``, ADR-0007/0019).

The official ``openai`` SDK, the model name, and the ``dimensions`` request
parameter live only in this module — callers depend on ``EmbeddingPort`` and
receive plain ``list[float]`` vectors. Model is ``text-embedding-3-large`` with
``dimensions=1536`` (fits the ``vector(1536)`` column, no schema change; see
ADR-0019 and ``docs/research/2026-07-12/embeddings.md``).

Batching: ``embed_documents`` greedily sub-batches so each request stays within
OpenAI's per-request limits — **≤2048 inputs** and **≤250_000 tokens** (50k of
headroom under the 300k cap). Token counts are estimated with a cheap local
heuristic (``len(text) // 4 + 1``) rather than pulling in ``tiktoken``. Sub-batch
results are concatenated in input order, so overall order is preserved regardless
of input size. No retry/backoff lives here — Celery owns retries (research §3).
"""

from __future__ import annotations

from typing import Any, Protocol

# Per-request caps (OpenAI create-embeddings limits, research §1). The token cap
# keeps 50k of headroom under the documented 300k summed-tokens limit.
_MAX_INPUTS_PER_REQUEST = 2048
_MAX_TOKENS_PER_REQUEST = 250_000


class _EmbeddingsClient(Protocol):
    """The narrow slice of the OpenAI client this adapter uses (test seam).

    Both the real ``openai.OpenAI`` client and the test fake expose
    ``client.embeddings.create(model=, input=, dimensions=)`` returning an object
    whose ``.data[i].embedding`` is the i-th input's vector.
    """

    embeddings: Any


def _estimate_tokens(text: str) -> int:
    """Cheap local token estimate — ``len(text) // 4 + 1`` (no ``tiktoken`` dep)."""
    return len(text) // 4 + 1


class OpenAIEmbeddingAdapter:
    """``EmbeddingPort`` implementation over OpenAI's embeddings API.

    Constructed with the API key, model name, and vector ``dimensions``. The real
    ``openai.OpenAI`` client is built lazily on first use (so the SDK import stays
    inside this module and an injected fake needs no key/network); tests pass a
    ``client`` directly.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimensions: int,
        client: _EmbeddingsClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._client = client

    @property
    def model(self) -> str:
        """Stable identity — ``{model}@{dimensions}`` (e.g. ``text-embedding-3-large@1536``).

        Encodes model **and** dims because ``large@1536`` ≠ ``large@3072`` at the
        vector level; readable without a network call (ADR-0019).
        """
        return f"{self._model}@{self._dimensions}"

    def _get_client(self) -> _EmbeddingsClient:
        """Return the injected client, or lazily build ``openai.OpenAI``.

        The ``openai`` import lives here so it is the only place the SDK is
        referenced and so an injected client keeps the adapter import-light.
        """
        if self._client is None:
            import openai  # local import — the sole SDK reference (ADR-0007/0009)

            self._client = openai.OpenAI(api_key=self._api_key)
        return self._client

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """One API request for a bounded sub-batch → one vector per input, in order."""
        response = self._get_client().embeddings.create(
            model=self._model, input=texts, dimensions=self._dimensions
        )
        return [item.embedding for item in response.data]

    def embed_query(self, text: str) -> list[float]:
        """Embed a single search query into one vector (one request)."""
        return self._embed_batch([text])[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch, returning one vector per input in input order.

        Greedily accumulates inputs into a sub-batch until the next input would
        push the request past ``_MAX_INPUTS_PER_REQUEST`` inputs or
        ``_MAX_TOKENS_PER_REQUEST`` estimated tokens, then flushes it as one
        request; results are concatenated in order. Empty input → ``[]``.
        """
        if not texts:
            return []

        vectors: list[list[float]] = []
        batch: list[str] = []
        batch_tokens = 0
        for text in texts:
            tokens = _estimate_tokens(text)
            # Flush before adding when the addition would breach either cap; a
            # single oversized input still gets its own request (batch empty).
            if batch and (
                len(batch) + 1 > _MAX_INPUTS_PER_REQUEST
                or batch_tokens + tokens > _MAX_TOKENS_PER_REQUEST
            ):
                vectors.extend(self._embed_batch(batch))
                batch = []
                batch_tokens = 0
            batch.append(text)
            batch_tokens += tokens
        if batch:
            vectors.extend(self._embed_batch(batch))
        return vectors
