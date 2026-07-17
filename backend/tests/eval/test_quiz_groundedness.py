"""F1 gate — deterministic quiz groundedness eval (QUIZ-23).

Runs the *real* deck pipeline (the deterministic local adapter + the QC/dedup
pipeline in ``RunDeckGeneration`` + deterministic embeddings) over the golden book,
persisted through the real repositories, then asserts groundedness **invariants**
over what actually persisted — not fixed per-section item counts. The local
embedding is bag-of-tokens, so a section's free-recall and cloze items are near
duplicates and one may legitimately be dedup-discarded (design §Evals, Phase C
note); the eval therefore pins containment, cloze-mask validity, anchor
resolvability, and the generated+discarded accounting rather than a deck size.

The discrimination case feeds the same pipeline a poisoned candidate whose
``anchor_quote`` is absent from the chunk it cites and asserts the pipeline
discards it (it never persists) — the sensor that proves the groundedness guard
is load-bearing, not incidental.

DB-backed (``requires_db``): part of the PR suite, fully offline (no provider
network — the local adapter and deterministic embeddings need no key).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Connection

from app.application.quiz import RunDeckGeneration
from app.application.quiz_qc import CLOZE_BLANK, quote_in_text
from app.core.config import get_settings
from app.domain.entities import (
    QuizCandidate,
    QuizDeckResult,
    QuizGenerationJob,
    QuizItem,
    QuizItemType,
    QuizJobStatus,
    Source,
)
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemyQuizItemRepository,
    SqlAlchemyQuizJobRepository,
)
from app.infrastructure.embeddings import build_embedding_adapter
from app.infrastructure.quiz.local import DeterministicQuizAdapter
from app.infrastructure.scheduling.fsrs import FsrsSchedulingAdapter
from tests.conftest import requires_db
from tests.eval_runner import build_corpus_in_db, seed_source
from tests.golden_corpus import golden_book

pytestmark = requires_db

_NOW = datetime(2026, 7, 16, 12, 0, 0, tzinfo=UTC)


def _run_deck(
    jobs: SqlAlchemyQuizJobRepository, items: SqlAlchemyQuizItemRepository
) -> RunDeckGeneration:
    settings = get_settings()
    return RunDeckGeneration(
        jobs=jobs,
        items=items,
        generation=DeterministicQuizAdapter(),
        embeddings=build_embedding_adapter(settings),
        scheduling=FsrsSchedulingAdapter(
            desired_retention=settings.fsrs_desired_retention,
            fuzzing=False,  # deterministic scheduling — no fuzz in tests (QUIZ-11)
            maximum_interval=36500,
        ),
        clock=_FixedClock(_NOW),
        ids=uuid4,
        min_section_chars=settings.quiz_min_section_chars,
        dedup_threshold=settings.quiz_dedup_threshold,
    )


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _queued_job(source_id: UUID) -> QuizGenerationJob:
    return QuizGenerationJob(
        id=uuid4(),
        source_id=source_id,
        status=QuizJobStatus.QUEUED,
        attempts=0,
        generated_count=0,
        discarded_count=0,
        failed_sections=0,
        last_error=None,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _build_deck(db_conn: Connection) -> tuple[Source, QuizGenerationJob, list[QuizItem]]:
    """Seed the golden book and run the real deck pipeline over it; return persisted state."""
    _user, source = seed_source(db_conn, email=f"quiz-eval-{uuid4()}@example.com")
    build_corpus_in_db(db_conn, source, golden_book())

    jobs = SqlAlchemyQuizJobRepository(db_conn)
    items = SqlAlchemyQuizItemRepository(db_conn)
    run = _run_deck(jobs, items)

    job = jobs.add(_queued_job(source.id))
    run.begin(job.id)
    handle = run.begin_deck(source.id)
    result = run.collect(handle)
    assert result is not None  # the local adapter never pends
    final_job = run.finalize(job.id, result)
    assert final_job is not None
    return source, final_job, items.list_for_source(source.id)


def _chunk_text_by_anchor(db_conn: Connection, source_id: UUID) -> dict[str, str]:
    """Map each eligible section's anchor → its concatenated chunk text (grounding bound)."""
    sections = SqlAlchemyQuizItemRepository(db_conn).sections_for_generation(
        source_id, min_chars=get_settings().quiz_min_section_chars
    )
    return {
        section.anchor: "\n".join(text for _cid, text in section.chunks)
        for section in sections
    }


# --- Groundedness invariants over persisted items (QUIZ-23) --------------------


def test_golden_deck_persists_only_grounded_items(db_conn: Connection) -> None:
    source, job, items = _build_deck(db_conn)

    # The golden book has two eligible sections (ch1/ch3 ≥ 200 chars; ch2 is below),
    # each yielding one free_recall + one cloze = 4 candidates. Accounting invariant:
    # every candidate is either generated or discarded (QUIZ-09), never lost.
    assert job.generated_count + job.discarded_count == 4
    assert job.status == QuizJobStatus.SUCCEEDED
    # At least the two distinct free_recall items survive dedup (a same-sentence cloze
    # may be dropped as a near-duplicate) — the deck is non-empty and matches the job.
    assert len(items) == job.generated_count >= 2

    chunk_text = _chunk_text_by_anchor(db_conn, source.id)
    corpus = SqlAlchemyCorpusRepository(db_conn)

    for item in items:
        # (1) 100% groundedness: the snapshotted excerpt is verbatim (whitespace/case
        # normalized) in the chunk text of the section it cites.
        assert item.anchor in chunk_text, f"item anchor {item.anchor} not an eligible section"
        assert quote_in_text(item.source_excerpt, chunk_text[item.anchor])
        # chunk_hash pins the snapshot to that exact chunk's bytes (QUIZ-06).
        assert item.chunk_hash == hashlib.sha256(
            chunk_text[item.anchor].encode("utf-8")
        ).hexdigest()
        # (2) cloze mask validity: answer appears in the excerpt and the question
        # carries the blank (QUIZ-07).
        if item.item_type == QuizItemType.CLOZE:
            assert CLOZE_BLANK in item.question
            assert quote_in_text(item.answer, item.source_excerpt)
        # (3) anchor resolvability: the anchor resolves to a real section in the
        # corpus and the snapshotted section_path matches it (QUIZ-15/23).
        section = corpus.get_section(source.id, item.anchor)
        assert section is not None
        assert section.section_path == item.section_path


# --- Discrimination: a poisoned candidate must be discarded (QUIZ-23) ----------


def test_pipeline_discards_candidate_whose_quote_is_not_in_the_chunk(
    db_conn: Connection,
) -> None:
    settings = get_settings()
    _user, source = seed_source(db_conn, email=f"quiz-poison-{uuid4()}@example.com")
    build_corpus_in_db(db_conn, source, golden_book())

    jobs = SqlAlchemyQuizJobRepository(db_conn)
    items = SqlAlchemyQuizItemRepository(db_conn)
    run = _run_deck(jobs, items)

    # A real chunk from the first eligible golden section — the id both candidates cite.
    section = items.sections_for_generation(
        source.id, min_chars=settings.quiz_min_section_chars
    )[0]
    chunk_id, chunk_text = section.chunks[0]
    grounded_quote = chunk_text.split(".")[0].strip() + "."  # a verbatim leading sentence

    control = QuizCandidate(
        item_type=QuizItemType.FREE_RECALL,
        question="What does the passage state?",
        answer=grounded_quote,
        source_chunk_id=chunk_id,
        anchor_quote=grounded_quote,
    )
    poisoned = QuizCandidate(
        item_type=QuizItemType.FREE_RECALL,
        question="What is fabricated here?",
        answer="an assertion the source never makes",
        source_chunk_id=chunk_id,
        anchor_quote="this fabricated sentence never appears in the golden book",
    )

    job = jobs.add(_queued_job(source.id))
    run.begin(job.id)
    final_job = run.finalize(
        job.id, QuizDeckResult(candidates=(control, poisoned), errors=())
    )

    assert final_job is not None
    # The control persists; the poisoned candidate is discarded and never reaches the DB.
    persisted = items.list_for_source(source.id)
    excerpts = {item.source_excerpt for item in persisted}
    assert grounded_quote in excerpts
    assert "this fabricated sentence never appears in the golden book" not in excerpts
    assert final_job.generated_count == 1
    assert final_job.discarded_count == 1
