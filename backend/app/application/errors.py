"""Application-layer errors for the Identity module (task B4).

Framework-free exceptions raised by use-case services. The web layer (Phase C)
maps these to HTTP responses; keeping them here preserves the layering boundary
(ADR-007/009) and lets unit tests assert behaviour without FastAPI.
"""

from __future__ import annotations


class IdentityError(Exception):
    """Base class for identity use-case errors."""


class ValidationError(IdentityError):
    """Input failed validation (email format or password policy, FR-AUTH-010)."""


class EmailAlreadyExists(IdentityError):
    """Registration attempted with an email that is already taken."""


class InvalidCredentials(IdentityError):
    """Login failed. Uniform for unknown email or wrong password (no enumeration)."""


class NotAuthenticated(IdentityError):
    """No valid session resolves the presented token."""


class NotAuthorized(IdentityError):
    """An authenticated user attempted to act on a resource they do not own."""


class InvalidSourceUpload(Exception):
    """An uploaded source failed validation before anything was persisted.

    ``kind`` distinguishes the failure so the web layer can map it to the right
    status (``extension``/``content_type`` → 415, ``size`` → 413,
    ``empty``/``title`` → 422).
    """

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class SourceNotFound(Exception):
    """A source does not exist or is not the caller's.

    Non-owner and missing reads collapse to this single error so the web layer
    returns 404 either way (no existence disclosure — spec P1-View AC2).
    """


class StorageUnavailable(Exception):
    """Object storage could not complete an operation for a transient reason.

    Raised on the upload path when the file could not be written (SRC-09; no
    source row is persisted) and by the storage adapter's read path for any
    non-missing-object fault, so callers classify retries on a Learny-owned
    signal instead of vendor exception types (ADR-007/009).
    """


class ActiveIngestionExists(Exception):
    """A start was attempted while an active job already exists for the source.

    Enforces "at most one active ingestion job per source" (ING-03); the web
    layer maps this to 409 and enqueues nothing.
    """


class IngestionNotFound(Exception):
    """No ingestion job exists yet for the source (ING-12).

    Raised by the read path when ``get_latest_for_source`` finds nothing; the web
    layer maps it to 404 (the sources list conveys the pre-start ``uploaded``
    state instead).
    """


class EnqueueFailed(Exception):
    """The broker/enqueue call failed after the queued job was committed (ING-11).

    The start handler compensates the job to terminal ``failed`` before raising;
    the web layer maps this to 502 and no phantom active job is left behind.
    """


class InvalidDocumentError(Exception):
    """The source bytes are not a parseable document of the parser's format (CORP-06).

    Raised by a parser adapter for bad bytes, a corrupt archive, an unresolvable
    structure, or (for PDF) an encrypted/text-free file. It lives here (not in
    ``infrastructure``) so the adapter raises a transport-agnostic error without
    importing worker modules, and it is terminal by the existing task rule that
    any non-retryable raise fails the job (no retry).
    """


class CorpusNotFound(Exception):
    """A source exists and is owned by the caller but has no corpus yet (A-7).

    Raised by the structure read path when ``get_structure`` returns ``None``;
    the web layer maps it to 404, matching the ownership-as-404 behavior so the
    control is only offered on ``ready`` sources.
    """


class SourceNotReady(Exception):
    """A question was asked against a source whose ``status != "ready"`` (QA-08).

    Raised by the Q&A service after the ownership check and before retrieval, so
    neither retrieval nor generation runs; the web layer maps it to 409 naming
    the not-ready state.
    """


class AnswerGenerationFailed(Exception):
    """The answer-generation port raised an operational failure (QA-17).

    The Q&A service wraps any exception from
    :meth:`~app.domain.ports.AnswerGenerationPort.generate` in this error; the
    web layer maps it to 502 with a generic body that leaks no provider or
    internal detail. Nothing is persisted, so there is no state to roll back.
    """


class TeachingSessionNotFound(Exception):
    """A teaching session does not exist or is not the caller's (TEACH-06).

    Mirrors :class:`SourceNotFound`: a missing session and a non-owner (reached
    via the parent source's ownership) collapse to this single error so the web
    layer returns 404 either way and existence is never disclosed (TEACH-02).
    """


class InvalidTeachingTarget(Exception):
    """The requested ``target_anchor`` matches no section of the corpus (TEACH-04).

    Raised by ``StartTeachingSession`` after ownership and readiness pass but the
    anchor resolves to no section; the web layer maps it to 422.
    """


class TeachingTargetGone(Exception):
    """A session's ``target_anchor`` no longer resolves in the current corpus.

    Re-ingestion (AD-018) can replace the corpus and drop the section the session
    was anchored to; a new turn then has no target subtree to scope. Raised by
    ``PostTeachingTurn``; the web layer maps it to 409 with a readable detail so
    the reader starts a new session (TEACH-16).
    """


class TeachingTurnConflict(Exception):
    """Two turns raced for one ``(session_id, turn_index)`` (TEACH-17).

    The turn repository translates the unique-index violation into this error;
    the web layer maps it to 409 so the losing writer can retry against the next
    index. It lives here (not in ``infrastructure``) so the adapter raises a
    transport-agnostic error, matching :class:`InvalidDocumentError`.
    """


class QuizDeckConflict(Exception):
    """A deck generation was requested while one is already in flight (QUIZ-04).

    ``PlanDeckGeneration`` guards the single-in-flight invariant with an
    application pre-check (``QuizJobRepository.get_active_for_source`` returns a
    queued/running job); the web layer maps this to 409 so a second POST does not
    start a competing deck job for the same source.
    """


class QuizItemNotFound(Exception):
    """A quiz item does not exist or is not the caller's (QUIZ-12/18).

    Mirrors :class:`SourceNotFound`: a missing item and a non-owner (reached via
    the parent source's ownership) collapse to this single error so the web layer
    returns 404 either way and an item's existence is never disclosed.
    """


class QuizItemNotReviewable(Exception):
    """A review was submitted for a non-``active`` quiz item (QUIZ-12).

    ``SubmitReview`` rejects items reconciliation left ``stale`` or ``orphaned``
    (their citation no longer resolves), so a suspended card is not scheduled; the
    web layer maps this to 409.
    """
