"""End-of-section checkpoint use cases (v8 ``section-checkpoint-and-calibration``).

A checkpoint is the optional loop a learner takes after finishing one section:
a prediction of how much they can recall, then up to three unaided recalls of the
section's cards (each with a one-tap confidence), then one explanation of the
section from memory. Explain-back feedback quotes the passage and never grades it.
The learner self-assesses, and every graded attempt goes through
:class:`~app.application.reviews.SubmitReview`, so FSRS schedules what was missed.

Framework-free (ADR-007/009). The invariants enforced here rather than trusted
to the client:

- No answer before the attempt. Starting returns questions only. A recall's
  answer is returned by the call that stores its response. "Just explain" is the
  only way to see the passage early, and it marks the attempt assisted.
- Assistance is decided server-side. A recall grade is unassisted (there is no
  hint path). An explanation grade is assisted iff the passage was revealed
  before the response.
- Once-only steps. Respond and grade are conditional writes, so a retry or a race
  cannot store a second response or append a second review-log row.

Explain-back runs through the existing :class:`~app.domain.ports.GenerationPort`
in answer mode, with a frozen application-owned message. Its evidence is the
section's own chunks, ordered least-covered-by-the-explanation first, which makes
the deterministic extractive adapter quote what the learner left out. Whatever
the port does, the learner always gets a passage: a not-found, a raise or an
ungrounded reply falls back to quoting the least-covered chunk.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from uuid import UUID

from app.application.budget import KIND_GENERATION, DailyBudget
from app.application.errors import (
    CheckpointAttemptConflict,
    CheckpointAttemptNotFound,
    CorpusNotFound,
    InvalidCheckpointRating,
    QuizItemNotFound,
)
from app.application.grounding import ground, ground_spans
from app.application.identity import AuthorizeOwnership
from app.application.ingestion import readable_source
from app.application.quiz_qc import content_key, normalize_text
from app.application.reviews import ReviewedSchedule, SubmitReview
from app.domain.entities import (
    CHECKPOINT_CARD_QUESTION,
    MODE_ANSWER,
    CalibrationLevel,
    CheckpointAttempt,
    CheckpointAttemptKind,
    Evidence,
    FeedbackCitation,
    GeneratedAnswer,
    OwnedAttempt,
    QuizItem,
    QuizItemOrigin,
    QuizItemStatus,
    QuizItemType,
    QuizSection,
    SectionCheckpoint,
    User,
)
from app.domain.ports import (
    CheckpointRepository,
    Clock,
    GenerationPort,
    QuizItemRepository,
    SchedulingPort,
    SourceRepository,
)

logger = logging.getLogger(__name__)

# How many of the section's cards a checkpoint recalls (the research template asks
# for 3–5 retrieval items; three keeps the loop short enough to stay optional).
MAX_RECALL_ATTEMPTS = 3
# How many of the section's chunks explain-back hands the generation port.
MAX_EXPLAIN_EVIDENCE = 6
# Upper bound on a typed response or explanation, in characters.
MAX_RESPONSE_CHARS = 4000
# The explanation self-assessment scale: Missed it / Partly / Got it, which are
# FSRS Again / Hard / Good. Easy is not offered for an explanation.
MAX_EXPLAIN_RATING = 3

# The frozen user turn explain-back sends through the answer port. The system
# prompt stays the answer prompt, byte-stable and cacheable (ADR-0020); this
# message carries the task. It asks for formative feedback and forbids a grade
# (MEC rates automatic grading high-risk), and the evidence it is answered from
# is the section itself.
EXPLAIN_BACK_MESSAGE = (
    'I just finished reading the section "{title}" and explained it from memory, '
    "without looking:\n\n"
    "<explanation>\n{explanation}\n</explanation>\n\n"
    "Give me brief, encouraging feedback on my explanation. Say in one sentence what "
    "it captured, then quote the passages of this section that it left out or got "
    "wrong, citing each one. Do not grade or score it, and do not say whether it "
    "passed."
)
# Shown when the learner gets passages and no feedback prose: a blank explanation,
# a provider that failed or answered without a grounded citation, or an extractive
# reply that only restates its passages.
FALLBACK_FEEDBACK = "Compare your explanation with this passage from the section."
EXTRACTIVE_FEEDBACK = "These passages from the section are worth comparing with your explanation."

_WORD = re.compile(r"\w+")


@dataclass(frozen=True)
class StartedCheckpoint:
    """A new checkpoint and its attempts. Each recall carries its question only."""

    checkpoint: SectionCheckpoint
    attempts: tuple[tuple[CheckpointAttempt, str], ...]


@dataclass(frozen=True)
class RecallReveal:
    """What a recall response unlocks: the card's answer and its citation."""

    answer: str
    source_excerpt: str
    anchor: str
    section_path: tuple[str, ...]


@dataclass(frozen=True)
class ExplainFeedback:
    """Formative feedback on an explanation: prose plus the passages it quotes."""

    feedback: str
    citations: tuple[FeedbackCitation, ...]


@dataclass(frozen=True)
class RevealedPassage:
    """The passage "Just explain" shows, which marks the attempt assisted."""

    passage: str
    anchor: str
    section_path: tuple[str, ...]


@dataclass(frozen=True)
class GradedAttempt:
    """A graded attempt: the card it reviewed and that card's new schedule."""

    quiz_item_id: UUID
    reviewed: ReviewedSchedule


def _words(text: str) -> set[str]:
    return {word for word in _WORD.findall(text.casefold()) if len(word) > 2}


def least_covered_first(
    chunks: Sequence[tuple[UUID, str]], response: str
) -> list[tuple[UUID, str]]:
    """Order a section's chunks by how little of each the response mentions.

    Coverage is the share of a chunk's words (longer than two letters,
    case-folded) that also appear in the response. The least-covered chunk comes
    first, and ties keep reading order, so a blank response yields reading order.
    """
    said = _words(response)

    def coverage(indexed: tuple[int, tuple[UUID, str]]) -> tuple[float, int]:
        index, (_, text) = indexed
        words = _words(text)
        share = len(words & said) / len(words) if words else 1.0
        return share, index

    return [chunk for _, chunk in sorted(enumerate(chunks), key=coverage)]


def _evidence(
    section: QuizSection, source_id: UUID, chunks: Sequence[tuple[UUID, str]]
) -> list[Evidence]:
    return [
        Evidence(
            chunk_id=chunk_id,
            source_id=source_id,
            section_path=section.section_path,
            anchor=section.anchor,
            page_span=None,
            snippet=text,
            score=0.0,
        )
        for chunk_id, text in chunks
    ]


def _owned(checkpoints: CheckpointRepository, user: User, attempt_id: UUID) -> OwnedAttempt:
    owned = checkpoints.get_attempt(attempt_id)
    if owned is None or owned.checkpoint.user_id != user.id:
        raise CheckpointAttemptNotFound("Checkpoint attempt not found.")
    return owned


def _section(items: QuizItemRepository, checkpoint: SectionCheckpoint) -> QuizSection:
    section = items.section_for_anchor(checkpoint.source_id, checkpoint.anchor)
    if section is None or not section.chunks:
        raise CorpusNotFound("No section for this anchor.")
    return section


class StartCheckpoint:
    """Begin a checkpoint on one section of a source the caller can read.

    A missing or unreadable source, and an anchor that resolves to no section, are
    404s that persist nothing. The section's canonical anchor is snapshotted. The
    recall attempts are the caller's own active, unflagged, non-checkpoint cards
    on that anchor, due first and at most three, followed by exactly one explain
    attempt.
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        items: QuizItemRepository,
        checkpoints: CheckpointRepository,
        authorize: AuthorizeOwnership,
        clock: Clock,
        ids: Callable[[], UUID],
    ) -> None:
        self._sources = sources
        self._items = items
        self._checkpoints = checkpoints
        self._authorize = authorize
        self._clock = clock
        self._ids = ids

    def __call__(
        self, *, user: User, source_id: UUID, anchor: str, prediction: int | None
    ) -> StartedCheckpoint:
        readable_source(
            user=user, source_id=source_id, sources=self._sources, authorize=self._authorize
        )
        section = self._items.section_for_anchor(source_id, anchor)
        if section is None:
            raise CorpusNotFound("No section for this anchor.")

        checkpoint = SectionCheckpoint(
            id=self._ids(),
            user_id=user.id,
            source_id=source_id,
            anchor=section.anchor,
            section_title=section.title,
            prediction=prediction,
            created_at=self._clock.now(),
        )
        cards = self._items.recall_cards(
            user.id, source_id, section.anchor, limit=MAX_RECALL_ATTEMPTS
        )
        attempts: list[tuple[CheckpointAttempt, str]] = [
            (
                CheckpointAttempt(
                    id=self._ids(),
                    checkpoint_id=checkpoint.id,
                    kind=CheckpointAttemptKind.RECALL,
                    position=position,
                    quiz_item_id=card.id,
                ),
                card.question,
            )
            for position, card in enumerate(cards)
        ]
        attempts.append(
            (
                CheckpointAttempt(
                    id=self._ids(),
                    checkpoint_id=checkpoint.id,
                    kind=CheckpointAttemptKind.EXPLAIN,
                    position=len(cards),
                ),
                CHECKPOINT_CARD_QUESTION.format(title=section.title),
            )
        )
        self._checkpoints.add(checkpoint, [attempt for attempt, _ in attempts])
        return StartedCheckpoint(checkpoint=checkpoint, attempts=tuple(attempts))


class RevealPassage:
    """ "Just explain": show the section's opening passage before the explanation.

    Only an ``explain`` attempt with no response yet can be revealed. Revealing
    again keeps the first stamp. Anything else is a 409 that changes nothing. A
    revealed attempt's grade is recorded as assisted.
    """

    def __init__(
        self,
        *,
        checkpoints: CheckpointRepository,
        items: QuizItemRepository,
        clock: Clock,
    ) -> None:
        self._checkpoints = checkpoints
        self._items = items
        self._clock = clock

    def __call__(self, *, user: User, attempt_id: UUID) -> RevealedPassage:
        owned = _owned(self._checkpoints, user, attempt_id)
        if (
            owned.attempt.kind != CheckpointAttemptKind.EXPLAIN
            or owned.attempt.responded_at is not None
        ):
            raise CheckpointAttemptConflict("This attempt cannot be revealed.")
        section = _section(self._items, owned.checkpoint)
        if not self._checkpoints.mark_revealed(attempt_id, self._clock.now()):
            raise CheckpointAttemptConflict("This attempt cannot be revealed.")
        return RevealedPassage(
            passage=section.chunks[0][1],
            anchor=section.anchor,
            section_path=section.section_path,
        )


class RespondToAttempt:
    """Store an attempt's response and confidence once, then show what it unlocks.

    A recall response returns the card's answer and citation. An explain response
    returns formative feedback that quotes the section. A blank explanation
    spends nothing, and any port failure falls back to the least-covered passage.
    Budget refusals (429, 503) happen before anything is stored. A second
    response to the same attempt is a 409 that keeps the first.
    """

    def __init__(
        self,
        *,
        checkpoints: CheckpointRepository,
        items: QuizItemRepository,
        generation: GenerationPort,
        clock: Clock,
        budget: DailyBudget | None = None,
    ) -> None:
        self._checkpoints = checkpoints
        self._items = items
        self._generation = generation
        self._clock = clock
        self._budget = budget

    def __call__(
        self,
        *,
        user: User,
        attempt_id: UUID,
        response: str,
        confidence: int,
        response_language: str | None = None,
    ) -> RecallReveal | ExplainFeedback:
        owned = _owned(self._checkpoints, user, attempt_id)
        if owned.attempt.responded_at is not None:
            raise CheckpointAttemptConflict("This attempt already has a response.")
        if owned.attempt.kind == CheckpointAttemptKind.RECALL:
            return self._recall(owned, response, confidence)
        return self._explain(user, owned, response, confidence, response_language)

    def _claim(
        self,
        attempt_id: UUID,
        response: str,
        confidence: int,
        feedback: ExplainFeedback | None = None,
    ) -> None:
        claimed = self._checkpoints.claim_response(
            attempt_id,
            response=response,
            confidence=confidence,
            feedback=None if feedback is None else feedback.feedback,
            feedback_citations=() if feedback is None else feedback.citations,
            now=self._clock.now(),
        )
        if not claimed:
            raise CheckpointAttemptConflict("This attempt already has a response.")

    def _store(self, attempt_id: UUID, feedback: ExplainFeedback) -> None:
        self._checkpoints.store_feedback(
            attempt_id, feedback=feedback.feedback, feedback_citations=feedback.citations
        )

    def _recall(self, owned: OwnedAttempt, response: str, confidence: int) -> RecallReveal:
        item_id = owned.attempt.quiz_item_id
        item = self._items.get_by_id(item_id) if item_id is not None else None
        if item is None:
            raise QuizItemNotFound("Quiz item not found.")
        self._claim(owned.attempt.id, response, confidence)
        return RecallReveal(
            answer=item.answer,
            source_excerpt=item.source_excerpt,
            anchor=item.anchor,
            section_path=item.section_path,
        )

    def _explain(
        self,
        user: User,
        owned: OwnedAttempt,
        response: str,
        confidence: int,
        response_language: str | None,
    ) -> ExplainFeedback:
        checkpoint = owned.checkpoint
        section = _section(self._items, checkpoint)
        ordered = least_covered_first(section.chunks, response)[:MAX_EXPLAIN_EVIDENCE]
        evidence = _evidence(section, checkpoint.source_id, ordered)
        fallback = ExplainFeedback(
            feedback=FALLBACK_FEEDBACK,
            citations=(
                FeedbackCitation(
                    anchor=section.anchor,
                    section_path=section.section_path,
                    quote=evidence[0].snippet,
                ),
            ),
        )
        if not response.strip():
            self._claim(owned.attempt.id, response, confidence, fallback)
            return fallback

        if self._budget is not None:
            self._budget.assert_generation(user.id, kind=KIND_GENERATION)
        # Claim before paying for the provider. The conditional UPDATE holds the
        # attempt's row lock until this request commits, so a concurrent second
        # response waits, then matches nothing and is refused without generating.
        self._claim(owned.attempt.id, response, confidence)
        message = EXPLAIN_BACK_MESSAGE.format(
            title=checkpoint.section_title, explanation=response.strip()
        )
        try:
            generated = self._generation.generate(
                message=message,
                mode=MODE_ANSWER,
                evidence=evidence,
                response_language=response_language,
            )
        except Exception:  # noqa: BLE001 - any port failure still owes the learner a passage
            logger.warning(
                "explain-back generation failed; quoting the section instead",
                extra={"attempt_id": str(owned.attempt.id)},
                exc_info=True,
            )
            self._store(owned.attempt.id, fallback)
            return fallback

        feedback = _feedback(generated, evidence) or fallback
        self._store(owned.attempt.id, feedback)
        if self._budget is not None:
            self._budget.record(
                user.id,
                usd_micros=self._budget.usage_micros(generated.usage, generated.profile_id),
                kind=KIND_GENERATION,
            )
        return feedback


def _feedback(generated: GeneratedAnswer, evidence: list[Evidence]) -> ExplainFeedback | None:
    """Ground the port's reply into feedback, or ``None`` when nothing survives.

    Each surviving citation quotes the sentence the provider cited when it
    reported one, else the whole chunk. A reply that only restates its passages,
    which is what the extractive adapter returns, carries no feedback of its own,
    so it gets a fixed lead line instead of printing the quotes twice.
    """
    grounded = ground(generated, evidence)
    if grounded is None:
        return None
    text, citations = grounded
    spans = {span.chunk_id: span.quote for span in ground_spans(generated, citations)}
    quotes = tuple(
        FeedbackCitation(
            anchor=item.anchor,
            section_path=item.section_path,
            quote=spans.get(item.chunk_id, item.snippet),
        )
        for item in citations
    )
    restated = "\n\n".join(item.snippet for item in citations)
    prose = EXTRACTIVE_FEEDBACK if text.strip() == restated.strip() else text
    return ExplainFeedback(feedback=prose, citations=quotes)


class GradeAttempt:
    """Self-assess a responded attempt once and schedule it through FSRS.

    A recall attempt reviews its card with rating 1–4, unassisted. An explain
    attempt takes 1–3 (Missed it / Partly / Got it) and reviews the caller's
    ``checkpoint`` card for that section. When the caller has no active one,
    the card is minted first: owned by the caller, its answer the first passage
    the feedback quoted. It is assisted iff "Just explain" was used before the
    response. The confidence is the one stored with the response, so the client
    cannot change it after seeing the answer.
    """

    def __init__(
        self,
        *,
        checkpoints: CheckpointRepository,
        items: QuizItemRepository,
        submit_review: SubmitReview,
        scheduling: SchedulingPort,
        generation_model: str,
        clock: Clock,
        ids: Callable[[], UUID],
        max_card_chars: int,
    ) -> None:
        self._checkpoints = checkpoints
        self._items = items
        self._submit_review = submit_review
        self._scheduling = scheduling
        self._generation_model = generation_model
        self._clock = clock
        self._ids = ids
        self._max_card_chars = max_card_chars

    def __call__(
        self, *, user: User, attempt_id: UUID, rating: int, client_tz: str | None = None
    ) -> GradedAttempt:
        owned = _owned(self._checkpoints, user, attempt_id)
        attempt = owned.attempt
        explain = attempt.kind == CheckpointAttemptKind.EXPLAIN
        if explain and rating > MAX_EXPLAIN_RATING:
            raise InvalidCheckpointRating("An explanation is rated 1 to 3.")
        # A recall whose card was deleted since the start is refused before the
        # claim, so it never leaves a graded stamp with no review behind it.
        if not explain and attempt.quiz_item_id is None:
            raise QuizItemNotFound("Quiz item not found.")
        if not self._checkpoints.claim_grade(attempt.id, self._clock.now()):
            raise CheckpointAttemptConflict("This attempt cannot be graded now.")

        if explain:
            item_id = self._checkpoint_card(user, owned).id
            assisted = attempt.revealed_at is not None
        else:
            assert attempt.quiz_item_id is not None  # refused above
            item_id = attempt.quiz_item_id
            assisted = False
        reviewed = self._submit_review(
            user=user,
            item_id=item_id,
            rating=rating,
            assisted=assisted,
            confidence=attempt.confidence,
            client_tz=client_tz,
        )
        if reviewed.log_id is None:
            # SubmitReview always appends a log row; without its id the attempt
            # could not be joined to its review, so refuse rather than drop the link.
            raise RuntimeError("A graded review returned no review-log id.")
        self._checkpoints.link_grade(
            attempt.id, quiz_item_id=item_id, review_log_id=reviewed.log_id
        )
        return GradedAttempt(quiz_item_id=item_id, reviewed=reviewed)

    def _checkpoint_card(self, user: User, owned: OwnedAttempt) -> QuizItem:
        checkpoint = owned.checkpoint
        existing = self._items.active_checkpoint_card(
            user.id, checkpoint.source_id, checkpoint.anchor
        )
        if existing is not None:
            return existing

        section = self._items.section_for_anchor(checkpoint.source_id, checkpoint.anchor)
        quoted = owned.attempt.feedback_citations
        if quoted:
            passage = quoted[0].quote
        elif section is not None and section.chunks:
            passage = section.chunks[0][1]
        else:
            raise CorpusNotFound("No section for this anchor.")
        passage = passage[: self._max_card_chars]
        question = CHECKPOINT_CARD_QUESTION.format(title=checkpoint.section_title)
        now = self._clock.now()
        item = QuizItem(
            id=self._ids(),
            source_id=checkpoint.source_id,
            user_id=user.id,
            origin=QuizItemOrigin.CHECKPOINT,
            item_type=QuizItemType.FREE_RECALL,
            question=question,
            answer=passage,
            section_path=section.section_path if section is not None else (),
            anchor=checkpoint.anchor,
            source_excerpt=passage,
            chunk_hash=hashlib.sha256(normalize_text(passage).encode("utf-8")).hexdigest(),
            content_key=content_key(QuizItemType.FREE_RECALL, question, passage),
            status=QuizItemStatus.ACTIVE,
            generation_meta={"model": self._generation_model},
            created_at=now,
            updated_at=now,
        )
        self._items.upsert(item, embedding=None)
        self._items.create_scheduling(item.id, self._scheduling.initial())
        return item


class SourceCalibration:
    """Per-book calibration for one readable source (S7).

    For each of the learner's three confidence levels, how many of their
    unaided, not-undone grades carried that confidence on this book's cards and
    how many of those were recalled (FSRS pass, rating 2 or more). A missing or
    unreadable source is the same 404 as everywhere else; a readable source
    always answers with exactly three rows, zero-filled when a level has no
    attempts. Rows are never another learner's: the query joins the caller's
    own log rows to their own cards on this source.
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        items: QuizItemRepository,
        authorize: AuthorizeOwnership,
    ) -> None:
        self._sources = sources
        self._items = items
        self._authorize = authorize

    def __call__(self, *, user: User, source_id: UUID) -> list[CalibrationLevel]:
        readable_source(
            user=user, source_id=source_id, sources=self._sources, authorize=self._authorize
        )
        return self._items.source_calibration(user.id, source_id)
