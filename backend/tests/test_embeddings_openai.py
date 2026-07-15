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

import pytest

from app.infrastructure.embeddings.openai import OpenAIEmbeddingAdapter

_MODEL = "text-embedding-3-large"
_DIM = 1536


class _FakeData:
    def __init__(self, embedding: list[float]) -> None:
        self.embedding = embedding


class _FakeResponse:
    def __init__(self, data: list[_FakeData]) -> None:
        self.data = data


class _FakeEmbeddingsResource:
    """Records each ``create`` call; returns one marked vector per input, in order.

    The marker (vector element 0) is ``float(int(text))`` when the input is a
    numeric string, so a caller can assert the returned order matches the input
    order across concatenated sub-batches.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, *, model: str, input: list[str], dimensions: int) -> _FakeResponse:
        self.calls.append({"model": model, "input": list(input), "dimensions": dimensions})
        data = []
        for text in input:
            marker = float(int(text)) if text.lstrip("-").isdigit() else 0.0
            data.append(_FakeData([marker] + [0.0] * (dimensions - 1)))
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
