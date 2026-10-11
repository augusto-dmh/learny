"""Checkpoint use cases against Postgres, the real FSRS adapter and a fake port.

Each test pins one check from
``.specs/features/section-checkpoint-and-calibration/checks.md`` on persisted
state: which cards a checkpoint recalls, that a grade goes through FSRS with the
stored confidence, that assistance is decided by whether the passage was
revealed, and that explain-back always returns a quoted passage whatever the
generation port does.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, func, select

from app.application.budget import DailyBudget, TokenPrices
from app.application.checkpoints import (
    EXPLAIN_BACK_MESSAGE,
    GradeAttempt,
    RespondToAttempt,
    RevealPassage,
    StartCheckpoint,
)
from app.application.dates import local_day
from app.application.identity import AuthorizeOwnership
from app.application.reviews import SubmitReview
from app.domain.entities import (
    MODE_ANSWER,
    CheckpointAttemptKind,
    CitedSpan,
    GeneratedAnswer,
    QuizItemOrigin,
    QuizItemStatus,
    QuizItemType,
    TokenUsage,
    User,
)
from app.infrastructure.db.metadata import (
    checkpoint_attempts,
    quiz_items,
    review_log,
    section_checkpoints,
    study_days,
)
from app.infrastructure.db.repositories import (
    SqlAlchemyAiSpendDayRepository,
    SqlAlchemyCheckpointRepository,
    SqlAlchemyQuizItemRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyStudyDayRepository,
)
from app.infrastructure.scheduling.fsrs import FsrsSchedulingAdapter
from tests.checkpoint_seed import ANCHOR, CHUNKS, TITLE, add_card, add_corpus, add_source, add_user
from tests.conftest import requires_db
from tests.fakes import FakeAnswerGeneration, FakeClock

pytestmark = requires_db

_NOW = datetime(2026, 10, 2, 12, 0, 0, tzinfo=UTC)
_PRICES = TokenPrices(
    input_micros_per_million=1_000_000,
    output_micros_per_million=2_000_000,
    embed_micros_per_million=0,
)
_MAX_CARD_CHARS = 40


# --- wiring ---------------------------------------------------------------------


def _start(db_conn: Connection) -> StartCheckpoint:
    return StartCheckpoint(
        sources=SqlAlchemySourceRepository(db_conn),
        items=SqlAlchemyQuizItemRepository(db_conn),
        checkpoints=SqlAlchemyCheckpointRepository(db_conn),
        authorize=AuthorizeOwnership(),
        clock=FakeClock(_NOW),
        ids=uuid4,
    )


def _budget(db_conn: Connection, *, cap_micros: int = 1_000_000) -> DailyBudget:
    return DailyBudget(
        repo=SqlAlchemyAiSpendDayRepository(db_conn),
        clock=FakeClock(_NOW),
        daily_cap_micros=cap_micros,
        prices=_PRICES,
        ask_daily_cap=8,
        teach_start_daily_cap=1,
    )


def _respond(
    db_conn: Connection,
    generation: FakeAnswerGeneration | None = None,
    budget: DailyBudget | None = None,
) -> RespondToAttempt:
    return RespondToAttempt(
        checkpoints=SqlAlchemyCheckpointRepository(db_conn),
        items=SqlAlchemyQuizItemRepository(db_conn),
        generation=generation or FakeAnswerGeneration(error=AssertionError("not expected")),
        clock=FakeClock(_NOW),
        budget=budget,
    )


def _reveal(db_conn: Connection) -> RevealPassage:
    return RevealPassage(
        checkpoints=SqlAlchemyCheckpointRepository(db_conn),
        items=SqlAlchemyQuizItemRepository(db_conn),
        clock=FakeClock(_NOW),
    )


def _grade(db_conn: Connection) -> GradeAttempt:
    scheduling = FsrsSchedulingAdapter(fuzzing=False)
    return GradeAttempt(
        checkpoints=SqlAlchemyCheckpointRepository(db_conn),
        items=SqlAlchemyQuizItemRepository(db_conn),
        submit_review=SubmitReview(
            items=SqlAlchemyQuizItemRepository(db_conn),
            scheduling=scheduling,
            clock=FakeClock(_NOW),
            study_days=SqlAlchemyStudyDayRepository(db_conn),
        ),
        scheduling=scheduling,
        generation_model="local-extractive",
        clock=FakeClock(_NOW),
        ids=uuid4,
        max_card_chars=_MAX_CARD_CHARS,
    )


def _book(db_conn: Connection, *, is_sample: bool = False) -> tuple[User, UUID]:
    user = add_user(db_conn)
    owner = add_user(db_conn) if is_sample else user
    source_id = add_source(db_conn, owner.id, is_sample=is_sample)
    add_corpus(db_conn, source_id)
    return user, source_id


def _explain_attempt_id(started) -> UUID:  # noqa: ANN001
    return next(a.id for a, _ in started.attempts if a.kind == CheckpointAttemptKind.EXPLAIN)


def _log_rows(db_conn: Connection, item_id: UUID) -> list:
    return db_conn.execute(
        select(review_log.c.rating, review_log.c.confidence, review_log.c.assisted).where(
            review_log.c.quiz_item_id == item_id
        )
    ).all()


def _chunk_ids(db_conn: Connection, source_id: UUID) -> dict[str, UUID]:
    section = SqlAlchemyQuizItemRepository(db_conn).section_for_anchor(source_id, ANCHOR)
    return {text: chunk_id for chunk_id, text in section.chunks}


# --- C5, C6: which cards a checkpoint recalls -------------------------------------


def test_start_selects_due_first_owned_active_cards_on_anchor(db_conn: Connection) -> None:
    user, source_id = _book(db_conn)
    later = add_card(db_conn, source_id, due=_NOW - timedelta(hours=1))
    sooner = add_card(db_conn, source_id, due=_NOW - timedelta(days=2))
    add_card(db_conn, source_id, status=QuizItemStatus.STALE)
    add_card(db_conn, source_id, flagged=True)
    add_card(db_conn, source_id, anchor="ch2.xhtml")
    add_card(db_conn, source_id, user_id=user.id, origin=QuizItemOrigin.CHECKPOINT)
    stranger = add_user(db_conn)
    foreign_source = add_source(db_conn, stranger.id)
    add_corpus(db_conn, foreign_source)
    add_card(db_conn, foreign_source)
    # Another learner's card on this very source and anchor (a cloned card on a
    # shared book looks exactly like this): only the owner filter excludes it.
    add_card(db_conn, source_id, user_id=stranger.id, due=_NOW - timedelta(days=9))

    started = _start(db_conn)(user=user, source_id=source_id, anchor=ANCHOR, prediction=2)

    kinds = [(a.kind, a.quiz_item_id) for a, _ in started.attempts]
    assert kinds == [
        (CheckpointAttemptKind.RECALL, sooner.id),
        (CheckpointAttemptKind.RECALL, later.id),
        (CheckpointAttemptKind.EXPLAIN, None),
    ]
    stored = db_conn.execute(
        select(section_checkpoints.c.prediction, section_checkpoints.c.anchor).where(
            section_checkpoints.c.id == started.checkpoint.id
        )
    ).one()
    assert (stored.prediction, stored.anchor) == (2, ANCHOR)


def test_start_caps_recall_attempts_at_three(db_conn: Connection) -> None:
    user, source_id = _book(db_conn)
    cards = [add_card(db_conn, source_id, due=_NOW - timedelta(hours=n)) for n in range(1, 6)]

    started = _start(db_conn)(user=user, source_id=source_id, anchor=ANCHOR, prediction=None)

    recalls = [
        a.quiz_item_id for a, _ in started.attempts if a.kind == CheckpointAttemptKind.RECALL
    ]
    # Due ascending: the most overdue three (5h, 4h, 3h ago).
    assert recalls == [cards[4].id, cards[3].id, cards[2].id]
    assert [a.kind for a, _ in started.attempts][-1] == CheckpointAttemptKind.EXPLAIN
    assert len(started.attempts) == 4


def test_start_without_cards_has_only_explain(db_conn: Connection) -> None:
    user, source_id = _book(db_conn)

    started = _start(db_conn)(user=user, source_id=source_id, anchor=ANCHOR, prediction=1)

    assert [a.kind for a, _ in started.attempts] == [CheckpointAttemptKind.EXPLAIN]
    assert started.attempts[0][1] == f'Explain "{TITLE}" in your own words.'


# --- C14: a recall grade is an unassisted FSRS review with the stored confidence --


def test_grade_recall_reviews_card_with_confidence_unassisted(db_conn: Connection) -> None:
    user, source_id = _book(db_conn)
    card = add_card(db_conn, source_id)
    items = SqlAlchemyQuizItemRepository(db_conn)
    before = items.get_scheduling(card.id)
    started = _start(db_conn)(user=user, source_id=source_id, anchor=ANCHOR, prediction=None)
    attempt_id = started.attempts[0][0].id
    _respond(db_conn)(user=user, attempt_id=attempt_id, response="", confidence=2)

    graded = _grade(db_conn)(user=user, attempt_id=attempt_id, rating=1)

    expected, _ = FsrsSchedulingAdapter(fuzzing=False).review(before, 1, _NOW)
    assert items.get_scheduling(card.id) == expected
    assert graded.quiz_item_id == card.id
    assert [tuple(r) for r in _log_rows(db_conn, card.id)] == [(1, 2, False)]
    linked = db_conn.execute(
        select(checkpoint_attempts.c.review_log_id).where(checkpoint_attempts.c.id == attempt_id)
    ).scalar_one()
    log_id = db_conn.execute(
        select(review_log.c.id).where(review_log.c.quiz_item_id == card.id)
    ).scalar_one()
    assert linked == log_id
    reviews = db_conn.execute(
        select(study_days.c.reviews_count).where(
            study_days.c.user_id == user.id, study_days.c.day == local_day(_NOW, None)
        )
    ).scalar_one()
    assert reviews == 1


# --- C18, C19, C20: the explanation reviews the section's checkpoint card ---------


def _explained(db_conn: Connection, user: User, source_id: UUID, *, reveal: bool = False) -> UUID:
    started = _start(db_conn)(user=user, source_id=source_id, anchor=ANCHOR, prediction=None)
    attempt_id = _explain_attempt_id(started)
    if reveal:
        _reveal(db_conn)(user=user, attempt_id=attempt_id)
    # Blank: no generation call, the least-covered chunk (reading order) is quoted.
    _respond(db_conn)(user=user, attempt_id=attempt_id, response="", confidence=3)
    return attempt_id


@pytest.mark.parametrize("rating", [1, 2, 3])
def test_grade_explain_mints_and_reviews_checkpoint_card(db_conn: Connection, rating: int) -> None:
    user, source_id = _book(db_conn)
    attempt_id = _explained(db_conn, user, source_id)

    graded = _grade(db_conn)(user=user, attempt_id=attempt_id, rating=rating)

    card = SqlAlchemyQuizItemRepository(db_conn).get_by_id(graded.quiz_item_id)
    assert card is not None and card.origin == QuizItemOrigin.CHECKPOINT
    assert [r.rating for r in _log_rows(db_conn, card.id)] == [rating]


def test_minted_card_shape_and_owner_on_sample(db_conn: Connection) -> None:
    user, source_id = _book(db_conn, is_sample=True)
    started = _start(db_conn)(user=user, source_id=source_id, anchor=ANCHOR, prediction=None)
    attempt_id = _explain_attempt_id(started)
    ids = _chunk_ids(db_conn, source_id)
    # The provider cites the third chunk with a sentence-level span.
    generation = FakeAnswerGeneration(
        answer=GeneratedAnswer(
            text="You covered the pins. You left out the machines.",
            cited_chunk_ids=(ids[CHUNKS[2]],),
            model="m",
            found=True,
            spans=(CitedSpan(chunk_id=ids[CHUNKS[2]], quote=CHUNKS[2], start=0, end=10),),
        )
    )
    _respond(db_conn, generation)(
        user=user, attempt_id=attempt_id, response="pins are made by many hands", confidence=1
    )

    graded = _grade(db_conn)(user=user, attempt_id=attempt_id, rating=1)

    card = SqlAlchemyQuizItemRepository(db_conn).get_by_id(graded.quiz_item_id)
    assert card.user_id == user.id
    assert card.origin == QuizItemOrigin.CHECKPOINT
    assert card.item_type == QuizItemType.FREE_RECALL
    assert card.question == f'Explain "{TITLE}" in your own words.'
    assert card.anchor == ANCHOR
    assert card.section_path == ("Book I", TITLE)
    assert card.answer == CHUNKS[2][:_MAX_CARD_CHARS]
    assert card.source_excerpt == CHUNKS[2][:_MAX_CARD_CHARS]
    # Scheduled fresh before its first review: the log row's "previous" snapshot is
    # exactly what a new card receives.
    fresh = FsrsSchedulingAdapter(fuzzing=False).initial()
    prev = db_conn.execute(
        select(
            review_log.c.prev_state,
            review_log.c.prev_step,
            review_log.c.prev_stability,
            review_log.c.prev_difficulty,
            review_log.c.prev_last_review,
        ).where(review_log.c.quiz_item_id == card.id)
    ).one()
    assert tuple(prev) == (fresh.state, fresh.step, fresh.stability, fresh.difficulty, None)


def test_minted_card_falls_back_to_first_chunk(db_conn: Connection) -> None:
    user, source_id = _book(db_conn)
    started = _start(db_conn)(user=user, source_id=source_id, anchor=ANCHOR, prediction=None)
    attempt_id = _explain_attempt_id(started)
    # Feedback quoted nothing: force an empty citation set on the stored attempt.
    db_conn.execute(
        checkpoint_attempts.update()
        .where(checkpoint_attempts.c.id == attempt_id)
        .values(responded_at=_NOW, response="x", confidence=2)
    )

    graded = _grade(db_conn)(user=user, attempt_id=attempt_id, rating=2)

    card = SqlAlchemyQuizItemRepository(db_conn).get_by_id(graded.quiz_item_id)
    assert card.answer == CHUNKS[0][:_MAX_CARD_CHARS]


def test_second_checkpoint_reuses_existing_card(db_conn: Connection) -> None:
    user, source_id = _book(db_conn)
    first = _grade(db_conn)(user=user, attempt_id=_explained(db_conn, user, source_id), rating=1)
    card_before = SqlAlchemyQuizItemRepository(db_conn).get_by_id(first.quiz_item_id)

    second = _grade(db_conn)(user=user, attempt_id=_explained(db_conn, user, source_id), rating=3)

    assert second.quiz_item_id == first.quiz_item_id
    count = db_conn.execute(
        select(func.count())
        .select_from(quiz_items)
        .where(quiz_items.c.user_id == user.id, quiz_items.c.origin == QuizItemOrigin.CHECKPOINT)
    ).scalar_one()
    assert count == 1
    card_after = SqlAlchemyQuizItemRepository(db_conn).get_by_id(first.quiz_item_id)
    assert (card_after.question, card_after.answer) == (card_before.question, card_before.answer)
    assert [r.rating for r in _log_rows(db_conn, first.quiz_item_id)] == [1, 3]


# --- C21–C26: explain-back feedback ----------------------------------------------


def test_explain_calls_answer_mode_once_least_covered_first(db_conn: Connection) -> None:
    user = add_user(db_conn)
    source_id = add_source(db_conn, user.id)
    many = tuple(f"Passage number {n} talks about topic{n} only." for n in range(8))
    add_corpus(db_conn, source_id, sections=((ANCHOR, TITLE, CHUNKS + many),))
    started = _start(db_conn)(user=user, source_id=source_id, anchor=ANCHOR, prediction=None)
    ids = _chunk_ids(db_conn, source_id)
    generation = FakeAnswerGeneration(
        answer=GeneratedAnswer(
            text="Good start.", cited_chunk_ids=(ids[CHUNKS[1]],), model="m", found=True
        )
    )
    explanation = "Pin making is divided into eighteen distinct operations by different hands."

    feedback = _respond(db_conn, generation)(
        user=user,
        attempt_id=_explain_attempt_id(started),
        response=explanation,
        confidence=2,
    )

    assert len(generation.calls) == 1
    call = generation.calls[0]
    assert call["mode"] == MODE_ANSWER
    assert call["message"] == EXPLAIN_BACK_MESSAGE.format(title=TITLE, explanation=explanation)
    snippets = [e.snippet for e in call["evidence"]]
    assert len(snippets) == 6
    # The chunk the explanation echoes is the most covered: never in the first six
    # when eight untouched passages exist; untouched ones keep reading order.
    assert CHUNKS[0] not in snippets
    assert snippets[:2] == [CHUNKS[1], CHUNKS[2]]
    assert feedback.feedback == "Good start."
    assert [c.quote for c in feedback.citations] == [CHUNKS[1]]


def test_explain_drops_ungrounded_citations(db_conn: Connection) -> None:
    user, source_id = _book(db_conn)
    started = _start(db_conn)(user=user, source_id=source_id, anchor=ANCHOR, prediction=None)
    ids = _chunk_ids(db_conn, source_id)
    generation = FakeAnswerGeneration(
        answer=GeneratedAnswer(
            text="Compare these.",
            cited_chunk_ids=(uuid4(), ids[CHUNKS[2]]),
            model="m",
            found=True,
        )
    )

    feedback = _respond(db_conn, generation)(
        user=user, attempt_id=_explain_attempt_id(started), response="workers", confidence=2
    )

    assert [c.quote for c in feedback.citations] == [CHUNKS[2]]


@pytest.mark.parametrize("outcome", ["not_found", "raises", "ungrounded"])
def test_explain_fallback_on_not_found_raise_or_ungrounded(
    db_conn: Connection, outcome: str
) -> None:
    user, source_id = _book(db_conn)
    started = _start(db_conn)(user=user, source_id=source_id, anchor=ANCHOR, prediction=None)
    usage = TokenUsage(input_tokens=1000, output_tokens=1000)
    if outcome == "raises":
        generation = FakeAnswerGeneration(error=RuntimeError("provider down"))
    elif outcome == "not_found":
        generation = FakeAnswerGeneration(
            answer=GeneratedAnswer(text="", cited_chunk_ids=(), model="m", found=False, usage=usage)
        )
    else:
        generation = FakeAnswerGeneration(
            answer=GeneratedAnswer(
                text="Hm.", cited_chunk_ids=(uuid4(),), model="m", found=True, usage=usage
            )
        )
    # "Pin making …" is fully echoed, so the least-covered chunk is the second one.
    response = CHUNKS[0]

    feedback = _respond(db_conn, generation, _budget(db_conn))(
        user=user, attempt_id=_explain_attempt_id(started), response=response, confidence=2
    )

    assert [c.quote for c in feedback.citations] == [CHUNKS[1]]
    assert feedback.citations[0].anchor == ANCHOR
    row = SqlAlchemyAiSpendDayRepository(db_conn).get_for_day(user.id, _NOW.date())
    if outcome == "raises":
        assert row is None
    else:
        # A completed call that grounded nothing still cost what it reported.
        assert row is not None and row.usd_micros == 3000


def test_blank_explanation_skips_generation(db_conn: Connection) -> None:
    user, source_id = _book(db_conn)
    started = _start(db_conn)(user=user, source_id=source_id, anchor=ANCHOR, prediction=None)
    generation = FakeAnswerGeneration(error=AssertionError("must not be called"))

    for blank in ("", "   \n"):
        attempt_id = (
            _explain_attempt_id(started)
            if blank == ""
            else _explain_attempt_id(
                _start(db_conn)(user=user, source_id=source_id, anchor=ANCHOR, prediction=None)
            )
        )
        feedback = _respond(db_conn, generation)(
            user=user, attempt_id=attempt_id, response=blank, confidence=1
        )
        assert [c.quote for c in feedback.citations] == [CHUNKS[0]]

    assert generation.calls == []


def test_explain_debits_usage_as_generation(db_conn: Connection) -> None:
    user, source_id = _book(db_conn)
    started = _start(db_conn)(user=user, source_id=source_id, anchor=ANCHOR, prediction=None)
    ids = _chunk_ids(db_conn, source_id)
    usage = TokenUsage(input_tokens=1000, output_tokens=500)
    generation = FakeAnswerGeneration(
        answer=GeneratedAnswer(
            text="Nice.", cited_chunk_ids=(ids[CHUNKS[1]],), model="m", found=True, usage=usage
        )
    )
    budget = _budget(db_conn)

    _respond(db_conn, generation, budget)(
        user=user, attempt_id=_explain_attempt_id(started), response="workers", confidence=3
    )

    row = SqlAlchemyAiSpendDayRepository(db_conn).get_for_day(user.id, _NOW.date())
    assert row is not None
    assert row.usd_micros == budget.usage_micros(usage, None) == 2000
    assert row.ask_count == 0
    assert row.teach_starts == 0


# --- C31: assistance is whether the passage was revealed before the response -----


def test_revealed_explain_grade_is_assisted(db_conn: Connection) -> None:
    user, source_id = _book(db_conn)
    attempt_id = _explained(db_conn, user, source_id, reveal=True)

    graded = _grade(db_conn)(user=user, attempt_id=attempt_id, rating=3)

    assert [tuple(r) for r in _log_rows(db_conn, graded.quiz_item_id)] == [(3, 3, True)]


def test_unrevealed_explain_grade_is_unassisted(db_conn: Connection) -> None:
    user, source_id = _book(db_conn)
    attempt_id = _explained(db_conn, user, source_id)

    graded = _grade(db_conn)(user=user, attempt_id=attempt_id, rating=3)

    assert [tuple(r) for r in _log_rows(db_conn, graded.quiz_item_id)] == [(3, 3, False)]
