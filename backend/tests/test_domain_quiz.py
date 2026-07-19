"""Active-recall domain contracts + quiz QC helpers (Cycle E, design §Domain).

Unit coverage for the pure grounding/identity helpers (QUIZ-06/07, content_key), the
no-MCQ item vocabulary (QUIZ-10), the deck-handle Celery round-trip, the job transition
helpers (QUIZ-09), and the runtime-checkable port protocols. Pure domain/application —
no DB, no framework.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.quiz_qc import (
    CLOZE_BLANK,
    cloze_is_valid,
    content_key,
    normalize_text,
    quote_in_text,
)
from app.domain.entities import (
    ACTIVE_QUIZ_JOB_STATUSES,
    CardProvenance,
    DueReviewItem,
    QuizDeckHandle,
    QuizGenerationJob,
    QuizItem,
    QuizItemOrigin,
    QuizItemStatus,
    QuizItemType,
    QuizJobStatus,
    SourceHighlight,
)
from app.domain.ports import (
    QuizDeckEnqueuer,
    QuizGenerationPort,
    QuizItemRepository,
    QuizJobRepository,
    SchedulingPort,
)

# --- QC helpers ------------------------------------------------------------------


def test_normalize_text_lowercases_and_collapses_whitespace() -> None:
    assert normalize_text("  The   Quick\tBrown\nFox  ") == "the quick brown fox"


def test_content_key_is_stable_for_equal_normalized_content() -> None:
    # Whitespace/case differences normalize to the same upsert identity (QUIZ-02).
    a = content_key(QuizItemType.FREE_RECALL, "The Cat", "It Sat")
    b = content_key(QuizItemType.FREE_RECALL, "  the   cat ", "it sat")
    assert a == b


def test_content_key_includes_item_type() -> None:
    # A cloze and a free_recall item from the same sentence must not collide (design).
    free = content_key(QuizItemType.FREE_RECALL, "What sat?", "the cat")
    cloze = content_key(QuizItemType.CLOZE, "What sat?", "the cat")
    assert free != cloze


def test_content_key_is_hex_sha256() -> None:
    key = content_key(QuizItemType.FREE_RECALL, "q", "a")
    assert len(key) == 64
    assert all(c in "0123456789abcdef" for c in key)


def test_quote_in_text_true_when_present_whitespace_normalized() -> None:
    # QUIZ-06: an anchor quote that appears (whitespace-normalized) in the chunk grounds.
    assert quote_in_text("the quick fox", "The  quick   fox jumped over") is True


def test_quote_in_text_false_when_absent() -> None:
    # QUIZ-06 discrimination: an ungrounded quote is not found → the item is discarded.
    assert quote_in_text("a purple monkey", "The quick fox jumped over") is False


def test_cloze_is_valid_when_masked_span_in_quote_and_blank_present() -> None:
    assert cloze_is_valid("The ____ sat on the mat", "cat", "The cat sat on the mat") is True


def test_cloze_invalid_when_masked_span_absent_from_quote() -> None:
    # QUIZ-07: masked span not in the anchor quote → discarded.
    assert cloze_is_valid("The ____ sat on the mat", "dog", "The cat sat on the mat") is False


def test_cloze_invalid_when_blank_missing() -> None:
    # QUIZ-07: a cloze question must carry the ____ blank (A-5).
    assert CLOZE_BLANK == "____"
    assert cloze_is_valid("The cat sat on the mat", "cat", "The cat sat on the mat") is False


# --- Item type / status vocabulary (QUIZ-10) -------------------------------------


def test_item_types_are_exactly_free_recall_and_cloze() -> None:
    # QUIZ-10: the only two kinds — no MCQ constant exists anywhere in the vocabulary.
    values = {
        v for k, v in vars(QuizItemType).items() if not k.startswith("_") and isinstance(v, str)
    }
    assert values == {"free_recall", "cloze"}


def test_item_status_vocabulary() -> None:
    assert QuizItemStatus.ACTIVE == "active"
    assert QuizItemStatus.STALE == "stale"
    assert QuizItemStatus.ORPHANED == "orphaned"


def test_active_quiz_job_statuses_are_exactly_queued_and_running() -> None:
    assert ACTIVE_QUIZ_JOB_STATUSES == frozenset({"queued", "running"})


# --- Deck handle Celery round-trip (design §Domain) ------------------------------


def test_deck_handle_round_trips_local_inline_payload() -> None:
    # The local adapter carries its inline result on the handle; it must survive the
    # Celery JSON hop between begin_deck and the poll task.
    handle = QuizDeckHandle(
        provider="local",
        batch_id=None,
        payload={"candidates": [{"item_type": "free_recall", "question": "q"}]},
    )
    assert QuizDeckHandle.from_payload(handle.to_payload()) == handle


def test_deck_handle_round_trips_anthropic_batch_id() -> None:
    handle = QuizDeckHandle(
        provider="anthropic",
        batch_id="msgbatch_123",
        payload={"sections": {"sec-a": ["chunk-1"]}},
    )
    assert QuizDeckHandle.from_payload(handle.to_payload()) == handle


# --- Job transitions (QUIZ-09) ---------------------------------------------------


def _job() -> QuizGenerationJob:
    now = datetime(2026, 7, 16, tzinfo=UTC)
    return QuizGenerationJob(
        id=uuid4(),
        source_id=uuid4(),
        status=QuizJobStatus.QUEUED,
        attempts=0,
        generated_count=0,
        discarded_count=0,
        failed_sections=0,
        last_error=None,
        created_at=now,
        updated_at=now,
    )


def test_job_started_transitions_to_running_and_increments_attempts() -> None:
    now = datetime(2026, 7, 16, 1, tzinfo=UTC)
    started = _job().started(now)
    assert started.status == QuizJobStatus.RUNNING
    assert started.attempts == 1
    assert started.updated_at == now


def test_job_succeeded_records_counts() -> None:
    now = datetime(2026, 7, 16, 2, tzinfo=UTC)
    done = _job().started(now).succeeded(
        now, generated_count=5, discarded_count=2, failed_sections=1
    )
    assert done.status == QuizJobStatus.SUCCEEDED
    assert done.generated_count == 5
    assert done.discarded_count == 2
    assert done.failed_sections == 1


def test_job_failed_sets_last_error() -> None:
    now = datetime(2026, 7, 16, 3, tzinfo=UTC)
    failed = _job().started(now).failed(now, "batch timeout")
    assert failed.status == QuizJobStatus.FAILED
    assert failed.last_error == "batch timeout"


def test_job_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        _job().status = QuizJobStatus.RUNNING  # type: ignore[misc]


def test_quiz_item_is_frozen() -> None:
    now = datetime(2026, 7, 16, tzinfo=UTC)
    item = QuizItem(
        id=uuid4(),
        source_id=uuid4(),
        item_type=QuizItemType.FREE_RECALL,
        question="q",
        answer="a",
        section_path=("Chapter 1",),
        anchor="ch1.xhtml",
        source_excerpt="the cat sat",
        chunk_hash="deadbeef",
        content_key=content_key(QuizItemType.FREE_RECALL, "q", "a"),
        status=QuizItemStatus.ACTIVE,
        generation_meta={},
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(FrozenInstanceError):
        item.status = QuizItemStatus.STALE  # type: ignore[misc]


# --- Card origin and provenance (CAP-10, CAP-16, CAP-19) -------------------------


def test_item_origins_are_exactly_deck_and_highlight() -> None:
    """The vocabulary is closed: a third origin would need its own identity rule."""
    origins = {
        value
        for key, value in vars(QuizItemOrigin).items()
        if not key.startswith("_") and isinstance(value, str)
    }
    assert origins == {"deck", "highlight"}


def test_item_origin_vocabulary() -> None:
    assert QuizItemOrigin.DECK == "deck"
    assert QuizItemOrigin.HIGHLIGHT == "highlight"


def _item(**overrides) -> QuizItem:  # noqa: ANN003
    now = datetime(2026, 7, 19, tzinfo=UTC)
    fields = {
        "id": uuid4(),
        "source_id": uuid4(),
        "item_type": QuizItemType.FREE_RECALL,
        "question": "q",
        "answer": "a",
        "section_path": ("Chapter 1",),
        "anchor": "ch1.xhtml",
        "source_excerpt": "the cat sat",
        "chunk_hash": "deadbeef",
        "content_key": content_key(QuizItemType.FREE_RECALL, "q", "a"),
        "status": QuizItemStatus.ACTIVE,
        "generation_meta": {},
        "created_at": now,
        "updated_at": now,
    }
    return QuizItem(**{**fields, **overrides})


def test_quiz_item_defaults_to_deck_origin_with_no_provenance() -> None:
    """The pre-capture construction sites are all deck generation, so that is the
    default — matching the column's server default and needing no backfill."""
    item = _item()

    assert item.origin == QuizItemOrigin.DECK
    assert item.note_anchor_id is None


def test_quiz_item_carries_highlight_origin_and_its_anchor_provenance() -> None:
    anchor_id = uuid4()

    item = _item(origin=QuizItemOrigin.HIGHLIGHT, note_anchor_id=anchor_id)

    assert item.origin == QuizItemOrigin.HIGHLIGHT
    assert item.note_anchor_id == anchor_id


def test_highlight_item_keeps_its_excerpt_when_provenance_is_severed() -> None:
    """Deleting the origin note clears the link, never the card: the excerpt is the
    card's own snapshot, so it stays renderable (CAP-15)."""
    item = _item(
        origin=QuizItemOrigin.HIGHLIGHT,
        note_anchor_id=None,
        source_excerpt="the quoted sentence",
    )

    assert item.note_anchor_id is None
    assert item.source_excerpt == "the quoted sentence"


def test_due_review_item_has_no_provenance_by_default() -> None:
    now = datetime(2026, 7, 19, tzinfo=UTC)

    due = DueReviewItem(item=_item(), source_title="Book", due=now)

    assert due.provenance is None


def test_due_review_item_carries_origin_note_provenance() -> None:
    now = datetime(2026, 7, 19, tzinfo=UTC)
    note_id = uuid4()

    due = DueReviewItem(
        item=_item(origin=QuizItemOrigin.HIGHLIGHT, note_anchor_id=uuid4()),
        source_title="Book",
        due=now,
        provenance=CardProvenance(note_id=note_id, note_title="On attention"),
    )

    assert due.provenance == CardProvenance(note_id=note_id, note_title="On attention")


def test_source_highlight_carries_note_title_and_body_flag() -> None:
    highlight = SourceHighlight(
        note_id=uuid4(),
        anchor="ch1.xhtml",
        quote_exact="the cat sat",
        quote_prefix="",
        quote_suffix="",
        status="active",
        note_title="On attention",
        has_body=True,
    )

    assert highlight.note_title == "On attention"
    assert highlight.has_body is True


def test_source_highlight_defaults_to_untitled_and_bodyless() -> None:
    """The painter's construction sites predate the rail and supply neither field."""
    highlight = SourceHighlight(
        note_id=uuid4(),
        anchor="ch1.xhtml",
        quote_exact="the cat sat",
        quote_prefix="",
        quote_suffix="",
        status="active",
    )

    assert highlight.note_title == ""
    assert highlight.has_body is False


# --- Port protocols are runtime-checkable ----------------------------------------


def test_quiz_generation_port_is_runtime_checkable_protocol() -> None:
    class ConformingAdapter:
        model = "local-deterministic"

        def begin_deck(self, sections):  # noqa: ANN001, ANN201
            return None

        def collect_deck(self, handle):  # noqa: ANN001, ANN201
            return None

    class MissingCollect:
        model = "x"

        def begin_deck(self, sections):  # noqa: ANN001, ANN201
            return None

    assert isinstance(ConformingAdapter(), QuizGenerationPort)
    assert not isinstance(MissingCollect(), QuizGenerationPort)


def test_scheduling_port_is_runtime_checkable_protocol() -> None:
    class ConformingScheduler:
        def initial(self):  # noqa: ANN201
            return None

        def review(self, snapshot, rating, reviewed_at):  # noqa: ANN001, ANN201
            return None

    class MissingReview:
        def initial(self):  # noqa: ANN201
            return None

    assert isinstance(ConformingScheduler(), SchedulingPort)
    assert not isinstance(MissingReview(), SchedulingPort)


def test_quiz_deck_enqueuer_is_runtime_checkable_protocol() -> None:
    class ConformingEnqueuer:
        def enqueue_quiz_deck(self, *, source_id, job_id):  # noqa: ANN001, ANN201
            return None

    assert isinstance(ConformingEnqueuer(), QuizDeckEnqueuer)
    assert not isinstance(object(), QuizDeckEnqueuer)


def test_quiz_job_repository_is_runtime_checkable_protocol() -> None:
    class ConformingRepo:
        def add(self, job):  # noqa: ANN001, ANN201
            return job

        def get_by_id(self, job_id):  # noqa: ANN001, ANN201
            return None

        def get_active_for_source(self, source_id):  # noqa: ANN001, ANN201
            return None

        def get_latest_for_source(self, source_id):  # noqa: ANN001, ANN201
            return None

        def update(self, job):  # noqa: ANN001, ANN201
            return job

    class MissingActive:
        def add(self, job):  # noqa: ANN001, ANN201
            return job

    assert isinstance(ConformingRepo(), QuizJobRepository)
    assert not isinstance(MissingActive(), QuizJobRepository)


def test_quiz_item_repository_requires_upsert_and_due_for_user() -> None:
    # Upsert (QUIZ-02) and the due-queue read (QUIZ-13) are the load-bearing methods.
    class WithoutUpsert:
        def due_for_user(self, user_id, *, now, limit, source_id=None):  # noqa: ANN001, ANN201
            return (0, [])

    assert not isinstance(WithoutUpsert(), QuizItemRepository)
