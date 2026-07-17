"""C2 gate — Celery deck tasks + enqueuer (integration, live test DB).

Drives ``generate_quiz_deck`` / ``poll_quiz_deck`` *functions* directly against the
migrated test engine with a controllable bound ``self`` (no broker, no eager mode),
mirroring ``test_worker_tasks``. The local provider path runs end to end (real corpus
→ real deterministic adapter → persisted grounded items + FSRS scheduling rows); the
batch path is exercised with an injected fake adapter for pending/deadline/retry
branches. Seeds are committed (the task commits through its own engine) and cleaned
up via the user cascade.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy import delete as sa_delete

from app.application.quiz_qc import content_key
from app.domain.entities import (
    CorpusSectionRecord,
    IngestionJob,
    IngestionStatus,
    ParsedBlock,
    ParsedSection,
    QuizCandidate,
    QuizDeckHandle,
    QuizDeckResult,
    QuizGenerationJob,
    QuizItem,
    QuizItemStatus,
    QuizItemType,
    QuizJobStatus,
    ReviewLogEntry,
    SchedulingSnapshot,
    SectionChunk,
    Source,
    User,
)
from app.infrastructure.db.metadata import quiz_item_scheduling, quiz_items, users
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemyIngestionJobRepository,
    SqlAlchemyQuizItemRepository,
    SqlAlchemyQuizJobRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyUserRepository,
)
from app.infrastructure.worker.enqueuer import CeleryQuizDeckEnqueuer
from app.infrastructure.worker.steps import NoOpIngestionStep
from app.worker.tasks import generate_quiz_deck, poll_quiz_deck, run_ingestion
from tests.conftest import requires_db

pytestmark = requires_db

_generate = generate_quiz_deck.run.__func__
_poll = poll_quiz_deck.run.__func__
_ingest = run_ingestion.run.__func__

# Two distinct leaf sections, each ≥ quiz_min_section_chars (200) so both are eligible.
_TEXT_A = (
    "The mitochondria is the powerhouse of the cell and produces most of the "
    "adenosine triphosphate that living organisms rely on for energy. "
    "It has its own genome and replicates independently of the host nucleus, "
    "which is strong evidence for the endosymbiotic origin of the organelle."
)
_TEXT_B = (
    "Photosynthesis converts light energy into chemical energy stored in glucose "
    "molecules inside the chloroplasts of green plants and cyanobacteria. "
    "The light-dependent reactions split water and release oxygen as a byproduct, "
    "while the Calvin cycle fixes carbon dioxide into organic sugars."
)


class FakeSelf:
    """A controllable bound-task ``self``: request.retries, max_retries, retry()."""

    class RetrySignal(Exception):
        """Sentinel raised by :meth:`retry`, standing in for Celery's ``Retry``."""

    def __init__(self, *, retries: int = 0, max_retries: int = 3) -> None:
        self.request = SimpleNamespace(retries=retries)
        self.max_retries = max_retries
        self.retry_calls: list[dict] = []

    def retry(self, *, exc, countdown):  # noqa: ANN001, ANN202
        self.retry_calls.append({"exc": exc, "countdown": countdown})
        raise self.RetrySignal


class FakeQuizAdapter:
    """``QuizGenerationPort`` double for the batch path (pending/result/error)."""

    model = "fake-quiz@1"

    def __init__(
        self,
        *,
        result: QuizDeckResult | None = None,
        begin_error: Exception | None = None,
    ) -> None:
        self._result = result
        self._begin_error = begin_error
        self.begin_calls = 0

    def begin_deck(self, sections) -> QuizDeckHandle:  # noqa: ANN001
        self.begin_calls += 1
        if self._begin_error is not None:
            raise self._begin_error
        return QuizDeckHandle(provider="anthropic", batch_id="batch-1", payload={})

    def collect_deck(self, handle: QuizDeckHandle) -> QuizDeckResult | None:
        return self._result


@pytest.fixture
def seed(db_engine: Engine, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """Point the deck task's engine at the test DB; seed committed rows.

    Returns a callable committing a user + ready source + optional queued deck job and
    optional two-section corpus, recording the user for cascade cleanup.
    """
    monkeypatch.setattr("app.worker.tasks.get_engine", lambda: db_engine)
    created_users: list[UUID] = []

    def _seed(
        *,
        job_status: str | None = QuizJobStatus.QUEUED,
        with_corpus: bool = False,
    ) -> SimpleNamespace:
        now = datetime.now(UTC)
        user = User(id=uuid4(), email=f"{uuid4()}@example.com", created_at=now)
        source = Source(
            id=uuid4(),
            user_id=user.id,
            title="Biology",
            filename="bio.epub",
            content_type="application/epub+zip",
            byte_size=1024,
            checksum="d" * 64,
            object_key=f"sources/{uuid4()}.epub",
            status="ready",
            created_at=now,
            updated_at=now,
        )
        job = QuizGenerationJob(
            id=uuid4(),
            source_id=source.id,
            status=job_status or QuizJobStatus.QUEUED,
            attempts=0,
            generated_count=0,
            discarded_count=0,
            failed_sections=0,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
        created_users.append(user.id)
        with db_engine.begin() as conn:
            SqlAlchemyUserRepository(conn).add(user)
            SqlAlchemySourceRepository(conn).add(source)
            if job_status is not None:
                SqlAlchemyQuizJobRepository(conn).add(job)
            if with_corpus:
                SqlAlchemyCorpusRepository(conn).replace(
                    source.id,
                    title="Biology",
                    authors=["A"],
                    language="en",
                    schema_version=1,
                    sections=[
                        _section_record(1, "Cells", ("Chapter 1",), "ch1", _TEXT_A),
                        _section_record(2, "Plants", ("Chapter 2",), "ch2", _TEXT_B),
                    ],
                )
        return SimpleNamespace(user=user, source=source, job=job)

    yield _seed

    with db_engine.begin() as conn:
        for user_id in created_users:
            conn.execute(sa_delete(users).where(users.c.id == user_id))


def _section_record(
    position: int, title: str, section_path: tuple[str, ...], anchor: str, text: str
) -> CorpusSectionRecord:
    return CorpusSectionRecord(
        section=ParsedSection(
            position=position,
            title=title,
            depth=len(section_path),
            section_path=section_path,
            anchor=anchor,
            blocks=(
                ParsedBlock(position=0, block_type="paragraph", html_fragment="<p/>"),
            ),
        ),
        markdown=text,
        chunks=(
            SectionChunk(
                index=0,
                text=text,
                section_path=section_path,
                anchor=anchor,
                page_span=None,
            ),
        ),
    )


def _read_job(engine: Engine, job_id: UUID) -> QuizGenerationJob:
    with engine.connect() as conn:
        return SqlAlchemyQuizJobRepository(conn).get_by_id(job_id)


def _count_items(engine: Engine, source_id: UUID) -> int:
    with engine.connect() as conn:
        return len(SqlAlchemyQuizItemRepository(conn).list_for_source(source_id))


def _count_scheduling(engine: Engine, source_id: UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(quiz_item_scheduling)
        .join(quiz_items, quiz_item_scheduling.c.quiz_item_id == quiz_items.c.id)
        .where(quiz_items.c.source_id == source_id)
    )
    with engine.connect() as conn:
        return conn.execute(stmt).scalar_one()


def _add_queued_job(engine: Engine, source_id: UUID) -> QuizGenerationJob:
    now = datetime.now(UTC)
    job = QuizGenerationJob(
        id=uuid4(),
        source_id=source_id,
        status=QuizJobStatus.QUEUED,
        attempts=0,
        generated_count=0,
        discarded_count=0,
        failed_sections=0,
        last_error=None,
        created_at=now,
        updated_at=now,
    )
    with engine.begin() as conn:
        SqlAlchemyQuizJobRepository(conn).add(job)
    return job


# --- local provider: full pipeline (QUIZ-05/09) ---------------------------------


def test_generate_local_persists_grounded_items_and_scheduling(seed, db_engine: Engine) -> None:
    ctx = seed(with_corpus=True)

    _generate(FakeSelf(), str(ctx.source.id), str(ctx.job.id))

    job = _read_job(db_engine, ctx.job.id)
    assert job.status == QuizJobStatus.SUCCEEDED
    # 2 eligible sections × (1 free_recall + 1 cloze) = 4 candidates. Every candidate is
    # accepted or discarded (a same-sentence cloze may be deduped vs its free_recall,
    # QUIZ-08); the counts account for all four and generated is what actually persists.
    assert job.generated_count + job.discarded_count == 4
    items = _count_items(db_engine, ctx.source.id)
    assert items == job.generated_count >= 2  # the two distinct free_recall items survive
    # Every persisted item has exactly one initial scheduling row (QUIZ-09).
    assert _count_scheduling(db_engine, ctx.source.id) == items


def test_generate_is_idempotent_across_reruns(seed, db_engine: Engine) -> None:
    ctx = seed(with_corpus=True)
    _generate(FakeSelf(), str(ctx.source.id), str(ctx.job.id))
    first_items = _count_items(db_engine, ctx.source.id)
    first_scheduling = _count_scheduling(db_engine, ctx.source.id)
    assert first_items == first_scheduling >= 2

    # A second pass on a fresh queued job re-generates the same content_keys: items
    # are upserted (not duplicated) and no scheduling row is re-created (QUIZ-02/09).
    job2 = _add_queued_job(db_engine, ctx.source.id)
    _generate(FakeSelf(), str(ctx.source.id), str(job2.id))

    assert _read_job(db_engine, job2.id).status == QuizJobStatus.SUCCEEDED
    assert _count_items(db_engine, ctx.source.id) == first_items
    assert _count_scheduling(db_engine, ctx.source.id) == first_scheduling


def test_generate_noop_for_terminal_job(seed, db_engine: Engine) -> None:
    ctx = seed(job_status=QuizJobStatus.SUCCEEDED, with_corpus=True)

    _generate(FakeSelf(), str(ctx.source.id), str(ctx.job.id))

    # Already terminal ⇒ begin no-ops; nothing generated.
    assert _read_job(db_engine, ctx.job.id).status == QuizJobStatus.SUCCEEDED
    assert _count_items(db_engine, ctx.source.id) == 0


# --- batch provider: pending / poll / deadline (QUIZ-05 + timeout edge) ----------


def test_generate_pending_batch_schedules_poll(seed, db_engine: Engine) -> None:
    ctx = seed()  # no corpus needed — the fake ignores sections
    fake = FakeQuizAdapter(result=None)

    with (
        patch("app.worker.tasks.build_quiz_adapter", lambda settings: fake),
        patch("app.worker.tasks.poll_quiz_deck.apply_async") as apply_async,
    ):
        _generate(FakeSelf(), str(ctx.source.id), str(ctx.job.id))

    # Job claimed running; no finalize; poll scheduled with the handle payload + deadline.
    assert _read_job(db_engine, ctx.job.id).status == QuizJobStatus.RUNNING
    assert _count_items(db_engine, ctx.source.id) == 0
    apply_async.assert_called_once()
    kwargs = apply_async.call_args.kwargs
    args = kwargs["args"]
    assert args[0] == str(ctx.job.id)
    assert QuizDeckHandle.from_payload(args[1]).batch_id == "batch-1"
    datetime.fromisoformat(args[2])  # a valid ISO deadline
    assert kwargs["countdown"] > 0


def test_poll_pending_before_deadline_reschedules(seed, db_engine: Engine) -> None:
    ctx = seed(job_status=QuizJobStatus.RUNNING)
    fake = FakeQuizAdapter(result=None)
    handle = QuizDeckHandle(provider="anthropic", batch_id="batch-1", payload={}).to_payload()
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

    with (
        patch("app.worker.tasks.build_quiz_adapter", lambda settings: fake),
        patch("app.worker.tasks.poll_quiz_deck.apply_async") as apply_async,
    ):
        _poll(FakeSelf(), str(ctx.job.id), handle, future)

    apply_async.assert_called_once()
    assert _read_job(db_engine, ctx.job.id).status == QuizJobStatus.RUNNING


def test_poll_past_deadline_fails_with_timeout(seed, db_engine: Engine) -> None:
    ctx = seed(job_status=QuizJobStatus.RUNNING)
    fake = FakeQuizAdapter(result=None)
    handle = QuizDeckHandle(provider="anthropic", batch_id="batch-1", payload={}).to_payload()
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    with (
        patch("app.worker.tasks.build_quiz_adapter", lambda settings: fake),
        patch("app.worker.tasks.poll_quiz_deck.apply_async") as apply_async,
    ):
        _poll(FakeSelf(), str(ctx.job.id), handle, past)

    apply_async.assert_not_called()
    job = _read_job(db_engine, ctx.job.id)
    assert job.status == QuizJobStatus.FAILED
    assert job.last_error == "Quiz deck generation timed out."


def test_poll_result_finalizes_and_persists(seed, db_engine: Engine) -> None:
    ctx = seed(job_status=QuizJobStatus.RUNNING, with_corpus=True)
    # Read a real chunk id to cite a grounded candidate through the collected result.
    with db_engine.connect() as conn:
        sections = SqlAlchemyQuizItemRepository(conn).sections_for_generation(
            ctx.source.id, min_chars=200
        )
    chunk_id, chunk_text = sections[0].chunks[0]
    candidate = QuizCandidate(
        item_type=QuizItemType.FREE_RECALL,
        question="What is the powerhouse of the cell?",
        answer="The mitochondria",
        source_chunk_id=chunk_id,
        anchor_quote="the powerhouse of the cell",
    )
    assert "the powerhouse of the cell" in chunk_text.lower()
    fake = FakeQuizAdapter(result=QuizDeckResult(candidates=(candidate,), errors=()))
    handle = QuizDeckHandle(provider="anthropic", batch_id="batch-1", payload={}).to_payload()
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

    with patch("app.worker.tasks.build_quiz_adapter", lambda settings: fake):
        _poll(FakeSelf(), str(ctx.job.id), handle, future)

    job = _read_job(db_engine, ctx.job.id)
    assert job.status == QuizJobStatus.SUCCEEDED
    assert job.generated_count == 1
    assert _count_items(db_engine, ctx.source.id) == 1
    assert _count_scheduling(db_engine, ctx.source.id) == 1


# --- provider fault: retry then terminal (QUIZ-09) ------------------------------


def test_generate_provider_fault_retries_then_fails(seed, db_engine: Engine) -> None:
    ctx = seed()
    fake = FakeQuizAdapter(begin_error=RuntimeError("anthropic 503"))

    # Retries remaining: the task records a retry and re-raises, job stays running.
    with patch("app.worker.tasks.build_quiz_adapter", lambda settings: fake):
        retrying = FakeSelf(retries=0, max_retries=3)
        with pytest.raises(FakeSelf.RetrySignal):
            _generate(retrying, str(ctx.source.id), str(ctx.job.id))
    assert len(retrying.retry_calls) == 1
    assert retrying.retry_calls[0]["countdown"] > 0
    assert _read_job(db_engine, ctx.job.id).status == QuizJobStatus.RUNNING

    # Retries exhausted: terminal failure with the redacted summary.
    with patch("app.worker.tasks.build_quiz_adapter", lambda settings: fake):
        _generate(FakeSelf(retries=3, max_retries=3), str(ctx.source.id), str(ctx.job.id))
    job = _read_job(db_engine, ctx.job.id)
    assert job.status == QuizJobStatus.FAILED
    assert job.last_error == "Quiz deck generation failed."


# --- reconcile wiring inside the ingestion pipeline (QUIZ-16) --------------------


def test_reconcile_runs_inside_ingestion_pipeline(
    db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A re-ingestion reconciles quiz items in the same pipeline: a previously-stale
    item whose anchor + quote are present in the (replaced) corpus flips back to
    ``active`` after ``run_ingestion`` runs — proving the reconcile step is wired in."""
    monkeypatch.setattr("app.worker.tasks.get_engine", lambda: db_engine)
    now = datetime.now(UTC)
    user = User(id=uuid4(), email=f"{uuid4()}@x.com", created_at=now)
    source = Source(
        id=uuid4(),
        user_id=user.id,
        title="Biology",
        filename="bio.epub",
        content_type="application/epub+zip",
        byte_size=10,
        checksum="d" * 64,
        object_key=f"sources/{uuid4()}.epub",
        status="processing",
        created_at=now,
        updated_at=now,
    )
    job = IngestionJob(
        id=uuid4(),
        source_id=source.id,
        status=IngestionStatus.QUEUED,
        attempts=0,
        last_error=None,
        created_at=now,
        updated_at=now,
    )
    stale = QuizItem(
        id=uuid4(),
        source_id=source.id,
        item_type=QuizItemType.FREE_RECALL,
        question="Q?",
        answer="A",
        section_path=("Chapter 1",),
        anchor="ch1",
        source_excerpt="powerhouse of the cell",
        chunk_hash="h" * 64,
        content_key=content_key(QuizItemType.FREE_RECALL, "Q?", "A"),
        status=QuizItemStatus.STALE,
        generation_meta={},
        created_at=now,
        updated_at=now,
    )
    with db_engine.begin() as conn:
        SqlAlchemyUserRepository(conn).add(user)
        SqlAlchemySourceRepository(conn).add(source)
        SqlAlchemyIngestionJobRepository(conn).add(job)
        SqlAlchemyCorpusRepository(conn).replace(
            source.id,
            title="Biology",
            authors=["A"],
            language="en",
            schema_version=1,
            sections=[_section_record(1, "Cells", ("Chapter 1",), "ch1", _TEXT_A)],
        )
        repo = SqlAlchemyQuizItemRepository(conn)
        repo.upsert(stale, embedding=None)
        repo.create_scheduling(
            stale.id,
            SchedulingSnapshot(
                state=1, step=0, stability=3.5, difficulty=5.0, due=now, last_review=None
            ),
        )
        repo.append_log(stale.id, ReviewLogEntry(rating=3, reviewed_at=now))

    try:
        with patch("app.worker.tasks._build_step", lambda conn: NoOpIngestionStep()):
            _ingest(FakeSelf(), str(source.id), str(job.id))
        with db_engine.connect() as conn:
            reconciled = SqlAlchemyQuizItemRepository(conn).get_by_id(stale.id)
        assert reconciled.status == QuizItemStatus.ACTIVE
    finally:
        with db_engine.begin() as conn:
            conn.execute(sa_delete(users).where(users.c.id == user.id))


# --- enqueuer (QUIZ-03) ---------------------------------------------------------


def test_celery_quiz_enqueuer_applies_async_with_ids_only() -> None:
    source_id, job_id = uuid4(), uuid4()

    with patch("app.worker.tasks.generate_quiz_deck.apply_async") as apply_async:
        CeleryQuizDeckEnqueuer().enqueue_quiz_deck(source_id=source_id, job_id=job_id)

    apply_async.assert_called_once_with(args=[str(source_id), str(job_id)])
