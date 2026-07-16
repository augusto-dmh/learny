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

from app.domain.entities import (
    AnswerCompleted,
    AnswerTextDelta,
    Evidence,
    HistoryTurn,
)
from app.domain.ports import AnswerGenerationPort, TeachingGenerationPort
from app.infrastructure.answering import DeterministicAnswerAdapter
from app.infrastructure.answering import local as local_module
from app.infrastructure.answering.local import DeterministicTeachingAdapter

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


# --- DeterministicTeachingAdapter (TEACH-24 / AD-032) --------------------------


def _teach(adapter: DeterministicTeachingAdapter, evidence: list[Evidence]):
    return adapter.generate(
        message="explain this",
        target_section_path=("Chapter 1",),
        history=[HistoryTurn(message="earlier", response_text="prior")],
        evidence=evidence,
    )


def test_teaching_same_input_generates_identically() -> None:
    # AD-032: deterministic — same evidence twice → equal results.
    adapter = DeterministicTeachingAdapter()
    evidence = [_evidence("alpha"), _evidence("beta")]

    assert _teach(adapter, evidence) == _teach(adapter, evidence)


def test_teaching_composes_top_snippets_and_cites_selected() -> None:
    # AD-032: uses ≤ 3 snippets in retrieval order, cites exactly those chunks,
    # composes text only from the evidence (grounded by construction).
    adapter = DeterministicTeachingAdapter()
    evidence = [_evidence(f"snippet-{i}") for i in range(5)]

    result = _teach(adapter, evidence)

    assert result.found is True
    assert result.cited_chunk_ids == tuple(e.chunk_id for e in evidence[:3])
    assert set(result.cited_chunk_ids).issubset({e.chunk_id for e in evidence})
    assert result.text == "snippet-0\n\nsnippet-1\n\nsnippet-2"
    assert result.model == _MODEL


def test_teaching_single_evidence_item_works() -> None:
    # A lone evidence item produces a found response citing that chunk.
    adapter = DeterministicTeachingAdapter()
    only = _evidence("lonely passage")

    result = _teach(adapter, [only])

    assert result.found is True
    assert result.cited_chunk_ids == (only.chunk_id,)
    assert result.text == "lonely passage"
    assert result.model == _MODEL


def test_teaching_empty_evidence_returns_not_found_empty_result() -> None:
    # Done-when: empty evidence → found=False, empty text and no citations.
    adapter = DeterministicTeachingAdapter()

    result = _teach(adapter, [])

    assert result.found is False
    assert result.text == ""
    assert result.cited_chunk_ids == ()
    assert result.model == _MODEL


def test_teaching_prose_ignores_message_target_and_history() -> None:
    # AD-032: the deterministic prose is a function of the evidence only — varying
    # message/target/history with the same evidence yields an identical result.
    adapter = DeterministicTeachingAdapter()
    evidence = [_evidence("alpha"), _evidence("beta")]

    first = adapter.generate(
        message="one",
        target_section_path=("Chapter 1",),
        history=[],
        evidence=evidence,
    )
    second = adapter.generate(
        message="a completely different question",
        target_section_path=("Chapter 9", "Deep Section"),
        history=[HistoryTurn(message="m", response_text="r")],
        evidence=evidence,
    )

    assert first == second


def test_teaching_model_identity_readable_without_a_generate_call() -> None:
    # TEACH-11/TEACH-24: the turn service reads this stable identity on the
    # empty-evidence not-found path, where the port is never invoked.
    assert DeterministicTeachingAdapter().model == _MODEL


# --- Streaming contract (GEN-12) -----------------------------------------------
#
# Derived from the domain stream contract (design §5) and C1 Done-when: the
# deterministic adapters implement ``generate_stream`` as one full-text delta then
# exactly one AnswerCompleted (always last, authoritative — equal to the buffered
# ``generate`` result); the stream is deterministic; and both deterministic
# adapters plus the answer fake structurally satisfy their port Protocols.


def test_answer_stream_yields_full_text_delta_then_one_authoritative_completed() -> None:
    adapter = DeterministicAnswerAdapter()
    evidence = [_evidence("alpha"), _evidence("beta")]

    events = list(adapter.generate_stream(question="q", evidence=evidence))

    # The full extractive text arrives as a single delta, then exactly one
    # AnswerCompleted, always last.
    deltas = [e for e in events if isinstance(e, AnswerTextDelta)]
    completed = [e for e in events if isinstance(e, AnswerCompleted)]
    assert deltas == [AnswerTextDelta(text="alpha\n\nbeta")]
    assert len(completed) == 1
    assert isinstance(events[-1], AnswerCompleted)
    # The completed event's answer is authoritative — identical to the buffered path.
    assert events[-1].answer == adapter.generate(question="q", evidence=evidence)
    assert events[-1].answer.text == "alpha\n\nbeta"
    assert events[-1].answer.found is True


def test_answer_stream_is_deterministic() -> None:
    adapter = DeterministicAnswerAdapter()
    evidence = [_evidence("alpha")]

    first = list(adapter.generate_stream(question="q", evidence=evidence))
    second = list(adapter.generate_stream(question="q", evidence=evidence))

    assert first == second


def test_teaching_stream_yields_full_text_delta_then_one_authoritative_completed() -> None:
    adapter = DeterministicTeachingAdapter()
    evidence = [_evidence("alpha"), _evidence("beta")]

    events = list(
        adapter.generate_stream(
            message="explain",
            target_section_path=("Chapter 1",),
            history=[HistoryTurn(message="earlier", response_text="prior")],
            evidence=evidence,
        )
    )

    deltas = [e for e in events if isinstance(e, AnswerTextDelta)]
    completed = [e for e in events if isinstance(e, AnswerCompleted)]
    assert deltas == [AnswerTextDelta(text="alpha\n\nbeta")]
    assert len(completed) == 1
    assert isinstance(events[-1], AnswerCompleted)
    assert events[-1].answer == adapter.generate(
        message="explain",
        target_section_path=("Chapter 1",),
        history=[HistoryTurn(message="earlier", response_text="prior")],
        evidence=evidence,
    )


def test_deterministic_adapters_conform_to_their_port_protocols() -> None:
    # GEN-12: the runtime-checkable ports now include ``generate_stream``; the
    # deterministic adapters satisfy them structurally.
    assert isinstance(DeterministicAnswerAdapter(), AnswerGenerationPort)
    assert isinstance(DeterministicTeachingAdapter(), TeachingGenerationPort)


def test_answer_fake_conforms_to_the_answer_port_protocol() -> None:
    from tests.fakes import FakeAnswerGeneration

    assert isinstance(FakeAnswerGeneration(), AnswerGenerationPort)
