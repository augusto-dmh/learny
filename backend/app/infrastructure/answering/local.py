"""Deterministic, network-free answer/teaching adapters (ADR-0007/0009).

The default generators (AD-024/AD-032, mirror of the embedding adapter's AD-019):
pure Python, no network, no provider SDK. Both compose an extractive answer from
the retrieved evidence's own snippets — the top ``_MAX_SNIPPETS`` in retrieval
rank order, joined by blank lines — and cite exactly those chunks, so the result
is grounded by construction. Same evidence → identical result (deterministic),
keeping golden-fixture answers stable. ``DeterministicAnswerAdapter`` serves the
Q&A path (``AnswerGenerationPort``); ``DeterministicTeachingAdapter`` serves the
teaching turn path (``TeachingGenerationPort``) and ignores the message, target,
and history for its deterministic prose, drawing only on the scoped evidence.

Swapping in a real provider later is an adapter change behind the respective
port, never a domain change (ADR-0007/0009).
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


def _extractive_answer(
    evidence: Sequence[Evidence], *, model: str
) -> GeneratedAnswer:
    """Compose a grounded answer from the top evidence snippets, citing those chunks.

    Empty evidence → ``found=False`` empty result (defensive; the services
    short-circuit before calling a generator). Otherwise the answer is the top
    ``min(_MAX_SNIPPETS, len(evidence))`` snippets in retrieval order joined by
    blank lines, citing exactly those chunk ids, ``found=True``. Shared by both
    deterministic adapters so the answer and teaching paths compose prose
    identically (design §Components).
    """
    if not evidence:
        return GeneratedAnswer(
            text="", cited_chunk_ids=(), model=model, found=False
        )
    selected = list(evidence[:_MAX_SNIPPETS])
    text = "\n\n".join(item.snippet for item in selected)
    cited = tuple(item.chunk_id for item in selected)
    return GeneratedAnswer(
        text=text, cited_chunk_ids=cited, model=model, found=True
    )


def _extractive_stream(
    evidence: Sequence[Evidence], *, model: str
) -> Iterator[AnswerStreamEvent]:
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


class DeterministicAnswerAdapter:
    """``AnswerGenerationPort`` implementation — extractive, evidence-only.

    Needs no provider client: constructed with no arguments and makes no network
    call, so the answer path is testable offline (AD-024).
    """

    # Stable model identity, readable without a ``generate`` call so the Q&A
    # service can surface it on the not-found-on-empty-evidence response where the
    # port is deliberately not invoked (QA-04/QA-13).
    model = _MODEL

    def generate(
        self, *, question: str, evidence: Sequence[Evidence]
    ) -> GeneratedAnswer:
        """Compose an answer from the top evidence snippets, citing those chunks."""
        return _extractive_answer(evidence, model=self.model)

    def generate_stream(
        self, *, question: str, evidence: Sequence[Evidence]
    ) -> Iterator[AnswerStreamEvent]:
        """Stream the extractive answer (one full-text delta, then completed)."""
        return _extractive_stream(evidence, model=self.model)


class DeterministicTeachingAdapter:
    """``TeachingGenerationPort`` implementation — extractive, evidence-only (AD-032).

    Mirrors :class:`DeterministicAnswerAdapter` for the teaching turn path: no
    provider client, no network, so the turn path is testable offline. The
    ``message``, ``target_section_path``, and bounded ``history`` do not shape the
    deterministic prose — the response is composed solely from the scoped evidence
    snippets, so it is grounded by construction and golden-fixture stable. A real
    conversational adapter will use those inputs behind this same port.
    """

    # Same identity as the Q&A default (same strategy family); a provider ADR will
    # introduce distinct ids. Readable without a ``generate`` call so the turn
    # service reports it on the empty-evidence not-found path (TEACH-11/TEACH-24).
    model = _MODEL

    def generate(
        self,
        *,
        message: str,
        target_section_path: tuple[str, ...],
        history: Sequence[HistoryTurn],
        evidence: Sequence[Evidence],
    ) -> GeneratedAnswer:
        """Compose a teaching response from the top scoped evidence snippets."""
        return _extractive_answer(evidence, model=self.model)

    def generate_stream(
        self,
        *,
        message: str,
        target_section_path: tuple[str, ...],
        history: Sequence[HistoryTurn],
        evidence: Sequence[Evidence],
    ) -> Iterator[AnswerStreamEvent]:
        """Stream the extractive teaching response (one full-text delta, then completed)."""
        return _extractive_stream(evidence, model=self.model)
