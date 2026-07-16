"""Cited question-answering service (design §AskQuestion).

Framework-free orchestration of the answer path: ownership → readiness →
retrieve → short-circuit on empty → generate → grounding guard → result. It
composes the Phase-6 ``RetrieveEvidence`` service and the Learny-owned
``AnswerGenerationPort``; the grounding invariant (ADR-0003 / AD-027) lives here
once so it holds for every future adapter, not per-adapter goodwill. No FastAPI /
SQLAlchemy / provider-SDK type crosses this boundary (ADR-0007/0009).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from uuid import UUID

from app.application.errors import AnswerGenerationFailed, SourceNotReady
from app.application.grounding import ground
from app.application.identity import AuthorizeOwnership
from app.application.ingestion import SOURCE_STATUS_READY, authorized_source
from app.application.retrieval import RetrieveEvidence
from app.application.streaming import (
    AskStreamEvent,
    StreamAnswer,
    hold_back_deltas,
)
from app.domain.entities import Evidence, QuestionAnswer, User
from app.domain.ports import AnswerGenerationPort, SourceRepository

logger = logging.getLogger(__name__)

# ``QuestionAnswer.status`` vocabulary (design §Data/DTOs). ``answered`` carries a
# grounded citation set; ``not_found_in_source`` is the explicit, first-class
# "the source cannot support this" product outcome (ADR-0003 / D-3).
_ANSWERED = "answered"
_NOT_FOUND_IN_SOURCE = "not_found_in_source"


class AskQuestion:
    """Answer an owner's question against a ready source with grounded citations.

    Ownership is enforced first via ``authorized_source`` (reused from ingestion):
    a missing source and a non-owner collapse to ``SourceNotFound`` so existence
    is never disclosed. A source whose ``status != "ready"`` raises
    ``SourceNotReady`` before any retrieval or generation runs (QA-08). Otherwise
    the Phase-6 ``RetrieveEvidence`` service runs with the server-controlled
    ``evidence_top_k``; empty evidence short-circuits to ``not_found_in_source``
    without invoking the generation port (QA-13). The port's answer is then
    guarded — ``found`` flag, non-blank text, and a grounding filter that keeps
    only citations referencing retrieved evidence, in evidence-rank order and
    inherently deduped (QA-14..16, QA-02/03) — and any port exception becomes an
    ``AnswerGenerationFailed`` (QA-17). Exactly one content-free log line records
    each completion (QA-12).
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        authorize: AuthorizeOwnership,
        retrieve: RetrieveEvidence,
        generation: AnswerGenerationPort,
        evidence_top_k: int,
    ) -> None:
        self._sources = sources
        self._authorize = authorize
        self._retrieve = retrieve
        self._generation = generation
        self._evidence_top_k = evidence_top_k

    def __call__(
        self, *, user: User, source_id: UUID, question: str
    ) -> QuestionAnswer:
        source = authorized_source(
            user=user,
            source_id=source_id,
            sources=self._sources,
            authorize=self._authorize,
        )
        if source.status != SOURCE_STATUS_READY:
            # Guard before retrieval/generation so neither runs (QA-08).
            raise SourceNotReady("Source is not ready for questions.")

        evidence = self._retrieve(
            user=user,
            source_id=source_id,
            query=question,
            top_k=self._evidence_top_k,
        )
        result = self._answer(question=question, evidence=evidence)
        # One content-free lifecycle log per completion — never the question or
        # answer text (QA-12).
        logger.info(
            "qa completed outcome=%s source_id=%s evidence_count=%s model=%s",
            result.status,
            source_id,
            result.evidence_count,
            result.model,
        )
        return result

    def stream(
        self, *, user: User, source_id: UUID, question: str
    ) -> Iterator[AskStreamEvent]:
        """Answer incrementally: the same guards + grounding as ``__call__``, streamed.

        The ownership, readiness, retrieval and empty-evidence checks run **eagerly**
        (before this returns), so the four HTTP error outcomes (404/409, plus the
        empty short-circuit) surface as plain HTTP before any SSE bytes are sent — the
        returned iterator yields only stream events. Non-empty evidence drives the
        generation port's stream through the sentinel hold-back and the shared
        grounding guard; the terminal :class:`~app.application.streaming.StreamAnswer`
        carries the identical :class:`QuestionAnswer` the buffered path returns. A port
        failure surfaces as ``AnswerGenerationFailed`` from within the stream (QA-17).
        """
        source = authorized_source(
            user=user,
            source_id=source_id,
            sources=self._sources,
            authorize=self._authorize,
        )
        if source.status != SOURCE_STATUS_READY:
            raise SourceNotReady("Source is not ready for questions.")

        evidence = self._retrieve(
            user=user,
            source_id=source_id,
            query=question,
            top_k=self._evidence_top_k,
        )
        return self._answer_stream(question=question, evidence=evidence)

    def _answer_stream(
        self, *, question: str, evidence: list[Evidence]
    ) -> Iterator[AskStreamEvent]:
        evidence_count = len(evidence)
        if not evidence:
            # No supporting evidence → not found; the port is never invoked (QA-13).
            yield StreamAnswer(
                self._not_found(evidence_count, self._generation.model)
            )
            return

        stream = self._generation.generate_stream(
            question=question, evidence=evidence
        )
        # Hold-back yields presentable deltas and returns the authoritative answer.
        answer = yield from hold_back_deltas(stream)

        grounded = ground(answer, evidence)
        if grounded is None:
            result = self._not_found(evidence_count, answer.model)
        else:
            text, citations = grounded
            result = QuestionAnswer(
                status=_ANSWERED,
                text=text,
                citations=tuple(citations),
                evidence_count=evidence_count,
                model=answer.model,
            )
        yield StreamAnswer(result)

    def _answer(
        self, *, question: str, evidence: list[Evidence]
    ) -> QuestionAnswer:
        evidence_count = len(evidence)
        if not evidence:
            # No supporting evidence → not found; the port is never invoked
            # (QA-13). Model identity comes from the port, not a generate call.
            return self._not_found(evidence_count, self._generation.model)

        try:
            generated = self._generation.generate(
                question=question, evidence=evidence
            )
        except Exception as exc:  # any port failure maps to 502 (QA-17)
            # Learny-owned failure with a generic message; the web layer returns a
            # body that leaks no provider/internal detail (QA-17).
            raise AnswerGenerationFailed("Answer generation failed.") from exc

        # Grounding guard (AD-027), shared with the teaching turn path: keeps only
        # citations referencing retrieved evidence, in evidence-rank order and
        # deduped, or None when found == false (QA-14), text is blank (QA-16), or
        # no citation survives grounding (QA-15) → the explicit not-found outcome.
        grounded = ground(generated, evidence)
        if grounded is None:
            return self._not_found(evidence_count, generated.model)

        text, citations = grounded
        return QuestionAnswer(
            status=_ANSWERED,
            text=text,
            citations=tuple(citations),
            evidence_count=evidence_count,
            model=generated.model,
        )

    @staticmethod
    def _not_found(evidence_count: int, model: str) -> QuestionAnswer:
        return QuestionAnswer(
            status=_NOT_FOUND_IN_SOURCE,
            text="",
            citations=(),
            evidence_count=evidence_count,
            model=model,
        )
