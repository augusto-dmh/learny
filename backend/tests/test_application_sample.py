"""Shared-sample seed (FS-06, unit, in-memory fakes).

Tests inject synthetic EPUB bytes. They never ingest a 24k-word book.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.application.errors import EnqueueFailed, StorageUnavailable
from app.application.ingestion import SOURCE_STATUS_FAILED, SOURCE_STATUS_PROCESSING
from app.application.sample import (
    SAMPLE_OPERATOR_EMAIL,
    SAMPLE_TITLE,
    SampleOperatorReserved,
    SeedSample,
)
from app.domain.entities import (
    PasswordCredential,
    QuizItem,
    QuizItemOrigin,
    SchedulingSnapshot,
    User,
)
from tests.fakes import (
    FailingStorage,
    FakeClock,
    FakeCredentialRepository,
    FakeIngestionEnqueuer,
    FakeIngestionEventRepository,
    FakeIngestionJobRepository,
    FakeSourceRepository,
    FakeStorage,
    FakeUserRepository,
)

_NOW = datetime(2026, 7, 16, 12, 0, 0, tzinfo=UTC)
_SYNTHETIC_EPUB = b"PK\x03\x04-synthetic-sample-epub"


class _FakeQuizItems:
    def __init__(self) -> None:
        self.items: list[QuizItem] = []
        self.scheduling: dict[UUID, SchedulingSnapshot] = {}

    def upsert(self, item: QuizItem, *, embedding) -> bool:  # noqa: ANN001
        self.items.append(item)
        return True

    def create_scheduling(self, quiz_item_id: UUID, snapshot: SchedulingSnapshot) -> None:
        self.scheduling[quiz_item_id] = snapshot

    def list_for_source(
        self,
        source_id: UUID,
        *,
        origin: QuizItemOrigin | None = None,
        user_id: UUID | None = None,
    ) -> list[QuizItem]:
        return [
            item
            for item in self.items
            if item.source_id == source_id
            and (origin is None or item.origin == origin)
            and (user_id is None or item.user_id == user_id)
        ]


class _InitialScheduling:
    def initial(self) -> SchedulingSnapshot:
        return SchedulingSnapshot(
            state=1, step=0, stability=None, difficulty=None, due=_NOW, last_review=None
        )


def _seed(
    *,
    sources: FakeSourceRepository | None = None,
    storage: FakeStorage | FailingStorage | None = None,
    enqueuer: FakeIngestionEnqueuer | None = None,
    users: FakeUserRepository | None = None,
    credentials: FakeCredentialRepository | None = None,
    items: _FakeQuizItems | None = None,
) -> tuple[SeedSample, FakeSourceRepository, FakeIngestionEnqueuer, _FakeQuizItems]:
    sources = sources if sources is not None else FakeSourceRepository()
    storage = storage if storage is not None else FakeStorage()
    enqueuer = enqueuer if enqueuer is not None else FakeIngestionEnqueuer()
    users = users if users is not None else FakeUserRepository()
    credentials = credentials if credentials is not None else FakeCredentialRepository()
    items = items if items is not None else _FakeQuizItems()
    seed = SeedSample(
        users=users,
        credentials=credentials,
        sources=sources,
        storage=storage,
        jobs=FakeIngestionJobRepository(),
        events=FakeIngestionEventRepository(),
        items=items,
        scheduling=_InitialScheduling(),
        clock=FakeClock(_NOW),
        ids=uuid4,
        epub_bytes=_SYNTHETIC_EPUB,
        enqueuer=enqueuer,
    )
    return seed, sources, enqueuer, items


def test_seed_when_sample_exists_returns_that_source_without_a_second_insert() -> None:
    seed, sources, enqueuer, _items = _seed()
    first = seed()
    add_calls = sources.add_calls
    enqueue_calls = list(enqueuer.calls)

    second = seed()

    assert second.id == first.id
    assert sources.add_calls == add_calls == 1
    assert enqueuer.calls == enqueue_calls
    assert len([s for s in sources.list_by_user(uuid4()) if s.is_sample]) == 1


def test_enqueue_failure_leaves_no_ready_sample() -> None:
    enqueuer = FakeIngestionEnqueuer(error=RuntimeError("broker down"))
    seed, sources, _enqueuer, _items = _seed(enqueuer=enqueuer)

    with pytest.raises(EnqueueFailed):
        seed()

    sample = sources.get_sample()
    assert sample is not None
    assert sample.is_sample is True
    assert sample.status == SOURCE_STATUS_FAILED
    assert sample.status != "ready"


def test_storage_failure_leaves_no_sample_source() -> None:
    seed, sources, enqueuer, _items = _seed(storage=FailingStorage())

    with pytest.raises(StorageUnavailable):
        seed()

    assert sources.get_sample() is None
    assert sources.add_calls == 0
    assert enqueuer.calls == []


def test_successful_seed_is_processing_not_ready_and_does_not_clone_corpus() -> None:
    seed, sources, enqueuer, items = _seed()

    sample = seed()
    other_user_id = uuid4()
    listed = sources.list_by_user(other_user_id)

    assert sample.title == SAMPLE_TITLE
    assert sample.is_sample is True
    assert sample.status == SOURCE_STATUS_PROCESSING
    assert sample.status != "ready"
    assert sources.get_sample() is not None
    assert sources.get_sample().id == sample.id
    # Two learners see the same sample row: list_by_user unions is_sample, and
    # seed never inserts a per-user corpus or a second sample (FS-06).
    assert listed == [sample]
    assert sources.add_calls == 1
    templates = [i for i in items.list_for_source(sample.id) if i.origin == QuizItemOrigin.DECK]
    assert len(templates) == 5
    assert all(item.user_id == sample.user_id for item in templates)
    assert len(enqueuer.calls) == 1
    assert enqueuer.calls[0][0] == sample.id


def test_seed_creates_operator_without_inserting_a_second_user_on_repeat() -> None:
    users = FakeUserRepository()
    seed, _sources, _enqueuer, _items = _seed(users=users)
    seed()
    seed()

    assert users.get_by_email(SAMPLE_OPERATOR_EMAIL) is not None
    assert len(users._by_id) == 1


def test_seed_refuses_a_password_account_at_the_operator_email() -> None:
    users = FakeUserRepository()
    credentials = FakeCredentialRepository()
    existing = users.add(User(id=uuid4(), email=SAMPLE_OPERATOR_EMAIL, created_at=_NOW))
    credentials.add(
        PasswordCredential(
            user_id=existing.id,
            password_hash="hashed",
            algo_params={},
            updated_at=_NOW,
        )
    )
    seed, sources, _enqueuer, _items = _seed(users=users, credentials=credentials)

    with pytest.raises(SampleOperatorReserved):
        seed()

    assert sources.get_sample() is None
