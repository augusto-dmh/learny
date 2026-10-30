"""OpenAI embedding adapter — batching, dims, order (EMB-01/02/05), no network.

The adapter is exercised against a *fake* client that records every
``embeddings.create`` call and returns canned vectors — the real ``openai`` SDK is
never imported or reached (CI stays offline). Each fake vector's first element
carries an integer marker derived from its input so input→output order can be
asserted across sub-batch boundaries. A ``@pytest.mark.live`` smoke exercises the
real API and is skipped unless ``LEARNY_OPENAI_API_KEY`` is set.
"""

from __future__ import annotations

import os
import re
from types import SimpleNamespace

import httpx
import openai as openai_sdk
import pytest

from app.infrastructure.embeddings.openai import OpenAIEmbeddingAdapter
from app.infrastructure.providers.errors import ProviderUnavailable

_MODEL = "text-embedding-3-large"
_DIM = 1536


class _FakeData:
    def __init__(self, embedding: list[float]) -> None:
        self.embedding = embedding


class _FakeResponse:
    def __init__(self, data: list[_FakeData]) -> None:
        self.data = data


class _FakeEmbeddingsResource:
    """Records each ``create`` call verbatim; returns one marked vector per input.

    The marker (vector element 0) is ``float(int(text))`` when the input is a
    numeric string, so a caller can assert the returned order matches the input
    order across concatenated sub-batches. Calls are recorded exactly as passed —
    a hosted request carries a ``dimensions`` key, a compat-kind request must not,
    so the absence of the key is the assertable fact. A compat call (no
    ``dimensions`` key) is served at the fake's native dimension.
    """

    def __init__(self, *, native_dim: int = 768) -> None:
        self.native_dim = native_dim
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _FakeResponse:
        self.calls.append(kwargs)
        dim = kwargs.get("dimensions", self.native_dim)
        assert isinstance(dim, int), "fake needs dimensions or native_dim"
        data = []
        for text in kwargs.get("input", []):
            marker = (
                float(int(text)) if isinstance(text, str) and text.lstrip("-").isdigit() else 0.0
            )
            data.append(_FakeData([marker] + [0.0] * (dim - 1)))
        return _FakeResponse(data)


class _FakeClient:
    def __init__(self) -> None:
        self.embeddings = _FakeEmbeddingsResource()


def _adapter(client: _FakeClient) -> OpenAIEmbeddingAdapter:
    return OpenAIEmbeddingAdapter(
        api_key="unused-fake", model=_MODEL, dimensions=_DIM, client=client
    )


def test_model_identity_encodes_model_and_dims() -> None:
    # EMB-04: identity is model@dims, readable without a network call.
    adapter = _adapter(_FakeClient())

    assert adapter.model == "text-embedding-3-large@1536"


def test_embed_query_makes_one_request_and_returns_one_vector() -> None:
    client = _FakeClient()

    vector = _adapter(client).embed_query("42")

    assert len(client.embeddings.calls) == 1
    assert client.embeddings.calls[0]["input"] == ["42"]
    assert client.embeddings.calls[0]["dimensions"] == _DIM
    assert len(vector) == _DIM
    assert vector[0] == 42.0


def test_empty_document_list_returns_empty_and_makes_no_request() -> None:
    client = _FakeClient()

    assert _adapter(client).embed_documents([]) == []
    assert client.embeddings.calls == []


def test_input_order_preserved_across_subbatches() -> None:
    # EMB-01/02: 5000 inputs span three ≤2048 sub-batches; output stays in order.
    client = _FakeClient()
    texts = [str(i) for i in range(5000)]

    vectors = _adapter(client).embed_documents(texts)

    assert len(vectors) == 5000
    assert [v[0] for v in vectors] == [float(i) for i in range(5000)]
    # Sub-batched: ceil(5000 / 2048) == 3 requests, none exceeding the input cap.
    assert len(client.embeddings.calls) == 3
    assert [len(c["input"]) for c in client.embeddings.calls] == [2048, 2048, 904]


def test_dimensions_sent_on_every_request() -> None:
    # EMB-01: dimensions=1536 is passed on each sub-batch request.
    client = _FakeClient()

    _adapter(client).embed_documents([str(i) for i in range(3000)])

    assert client.embeddings.calls  # multiple requests
    assert all(c["dimensions"] == _DIM for c in client.embeddings.calls)


def test_subbatch_boundary_at_2048_inputs() -> None:
    # Exactly 2048 → one request; 2049 → two requests split [2048, 1].
    client = _FakeClient()
    _adapter(client).embed_documents([str(i) for i in range(2048)])
    assert [len(c["input"]) for c in client.embeddings.calls] == [2048]

    client = _FakeClient()
    _adapter(client).embed_documents([str(i) for i in range(2049)])
    assert [len(c["input"]) for c in client.embeddings.calls] == [2048, 1]


def test_subbatch_boundary_at_token_cap() -> None:
    # Each text estimates 50_000 tokens (len // 4 + 1), so five fill the 250_000
    # cap exactly and the sixth starts a new request → split [5, 1].
    client = _FakeClient()
    long_text = "a" * 199_996  # len // 4 + 1 == 50_000

    _adapter(client).embed_documents([long_text] * 6)

    assert [len(c["input"]) for c in client.embeddings.calls] == [5, 1]


@pytest.mark.live
@pytest.mark.skipif(
    not os.getenv("LEARNY_OPENAI_API_KEY"),
    reason="LEARNY_OPENAI_API_KEY unset — live OpenAI smoke skipped (CI stays offline)",
)
def test_live_embeds_one_string() -> None:
    adapter = OpenAIEmbeddingAdapter(
        api_key=os.environ["LEARNY_OPENAI_API_KEY"], model=_MODEL, dimensions=_DIM
    )

    vector = adapter.embed_query("Learny live embedding smoke test.")

    assert len(vector) == _DIM
    assert any(component != 0.0 for component in vector)


# --- Compat kind (ADR-0019 amendment): self-hosted OpenAI-compatible runtimes ----


class _ScriptedEmbeddingsResource:
    """Serves a scripted response (or raises a scripted error) once per call."""

    def __init__(
        self,
        *,
        vectors: list[object] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.vectors = vectors or []
        self.error = error
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _FakeResponse:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return _FakeResponse([_FakeData(v) for v in self.vectors])  # type: ignore[arg-type]


def _compat_adapter(
    resource: _ScriptedEmbeddingsResource, *, base_url: str = "http://localhost:11434/v1"
) -> OpenAIEmbeddingAdapter:
    client = SimpleNamespace(embeddings=resource)
    return OpenAIEmbeddingAdapter(
        api_key="unused-fake",
        model="nomic-embed-text",
        dimensions=None,
        expected_dim=768,
        base_url=base_url,
        client=client,
    )


def test_compat_construction_needs_exactly_one_dim_contract() -> None:
    # dimensions and expected_dim are exclusive: neither (no contract) or both
    # (two contracts) are construction errors.
    with pytest.raises(ValueError, match="exactly one"):
        OpenAIEmbeddingAdapter(api_key="k", model="m", dimensions=None)
    with pytest.raises(ValueError, match="exactly one"):
        OpenAIEmbeddingAdapter(api_key="k", model="m", dimensions=1536, expected_dim=768)


def test_compat_identity_encodes_expected_dim() -> None:
    adapter = OpenAIEmbeddingAdapter(
        api_key="k", model="nomic-embed-text", dimensions=None, expected_dim=768
    )

    assert adapter.model == "nomic-embed-text@768"


def test_compat_omits_dimensions_parameter() -> None:
    # The OpenAI-only dimensions request parameter never enters a compat request;
    # the fake serves its native 768 width instead.
    resource = _ScriptedEmbeddingsResource(vectors=[[0.0] * 768 for _ in range(2)])

    out = _compat_adapter(resource).embed_documents(["a", "b"])

    assert out == [[0.0] * 768, [0.0] * 768]
    assert len(resource.calls) == 1
    assert "dimensions" not in resource.calls[0]


def test_compat_validates_response_shape_passes_clean_response() -> None:
    resource = _ScriptedEmbeddingsResource(vectors=[[0.5, 0.25] + [0.0] * 766])

    out = _compat_adapter(resource).embed_query("q")

    assert len(out) == 768


@pytest.mark.parametrize(
    ("vectors", "received"),
    [
        pytest.param([[0.0] * 768], "1 vectors for 2 inputs", id="wrong-count"),
        pytest.param(
            [[0.0] * 767 + ["oops"], [0.0] * 768],
            "non-numeric vector for input 0",
            id="non-numeric",
        ),
        pytest.param(
            [[0.0] * 512, [0.0] * 768],
            "512-dimension vector for input 0",
            id="wrong-dim",
        ),
    ],
)
def test_unexpected_shape_raises_naming_model_and_dim(vectors: list[object], received: str) -> None:
    resource = _ScriptedEmbeddingsResource(vectors=vectors)

    with pytest.raises(ValueError, match=re.escape(received)) as excinfo:
        _compat_adapter(resource).embed_documents(["a", "b"])

    message = str(excinfo.value)
    assert "nomic-embed-text" in message
    assert "768" in message


def test_transport_failure_names_host() -> None:
    # An unreachable local runtime raises the Learny taxonomy error with the
    # configured host in the message, so the operator reads which runtime is down.
    request = httpx.Request("POST", "http://localhost:11434/v1/embeddings")
    resource = _ScriptedEmbeddingsResource(error=openai_sdk.APIConnectionError(request=request))

    with pytest.raises(ProviderUnavailable, match="localhost:11434"):
        _compat_adapter(resource).embed_query("q")


def test_hosted_kind_transport_failure_unchanged() -> None:
    # Without a base_url the hosted path's behavior is exactly as before: the raw
    # SDK exception propagates (Celery owns retries and classification).
    request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    resource = _ScriptedEmbeddingsResource(error=openai_sdk.APIConnectionError(request=request))
    client = SimpleNamespace(embeddings=resource)
    adapter = OpenAIEmbeddingAdapter(
        api_key="sk-test",
        model=_MODEL,
        dimensions=_DIM,
        client=client,
    )

    with pytest.raises(openai_sdk.APIConnectionError):
        adapter.embed_query("q")
