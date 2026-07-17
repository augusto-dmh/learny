"""Quiz deck-generation use-case services (Cycle E, design §Application services).

Framework-free orchestration of the deck path, mirroring the ingestion services
(ADR-007/009): nothing here imports FastAPI, SQLAlchemy, or Celery. ``PlanDeckGeneration``
runs on the HTTP request (create the queued job; the web handler enqueues after commit,
like ``StartIngestion``); ``RunDeckGeneration`` is the worker-side driver whose methods
run one-per-transaction inside the Celery task (the task opens a UoW per call, exactly as
``RunIngestion`` does). ``ListQuizItems`` serves the per-source overview.

The quality-control pipeline (QUIZ-06/07/08) and the ``content_key`` upsert identity
(QUIZ-02) live in ``RunDeckGeneration.finalize`` so grounding holds for every generation
adapter, not per-adapter goodwill. ``finalize`` is idempotent under ``acks_late``
redelivery: re-running it upserts the same items (never a duplicate) and never resets an
existing item's scheduling (QUIZ-09).
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.application.errors import QuizDeckConflict, SourceNotReady
from app.application.identity import AuthorizeOwnership
from app.application.ingestion import SOURCE_STATUS_READY, authorized_source
from app.application.quiz_qc import cloze_is_valid, content_key, quote_in_text
from app.domain.entities import (
    QuizCandidate,
    QuizDeckHandle,
    QuizDeckResult,
    QuizGenerationJob,
    QuizItem,
    QuizItemStatus,
    QuizItemType,
    QuizJobStatus,
    ReconcileSection,
    User,
)
from app.domain.ports import (
    Clock,
    CorpusRepository,
    EmbeddingPort,
    QuizGenerationPort,
    QuizItemRepository,
    QuizJobRepository,
    SchedulingPort,
    SourceRepository,
)

# The two item kinds the QC pipeline accepts (QUIZ-10 — no MCQ anywhere).
_VALID_ITEM_TYPES = frozenset({QuizItemType.FREE_RECALL, QuizItemType.CLOZE})


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Return the cosine similarity of two equal-length vectors (0.0 if either is zero).

    A tiny pure helper (no cosine utility exists elsewhere in the codebase): the dedup
    guard compares a candidate's embedding to already-accepted and persisted item
    embeddings (QUIZ-08).
    """
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _chunk_hash(text: str) -> str:
    """Return the SHA-256 of a chunk's text — the ``chunk_hash`` snapshot (QUIZ-06)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class QuizOverview:
    """The per-source quiz overview read model (QUIZ-14).

    Bundles the source's items (any status) with the per-status counts, the item→due
    map, and the latest deck job (or ``None`` when no deck has been requested) — the
    polling target the library UI reads for deck progress.
    """

    items: list[QuizItem]
    counts_by_status: dict[str, int]
    due_by_item: dict[UUID, datetime]
    latest_job: QuizGenerationJob | None


class PlanDeckGeneration:
    """Create a ``queued`` deck job for an owned, corpus-ready source (QUIZ-03/04).

    Mirrors ``StartIngestion``: ownership is enforced via ``authorized_source`` (missing
    or non-owner → ``SourceNotFound`` → 404, no disclosure); a source whose
    ``status != "ready"`` raises ``SourceNotReady`` (reusing the QA readiness contract)
    before any job is created (QUIZ-03 / edge case); the single-in-flight invariant is
    guarded here (``get_active_for_source`` → ``QuizDeckConflict`` → 409, QUIZ-04). The
    service does *not* enqueue — the web handler orchestrates commit-then-enqueue so the
    worker always dequeues a durable row (AD-016).
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        jobs: QuizJobRepository,
        authorize: AuthorizeOwnership,
        clock: Clock,
        ids: Callable[[], UUID],
    ) -> None:
        self._sources = sources
        self._jobs = jobs
        self._authorize = authorize
        self._clock = clock
        self._ids = ids

    def __call__(self, *, user: User, source_id: UUID) -> QuizGenerationJob:
        source = authorized_source(
            user=user,
            source_id=source_id,
            sources=self._sources,
            authorize=self._authorize,
        )
        if source.status != SOURCE_STATUS_READY:
            # Guard before creating a job so a not-ready source starts nothing (QUIZ-03).
            raise SourceNotReady("Source is not ready for quiz generation.")

        active = self._jobs.get_active_for_source(source_id)
        if active is not None:
            raise QuizDeckConflict("Deck generation is already in progress.")

        now = self._clock.now()
        return self._jobs.add(
            QuizGenerationJob(
                id=self._ids(),
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
        )


class RunDeckGeneration:
    """The background deck driver: one method per durable transition (QUIZ-05/06/07/08/09).

    The Celery task calls these across separate units of work (each built on its own
    connection), exactly as ``RunIngestion`` is driven. ``begin`` claims the job;
    ``begin_deck``/``collect`` bridge the ``QuizGenerationPort`` (inline for the local
    adapter, batch-polled for Anthropic); ``finalize`` runs the QC + dedup pipeline and
    records the terminal success; ``fail`` records terminal failure.
    """

    def __init__(
        self,
        *,
        jobs: QuizJobRepository,
        items: QuizItemRepository,
        generation: QuizGenerationPort,
        embeddings: EmbeddingPort,
        scheduling: SchedulingPort,
        clock: Clock,
        ids: Callable[[], UUID],
        min_section_chars: int,
        dedup_threshold: float,
    ) -> None:
        self._jobs = jobs
        self._items = items
        self._generation = generation
        self._embeddings = embeddings
        self._scheduling = scheduling
        self._clock = clock
        self._ids = ids
        self._min_section_chars = min_section_chars
        self._dedup_threshold = dedup_threshold

    def begin(self, job_id: UUID) -> QuizGenerationJob | None:
        """Transition ``queued``/``running`` → ``running`` (attempts+1); else no-op.

        Returns ``None`` when the job is missing or already terminal (idempotent under
        ``acks_late`` redelivery); otherwise persists the ``running`` transition.
        """
        job = self._jobs.get_by_id(job_id)
        if job is None or job.status not in {
            QuizJobStatus.QUEUED,
            QuizJobStatus.RUNNING,
        }:
            return None
        return self._jobs.update(job.started(self._clock.now()))

    def begin_deck(self, source_id: UUID) -> QuizDeckHandle:
        """Build the source's eligible sections and start a generation pass (QUIZ-05).

        Zero eligible sections is not an error: the adapter starts a pass over an empty
        section list and ``finalize`` records a zero-count success (spec edge case).
        """
        sections = self._items.sections_for_generation(
            source_id, min_chars=self._min_section_chars
        )
        return self._generation.begin_deck(sections)

    def collect(self, handle: QuizDeckHandle) -> QuizDeckResult | None:
        """Return the pass's result, or ``None`` while the batch is still pending (QUIZ-05)."""
        return self._generation.collect_deck(handle)

    def finalize(
        self, job_id: UUID, result: QuizDeckResult
    ) -> QuizGenerationJob | None:
        """Ground, dedup, and persist the pass's candidates; record success (QUIZ-06..09).

        Per candidate, in order: schema sanity → verbatim quote in the referenced chunk
        (QUIZ-06) → cloze mask validity (QUIZ-07) → embedding dedup vs already-accepted
        and persisted items (QUIZ-08) → ``content_key`` upsert (QUIZ-02). A new item gets
        its initial scheduling row (QUIZ-09); an existing item's content is updated with
        its scheduling untouched. Any failed check discards the candidate (never
        persisted, counted in ``discarded``). Idempotent under redelivery: a re-run
        upserts the same items and re-creates no scheduling (a re-generated ``content_key``
        already persisted skips the dedup guard so it is not spuriously discarded).
        """
        job = self._jobs.get_by_id(job_id)
        if job is None:
            return None
        now = self._clock.now()

        chunk_index = self._chunk_index(job.source_id)
        existing_keys = {item.content_key for item in self._items.list_for_source(job.source_id)}
        persisted_embeddings = [
            embedding for _id, embedding in self._items.existing_embeddings(job.source_id)
        ]

        accepted_keys: set[str] = set()
        accepted_embeddings: list[list[float]] = []
        generated = 0
        discarded = 0

        # Ground first, then embed every surviving candidate in ONE batch call: under a
        # real provider, per-candidate embed_query would be N sequential round-trips.
        grounded: list[tuple[QuizCandidate, tuple[tuple[str, ...], str, str], str]] = []
        for candidate in result.candidates:
            located = self._ground(candidate, chunk_index)
            if located is None:
                discarded += 1
                continue
            key = content_key(candidate.item_type, candidate.question, candidate.answer)
            if key in accepted_keys:
                # Exact duplicate candidate within this pass — the same item once.
                discarded += 1
                continue
            accepted_keys.add(key)
            grounded.append((candidate, located, key))
        accepted_keys.clear()

        embeddings = (
            self._embeddings.embed_documents(
                [f"{candidate.question}\n{candidate.answer}" for candidate, _, _ in grounded]
            )
            if grounded
            else []
        )

        for (candidate, located, key), embedding in zip(grounded, embeddings, strict=True):
            section_path, anchor, chunk_text = located
            embedding = list(embedding)
            is_regeneration = key in existing_keys
            if not is_regeneration and self._is_duplicate(
                embedding, accepted_embeddings + persisted_embeddings
            ):
                discarded += 1
                continue

            item = QuizItem(
                id=self._ids(),
                source_id=job.source_id,
                item_type=candidate.item_type,
                question=candidate.question,
                answer=candidate.answer,
                section_path=section_path,
                anchor=anchor,
                source_excerpt=candidate.anchor_quote,
                chunk_hash=_chunk_hash(chunk_text),
                content_key=key,
                status=QuizItemStatus.ACTIVE,
                generation_meta={"model": self._generation.model},
                created_at=now,
                updated_at=now,
            )
            inserted = self._items.upsert(item, embedding=embedding)
            if inserted:
                self._items.create_scheduling(item.id, self._scheduling.initial())
            accepted_keys.add(key)
            if not is_regeneration:
                accepted_embeddings.append(embedding)
            generated += 1

        return self._jobs.update(
            job.succeeded(
                now,
                generated_count=generated,
                discarded_count=discarded,
                failed_sections=len(result.errors),
            )
        )

    def fail(self, job_id: UUID, error: str) -> QuizGenerationJob | None:
        """Terminal failure: ``failed`` + durable ``last_error`` (QUIZ-09)."""
        job = self._jobs.get_by_id(job_id)
        if job is None:
            return None
        return self._jobs.update(job.failed(self._clock.now(), error))

    def _chunk_index(
        self, source_id: UUID
    ) -> dict[UUID, tuple[tuple[str, ...], str, str]]:
        """Map each eligible-section chunk id → its ``(section_path, anchor, text)``.

        The grounding index: a candidate's ``source_chunk_id`` must resolve here (the
        section it claims to come from) or it is discarded as ungrounded (QUIZ-06).
        """
        index: dict[UUID, tuple[tuple[str, ...], str, str]] = {}
        for section in self._items.sections_for_generation(
            source_id, min_chars=self._min_section_chars
        ):
            for chunk_id, text in section.chunks:
                index[chunk_id] = (section.section_path, section.anchor, text)
        return index

    def _ground(
        self,
        candidate,  # noqa: ANN001 — QuizCandidate; typed loosely to keep the helper local
        chunk_index: dict[UUID, tuple[tuple[str, ...], str, str]],
    ) -> tuple[tuple[str, ...], str, str] | None:
        """Return the candidate's ``(section_path, anchor, chunk_text)`` if it passes QC.

        ``None`` when schema-invalid (QUIZ-10), the cited chunk is unknown, the
        ``anchor_quote`` is not verbatim in that chunk (QUIZ-06), or a cloze's mask is
        invalid (QUIZ-07).
        """
        if candidate.item_type not in _VALID_ITEM_TYPES:
            return None
        if not (candidate.question.strip() and candidate.answer.strip()):
            return None
        if not candidate.anchor_quote.strip():
            return None
        located = chunk_index.get(candidate.source_chunk_id)
        if located is None:
            return None
        _section_path, _anchor, chunk_text = located
        if not quote_in_text(candidate.anchor_quote, chunk_text):
            return None
        if candidate.item_type == QuizItemType.CLOZE and not cloze_is_valid(
            candidate.question, candidate.answer, candidate.anchor_quote
        ):
            return None
        return located

    def _is_duplicate(
        self, embedding: list[float], targets: list[list[float]]
    ) -> bool:
        """Return whether ``embedding`` is within the dedup threshold of any target (QUIZ-08)."""
        return any(
            _cosine(embedding, target) >= self._dedup_threshold for target in targets
        )


class ListQuizItems:
    """Return the per-source quiz overview for its owner (QUIZ-14).

    Ownership is enforced via ``authorized_source`` (missing or non-owner →
    ``SourceNotFound`` → 404, no disclosure), then the items, per-status counts,
    item→due map, and latest deck job are read for the overview.
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        items: QuizItemRepository,
        jobs: QuizJobRepository,
        authorize: AuthorizeOwnership,
    ) -> None:
        self._sources = sources
        self._items = items
        self._jobs = jobs
        self._authorize = authorize

    def __call__(self, *, user: User, source_id: UUID) -> QuizOverview:
        authorized_source(
            user=user,
            source_id=source_id,
            sources=self._sources,
            authorize=self._authorize,
        )
        return QuizOverview(
            items=self._items.list_for_source(source_id),
            counts_by_status=self._items.counts_by_status(source_id),
            due_by_item=self._items.due_map(source_id),
            latest_job=self._jobs.get_latest_for_source(source_id),
        )


class ExportQuizDeck:
    """Return an owned source's title and items for ``.apkg`` export (QUIZ-22).

    Ownership is enforced via ``authorized_source`` (missing or non-owner →
    ``SourceNotFound`` → 404, no disclosure). All items (any status) are returned —
    stale/orphaned are still valid learning material and are footnoted in the
    export. The empty-deck 404 is the web layer's concern (nothing to stream).
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

    def __call__(self, *, user: User, source_id: UUID) -> tuple[str, list[QuizItem]]:
        source = authorized_source(
            user=user,
            source_id=source_id,
            sources=self._sources,
            authorize=self._authorize,
        )
        return source.title, self._items.list_for_source(source_id)


class ReconcileQuizItems:
    """Reconcile a source's quiz items against a freshly replaced corpus (QUIZ-16).

    Runs as a step of the ingestion pipeline after the corpus is replaced (invoked with
    only ``source_id`` — ownership is the ingestion job's already). Per item, comparing the
    snapshotted ``source_excerpt`` against the new corpus text (normalized containment):

    - anchor still present ∧ excerpt still in that section's text → keep ``active``;
    - anchor present ∧ excerpt gone → ``stale``;
    - anchor now an alias of a section normalization merged it into ∧ excerpt in that
      survivor → relocate to the survivor's canonical anchor + ``section_path``,
      ``active`` (AD-085); a canonical anchor always wins a collision with an alias;
    - anchor gone ∧ excerpt found verbatim elsewhere → relocate (adopt that section's
      anchor + ``section_path``, keep ``active``);
    - otherwise → ``orphaned``.

    Only ``anchor``/``section_path``/``status`` are ever written, and only when the
    outcome differs from the item's current state — ``quiz_item_scheduling`` and
    ``review_log`` rows are never touched (QUIZ-16). A source with no items is a no-op
    fast path (the corpus is not even read).
    """

    def __init__(
        self, *, items: QuizItemRepository, corpus: CorpusRepository
    ) -> None:
        self._items = items
        self._corpus = corpus

    def __call__(self, *, source_id: UUID) -> None:
        items = self._items.items_for_reconcile(source_id)
        if not items:
            return  # no-op fast path — nothing to reconcile

        sections = self._corpus.section_texts(source_id)
        # First section per anchor in reading order (matches ``get_section`` resolution).
        first_by_anchor: dict[str, ReconcileSection] = {}
        for section in sections:
            first_by_anchor.setdefault(section.anchor, section)
        # An anchor normalization merged away resolves to its surviving section
        # (AD-085); a canonical anchor always wins a collision, so aliases that shadow
        # a live anchor are ignored (that live anchor is already in first_by_anchor).
        alias_to_section: dict[str, ReconcileSection] = {}
        for section in sections:
            for alias in section.anchor_aliases:
                if alias not in first_by_anchor:
                    alias_to_section.setdefault(alias, section)

        for item in items:
            anchor, section_path, status = self._resolve(
                item, sections, first_by_anchor, alias_to_section
            )
            if (anchor, section_path, status) != (item.anchor, item.section_path, item.status):
                self._items.update_reconciliation(
                    item.id, anchor=anchor, section_path=section_path, status=status
                )

    def _resolve(
        self,
        item: QuizItem,
        sections: list[ReconcileSection],
        first_by_anchor: dict[str, ReconcileSection],
        alias_to_section: dict[str, ReconcileSection],
    ) -> tuple[str, tuple[str, ...], str]:
        """Return the item's reconciled ``(anchor, section_path, status)`` (QUIZ-16)."""
        current = first_by_anchor.get(item.anchor)
        if current is not None:
            if quote_in_text(item.source_excerpt, current.text):
                return item.anchor, item.section_path, QuizItemStatus.ACTIVE
            return item.anchor, item.section_path, QuizItemStatus.STALE

        # The item's anchor is no longer a live section but was merged into a survivor:
        # if its excerpt is in that survivor, relocate to the survivor's canonical
        # anchor + path and stay active (ING-22), leaving scheduling/log untouched.
        survivor = alias_to_section.get(item.anchor)
        if survivor is not None and quote_in_text(item.source_excerpt, survivor.text):
            return survivor.anchor, survivor.section_path, QuizItemStatus.ACTIVE

        for section in sections:
            if quote_in_text(item.source_excerpt, section.text):
                return section.anchor, section.section_path, QuizItemStatus.ACTIVE
        return item.anchor, item.section_path, QuizItemStatus.ORPHANED
