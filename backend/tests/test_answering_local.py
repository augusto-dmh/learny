"""B1 gate — deterministic, network-free answer adapter (unit).

Derived from QA-06 and the task Done-when: same question + evidence → identical
result (deterministic, no network); the answer is composed only from the provided
evidence snippets and cites exactly those chunks (cited ids ⊆ evidence ids); at
most three snippets are used even with more evidence; a single evidence item
works; empty evidence → ``found=False`` empty result; and the adapter module
imports no provider SDK (ADR-0007 — no SDK leak).
"""

from __future__ import annotations

import ast
import inspect
from uuid import uuid4

from app.domain.entities import Evidence
from app.infrastructure.answering import DeterministicAnswerAdapter
from app.infrastructure.answering import local as local_module

_MODEL = "local-extractive"


def _evidence(snippet: str) -> Evidence:
    return Evidence(
        chunk_id=uuid4(),
        source_id=uuid4(),
        section_path=("Chapter 1",),
        anchor="ch1.xhtml#p",
        page_span=None,
        snippet=snippet,
        score=0.5,
    )


def test_same_input_generates_identically() -> None:
    # QA-06: deterministic — same question + evidence twice → equal results.
    adapter = DeterministicAnswerAdapter()
    evidence = [_evidence("alpha"), _evidence("beta")]

    first = adapter.generate(question="what?", evidence=evidence)
    second = adapter.generate(question="what?", evidence=evidence)

    assert first == second


def test_cited_ids_are_the_used_evidence_ids() -> None:
    # QA-06: composed only from provided evidence; cited ids ⊆ evidence ids.
    adapter = DeterministicAnswerAdapter()
    evidence = [_evidence("alpha"), _evidence("beta")]

    result = adapter.generate(question="q", evidence=evidence)

    assert result.found is True
    assert result.cited_chunk_ids == (evidence[0].chunk_id, evidence[1].chunk_id)
    assert set(result.cited_chunk_ids).issubset({e.chunk_id for e in evidence})
    # Answer text is built from the evidence snippets, nothing invented.
    assert result.text == "alpha\n\nbeta"


def test_uses_at_most_three_snippets_with_five_evidence() -> None:
    # Done-when: ≤ 3 snippets used, in retrieval-rank order, with 5 evidence items.
    adapter = DeterministicAnswerAdapter()
    evidence = [_evidence(f"snippet-{i}") for i in range(5)]

    result = adapter.generate(question="q", evidence=evidence)

    assert result.cited_chunk_ids == tuple(e.chunk_id for e in evidence[:3])
    assert result.text == "snippet-0\n\nsnippet-1\n\nsnippet-2"
    assert result.found is True


def test_single_evidence_item_works() -> None:
    # Done-when: a lone evidence item produces a found answer citing that chunk.
    adapter = DeterministicAnswerAdapter()
    only = _evidence("lonely passage")

    result = adapter.generate(question="q", evidence=[only])

    assert result.found is True
    assert result.cited_chunk_ids == (only.chunk_id,)
    assert result.text == "lonely passage"
    assert result.model == _MODEL


def test_empty_evidence_returns_not_found_empty_result() -> None:
    # Done-when: empty evidence → found=False, empty text and no citations.
    adapter = DeterministicAnswerAdapter()

    result = adapter.generate(question="q", evidence=[])

    assert result.found is False
    assert result.text == ""
    assert result.cited_chunk_ids == ()
    assert result.model == _MODEL


def test_model_identity_readable_without_a_generate_call() -> None:
    # QA-04/QA-13: the service reads this stable identity on the empty-evidence
    # not-found path, where the port is never invoked.
    assert DeterministicAnswerAdapter().model == _MODEL


def test_adapter_module_imports_no_provider_sdk() -> None:
    # QA-06 / ADR-0007: no provider SDK leaks into the answer module.
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
    # QA-06: pure/network-free — constructs with no provider client dependency.
    adapter = DeterministicAnswerAdapter()

    result = adapter.generate(question="q", evidence=[_evidence("passage")])
    assert result.found is True  # produced a result, no client wired
