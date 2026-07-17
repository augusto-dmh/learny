"""C1 gate — deck generation services (unit, in-memory fakes).

Covers the deck use cases against the spec ACs with no DB: ``PlanDeckGeneration``
(QUIZ-03/04 + ownership), ``RunDeckGeneration`` grounding/cloze/dedup/upsert
pipeline (QUIZ-02/06/07/08/09/10) and its lifecycle transitions, and
``ListQuizItems`` (QUIZ-14). The QC pipeline is exercised through ``finalize`` with
hand-built candidates so each discard branch is asserted on the resulting counts +
persisted state, not on mock call counts alone.
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import UTC, datetime
from itertools import count
from uuid import UUID, uuid4

import pytest

from app.application.errors import QuizDeckConflict, SourceNotFound, SourceNotReady
from app.application.identity import AuthorizeOwnership
from app.application.quiz import (
    ListQuizItems,
    PlanDeckGeneration,
    RunDeckGeneration,
)
from app.application.quiz_qc import CLOZE_BLANK, content_key
from app.domain.entities import (
    QuizCandidate,
    QuizDeckResult,
    QuizGenerationJob,
    QuizItem,
    QuizItemStatus,
    QuizItemType,
    QuizJobStatus,
    QuizSection,
    SchedulingSnapshot,
    Source,
    User,
)
from tests.fakes import FakeClock, FakeSourceRepository

_NOW = datetime(2026, 7, 16, 12, 0, 0, tzinfo=UTC)


# --- fakes ----------------------------------------------------------------------


class FakeQuizJobRepository:
    """In-memory ``QuizJobRepository`` (add/get/active/latest/update)."""

    def __init__(self) -> None:
        self._by_id: dict[UUID, QuizGenerationJob] = {}

    def add(self, job: QuizGenerationJob) -> QuizGenerationJob:
        self._by_id[job.id] = job
        return job

    def get_by_id(self, job_id: UUID) -> QuizGenerationJob | None:
        return self._by_id.get(job_id)

    def get_active_for_source(self, source_id: UUID) -> QuizGenerationJob | None:
        active = [
            j
            for j in self._by_id.values()
            if j.source_id == source_id
            and j.status in {QuizJobStatus.QUEUED, QuizJobStatus.RUNNING}
        ]
        return max(active, key=lambda j: j.created_at) if active else None

    def get_latest_for_source(self, source_id: UUID) -> QuizGenerationJob | None:
        owned = [j for j in self._by_id.values() if j.source_id == source_id]
        return max(owned, key=lambda j: j.created_at) if owned else None

    def update(self, job: QuizGenerationJob) -> QuizGenerationJob:
        self._by_id[job.id] = job
        return job


class FakeQuizItemRepository:
    """In-memory ``QuizItemRepository`` — coherent upsert / scheduling / reads.

    ``upsert`` keys on ``(source_id, content_key)`` and returns ``True`` only on a
    genuine insert, so ``finalize`` creates scheduling exactly once per item; a
    re-upsert returns ``False`` and never touches the recorded scheduling snapshot
    (QUIZ-02). ``sections_for_generation`` returns a preset list.
    """

    def __init__(self, sections: list[QuizSection] | None = None) -> None:
        self._sections = sections or []
        self._items: dict[tuple[UUID, str], QuizItem] = {}
        self._embeddings: dict[UUID, list[float]] = {}
        self.scheduling: dict[UUID, SchedulingSnapshot] = {}
        self.create_scheduling_calls = 0
        self.update_scheduling_calls = 0

    def seed(self, item: QuizItem, embedding: list[float]) -> None:
        self._items[(item.source_id, item.content_key)] = item
        self._embeddings[item.id] = embedding
        self.scheduling[item.id] = _INITIAL

    def sections_for_generation(
        self, source_id: UUID, *, min_chars: int
    ) -> list[QuizSection]:
        return list(self._sections)

    def existing_embeddings(self, source_id: UUID) -> list[tuple[UUID, list[float]]]:
        return [
            (item.id, self._embeddings[item.id])
            for key, item in self._items.items()
            if key[0] == source_id and item.id in self._embeddings
        ]

    def upsert(self, item: QuizItem, *, embedding) -> bool:  # noqa: ANN001
        key = (item.source_id, item.content_key)
        inserted = key not in self._items
        if inserted:
            self._items[key] = item
        else:
            existing = self._items[key]
            self._items[key] = replace(
                item, id=existing.id, created_at=existing.created_at
            )
        target_id = self._items[key].id
        if embedding is not None:
            self._embeddings[target_id] = list(embedding)
        return inserted

    def create_scheduling(self, quiz_item_id: UUID, snapshot: SchedulingSnapshot) -> None:
        self.create_scheduling_calls += 1
        self.scheduling[quiz_item_id] = snapshot

    def update_scheduling(self, quiz_item_id: UUID, snapshot: SchedulingSnapshot) -> None:
        self.update_scheduling_calls += 1
        self.scheduling[quiz_item_id] = snapshot

    def list_for_source(self, source_id: UUID) -> list[QuizItem]:
        return [item for key, item in self._items.items() if key[0] == source_id]

    def counts_by_status(self, source_id: UUID) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.list_for_source(source_id):
            counts[item.status] = counts.get(item.status, 0) + 1
        return counts

    def due_map(self, source_id: UUID) -> dict[UUID, datetime]:
        return {
            item.id: self.scheduling[item.id].due
            for item in self.list_for_source(source_id)
            if item.id in self.scheduling
        }


_INITIAL = SchedulingSnapshot(
    state=1, step=0, stability=None, difficulty=None, due=_NOW, last_review=None
)


class FakeScheduling:
    """``SchedulingPort`` double whose ``initial`` returns a known snapshot."""

    def initial(self) -> SchedulingSnapshot:
        return _INITIAL

    def review(self, snapshot, rating, reviewed_at):  # noqa: ANN001, ANN201
        raise NotImplementedError


class FakeEmbedding:
    """``EmbeddingPort`` double mapping exact texts to preset vectors.

    Unmapped texts get a unique orthogonal basis vector, so distinct candidates never
    collide unless a test deliberately maps them to a similar vector (QUIZ-08).
    """

    model = "fake-embedding@2"

    def __init__(self, vectors: dict[str, list[float]] | None = None) -> None:
        self._vectors = vectors or {}
        self._counter = count()

    def embed_query(self, text: str) -> list[float]:
        if text in self._vectors:
            return list(self._vectors[text])
        basis = [0.0] * 64
        basis[next(self._counter) % 64] = 1.0
        return basis

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(t) for t in texts]


class FakeGeneration:
    """``QuizGenerationPort`` double: replays a preset handle/result, records calls."""

    model = "fake-generation@1"

    def __init__(self, result: QuizDeckResult | None = None) -> None:
        self._result = result
        self.begin_calls: list[list[QuizSection]] = []

    def begin_deck(self, sections):  # noqa: ANN001, ANN201
        from app.domain.entities import QuizDeckHandle

        self.begin_calls.append(list(sections))
        return QuizDeckHandle(provider="fake")

    def collect_deck(self, handle):  # noqa: ANN001, ANN201
        return self._result


# --- helpers --------------------------------------------------------------------


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def _unit_at(cosine: float) -> list[float]:
    """A unit vector whose cosine with ``[1, 0]`` is exactly ``cosine``."""
    return [cosine, math.sqrt(max(0.0, 1.0 - cosine * cosine))]


_OWNER = User(id=uuid4(), email="o@x.com", created_at=_NOW)
_CHUNK_ID = uuid4()
_CHUNK_TEXT = "The mitochondria is the powerhouse of the cell and makes energy."
_SECTION = QuizSection(
    section_path=("Chapter 1", "Cells"),
    anchor="ch1#cells",
    title="Cells",
    chunks=((_CHUNK_ID, _CHUNK_TEXT),),
)


def _source(user_id: UUID, status: str = "ready") -> Source:
    return Source(
        id=uuid4(),
        user_id=user_id,
        title="Biology",
        filename="bio.epub",
        content_type="application/epub+zip",
        byte_size=10,
        checksum="a" * 64,
        object_key=f"sources/{uuid4()}.epub",
        status=status,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _job(source_id: UUID, status: str = QuizJobStatus.QUEUED) -> QuizGenerationJob:
    return QuizGenerationJob(
        id=uuid4(),
        source_id=source_id,
        status=status,
        attempts=0,
        generated_count=0,
        discarded_count=0,
        failed_sections=0,
        last_error=None,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _run_service(
    jobs: FakeQuizJobRepository,
    items: FakeQuizItemRepository,
    *,
    embeddings: FakeEmbedding | None = None,
    generation: FakeGeneration | None = None,
    threshold: float = 0.9,
) -> RunDeckGeneration:
    return RunDeckGeneration(
        jobs=jobs,
        items=items,
        generation=generation or FakeGeneration(),
        embeddings=embeddings or FakeEmbedding(),
        scheduling=FakeScheduling(),
        clock=FakeClock(_NOW),
        ids=lambda: uuid4(),
        min_section_chars=200,
        dedup_threshold=threshold,
    )


def _free_recall(question: str, answer: str, quote: str) -> QuizCandidate:
    return QuizCandidate(
        item_type=QuizItemType.FREE_RECALL,
        question=question,
        answer=answer,
        source_chunk_id=_CHUNK_ID,
        anchor_quote=quote,
    )


# --- PlanDeckGeneration (QUIZ-03/04 + ownership) ---------------------------------


def _plan(sources: FakeSourceRepository, jobs: FakeQuizJobRepository) -> PlanDeckGeneration:
    return PlanDeckGeneration(
        sources=sources,
        jobs=jobs,
        authorize=AuthorizeOwnership(),
        clock=FakeClock(_NOW),
        ids=lambda: uuid4(),
    )


def test_plan_creates_queued_job_for_ready_owned_source() -> None:
    sources, jobs = FakeSourceRepository(), FakeQuizJobRepository()
    source = _source(_OWNER.id, status="ready")
    sources.add(source)

    job = _plan(sources, jobs)(user=_OWNER, source_id=source.id)

    assert job.status == QuizJobStatus.QUEUED
    assert job.source_id == source.id
    assert (job.generated_count, job.discarded_count, job.failed_sections) == (0, 0, 0)
    assert jobs.get_by_id(job.id) is job  # persisted, not enqueued here (QUIZ-03)


def test_plan_rejects_not_ready_source() -> None:
    sources, jobs = FakeSourceRepository(), FakeQuizJobRepository()
    source = _source(_OWNER.id, status="processing")
    sources.add(source)

    with pytest.raises(SourceNotReady):
        _plan(sources, jobs)(user=_OWNER, source_id=source.id)
    assert jobs.get_latest_for_source(source.id) is None  # nothing created


def test_plan_conflicts_when_active_job_exists() -> None:
    sources, jobs = FakeSourceRepository(), FakeQuizJobRepository()
    source = _source(_OWNER.id, status="ready")
    sources.add(source)
    jobs.add(_job(source.id, status=QuizJobStatus.RUNNING))

    with pytest.raises(QuizDeckConflict):
        _plan(sources, jobs)(user=_OWNER, source_id=source.id)


def test_plan_hides_non_owner_and_missing_as_not_found() -> None:
    sources, jobs = FakeSourceRepository(), FakeQuizJobRepository()
    source = _source(_OWNER.id, status="ready")
    sources.add(source)
    stranger = User(id=uuid4(), email="s@x.com", created_at=_NOW)

    with pytest.raises(SourceNotFound):
        _plan(sources, jobs)(user=stranger, source_id=source.id)
    with pytest.raises(SourceNotFound):
        _plan(sources, jobs)(user=_OWNER, source_id=uuid4())


# --- RunDeckGeneration lifecycle -------------------------------------------------


def test_begin_claims_queued_job_as_running() -> None:
    jobs, items = FakeQuizJobRepository(), FakeQuizItemRepository([_SECTION])
    job = jobs.add(_job(uuid4(), status=QuizJobStatus.QUEUED))

    running = _run_service(jobs, items).begin(job.id)

    assert running.status == QuizJobStatus.RUNNING
    assert running.attempts == 1


def test_begin_is_noop_for_missing_or_terminal_job() -> None:
    jobs, items = FakeQuizJobRepository(), FakeQuizItemRepository([_SECTION])
    terminal = jobs.add(_job(uuid4(), status=QuizJobStatus.SUCCEEDED))

    assert _run_service(jobs, items).begin(uuid4()) is None
    assert _run_service(jobs, items).begin(terminal.id) is None


def test_fail_marks_job_failed_with_last_error() -> None:
    jobs, items = FakeQuizJobRepository(), FakeQuizItemRepository([_SECTION])
    job = jobs.add(_job(uuid4(), status=QuizJobStatus.RUNNING))

    failed = _run_service(jobs, items).fail(job.id, "timeout")

    assert failed.status == QuizJobStatus.FAILED
    assert failed.last_error == "timeout"


def test_begin_deck_passes_eligible_sections_to_the_port() -> None:
    jobs, items = FakeQuizJobRepository(), FakeQuizItemRepository([_SECTION])
    generation = FakeGeneration()
    service = _run_service(jobs, items, generation=generation)

    service.begin_deck(uuid4())

    assert generation.begin_calls == [[_SECTION]]


def test_collect_returns_none_while_pending() -> None:
    jobs, items = FakeQuizJobRepository(), FakeQuizItemRepository([_SECTION])
    generation = FakeGeneration(result=None)  # batch still in progress
    from app.domain.entities import QuizDeckHandle

    assert (
        _run_service(jobs, items, generation=generation).collect(
            QuizDeckHandle(provider="fake")
        )
        is None
    )


# --- finalize: grounding / cloze / typing (QUIZ-06/07/10) ------------------------


def test_finalize_persists_grounded_item_with_snapshot_and_scheduling() -> None:
    jobs, items = FakeQuizJobRepository(), FakeQuizItemRepository([_SECTION])
    job = jobs.add(_job(uuid4(), status=QuizJobStatus.RUNNING))
    candidate = _free_recall(
        "What is the powerhouse of the cell?",
        "The mitochondria",
        "mitochondria is the powerhouse of the cell",
    )

    done = _run_service(jobs, items).finalize(
        job.id, QuizDeckResult(candidates=(candidate,), errors=())
    )

    assert done.status == QuizJobStatus.SUCCEEDED
    assert (done.generated_count, done.discarded_count) == (1, 0)
    persisted = items.list_for_source(job.source_id)
    assert len(persisted) == 1
    item = persisted[0]
    # Snapshot columns are stored from the verified quote + section (QUIZ-06).
    assert item.source_excerpt == "mitochondria is the powerhouse of the cell"
    assert item.section_path == ("Chapter 1", "Cells")
    assert item.anchor == "ch1#cells"
    assert item.status == QuizItemStatus.ACTIVE
    # A new item gets exactly one initial scheduling row (QUIZ-09).
    assert items.create_scheduling_calls == 1
    assert items.scheduling[item.id] == _INITIAL


def test_finalize_discards_unverbatim_quote() -> None:
    jobs, items = FakeQuizJobRepository(), FakeQuizItemRepository([_SECTION])
    job = jobs.add(_job(uuid4(), status=QuizJobStatus.RUNNING))
    candidate = _free_recall("Q?", "A", "this phrase is absent from the chunk")

    done = _run_service(jobs, items).finalize(
        job.id, QuizDeckResult(candidates=(candidate,), errors=())
    )

    assert (done.generated_count, done.discarded_count) == (0, 1)
    assert items.list_for_source(job.source_id) == []


def test_finalize_discards_candidate_citing_unknown_chunk() -> None:
    jobs, items = FakeQuizJobRepository(), FakeQuizItemRepository([_SECTION])
    job = jobs.add(_job(uuid4(), status=QuizJobStatus.RUNNING))
    candidate = QuizCandidate(
        item_type=QuizItemType.FREE_RECALL,
        question="Q?",
        answer="A",
        source_chunk_id=uuid4(),  # not in the section's chunks
        anchor_quote="mitochondria is the powerhouse of the cell",
    )

    done = _run_service(jobs, items).finalize(
        job.id, QuizDeckResult(candidates=(candidate,), errors=())
    )

    assert (done.generated_count, done.discarded_count) == (0, 1)


def test_finalize_discards_invalid_cloze() -> None:
    jobs, items = FakeQuizJobRepository(), FakeQuizItemRepository([_SECTION])
    job = jobs.add(_job(uuid4(), status=QuizJobStatus.RUNNING))
    # answer ("energy") is not the masked span of the anchor_quote, and no blank.
    bad_cloze = QuizCandidate(
        item_type=QuizItemType.CLOZE,
        question="The mitochondria is the powerhouse of the cell.",
        answer="chloroplast",
        source_chunk_id=_CHUNK_ID,
        anchor_quote="mitochondria is the powerhouse of the cell",
    )

    done = _run_service(jobs, items).finalize(
        job.id, QuizDeckResult(candidates=(bad_cloze,), errors=())
    )

    assert (done.generated_count, done.discarded_count) == (0, 1)


def test_finalize_keeps_valid_cloze() -> None:
    jobs, items = FakeQuizJobRepository(), FakeQuizItemRepository([_SECTION])
    job = jobs.add(_job(uuid4(), status=QuizJobStatus.RUNNING))
    good_cloze = QuizCandidate(
        item_type=QuizItemType.CLOZE,
        question=f"The {CLOZE_BLANK} is the powerhouse of the cell.",
        answer="mitochondria",
        source_chunk_id=_CHUNK_ID,
        anchor_quote="mitochondria is the powerhouse of the cell",
    )

    done = _run_service(jobs, items).finalize(
        job.id, QuizDeckResult(candidates=(good_cloze,), errors=())
    )

    assert (done.generated_count, done.discarded_count) == (1, 0)


def test_finalize_discards_non_free_recall_or_cloze_type() -> None:
    jobs, items = FakeQuizJobRepository(), FakeQuizItemRepository([_SECTION])
    job = jobs.add(_job(uuid4(), status=QuizJobStatus.RUNNING))
    mcq = QuizCandidate(
        item_type="mcq",
        question="Q?",
        answer="A",
        source_chunk_id=_CHUNK_ID,
        anchor_quote="mitochondria is the powerhouse of the cell",
    )

    done = _run_service(jobs, items).finalize(
        job.id, QuizDeckResult(candidates=(mcq,), errors=())
    )

    assert (done.generated_count, done.discarded_count) == (0, 1)
    assert items.list_for_source(job.source_id) == []


# --- finalize: dedup (QUIZ-08) ---------------------------------------------------


def test_finalize_discards_near_duplicate_within_run_at_threshold() -> None:
    jobs, items = FakeQuizJobRepository(), FakeQuizItemRepository([_SECTION])
    job = jobs.add(_job(uuid4(), status=QuizJobStatus.RUNNING))
    first = _free_recall("Q one?", "A one", "mitochondria is the powerhouse")
    second = _free_recall("Q two?", "A two", "makes energy")
    embed = FakeEmbedding(
        {"Q one?\nA one": [1.0, 0.0], "Q two?\nA two": _unit_at(0.9)}
    )
    assert _cosine([1.0, 0.0], _unit_at(0.9)) == pytest.approx(0.9)

    done = _run_service(jobs, items, embeddings=embed, threshold=0.9).finalize(
        job.id, QuizDeckResult(candidates=(first, second), errors=())
    )

    # cosine == threshold ⇒ the second is discarded (≥, QUIZ-08).
    assert (done.generated_count, done.discarded_count) == (1, 1)


def test_finalize_keeps_below_threshold_candidate() -> None:
    jobs, items = FakeQuizJobRepository(), FakeQuizItemRepository([_SECTION])
    job = jobs.add(_job(uuid4(), status=QuizJobStatus.RUNNING))
    first = _free_recall("Q one?", "A one", "mitochondria is the powerhouse")
    second = _free_recall("Q two?", "A two", "makes energy")
    embed = FakeEmbedding(
        {"Q one?\nA one": [1.0, 0.0], "Q two?\nA two": _unit_at(0.8)}
    )

    done = _run_service(jobs, items, embeddings=embed, threshold=0.9).finalize(
        job.id, QuizDeckResult(candidates=(first, second), errors=())
    )

    assert (done.generated_count, done.discarded_count) == (2, 0)


def test_finalize_dedups_against_persisted_items() -> None:
    jobs = FakeQuizJobRepository()
    items = FakeQuizItemRepository([_SECTION])
    job = jobs.add(_job(uuid4(), status=QuizJobStatus.RUNNING))
    # A pre-existing item (different content_key) with a known embedding.
    prior = QuizItem(
        id=uuid4(),
        source_id=job.source_id,
        item_type=QuizItemType.FREE_RECALL,
        question="Prior?",
        answer="Prior",
        section_path=("Chapter 1", "Cells"),
        anchor="ch1#cells",
        source_excerpt="mitochondria is the powerhouse",
        chunk_hash="h",
        content_key=content_key(QuizItemType.FREE_RECALL, "Prior?", "Prior"),
        status=QuizItemStatus.ACTIVE,
        generation_meta={},
        created_at=_NOW,
        updated_at=_NOW,
    )
    items.seed(prior, [1.0, 0.0])
    candidate = _free_recall("New?", "New", "makes energy")
    embed = FakeEmbedding({"New?\nNew": [1.0, 0.0]})

    done = _run_service(jobs, items, embeddings=embed, threshold=0.9).finalize(
        job.id, QuizDeckResult(candidates=(candidate,), errors=())
    )

    assert (done.generated_count, done.discarded_count) == (0, 1)


# --- finalize: upsert preserves scheduling, idempotency (QUIZ-02/09) -------------


def test_finalize_reupsert_preserves_scheduling_and_count() -> None:
    jobs, items = FakeQuizJobRepository(), FakeQuizItemRepository([_SECTION])
    candidate = _free_recall(
        "What is the powerhouse?",
        "The mitochondria",
        "mitochondria is the powerhouse of the cell",
    )
    result = QuizDeckResult(candidates=(candidate,), errors=())

    job1 = jobs.add(_job(uuid4(), status=QuizJobStatus.RUNNING))
    first = _run_service(jobs, items).finalize(job1.id, result)
    after_first = items.create_scheduling_calls

    # A second pass (redelivery / regeneration) over the same source + candidate.
    job2 = jobs.add(
        replace(_job(job1.source_id, status=QuizJobStatus.RUNNING), created_at=_NOW)
    )
    second = _run_service(jobs, items).finalize(job2.id, result)

    # Same accepted count both runs; no duplicate item; scheduling never re-created
    # or updated (QUIZ-02 / QUIZ-09 idempotent re-run).
    assert first.generated_count == second.generated_count == 1
    assert len(items.list_for_source(job1.source_id)) == 1
    assert items.create_scheduling_calls == after_first  # no new scheduling row
    assert items.update_scheduling_calls == 0


def test_finalize_zero_candidates_succeeds_with_zero_counts() -> None:
    jobs, items = FakeQuizJobRepository(), FakeQuizItemRepository([])
    job = jobs.add(_job(uuid4(), status=QuizJobStatus.RUNNING))

    done = _run_service(jobs, items).finalize(
        job.id, QuizDeckResult(candidates=(), errors=())
    )

    assert done.status == QuizJobStatus.SUCCEEDED
    assert (done.generated_count, done.discarded_count, done.failed_sections) == (0, 0, 0)


def test_finalize_counts_failed_sections_but_still_succeeds() -> None:
    jobs, items = FakeQuizJobRepository(), FakeQuizItemRepository([_SECTION])
    job = jobs.add(_job(uuid4(), status=QuizJobStatus.RUNNING))
    candidate = _free_recall(
        "What is the powerhouse?",
        "mitochondria",
        "mitochondria is the powerhouse of the cell",
    )

    done = _run_service(jobs, items).finalize(
        job.id,
        QuizDeckResult(candidates=(candidate,), errors=("section 3 failed",)),
    )

    # Partial success: the good section persists, the failed one is only counted.
    assert done.status == QuizJobStatus.SUCCEEDED
    assert (done.generated_count, done.failed_sections) == (1, 1)


# --- ListQuizItems (QUIZ-14) -----------------------------------------------------


def test_list_quiz_items_returns_overview_for_owner() -> None:
    sources, jobs, items = (
        FakeSourceRepository(),
        FakeQuizJobRepository(),
        FakeQuizItemRepository([_SECTION]),
    )
    source = _source(_OWNER.id, status="ready")
    sources.add(source)
    job = jobs.add(_job(source.id, status=QuizJobStatus.SUCCEEDED))
    candidate = _free_recall(
        "What is the powerhouse?",
        "mitochondria",
        "mitochondria is the powerhouse of the cell",
    )
    run_job = jobs.add(replace(_job(source.id, status=QuizJobStatus.RUNNING)))
    _run_service(jobs, items).finalize(
        run_job.id, QuizDeckResult(candidates=(candidate,), errors=())
    )

    overview = ListQuizItems(
        sources=sources, items=items, jobs=jobs, authorize=AuthorizeOwnership()
    )(user=_OWNER, source_id=source.id)

    assert len(overview.items) == 1
    assert overview.counts_by_status == {QuizItemStatus.ACTIVE: 1}
    assert set(overview.due_by_item.values()) == {_NOW}
    assert overview.latest_job is not None
    assert overview.latest_job.source_id == source.id
    # touch ``job`` so the first (succeeded) seed is not flagged as unused
    assert jobs.get_by_id(job.id).status == QuizJobStatus.SUCCEEDED


def test_list_quiz_items_hides_non_owner() -> None:
    sources, jobs, items = (
        FakeSourceRepository(),
        FakeQuizJobRepository(),
        FakeQuizItemRepository([_SECTION]),
    )
    source = _source(_OWNER.id, status="ready")
    sources.add(source)
    stranger = User(id=uuid4(), email="s@x.com", created_at=_NOW)

    with pytest.raises(SourceNotFound):
        ListQuizItems(
            sources=sources, items=items, jobs=jobs, authorize=AuthorizeOwnership()
        )(user=stranger, source_id=source.id)
