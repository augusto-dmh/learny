"""Deterministic, network-free generation adapter (ADR-0007/0009).

The default generator (AD-024/AD-032, mirror of the embedding adapter's AD-019):
pure Python, no network, no provider SDK. It composes an extractive answer from
the retrieved evidence's own snippets — the top ``_MAX_SNIPPETS`` in retrieval
rank order, joined by blank lines — and cites exactly those chunks, so the result
is grounded by construction. Same evidence → identical result (deterministic),
keeping golden-fixture answers stable. One adapter serves both modes: the
``message``, ``mode``, ``target_section_path``, and ``history`` do not shape the
deterministic prose, which draws only on the scoped evidence, so an answer turn
and a teach turn over the same evidence read alike.

Swapping in a real provider later is an adapter change behind the port, never a
domain change (ADR-0007/0009).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence

from app.domain.entities import (
    AnswerCompleted,
    AnswerStreamEvent,
    AnswerTextDelta,
    Evidence,
    GeneratedAnswer,
    HistoryTurn,
)

# Model identity surfaced on every result's diagnostics (QA-04/TEACH-24);
# distinguishes this extractive default from a future provider adapter.
_MODEL = "local-extractive"

# How many top-ranked snippets the extractive answer draws on. Adapter-local
# prompt-shaping detail, not product configuration (design §Tech Decisions).
_MAX_SNIPPETS = 3


def _extractive_answer(evidence: Sequence[Evidence], *, model: str) -> GeneratedAnswer:
    """Compose a grounded answer from the top evidence snippets, citing those chunks.

    Empty evidence → ``found=False`` empty result (defensive; the services
    short-circuit before calling a generator). Otherwise the answer is the top
    ``min(_MAX_SNIPPETS, len(evidence))`` snippets in retrieval order joined by
    blank lines, citing exactly those chunk ids, ``found=True``. Both modes compose
    prose through this one helper, as they always have.
    """
    if not evidence:
        return GeneratedAnswer(text="", cited_chunk_ids=(), model=model, found=False)
    selected = list(evidence[:_MAX_SNIPPETS])
    text = "\n\n".join(item.snippet for item in selected)
    cited = tuple(item.chunk_id for item in selected)
    return GeneratedAnswer(text=text, cited_chunk_ids=cited, model=model, found=True)


def _extractive_stream(evidence: Sequence[Evidence], *, model: str) -> Iterator[AnswerStreamEvent]:
    """Stream the extractive answer as one full-text delta then the completed event.

    Trivially chunked (the whole extractive text in a single delta) so the
    streaming surface is provider-independent: the deterministic path drives the
    same event contract the Anthropic adapter does (design §5). The completed event
    carries the authoritative :class:`GeneratedAnswer`. An empty/not-found answer
    (no evidence — the services short-circuit before this runs) yields no text
    delta, only the completed event.
    """
    answer = _extractive_answer(evidence, model=model)
    if answer.text:
        yield AnswerTextDelta(text=answer.text)
    yield AnswerCompleted(answer=answer)


class DeterministicGenerationAdapter:
    """``GenerationPort`` implementation — extractive, evidence-only.

    Needs no provider client: constructed with no arguments and makes no network
    call, so both the answer and the teach path are testable offline (AD-024). The
    ``mode``, ``target_section_path``, and prior ``history`` are accepted and do not
    shape the prose — it is composed solely from the scoped evidence, so a turn's
    output is exactly what it was before the ports converged, and before
    conversations carried history at all. A real conversational adapter dispatches
    on ``mode`` behind this same port.
    """

    # Stable model identity, readable without a ``generate`` call so the turn
    # service can surface it on the not-found-on-empty-evidence response where the
    # port is deliberately not invoked (QA-04/QA-13, TEACH-11/TEACH-24).
    model = _MODEL

    def generate(
        self,
        *,
        message: str,
        mode: str,
        evidence: Sequence[Evidence],
        history: Sequence[HistoryTurn] = (),
        target_section_path: tuple[str, ...] | None = None,
        tutor_phase: str | None = None,
        hint_level: str | None = None,
    ) -> GeneratedAnswer:
        """Compose a response from the top evidence snippets, citing those chunks."""
        return _extractive_answer(evidence, model=self.model)

    def generate_stream(
        self,
        *,
        message: str,
        mode: str,
        evidence: Sequence[Evidence],
        history: Sequence[HistoryTurn] = (),
        target_section_path: tuple[str, ...] | None = None,
        tutor_phase: str | None = None,
        hint_level: str | None = None,
    ) -> Iterator[AnswerStreamEvent]:
        """Stream the extractive response (one full-text delta, then completed)."""
        return _extractive_stream(evidence, model=self.model)
