"""T4 gate — deterministic, network-free embedding adapter (unit).

Derived from the "Embeddings behind a Learny port" story (RET-06/07/08) and the
task Done-when: same text → identical 1536-dim vector (deterministic, no network);
``embed_documents`` returns N vectors in input order; empty/whitespace text → a
zero vector (no division by zero); non-empty vectors are L2-normalized; and the
adapter module imports no provider SDK (ADR-0007 — no SDK leak).
"""

from __future__ import annotations

import ast
import inspect
import math

import pytest

from app.infrastructure.embeddings import DeterministicEmbeddingAdapter
from app.infrastructure.embeddings import local as local_module

_DIM = 1536


def test_same_text_embeds_identically() -> None:
    # RET-06: deterministic — same text twice → equal vectors.
    adapter = DeterministicEmbeddingAdapter()
    text = "the quick brown fox jumps"

    assert adapter.embed_query(text) == adapter.embed_query(text)


def test_query_vector_has_configured_dimension() -> None:
    # RET-06 / A-1: 1536-dim (from LEARNY_EMBEDDING_DIM).
    adapter = DeterministicEmbeddingAdapter()

    assert len(adapter.embed_query("meditations book one")) == _DIM


def test_embed_documents_returns_n_vectors_in_input_order() -> None:
    # RET-07: N texts in → N vectors out, each positionally the input's embedding.
    adapter = DeterministicEmbeddingAdapter()
    texts = ["alpha", "beta gamma", "delta epsilon zeta"]

    vectors = adapter.embed_documents(texts)

    assert len(vectors) == len(texts)
    assert all(len(v) == _DIM for v in vectors)
    for text, vector in zip(texts, vectors, strict=True):
        assert vector == adapter.embed_query(text)


def test_empty_and_whitespace_text_yield_zero_vector() -> None:
    # Edge: empty/whitespace → all-zero vector of length dim, no error/divide.
    adapter = DeterministicEmbeddingAdapter()

    for text in ("", "   ", "\n\t"):
        vector = adapter.embed_query(text)
        assert len(vector) == _DIM
        assert all(v == 0.0 for v in vector)


def test_non_empty_vector_is_l2_normalized() -> None:
    # Done-when: L2-normalized — non-empty vectors have unit length.
    adapter = DeterministicEmbeddingAdapter()

    vector = adapter.embed_query("meditations book one")
    norm = math.sqrt(sum(v * v for v in vector))

    assert norm == pytest.approx(1.0)


def test_adapter_module_imports_no_provider_sdk() -> None:
    # RET-08 / ADR-0007: no provider SDK leaks into the embedding module.
    tree = ast.parse(inspect.getsource(local_module))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert "openai" not in imported
    assert "anthropic" not in imported


def test_adapter_needs_no_client_argument() -> None:
    # RET-06: pure/network-free — constructs with no provider client dependency.
    adapter = DeterministicEmbeddingAdapter()

    assert adapter.embed_query("hello world")  # produces a vector, no client wired
