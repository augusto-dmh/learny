"""Ingestion worker tasks (ADR-005/ADR-014, design §Components).

Thin Celery adapters over the ``RunIngestion`` application service. The task owns
only the *retry decision* (a Celery concern — retry count lives on the request);
the pure service owns every durable DB transition. Each transition runs in its
own committed unit of work (``get_engine().begin()``), so the ``running`` state is
durable before the step runs and terminal state survives a crash.

The step now parses the EPUB and builds the canonical corpus: the step block runs
inside its own ``get_engine().begin()`` transaction, so a mid-build failure rolls
back with no partial corpus (CORP-08) and a successful build commits atomically.
No FastAPI import crosses into this module; Celery/SQLAlchemy never enter
``domain``/``application`` (ADR-007/009).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import Connection, text

from app.application.corpus import BuildCorpus
from app.application.ingestion import RunIngestion
from app.application.notes import ReconcileNoteAnchors
from app.application.quiz import ReconcileQuizItems, RunDeckGeneration
from app.application.retrieval import EmbedCorpus
from app.core.config import get_settings
from app.core.tracing import bind_trace, new_trace_scope, reset_trace
from app.domain.entities import ParsedBook, QuizDeckHandle
from app.domain.ports import IngestionStep, StoragePort
from app.infrastructure.clock import SystemClock
from app.infrastructure.db.engine import get_engine
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemyEmbeddingIndexRepository,
    SqlAlchemyIngestionEventRepository,
    SqlAlchemyIngestionJobRepository,
    SqlAlchemyNoteRepository,
    SqlAlchemyQuizItemRepository,
    SqlAlchemyQuizJobRepository,
    SqlAlchemySourceRepository,
)
from app.infrastructure.embeddings import build_embedding_adapter
from app.infrastructure.ingestion.factory import (
    EPUB_CONTENT_TYPE,
    PDF_CONTENT_TYPE,
    build_parser,
)
from app.infrastructure.ingestion.markup import Bs4MarkupConverter
from app.infrastructure.quiz import build_quiz_adapter
from app.infrastructure.scheduling import build_scheduling_adapter
from app.infrastructure.storage.s3 import S3StorageAdapter
from app.infrastructure.worker.steps import (
    CorpusIngestionStep,
    EmbedCorpusIngestionStep,
    RetryableIngestionError,
)
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

_clock = SystemClock()

# Manual backoff for retryable step failures (ING-07). Exponential in the attempt
# count, capped so a long-lived transient fault does not push retries out for hours.
_RETRY_BASE_COUNTDOWN = 10
_RETRY_MAX_COUNTDOWN = 600

# Durable failure text is a fixed, non-secret summary (ING-08 "redacted, non-secret").
# A step exception — in Phase 5 potentially carrying object keys, storage URLs, or
# filesystem paths — is written only to the server log (``exc_info``), never to the
# owner-readable ``last_error`` / event ``message``.
_STEP_FAILURE_ERROR = "Ingestion processing failed."


def _retry_countdown(retries: int) -> int:
    """Return the backoff (seconds) before the next retry given prior ``retries``."""
    return min(_RETRY_BASE_COUNTDOWN * (2**retries), _RETRY_MAX_COUNTDOWN)


def _elapsed_ms(start: float) -> float:
    """Milliseconds elapsed since ``start`` (a ``time.perf_counter`` reading)."""
    return round((time.perf_counter() - start) * 1000, 3)


def _build_storage() -> StoragePort:
    """Build the S3-compatible storage adapter from settings (web-layer mirror)."""
    settings = get_settings()
    return S3StorageAdapter(
        endpoint=settings.storage_endpoint,
        access_key=settings.storage_access_key,
        secret_key=settings.storage_secret_key,
        bucket=settings.storage_bucket,
        region=settings.storage_region,
    )


# SPEC_DEVIATION: design §5 wires the factory in `_build_step` from the job's
# source content type; here the content type is recovered inside the parser from
# the source filename instead.
# Reason: content type is not carried across the `DocumentParserPort.parse(bytes,
# *, filename)` seam, and `_build_step(conn)` must stay a one-argument seam the
# existing worker lifecycle tests patch. Upload validation keeps the filename
# extension and the stored content type in agreement, so the selected parser is
# the same one the content type would select.
class _ContentTypeDispatchParser:
    """Select the concrete parser per source at parse time (ING-15).

    Maps the source's filename extension to its content type and delegates to the
    format-dispatch factory, so EPUB routes to ebooklib and PDF to Docling behind
    one ``DocumentParserPort``. An unknown extension falls through to the factory's
    terminal ``InvalidDocumentError`` (no registered parser).
    """

    _EXTENSIONS = {"epub": EPUB_CONTENT_TYPE, "pdf": PDF_CONTENT_TYPE}

    def parse(self, source_bytes: bytes, *, filename: str) -> ParsedBook:
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        content_type = self._EXTENSIONS.get(extension, extension)
        return build_parser(content_type).parse(source_bytes, filename=filename)


def _build_step(conn: Connection) -> IngestionStep:
    """Wire the real corpus-build step on ``conn`` (the injectable Phase-5 seam).

    The parser is a format dispatcher that picks ebooklib or Docling per source
    (ING-15). Factored out so lifecycle tests can inject a lifecycle-only double
    without a live object store or a real document, exactly as prior cycles
    patched the step.
    """
    return CorpusIngestionStep(
        BuildCorpus(
            storage=_build_storage(),
            parser=_ContentTypeDispatchParser(),
            markup=Bs4MarkupConverter(),
            corpus=SqlAlchemyCorpusRepository(conn),
            events=SqlAlchemyIngestionEventRepository(conn),
            clock=_clock,
            ids=uuid4,
            chunk_max_chars=get_settings().chunk_max_chars,
        )
    )


def _build_run_ingestion(conn: Connection) -> RunIngestion:
    """Wire the ``RunIngestion`` driver on ``conn`` (the task's composition root)."""
    return RunIngestion(
        sources=SqlAlchemySourceRepository(conn),
        jobs=SqlAlchemyIngestionJobRepository(conn),
        events=SqlAlchemyIngestionEventRepository(conn),
        step=_build_step(conn),
        clock=_clock,
        ids=uuid4,
    )


def _build_embed_step(conn: Connection) -> IngestionStep:
    """Wire the corpus-embedding step on ``conn`` (the injectable embed seam).

    Composes ``EmbedCorpus`` with the settings-selected embedding adapter (the
    deterministic local adapter by default — no network, no provider SDK) so the
    semantic arm is populated during ingestion. Factored out like ``_build_step``
    so lifecycle tests can inject a failing double.
    """
    return EmbedCorpusIngestionStep(
        EmbedCorpus(
            embeddings=build_embedding_adapter(get_settings()),
            index=SqlAlchemyEmbeddingIndexRepository(conn),
            events=SqlAlchemyIngestionEventRepository(conn),
            clock=_clock,
            ids=uuid4,
            batch_size=get_settings().embedding_batch_size,
        )
    )


def _build_reconcile(conn: Connection) -> ReconcileQuizItems:
    """Wire ``ReconcileQuizItems`` on ``conn`` — the post-corpus-replace quiz step (QUIZ-16)."""
    return ReconcileQuizItems(
        items=SqlAlchemyQuizItemRepository(conn),
        corpus=SqlAlchemyCorpusRepository(conn),
    )


def _build_reconcile_notes(conn: Connection) -> ReconcileNoteAnchors:
    """Wire ``ReconcileNoteAnchors`` on ``conn`` — the post-corpus-replace note step (NF-07)."""
    return ReconcileNoteAnchors(
        notes=SqlAlchemyNoteRepository(conn),
        corpus=SqlAlchemyCorpusRepository(conn),
        markup=Bs4MarkupConverter(),
    )


def _build_embed_ingestion(conn: Connection) -> RunIngestion:
    """Wire a second ``RunIngestion`` whose step embeds the source's chunks."""
    return RunIngestion(
        sources=SqlAlchemySourceRepository(conn),
        jobs=SqlAlchemyIngestionJobRepository(conn),
        events=SqlAlchemyIngestionEventRepository(conn),
        step=_build_embed_step(conn),
        clock=_clock,
        ids=uuid4,
    )


@celery_app.task(bind=True, name="ingestion.run", max_retries=3)
def run_ingestion(self, source_id: str, job_id: str) -> None:  # noqa: ANN001 — bound task ``self``
    """Drive a source's ingestion job through its durable lifecycle (ING-02/07/08).

    Idempotent under ``acks_late`` redelivery: a missing or already-terminal job
    no-ops via ``begin_run``. On a retryable step failure with attempts remaining
    the task records a ``retrying`` event and re-raises ``self.retry``; otherwise
    (non-retryable error, or retries exhausted) it writes terminal ``failed`` and
    returns — the terminal state is already durable, so it is not re-raised.
    """
    jid = UUID(job_id)
    log = {"job_id": job_id, "source_id": source_id}
    # Bind the job/source trace fields so every record emitted during this task —
    # here and in the services it calls — is correlated (PROD-14). Reset on exit so
    # nothing leaks to the next task the worker picks up.
    token = new_trace_scope()
    bind_trace(job_id=job_id, source_id=source_id)
    start = time.perf_counter()
    try:
        return _run_ingestion_body(self, jid, job_id, source_id, log, start)
    finally:
        reset_trace(token)


def _run_ingestion_body(  # noqa: ANN001, ANN202 — mirrors the bound task ``self``
    self, jid: UUID, job_id: str, source_id: str, log: dict[str, str], start: float
):
    # 1. Claim the job: queued/running → running (attempts+1). None ⇒ missing row
    #    (ING-08 AC3) or already terminal (redelivery) ⇒ idempotent no-op.
    with get_engine().begin() as conn:
        job = _build_run_ingestion(conn).begin_run(jid)
    if job is None:
        logger.info("ingestion.run: no-op (missing or terminal job)", extra=log)
        return
    logger.info("ingestion.run: started", extra=log)

    # 2. Run the corpus-build step, then the embed step, each in its OWN committed
    #    transaction, separate from the lifecycle transitions and from each other:
    #    the durable ``running`` state is already committed; the whole build
    #    (parse → replace → counts event) commits atomically or rolls back with no
    #    partial corpus on any raise (CORP-08); then the embed step (embed →
    #    set_embeddings → counts event) runs after the corpus commit — so the
    #    embedding-provider call is outside the corpus-write transaction (RET-10) —
    #    and commits atomically or rolls back with no partial vectors (RET-12).
    #    Both share the retry/terminal classification below: a retryable embed
    #    fault retries the whole task (corpus replace is atomic + re-embed is
    #    idempotent → RET-11), any other embed error is terminal.
    try:
        with get_engine().begin() as conn:
            _build_run_ingestion(conn).run_step(job)
        # Reconcile quiz items against the freshly replaced corpus, in its own committed
        # transaction after the corpus build and before embedding (QUIZ-16). It needs only
        # the new corpus text; a source with no quiz items is a no-op fast path. A raise
        # here is classified by the retry/terminal branches below like any step fault.
        with get_engine().begin() as conn:
            _build_reconcile(conn)(source_id=job.source_id)
        # Then reconcile note anchors against the same replaced corpus — a sibling step
        # in its own committed transaction after quiz reconcile and before embedding
        # (NF-07); a source with no anchors is a no-op fast path. A raise is classified
        # by the retry/terminal branches below like any step fault.
        with get_engine().begin() as conn:
            _build_reconcile_notes(conn)(source_id=job.source_id)
        with get_engine().begin() as conn:
            _build_embed_ingestion(conn).run_step(job)
    except RetryableIngestionError as exc:
        # Persist only the fixed, non-secret summary (ING-08); the raw exception
        # goes to the server log via ``exc_info``, never the durable field.
        if self.request.retries < self.max_retries:
            with get_engine().begin() as conn:
                _build_run_ingestion(conn).record_retry(jid, _STEP_FAILURE_ERROR)
            logger.info("ingestion.run: retrying", extra=log, exc_info=exc)
            raise self.retry(exc=exc, countdown=_retry_countdown(self.request.retries)) from exc
        with get_engine().begin() as conn:
            _build_run_ingestion(conn).fail(jid, _STEP_FAILURE_ERROR)
        logger.info(
            "ingestion.run: failed (retries exhausted)",
            extra={**log, "duration_ms": _elapsed_ms(start)},
            exc_info=exc,
        )
        return
    except Exception as exc:  # noqa: BLE001 — any non-retryable error is terminal
        with get_engine().begin() as conn:
            _build_run_ingestion(conn).fail(jid, _STEP_FAILURE_ERROR)
        logger.info(
            "ingestion.run: failed",
            extra={**log, "duration_ms": _elapsed_ms(start)},
            exc_info=exc,
        )
        return

    # 3. Terminal success: succeeded + source ready + ``succeeded`` event.
    with get_engine().begin() as conn:
        _build_run_ingestion(conn).complete(jid)
    logger.info(
        "ingestion.run: succeeded", extra={**log, "duration_ms": _elapsed_ms(start)}
    )


# HNSW index over the semantic arm's ``embedding`` column. The bulk reembed drops
# it first (a bulk write into an HNSW index is far slower than a rebuild) and
# recreates it after with the SAME params as migration 0005 so the semantic arm is
# served identically afterward (EMB-18). ``IF EXISTS``/``IF NOT EXISTS`` keep both
# statements idempotent under redelivery.
_DROP_HNSW_INDEX = "DROP INDEX IF EXISTS ix_corpus_chunks_embedding_hnsw"
_CREATE_HNSW_INDEX = (
    "CREATE INDEX IF NOT EXISTS ix_corpus_chunks_embedding_hnsw "
    "ON corpus_chunks USING hnsw (embedding vector_cosine_ops) "
    "WITH (m = 16, ef_construction = 64)"
)


@celery_app.task(bind=True, name="reembed.document")
def reembed_document(self, source_id: str) -> None:  # noqa: ANN001 — bound task ``self``
    """Re-embed a source's chunks through the settings-selected provider (EMB-16).

    Ops-invoked (no HTTP endpoint): re-embeds only the chunks whose stored vector is
    missing or was produced by a different model, committing per batch, so the pass
    is idempotent and resumable — a re-run after a partial completion finishes the
    remainder and a fully-current source rewrites nothing (EMB-17). The HNSW index is
    dropped before the bulk write and recreated after (EMB-18). A raise fails the
    task and it is re-invoked by ops (no autoretry).
    """
    token = new_trace_scope()
    bind_trace(source_id=source_id)
    try:
        return _reembed_document_body(source_id)
    finally:
        reset_trace(token)


def _reembed_document_body(source_id: str) -> None:
    sid = UUID(source_id)
    log = {"source_id": source_id}
    start = time.perf_counter()
    settings = get_settings()
    adapter = build_embedding_adapter(settings)
    target = adapter.model
    batch_size = settings.embedding_batch_size

    logger.info("reembed.document: started", extra={**log, "model": target})

    # 1. Drop the HNSW index in its own committed txn before the bulk write.
    with get_engine().begin() as conn:
        conn.execute(text(_DROP_HNSW_INDEX))

    # 2. Re-embed the stale set in batches, each in its OWN committed txn: re-query
    #    ``stale_chunks_for_source`` each pass so committed progress shrinks the
    #    remaining set (resumable). A current source loops zero batches.
    embedded = 0
    while True:
        with get_engine().begin() as conn:
            index = SqlAlchemyEmbeddingIndexRepository(conn)
            batch = index.stale_chunks_for_source(sid, target, batch_size)
            if not batch:
                break
            vectors = adapter.embed_documents([chunk.text for chunk in batch])
            items = list(zip((chunk.id for chunk in batch), vectors, strict=True))
            index.set_embeddings(items, model=target)
            embedded += len(items)

    # 3. Recreate the HNSW index (same params as 0005) in its own committed txn.
    with get_engine().begin() as conn:
        conn.execute(text(_CREATE_HNSW_INDEX))

    logger.info(
        "reembed.document: completed",
        extra={**log, "chunks": embedded, "duration_ms": _elapsed_ms(start)},
    )


# --- Notes retrieval index (RFC-003 Cycle F, NL-01) -----------------------------


@celery_app.task(bind=True, name="notes.embed")
def embed_note(self, note_id: str) -> None:  # noqa: ANN001 — bound task ``self``
    """(Re)embed a note's whole body through the settings-selected provider (NL-01).

    Enqueued after a note create/update commits (AD-016). Idempotent and
    newest-body-wins: the body is read at run time inside the write transaction, so a
    stale enqueue that lands after a newer save still embeds the newest body; an empty
    body clears any stored vector (the note leaves the semantic arm, NL-06); a note
    deleted before the task runs is a no-op (its index rows died with it, NL-07). The
    input is truncated deterministically to the provider limit so an oversized note
    never fails the embed. A raise fails the task (mirrors ``reembed_document``); the
    lexical note arm keeps serving in the meantime.
    """
    token = new_trace_scope()
    bind_trace(note_id=note_id)
    try:
        return _embed_note_body(note_id)
    finally:
        reset_trace(token)


def _embed_note_body(note_id: str) -> None:
    nid = UUID(note_id)
    settings = get_settings()
    adapter = build_embedding_adapter(settings)
    with get_engine().begin() as conn:
        repo = SqlAlchemyNoteRepository(conn)
        note = repo.get_by_id(nid)
        if note is None:
            return  # deleted before the task ran — nothing to embed (NL-07)
        if not note.body_markdown:
            # Empty body → clear any prior vector so the note leaves the semantic arm.
            repo.set_embedding(nid, embedding=None, model=None)
            return
        truncated = note.body_markdown[: settings.notes_embedding_max_chars]
        vector = adapter.embed_documents([truncated])[0]
        repo.set_embedding(nid, embedding=vector, model=adapter.model)


@celery_app.task(bind=True, name="notes.refresh_cards")
def refresh_note_cards(self, note_id: str) -> None:  # noqa: ANN001 — bound task ``self``
    """Regenerate-and-match a promoted note's derived cards (NL-10 — body lands later).

    Registered now so ``CeleryNoteIndexEnqueuer.enqueue_refresh_cards`` has a task to
    address; the edit-stability regenerate-and-match implementation arrives with the
    note→quiz loop. A no-op until then.
    """
    return None


# --- Deck generation (Cycle E, QUIZ-05/09) --------------------------------------
#
# ``generate_quiz_deck`` mirrors ``run_ingestion``: the task owns only the Celery
# concerns (UoW-per-transition, retry decision, trace scope); ``RunDeckGeneration``
# owns every durable transition. The local adapter computes candidates inline, so the
# task finalizes in one invocation; the Anthropic adapter returns a pending batch, so
# the task schedules ``poll_quiz_deck`` to self-reschedule until the batch ends or the
# deadline passes. ``finalize`` is idempotent (upserts), so redelivery under
# ``acks_late`` never duplicates items or resets scheduling.

# Fixed, non-secret durable failure text (mirrors the ingestion redaction).
_DECK_FAILURE_ERROR = "Quiz deck generation failed."
_DECK_TIMEOUT_ERROR = "Quiz deck generation timed out."


def _build_run_deck(conn: Connection) -> RunDeckGeneration:
    """Wire the ``RunDeckGeneration`` driver on ``conn`` (the deck task's root)."""
    settings = get_settings()
    return RunDeckGeneration(
        jobs=SqlAlchemyQuizJobRepository(conn),
        items=SqlAlchemyQuizItemRepository(conn),
        generation=build_quiz_adapter(settings),
        embeddings=build_embedding_adapter(settings),
        scheduling=build_scheduling_adapter(settings),
        clock=_clock,
        ids=uuid4,
        min_section_chars=settings.quiz_min_section_chars,
        dedup_threshold=settings.quiz_dedup_threshold,
    )


def _retry_or_fail_deck(self, jid, exc, log, start):  # noqa: ANN001, ANN202 — bound task ``self``
    """Retry a deck task on a transient provider fault, else drive the job terminal.

    The redacted summary is persisted (never the raw exception, which may carry provider
    detail); the raw exception goes to the server log via ``exc_info``.
    """
    if self.request.retries < self.max_retries:
        logger.info("quiz.generate_deck: retrying", extra=log, exc_info=exc)
        raise self.retry(exc=exc, countdown=_retry_countdown(self.request.retries)) from exc
    with get_engine().begin() as conn:
        _build_run_deck(conn).fail(jid, _DECK_FAILURE_ERROR)
    logger.info(
        "quiz.generate_deck: failed",
        extra={**log, "duration_ms": _elapsed_ms(start)},
        exc_info=exc,
    )
    return None


def _finalize_deck(jid, result, log, start):  # noqa: ANN001, ANN202
    """Persist a completed pass and log success (idempotent; safe under redelivery)."""
    with get_engine().begin() as conn:
        _build_run_deck(conn).finalize(jid, result)
    logger.info(
        "quiz.generate_deck: succeeded",
        extra={**log, "duration_ms": _elapsed_ms(start)},
    )


@celery_app.task(bind=True, name="quiz.generate_deck", max_retries=3)
def generate_quiz_deck(self, source_id: str, job_id: str) -> None:  # noqa: ANN001 — bound task ``self``
    """Drive a source's deck-generation job (QUIZ-05/09).

    Idempotent under redelivery: a missing or already-terminal job no-ops via ``begin``.
    The local provider finalizes inline; a pending Anthropic batch schedules
    ``poll_quiz_deck`` with the handle payload and an absolute deadline. Any provider
    fault at begin/collect retries with backoff, then fails the job terminally.
    """
    jid, sid = UUID(job_id), UUID(source_id)
    log = {"job_id": job_id, "source_id": source_id}
    token = new_trace_scope()
    bind_trace(job_id=job_id, source_id=source_id)
    start = time.perf_counter()
    try:
        return _generate_quiz_deck_body(self, jid, sid, job_id, log, start)
    finally:
        reset_trace(token)


def _generate_quiz_deck_body(self, jid, sid, job_id, log, start):  # noqa: ANN001, ANN202
    # 1. Claim the job: queued/running → running. None ⇒ missing/terminal ⇒ no-op.
    with get_engine().begin() as conn:
        job = _build_run_deck(conn).begin(jid)
    if job is None:
        logger.info("quiz.generate_deck: no-op (missing or terminal job)", extra=log)
        return None
    logger.info("quiz.generate_deck: started", extra=log)

    # 2. Start the pass and collect once. A provider fault here retries the task.
    try:
        with get_engine().begin() as conn:
            handle = _build_run_deck(conn).begin_deck(sid)
        result = build_quiz_adapter(get_settings()).collect_deck(handle)
    except Exception as exc:  # noqa: BLE001 — classified as retryable/terminal below
        return _retry_or_fail_deck(self, jid, exc, log, start)

    # 3a. Pending batch: schedule the poll task with an absolute deadline.
    if result is None:
        settings = get_settings()
        deadline = _clock.now() + timedelta(seconds=settings.quiz_batch_timeout_s)
        poll_quiz_deck.apply_async(
            args=[job_id, handle.to_payload(), deadline.isoformat()],
            countdown=settings.quiz_batch_poll_interval_s,
        )
        logger.info("quiz.generate_deck: batch pending, scheduled poll", extra=log)
        return None

    # 3b. Inline result (local provider or an already-finished batch): finalize now.
    _finalize_deck(jid, result, log, start)
    return None


@celery_app.task(bind=True, name="quiz.poll_deck", max_retries=3)
def poll_quiz_deck(  # noqa: ANN001 — bound task ``self``
    self, job_id: str, handle_payload: dict, deadline_iso: str
) -> None:
    """Poll a pending deck batch: reschedule until it ends or the deadline passes.

    A still-pending batch reschedules this task after ``quiz_batch_poll_interval_s`` until
    the absolute ``deadline_iso`` is reached, at which point the job is failed with a
    timeout (edge case). A completed batch is finalized (idempotent). A provider fault
    retries with backoff, then fails the job.
    """
    jid = UUID(job_id)
    log = {"job_id": job_id}
    token = new_trace_scope()
    bind_trace(job_id=job_id)
    start = time.perf_counter()
    try:
        return _poll_quiz_deck_body(self, jid, job_id, handle_payload, deadline_iso, log, start)
    finally:
        reset_trace(token)


def _poll_quiz_deck_body(self, jid, job_id, handle_payload, deadline_iso, log, start):  # noqa: ANN001, ANN202
    handle = QuizDeckHandle.from_payload(handle_payload)
    try:
        result = build_quiz_adapter(get_settings()).collect_deck(handle)
    except Exception as exc:  # noqa: BLE001 — classified as retryable/terminal below
        return _retry_or_fail_deck(self, jid, exc, log, start)

    if result is None:
        # Still pending: fail on deadline, else reschedule this poll.
        if _clock.now() >= datetime.fromisoformat(deadline_iso):
            with get_engine().begin() as conn:
                _build_run_deck(conn).fail(jid, _DECK_TIMEOUT_ERROR)
            logger.info(
                "quiz.poll_deck: timed out",
                extra={**log, "duration_ms": _elapsed_ms(start)},
            )
            return None
        poll_quiz_deck.apply_async(
            args=[job_id, handle_payload, deadline_iso],
            countdown=get_settings().quiz_batch_poll_interval_s,
        )
        logger.info("quiz.poll_deck: still pending, rescheduled", extra=log)
        return None

    _finalize_deck(jid, result, log, start)
    return None
