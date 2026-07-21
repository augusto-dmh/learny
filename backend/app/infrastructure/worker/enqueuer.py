"""Celery enqueuer adapter (design §Components, AD-016).

``CeleryIngestionEnqueuer`` is the concrete ``IngestionEnqueuer``: it keeps
``apply_async`` out of application/handler code (ADR-007/009) and puts only ids
on the queue (AD-014). The start handler calls it *after* the queued job is
committed, so the worker always dequeues a durable row.
"""

from __future__ import annotations

from uuid import UUID

# The dedicated queue for PDF ingestion (ING-17). Its consumer is the isolated
# ``worker-pdf`` compose service; the default worker never drains it. Kept here as
# the single source of truth the compose command mirrors.
PDF_INGEST_QUEUE = "ingest-pdf"


class CeleryIngestionEnqueuer:
    """``IngestionEnqueuer`` backed by the Celery ``run_ingestion`` task.

    Routes PDF sources to the dedicated ``ingest-pdf`` queue and leaves every other
    source (EPUB today) on the default queue (ING-17); the decision is made here in
    the adapter so ``apply_async`` never leaks into application code (AD-016).
    """

    def enqueue_ingestion(
        self, *, source_id: UUID, job_id: UUID, content_type: str
    ) -> None:
        # Imported locally so the module import graph stays acyclic: the task
        # module wires this cycle's adapters, and the web composition root imports
        # this enqueuer.
        from app.infrastructure.ingestion.factory import PDF_CONTENT_TYPE
        from app.worker.tasks import run_ingestion

        options: dict[str, object] = {"args": [str(source_id), str(job_id)]}
        if content_type == PDF_CONTENT_TYPE:
            options["queue"] = PDF_INGEST_QUEUE
        run_ingestion.apply_async(**options)


class CeleryQuizDeckEnqueuer:
    """``QuizDeckEnqueuer`` backed by the Celery ``generate_quiz_deck`` task (QUIZ-03).

    The deck POST handler calls this *after* the queued job is committed so the worker
    always dequeues a durable row; only ids ride the queue (AD-014), mirroring
    :class:`CeleryIngestionEnqueuer`.
    """

    def enqueue_quiz_deck(self, *, source_id: UUID, job_id: UUID) -> None:
        from app.worker.tasks import generate_quiz_deck

        generate_quiz_deck.apply_async(args=[str(source_id), str(job_id)])


class CeleryNoteIndexEnqueuer:
    """``NoteIndexEnqueuer`` backed by the note-index Celery tasks (AD-016, NL-01).

    The note create/update handlers call this *after* the write is committed so the
    worker always reads a durable row; only the note id rides the queue (AD-014),
    mirroring :class:`CeleryIngestionEnqueuer`.
    """

    def enqueue_embed(self, note_id: UUID) -> None:
        from app.worker.tasks import embed_note

        embed_note.apply_async(args=[str(note_id)])

    def enqueue_refresh_cards(self, note_id: UUID) -> None:
        from app.worker.tasks import refresh_note_cards

        refresh_note_cards.apply_async(args=[str(note_id)])
