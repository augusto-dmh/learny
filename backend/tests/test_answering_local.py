"""B1 gate — deterministic, network-free generation adapter (unit).

Derived from QA-06 and the task Done-when: same message + evidence → identical
result (deterministic, no network); the answer is composed only from the provided
evidence snippets and cites exactly those chunks (cited ids ⊆ evidence ids); at
most three snippets are used even with more evidence; a single evidence item
works; empty evidence → ``found=False`` empty result; and the adapter module
imports no provider SDK (ADR-0007 — no SDK leak).

Since the ports converged, one adapter serves both modes, so every behaviour here
is asserted in each mode, and the extractive output is pinned to frozen literal
prose and citations so a mode-dispatching adapter cannot quietly shift it.
"""

from __future__ import annotations

import ast
import inspect
from uuid import uuid4

import pytest

from app.domain.entities import (
    MODE_ANSWER,
    MODE_TEACH,
    AnswerCompleted,
    AnswerReasoningDelta,
    AnswerTextDelta,
    Evidence,
    GeneratedAnswer,
    HistoryTurn,
)
from app.domain.ports import GenerationPort
from app.infrastructure.answering import DeterministicGenerationAdapter
from app.infrastructure.answering import local as local_module

_MODEL = "local-extractive"

# Both modes, so every behaviour below is asserted for the answer path and the
# teach path of the one converged adapter.
_MODES = pytest.mark.parametrize("mode", [MODE_ANSWER, MODE_TEACH])


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


def _target(mode: str) -> tuple[str, ...] | None:
    """The target a turn in ``mode`` carries — the teach path supplies one."""
    return ("Chapter 1",) if mode == MODE_TEACH else None


def _generate(adapter: DeterministicGenerationAdapter, mode: str, evidence: list[Evidence], **kw):
    return adapter.generate(
        message="what?",
        mode=mode,
        evidence=evidence,
        target_section_path=_target(mode),
        **kw,
    )


def _generate_stream(
    adapter: DeterministicGenerationAdapter, mode: str, evidence: list[Evidence], **kw
):
    return adapter.generate_stream(
        message="what?",
        mode=mode,
        evidence=evidence,
        target_section_path=_target(mode),
        **kw,
    )


# --- Output parity across the convergence (I-A1) -------------------------------


def test_extractive_output_is_the_frozen_prose_and_citations_in_both_modes() -> None:
    # The convergence must not shift a single byte of generated prose or any
    # citation: the extractive answer is still the top three snippets in retrieval
    # order joined by blank lines, citing exactly those chunks, in either mode.
    adapter = DeterministicGenerationAdapter()
    evidence = [_evidence(f"snippet-{i}") for i in range(5)]
    frozen = GeneratedAnswer(
        text="snippet-0\n\nsnippet-1\n\nsnippet-2",
        cited_chunk_ids=(evidence[0].chunk_id, evidence[1].chunk_id, evidence[2].chunk_id),
        model=_MODEL,
        found=True,
    )
    history = [HistoryTurn(message="earlier", response_text="prior")]

    answered = _generate(adapter, MODE_ANSWER, evidence, history=history)
    taught = _generate(adapter, MODE_TEACH, evidence, history=history)

    assert answered == frozen
    assert taught == frozen


def test_streamed_extractive_output_is_the_frozen_events_in_both_modes() -> None:
    # Same parity on the streaming path: one full-text delta carrying the frozen
    # prose, then the authoritative completed event.
    adapter = DeterministicGenerationAdapter()
    evidence = [_evidence("alpha"), _evidence("beta")]
    frozen = GeneratedAnswer(
        text="alpha\n\nbeta",
        cited_chunk_ids=(evidence[0].chunk_id, evidence[1].chunk_id),
        model=_MODEL,
        found=True,
    )

    answered = list(_generate_stream(adapter, MODE_ANSWER, evidence))
    taught = list(_generate_stream(adapter, MODE_TEACH, evidence))

    assert answered == [AnswerTextDelta(text="alpha\n\nbeta"), AnswerCompleted(answer=frozen)]
    assert taught == answered


@_MODES
def test_streamed_extractive_output_carries_no_reasoning(mode: str) -> None:
    # ANSW-06: reasoning belongs to a provider that thinks. This adapter extracts,
    # so a turn it serves has no reasoning to show — the offline, keyless contract is
    # unchanged by the thinking config the cloud adapter now sends.
    adapter = DeterministicGenerationAdapter()
    evidence = [_evidence("alpha"), _evidence("beta")]

    events = list(_generate_stream(adapter, mode, evidence))

    assert [e for e in events if isinstance(e, AnswerReasoningDelta)] == []


# --- Extractive composition (QA-06 / AD-032) -----------------------------------


@_MODES
def test_same_input_generates_identically(mode: str) -> None:
    # QA-06: deterministic — same message + evidence twice → equal results.
    adapter = DeterministicGenerationAdapter()
    evidence = [_evidence("alpha"), _evidence("beta")]

    assert _generate(adapter, mode, evidence) == _generate(adapter, mode, evidence)


@_MODES
def test_first_turn_output_is_unchanged_by_the_history_parameter(mode: str) -> None:
    # I-CM-8: the deterministic answer is a function of the evidence alone. A turn
    # with no history produces exactly the text and citations the ask path has always
    # produced ("alpha\n\nbeta", both chunks — pinned by the Q&A suite), and history
    # never shifts it, so goldens stay stable as conversations gain memory.
    adapter = DeterministicGenerationAdapter()
    evidence = [_evidence("alpha"), _evidence("beta")]

    without_argument = _generate(adapter, mode, evidence)
    empty_history = _generate(adapter, mode, evidence, history=[])
    with_history = _generate(
        adapter, mode, evidence, history=[HistoryTurn(message="earlier", response_text="reply")]
    )

    assert without_argument.text == "alpha\n\nbeta"
    assert without_argument.cited_chunk_ids == (evidence[0].chunk_id, evidence[1].chunk_id)
    assert empty_history == without_argument
    assert with_history == without_argument


@_MODES
def test_streamed_first_turn_output_is_unchanged_by_the_history_parameter(mode: str) -> None:
    # I-CM-8 on the streaming path: same deltas, same authoritative answer.
    adapter = DeterministicGenerationAdapter()
    evidence = [_evidence("alpha"), _evidence("beta")]

    without_argument = list(_generate_stream(adapter, mode, evidence))
    with_history = list(
        _generate_stream(
            adapter, mode, evidence, history=[HistoryTurn(message="earlier", response_text="reply")]
        )
    )

    assert without_argument == with_history
    assert without_argument[0] == AnswerTextDelta(text="alpha\n\nbeta")
    assert isinstance(without_argument[-1], AnswerCompleted)


@_MODES
def test_cited_ids_are_the_used_evidence_ids(mode: str) -> None:
    # QA-06: composed only from provided evidence; cited ids ⊆ evidence ids.
    adapter = DeterministicGenerationAdapter()
    evidence = [_evidence("alpha"), _evidence("beta")]

    result = _generate(adapter, mode, evidence)

    assert result.found is True
    assert result.cited_chunk_ids == (evidence[0].chunk_id, evidence[1].chunk_id)
    assert set(result.cited_chunk_ids).issubset({e.chunk_id for e in evidence})
    # Answer text is built from the evidence snippets, nothing invented.
    assert result.text == "alpha\n\nbeta"


@_MODES
def test_uses_at_most_three_snippets_with_five_evidence(mode: str) -> None:
    # Done-when: ≤ 3 snippets used, in retrieval-rank order, with 5 evidence items.
    adapter = DeterministicGenerationAdapter()
    evidence = [_evidence(f"snippet-{i}") for i in range(5)]

    result = _generate(adapter, mode, evidence)

    assert result.cited_chunk_ids == tuple(e.chunk_id for e in evidence[:3])
    assert result.text == "snippet-0\n\nsnippet-1\n\nsnippet-2"
    assert result.found is True


@_MODES
def test_single_evidence_item_works(mode: str) -> None:
    # Done-when: a lone evidence item produces a found answer citing that chunk.
    adapter = DeterministicGenerationAdapter()
    only = _evidence("lonely passage")

    result = _generate(adapter, mode, [only])

    assert result.found is True
    assert result.cited_chunk_ids == (only.chunk_id,)
    assert result.text == "lonely passage"
    assert result.model == _MODEL


@_MODES
def test_empty_evidence_returns_not_found_empty_result(mode: str) -> None:
    # Done-when: empty evidence → found=False, empty text and no citations.
    adapter = DeterministicGenerationAdapter()

    result = _generate(adapter, mode, [])

    assert result.found is False
    assert result.text == ""
    assert result.cited_chunk_ids == ()
    assert result.model == _MODEL


def test_prose_ignores_message_mode_target_and_history() -> None:
    # AD-032: the deterministic prose is a function of the evidence only — varying
    # message/mode/target/history with the same evidence yields an identical result.
    adapter = DeterministicGenerationAdapter()
    evidence = [_evidence("alpha"), _evidence("beta")]

    first = adapter.generate(
        message="one",
        mode=MODE_ANSWER,
        evidence=evidence,
        history=[],
        target_section_path=None,
    )
    second = adapter.generate(
        message="a completely different question",
        mode=MODE_TEACH,
        evidence=evidence,
        history=[HistoryTurn(message="m", response_text="r")],
        target_section_path=("Chapter 9", "Deep Section"),
    )

    assert first == second


def test_tutor_phase_kwargs_do_not_change_extractive_output() -> None:
    adapter = DeterministicGenerationAdapter()
    evidence = [_evidence("alpha"), _evidence("beta")]

    plain = _generate(adapter, MODE_TEACH, evidence)
    enveloped = _generate(adapter, MODE_TEACH, evidence, tutor_phase="open", hint_level="pump")

    assert enveloped == plain


def test_model_identity_readable_without_a_generate_call() -> None:
    # QA-04/QA-13, TEACH-11/TEACH-24: the turn service reads this stable identity on
    # the empty-evidence not-found path, where the port is never invoked.
    assert DeterministicGenerationAdapter().model == _MODEL


def test_adapter_module_imports_no_provider_sdk() -> None:
    # QA-06 / ADR-0007: no provider SDK leaks into the deterministic module.
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
    adapter = DeterministicGenerationAdapter()

    result = _generate(adapter, MODE_ANSWER, [_evidence("passage")])
    assert result.found is True  # produced a result, no client wired


# --- Streaming contract (GEN-12) -----------------------------------------------
#
# Derived from the domain stream contract (design §5) and C1 Done-when: the
# deterministic adapter implements ``generate_stream`` as one full-text delta then
# exactly one AnswerCompleted (always last, authoritative — equal to the buffered
# ``generate`` result); the stream is deterministic; and the adapter plus the
# generation fake structurally satisfy the port Protocol.


@_MODES
def test_stream_yields_full_text_delta_then_one_authoritative_completed(mode: str) -> None:
    adapter = DeterministicGenerationAdapter()
    evidence = [_evidence("alpha"), _evidence("beta")]

    events = list(_generate_stream(adapter, mode, evidence))

    # The full extractive text arrives as a single delta, then exactly one
    # AnswerCompleted, always last.
    deltas = [e for e in events if isinstance(e, AnswerTextDelta)]
    completed = [e for e in events if isinstance(e, AnswerCompleted)]
    assert deltas == [AnswerTextDelta(text="alpha\n\nbeta")]
    assert len(completed) == 1
    assert isinstance(events[-1], AnswerCompleted)
    # The completed event's answer is authoritative — identical to the buffered path.
    assert events[-1].answer == _generate(adapter, mode, evidence)
    assert events[-1].answer.text == "alpha\n\nbeta"
    assert events[-1].answer.found is True


@_MODES
def test_stream_is_deterministic(mode: str) -> None:
    adapter = DeterministicGenerationAdapter()
    evidence = [_evidence("alpha")]

    first = list(_generate_stream(adapter, mode, evidence))
    second = list(_generate_stream(adapter, mode, evidence))

    assert first == second


def test_deterministic_adapter_conforms_to_the_port_protocol() -> None:
    # GEN-12: the runtime-checkable port includes ``generate_stream``; the
    # deterministic adapter satisfies it structurally.
    assert isinstance(DeterministicGenerationAdapter(), GenerationPort)


def test_generation_fake_conforms_to_the_port_protocol() -> None:
    from tests.fakes import FakeAnswerGeneration

    assert isinstance(FakeAnswerGeneration(), GenerationPort)
