"""OpenAI embedding adapter (implements ``EmbeddingPort``, ADR-0007/0019).

The official ``openai`` SDK, the model name, the ``base_url``, and the
``dimensions`` request parameter live only in this module — callers depend on
``EmbeddingPort`` and receive plain ``list[float]`` vectors. The hosted default is
``text-embedding-3-large`` with ``dimensions=1536`` (fits the ``vector(1536)``
column, no schema change; see ADR-0019 and ``docs/research/2026-07-12/embeddings.md``).

The same adapter serves a **self-hosted OpenAI-compatible runtime** (Ollama, LM
Studio — ADR-0019 amendment, self-host only): constructed with ``base_url`` and
``dimensions=None`` it never sends the OpenAI-only ``dimensions`` parameter (local
runtimes ignore or reject it), and ``expected_dim`` turns every response into a
validated contract — one vector per input, each numeric, each exactly
``expected_dim`` long — so a runtime serving a different native dimension fails
loudly at the adapter instead of writing a wrong-shaped vector next to the corpus.
A transport failure with ``base_url`` set raises the Learny taxonomy
``ProviderUnavailable`` naming the configured host, so the operator reads which
runtime is down.

Batching: ``embed_documents`` greedily sub-batches so each request stays within
OpenAI's per-request limits — **≤2048 inputs** and **≤250_000 tokens** (50k of
headroom under the 300k cap). Token counts are estimated with a cheap local
heuristic (``len(text) // 4 + 1``) rather than pulling in ``tiktoken``. Sub-batch
results are concatenated in input order, so overall order is preserved regardless
of input size. No retry/backoff lives here — Celery owns retries (research §3).
"""

from __future__ import annotations

from typing import Any, NoReturn, Protocol
from urllib.parse import urlsplit

from app.infrastructure.providers.errors import ProviderUnavailable
from app.infrastructure.providers.translation import classify_provider_failure

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


def _host_of(base_url: str) -> str:
    """The ``host:port`` a configured base URL points at, for failure messages."""
    return urlsplit(base_url).netloc or base_url


class OpenAIEmbeddingAdapter:
    """``EmbeddingPort`` implementation over OpenAI's embeddings API.

    Constructed with the API key, model name, and vector ``dimensions``. The real
    ``openai.OpenAI`` client is built lazily on first use (so the SDK import stays
    inside this module and an injected fake needs no key/network); tests pass a
    ``client`` directly. ``base_url`` points the client at a self-hosted
    OpenAI-compatible runtime instead of the OpenAI API.

    ``dimensions=None`` omits the ``dimensions`` request parameter (the compat
    kind — the runtime serves its native dimension); ``expected_dim`` (set for the
    compat kind) validates every response against the configured vector width.
    Exactly one of the two must be set: it is both the identity's dimension half
    and the write contract.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimensions: int | None,
        expected_dim: int | None = None,
        base_url: str = "",
        client: _EmbeddingsClient | None = None,
    ) -> None:
        if (dimensions is None) == (expected_dim is None):
            raise ValueError(
                "OpenAIEmbeddingAdapter needs exactly one of dimensions (sent as the "
                "request parameter, hosted kind) or expected_dim (validated on every "
                "response, compat kind)"
            )
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._expected_dim = expected_dim
        self._base_url = base_url
        self._client = client

    @property
    def model(self) -> str:
        """Stable identity — ``{model}@{dim}`` (e.g. ``text-embedding-3-large@1536``).

        Encodes model **and** dims because ``large@1536`` ≠ ``large@3072`` at the
        vector level; readable without a network call (ADR-0019). The compat kind's
        dimension half is ``expected_dim`` — the width the runtime's responses are
        validated against, and the width the corpus's stamps must match.
        """
        dim = self._dimensions if self._dimensions is not None else self._expected_dim
        return f"{self._model}@{dim}"

    @property
    def base_url(self) -> str:
        """The configured runtime base URL (``""`` for the hosted OpenAI API)."""
        return self._base_url

    def _get_client(self) -> _EmbeddingsClient:
        """Return the injected client, or lazily build ``openai.OpenAI``.

        The ``openai`` import lives here so it is the only place the SDK is
        referenced and so an injected client keeps the adapter import-light.
        """
        if self._client is None:
            import openai  # local import — the sole SDK reference (ADR-0007/0009)

            self._client = openai.OpenAI(api_key=self._api_key, base_url=self._base_url or None)
        return self._client

    def _translate_transport(self, exc: BaseException) -> NoReturn:
        """Re-raise a transport failure, naming the host when one is configured.

        With no ``base_url`` (the hosted kind) the original exception propagates
        unchanged — the hosted path's behavior is exactly as before. With a
        ``base_url`` the failure is classified through the providers package's
        shared translator (the same SDK-type binding the compat generation adapter
        uses), and an unreachable runtime becomes ``ProviderUnavailable`` whose
        message names the configured host, so the operator reads which runtime is
        down (ADR-0019 amendment).
        """
        if not self._base_url:
            raise exc
        import httpx  # local import, like every transport reference in this module
        import openai  # local import — the sole SDK reference (ADR-0007/0009)

        translated = classify_provider_failure(
            exc,
            timeout_exceptions=(TimeoutError, httpx.TimeoutException, openai.APITimeoutError),
            unreachable_exceptions=(openai.APIConnectionError,),
        )
        if isinstance(translated, ProviderUnavailable):
            raise ProviderUnavailable(
                f"the embedding runtime at {_host_of(self._base_url)} could not be reached"
            ) from exc
        raise translated from exc

    def _validate_shape(self, vectors: list[Any], expected_count: int) -> list[list[float]]:
        """Reject a malformed runtime response before any caller sees a vector.

        The compat contract (ADR-0019 amendment): one vector per input, each entry
        numeric, each vector exactly ``expected_dim`` long. One message names the
        model, the expected dimension, and what was received (the count, or the
        offending vector's dimension), so a mismatched native dimension is an
        actionable error, never a silent wrong-shaped write beside the corpus.
        """
        expected = self._expected_dim
        assert expected is not None  # guaranteed by the constructor's contract
        if len(vectors) != expected_count:
            raise ValueError(
                f"the embedding runtime returned {len(vectors)} vectors for "
                f"{expected_count} inputs (model {self._model}, expected dimension "
                f"{expected})"
            )
        for i, vector in enumerate(vectors):
            if not isinstance(vector, list) or not all(
                isinstance(x, (int, float)) and not isinstance(x, bool) for x in vector
            ):
                raise ValueError(
                    f"the embedding runtime returned a non-numeric vector for input "
                    f"{i} (model {self._model}, expected dimension {expected})"
                )
            if len(vector) != expected:
                raise ValueError(
                    f"the embedding runtime returned a {len(vector)}-dimension vector "
                    f"for input {i}, expected {expected} (model {self._model}) — the "
                    "runtime's native embedding dimension does not match "
                    "LEARNY_EMBEDDING_DIM"
                )
        return vectors

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """One API request for a bounded sub-batch → one vector per input, in order."""
        kwargs: dict[str, Any] = {"model": self._model, "input": texts}
        # The hosted kind sends ``dimensions`` (the Matryoshka truncation request);
        # the compat kind never does — local runtimes ignore or reject OpenAI-only
        # parameters, and the runtime's native dimension is validated below instead.
        if self._dimensions is not None:
            kwargs["dimensions"] = self._dimensions
        try:
            response = self._get_client().embeddings.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 — every transport failure is translated
            self._translate_transport(exc)
        vectors = [item.embedding for item in response.data]
        if self._expected_dim is not None:
            return self._validate_shape(vectors, len(texts))
        return vectors

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
