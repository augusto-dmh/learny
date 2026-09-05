"""Idempotent shared-sample seed (operator, object, source, templates, enqueue).

Store-then-persist matches CreateSource: a storage failure leaves no sample row.
The service never marks the source ``ready`` — the worker does that after a
successful ingest. Enqueue is invoked by ``__call__`` so unit tests can inject a
failing enqueuer; the CLI commits ``persist`` first, then enqueues (AD-016).
Corpus chunks and embeddings are not cloned here: one ``is_sample`` source is
shared (FS-06).
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from app.application.errors import EnqueueFailed, StorageUnavailable
from app.application.ingestion import (
    SOURCE_STATUS_FAILED,
    SOURCE_STATUS_PROCESSING,
)
from app.application.quiz_qc import content_key
from app.application.validation import (
    EPUB_CONTENT_TYPE,
    EPUB_EXTENSION,
    SAMPLE_OPERATOR_EMAIL,
)
from app.domain.entities import (
    IngestionEvent,
    IngestionEventType,
    IngestionJob,
    IngestionStatus,
    QuizItem,
    QuizItemOrigin,
    QuizItemStatus,
    QuizItemType,
    Source,
    User,
)
from app.domain.ports import (
    Clock,
    CredentialRepository,
    IngestionEnqueuer,
    IngestionEventRepository,
    IngestionJobRepository,
    QuizItemRepository,
    SchedulingPort,
    SourceRepository,
    StoragePort,
    UserRepository,
)

SAMPLE_TITLE = "The Art of War"
SAMPLE_FILENAME = "art-of-war.epub"
SAMPLE_ENQUEUE_ERROR = "Failed to enqueue ingestion task."

logger = logging.getLogger(__name__)


class SampleOperatorReserved(Exception):
    """The operator email already belongs to a password account."""


# Operator-owned deck templates cloned per learner by EnsureStarterDeck. Distinct
# content_keys so the per-source deck unique holds five rows.
_TEMPLATE_CARDS: tuple[tuple[str, str], ...] = (
    (
        "What does Sun Tzu mean by “all warfare is based on deception”?",
        "Appear weak when you are strong, and strong when you are weak.",
    ),
    (
        "What is of supreme importance in war?",
        "To attack the enemy's strategy.",
    ),
    (
        "When should a general fight?",
        "When it is in the army's interest; avoid what is not.",
    ),
    (
        "How does Sun Tzu describe a victorious army?",
        "One that wins first and then seeks battle.",
    ),
    (
        "What must a commander know to be sure of victory?",
        "Know the enemy and know yourself.",
    ),
)


class SeedSample:
    """Insert the shared sample once: operator, bytes, source, five templates, job.

    A second call returns the existing ``is_sample`` source and does not insert
    again. ``__call__`` enqueues after persist; enqueue failure marks the new
    source ``failed``, never ``ready``.
    """

    def __init__(
        self,
        *,
        users: UserRepository,
        credentials: CredentialRepository,
        sources: SourceRepository,
        storage: StoragePort,
        jobs: IngestionJobRepository,
        events: IngestionEventRepository,
        items: QuizItemRepository,
        scheduling: SchedulingPort,
        clock: Clock,
        ids: Callable[[], UUID],
        epub_bytes: bytes,
        enqueuer: IngestionEnqueuer | None = None,
    ) -> None:
        self._users = users
        self._credentials = credentials
        self._sources = sources
        self._storage = storage
        self._jobs = jobs
        self._events = events
        self._items = items
        self._scheduling = scheduling
        self._clock = clock
        self._ids = ids
        self._epub_bytes = epub_bytes
        self._enqueuer = enqueuer

    def persist(self) -> tuple[Source, IngestionJob | None]:
        """Create the sample if missing.

        Return ``(source, job)``. ``job`` is None when the sample already exists.
        """
        existing = self._sources.get_sample()
        if existing is not None:
            return existing, None

        now = self._clock.now()
        operator = self._ensure_operator(now)
        source_id = self._ids()
        object_key = f"sources/{operator.id}/{source_id}{EPUB_EXTENSION}"
        try:
            self._storage.put_object(object_key, self._epub_bytes, content_type=EPUB_CONTENT_TYPE)
        except Exception as exc:
            raise StorageUnavailable("Could not store the uploaded file.") from exc

        source = self._sources.add(
            Source(
                id=source_id,
                user_id=operator.id,
                title=SAMPLE_TITLE,
                filename=SAMPLE_FILENAME,
                content_type=EPUB_CONTENT_TYPE,
                byte_size=len(self._epub_bytes),
                checksum=hashlib.sha256(self._epub_bytes).hexdigest(),
                object_key=object_key,
                status="uploaded",
                created_at=now,
                updated_at=now,
                is_sample=True,
            )
        )
        job = self._jobs.add(
            IngestionJob(
                id=self._ids(),
                source_id=source.id,
                status=IngestionStatus.QUEUED,
                attempts=0,
                last_error=None,
                created_at=now,
                updated_at=now,
            )
        )
        self._sources.set_status(source.id, SOURCE_STATUS_PROCESSING, now)
        source = self._sources.get_by_id(source.id) or source
        self._events.append(
            IngestionEvent(
                id=self._ids(),
                job_id=job.id,
                type=IngestionEventType.QUEUED,
                message=None,
                created_at=now,
            )
        )
        self._insert_templates(source, operator.id, now)
        return source, job

    def __call__(self) -> Source:
        source, job = self.persist()
        if job is None:
            return source
        if self._enqueuer is None:
            return source
        try:
            self._enqueuer.enqueue_ingestion(
                source_id=source.id,
                job_id=job.id,
                content_type=source.content_type,
            )
        except Exception as exc:
            now = self._clock.now()
            self._jobs.update(job.failed(now, SAMPLE_ENQUEUE_ERROR))
            self._sources.set_status(source.id, SOURCE_STATUS_FAILED, now)
            self._events.append(
                IngestionEvent(
                    id=self._ids(),
                    job_id=job.id,
                    type=IngestionEventType.FAILED,
                    message=SAMPLE_ENQUEUE_ERROR,
                    created_at=now,
                )
            )
            logger.warning(
                "sample seed enqueue failed",
                extra={"source_id": str(source.id), "job_id": str(job.id)},
            )
            raise EnqueueFailed("Could not start ingestion.") from exc
        return self._sources.get_by_id(source.id) or source

    def _ensure_operator(self, now: datetime) -> User:
        existing = self._users.get_by_email(SAMPLE_OPERATOR_EMAIL)
        if existing is not None:
            if self._credentials.get_by_user_id(existing.id) is not None:
                raise SampleOperatorReserved("sample operator email is already registered")
            return existing
        return self._users.add(User(id=self._ids(), email=SAMPLE_OPERATOR_EMAIL, created_at=now))

    def _insert_templates(self, source: Source, operator_id: UUID, now: datetime) -> None:
        initial = self._scheduling.initial()
        for question, answer in _TEMPLATE_CARDS:
            excerpt = f"{question} {answer}"
            item = QuizItem(
                id=self._ids(),
                source_id=source.id,
                user_id=operator_id,
                origin=QuizItemOrigin.DECK,
                item_type=QuizItemType.FREE_RECALL,
                question=question,
                answer=answer,
                section_path=("I. Laying Plans",),
                anchor="ch1.xhtml",
                source_excerpt=excerpt,
                chunk_hash=hashlib.sha256(excerpt.encode()).hexdigest(),
                content_key=content_key(QuizItemType.FREE_RECALL, question, answer),
                status=QuizItemStatus.ACTIVE,
                generation_meta={},
                created_at=now,
                updated_at=now,
            )
            if self._items.upsert(item, embedding=None):
                self._items.create_scheduling(item.id, initial)
