"""HTTP composition root for the Identity module (task C1).

This module is the single place where concrete adapters (DB repositories, the
Argon2id hasher, the token generator, the system clock) are assembled into the
framework-free application services, and exposed to FastAPI routers as
dependencies. Keeping the wiring here preserves the layering boundary
(ADR-007/009): routers stay thin, and the application/domain layers never import
FastAPI or SQLAlchemy.

Transaction boundary: a request-scoped SQLAlchemy ``Connection`` is opened per
request inside a transaction. The connection is committed when the handler
returns normally and rolled back on any exception, so each request is an atomic
unit of work (the repositories themselves are transaction-agnostic, per B3).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from functools import lru_cache
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Request
from sqlalchemy import Connection

from app.application.corpus import ReadSection, ReadSourceStructure
from app.application.identity import (
    AuthenticateUser,
    AuthorizeOwnership,
    CurrentUser,
    Logout,
    RegisterUser,
)
from app.application.ingestion import ReadIngestion, RunIngestion, StartIngestion
from app.application.qa import AskQuestion
from app.application.quiz import (
    ExportQuizDeck,
    ListQuizItems,
    PlanDeckGeneration,
    RunDeckGeneration,
)
from app.application.retrieval import RetrieveEvidence
from app.application.reviews import GetDueQueue, SubmitReview
from app.application.sources import CreateSource, GetSource, ListSources
from app.application.teaching import (
    ListTeachingSessions,
    PostTeachingTurn,
    ReadTeachingSession,
    StartTeachingSession,
)
from app.core.config import Settings, get_settings
from app.core.tracing import bind_trace
from app.domain.entities import Session, User
from app.domain.ports import (
    AnswerGenerationPort,
    IngestionEnqueuer,
    QuizDeckEnqueuer,
    StoragePort,
    TeachingGenerationPort,
)
from app.infrastructure.answering import (
    build_answer_adapter,
    build_teaching_adapter,
)
from app.infrastructure.clock import SystemClock
from app.infrastructure.db.engine import get_engine
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemyCredentialRepository,
    SqlAlchemyIngestionEventRepository,
    SqlAlchemyIngestionJobRepository,
    SqlAlchemyQuizItemRepository,
    SqlAlchemyQuizJobRepository,
    SqlAlchemySessionRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyTeachingSessionRepository,
    SqlAlchemyTeachingTurnRepository,
    SqlAlchemyUserRepository,
)
from app.infrastructure.db.retrieval import SqlAlchemyRetrievalRepository
from app.infrastructure.embeddings import build_embedding_adapter
from app.infrastructure.quiz import build_quiz_adapter
from app.infrastructure.scheduling import build_scheduling_adapter
from app.infrastructure.security.password_hasher import Argon2PasswordHasher
from app.infrastructure.security.tokens import SecretsTokenGenerator
from app.infrastructure.storage.s3 import S3StorageAdapter
from app.infrastructure.worker.enqueuer import (
    CeleryIngestionEnqueuer,
    CeleryQuizDeckEnqueuer,
)
from app.infrastructure.worker.steps import NoOpIngestionStep

# Process-wide singletons for the stateless adapters. The hasher in particular is
# expensive to construct (Argon2 parameter setup), so it is built once.
_hasher = Argon2PasswordHasher()
_tokens = SecretsTokenGenerator()
_clock = SystemClock()


def _build_storage() -> S3StorageAdapter:
    settings = get_settings()
    return S3StorageAdapter(
        endpoint=settings.storage_endpoint,
        access_key=settings.storage_access_key,
        secret_key=settings.storage_secret_key,
        bucket=settings.storage_bucket,
        region=settings.storage_region,
    )


# Process-wide storage adapter (holds a boto3 client; built once, ensures its
# bucket on first use). Overridable in tests via ``get_storage``.
_storage: StoragePort = _build_storage()


def get_db_connection(request: Request) -> Iterator[Connection]:
    """Yield a request-scoped connection wrapped in a transaction.

    Commits on success, rolls back if the handler raised. Stored on
    ``request.state`` is unnecessary — each dependency consumer shares the same
    yielded connection because FastAPI caches dependency results per request.
    """
    engine = get_engine()
    conn = engine.connect()
    trans = conn.begin()
    try:
        yield conn
    except Exception:
        trans.rollback()
        raise
    else:
        trans.commit()
    finally:
        conn.close()


DbConnection = Annotated[Connection, Depends(get_db_connection)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_register_user(conn: DbConnection) -> RegisterUser:
    return RegisterUser(
        users=SqlAlchemyUserRepository(conn),
        credentials=SqlAlchemyCredentialRepository(conn),
        sessions=SqlAlchemySessionRepository(conn),
        hasher=_hasher,
        tokens=_tokens,
        clock=_clock,
    )


def get_authenticate_user(conn: DbConnection) -> AuthenticateUser:
    return AuthenticateUser(
        users=SqlAlchemyUserRepository(conn),
        credentials=SqlAlchemyCredentialRepository(conn),
        sessions=SqlAlchemySessionRepository(conn),
        hasher=_hasher,
        tokens=_tokens,
        clock=_clock,
    )


def get_logout(conn: DbConnection) -> Logout:
    return Logout(sessions=SqlAlchemySessionRepository(conn))


def get_current_user_service(conn: DbConnection) -> CurrentUser:
    return CurrentUser(
        users=SqlAlchemyUserRepository(conn),
        sessions=SqlAlchemySessionRepository(conn),
        clock=_clock,
    )


def get_authorize_ownership() -> AuthorizeOwnership:
    return AuthorizeOwnership()


def resolve_current(
    request: Request,
    settings: AppSettings,
    current_user: Annotated[CurrentUser, Depends(get_current_user_service)],
) -> tuple[User, Session]:
    """Resolve the session cookie to (user, session) or raise ``NotAuthenticated``.

    The cookie name is read from settings (``session_cookie_name``) rather than a
    literal ``Cookie`` alias, so the configured name stays authoritative. The
    global exception handler maps ``NotAuthenticated`` to HTTP 401.
    """
    session_token = request.cookies.get(settings.session_cookie_name)
    user, session = current_user(raw_token=session_token)
    # Enrich the request's trace context so downstream handler logs carry the
    # authenticated user id (PROD-10). Bound only on success — anonymous/failed
    # requests carry no user_id.
    bind_trace(user_id=str(user.id))
    return user, session


CurrentPrincipal = Annotated[tuple[User, Session], Depends(resolve_current)]


def get_current_session(principal: CurrentPrincipal) -> Session:
    """FastAPI dependency: the authenticated session row (401 if absent)."""
    return principal[1]


def get_authenticated_user(principal: CurrentPrincipal) -> User:
    """FastAPI dependency: the authenticated user (401 if absent)."""
    return principal[0]


def get_storage() -> StoragePort:
    """FastAPI dependency: the process-wide storage adapter (overridable in tests)."""
    return _storage


Storage = Annotated[StoragePort, Depends(get_storage)]


def get_create_source(conn: DbConnection, storage: Storage, settings: AppSettings) -> CreateSource:
    return CreateSource(
        sources=SqlAlchemySourceRepository(conn),
        storage=storage,
        clock=_clock,
        ids=uuid4,
        max_bytes=settings.epub_max_bytes,
        pdf_max_bytes=settings.pdf_max_bytes,
    )


def get_list_sources(conn: DbConnection) -> ListSources:
    return ListSources(sources=SqlAlchemySourceRepository(conn))


def get_get_source(conn: DbConnection) -> GetSource:
    return GetSource(
        sources=SqlAlchemySourceRepository(conn),
        authorize=AuthorizeOwnership(),
    )


# --- Ingestion (worker-foundation) ---------------------------------------------
#
# The start path cannot use the request-scoped auto-commit ``get_db_connection``:
# ING-11 requires the queued job to be *committed* before a synchronous enqueue
# that may fail with 502, and (on failure) a second UoW to compensate the job to
# terminal ``failed``. So the two write UoWs go through an injectable factory
# (``get_ingestion_uow``) returning a fresh committing transaction in production;
# web tests override it to share the rolled-back ``db_conn`` without committing,
# exactly as ``get_storage``/``get_db_connection`` are overridden today. The GET
# read path keeps the ordinary request-scoped connection.


def _default_ingestion_uow() -> AbstractContextManager[Connection]:
    """Production start-path UoW: a fresh ``engine.begin()`` (commit on clean exit)."""
    return get_engine().begin()


_ingestion_uow: Callable[[], AbstractContextManager[Connection]] = _default_ingestion_uow


def get_ingestion_uow() -> Callable[[], AbstractContextManager[Connection]]:
    """FastAPI dependency: the start-path UoW factory (overridable in tests)."""
    return _ingestion_uow


_enqueuer: IngestionEnqueuer = CeleryIngestionEnqueuer()


def get_ingestion_enqueuer() -> IngestionEnqueuer:
    """FastAPI dependency: the process-wide ingestion enqueuer (overridable in tests)."""
    return _enqueuer


def build_start_ingestion(conn: Connection) -> StartIngestion:
    """Wire ``StartIngestion`` on a start-path UoW connection (not request-scoped)."""
    return StartIngestion(
        sources=SqlAlchemySourceRepository(conn),
        jobs=SqlAlchemyIngestionJobRepository(conn),
        events=SqlAlchemyIngestionEventRepository(conn),
        authorize=AuthorizeOwnership(),
        clock=_clock,
        ids=uuid4,
    )


def build_compensate(conn: Connection) -> RunIngestion:
    """Wire the enqueue-failure compensation driver on a start-path UoW connection.

    Only ``RunIngestion.fail`` is used (it never invokes the step), so the no-op
    step keeps the Phase-5 boundary intact — no parsing happens on this path.
    """
    return RunIngestion(
        sources=SqlAlchemySourceRepository(conn),
        jobs=SqlAlchemyIngestionJobRepository(conn),
        events=SqlAlchemyIngestionEventRepository(conn),
        step=NoOpIngestionStep(),
        clock=_clock,
        ids=uuid4,
    )


def get_read_ingestion(conn: DbConnection) -> ReadIngestion:
    return ReadIngestion(
        sources=SqlAlchemySourceRepository(conn),
        jobs=SqlAlchemyIngestionJobRepository(conn),
        events=SqlAlchemyIngestionEventRepository(conn),
        authorize=AuthorizeOwnership(),
    )


def get_read_source_structure(conn: DbConnection) -> ReadSourceStructure:
    return ReadSourceStructure(
        sources=SqlAlchemySourceRepository(conn),
        corpus=SqlAlchemyCorpusRepository(conn),
        authorize=AuthorizeOwnership(),
    )


def get_read_section(conn: DbConnection) -> ReadSection:
    return ReadSection(
        sources=SqlAlchemySourceRepository(conn),
        corpus=SqlAlchemyCorpusRepository(conn),
        authorize=AuthorizeOwnership(),
    )


def get_retrieve_evidence(conn: DbConnection) -> RetrieveEvidence:
    """Wire ``RetrieveEvidence`` on the request-scoped connection (RET-13/20).

    Mirrors ``get_read_source_structure``: the source repo enforces ownership, the
    hybrid retrieval repo and the settings-selected embedding adapter drive the
    query (so the query embedding matches the document embedding), and the per-arm
    limits / RRF ``k`` / HNSW ``ef_search`` / default ``top_k`` are all sourced from
    ``LEARNY_``-prefixed settings (never hard-coded).
    """
    settings = get_settings()
    return RetrieveEvidence(
        sources=SqlAlchemySourceRepository(conn),
        retrieval=SqlAlchemyRetrievalRepository(conn),
        embeddings=build_embedding_adapter(settings),
        authorize=AuthorizeOwnership(),
        semantic_limit=settings.retrieval_semantic_limit,
        lexical_limit=settings.retrieval_lexical_limit,
        rrf_k=settings.retrieval_rrf_k,
        ef_search=settings.hnsw_ef_search,
        default_top_k=settings.retrieval_top_k,
    )


# Process-wide answer generator, selected from settings at first use (ADR-0020).
# ``local`` (default) stays deterministic and network-free; ``anthropic`` builds the
# Claude adapter. Cached like ``get_settings`` so the provider is resolved once per
# process, and overridable in tests via ``dependency_overrides[get_answer_generation]``
# exactly like before.
@lru_cache
def get_answer_generation() -> AnswerGenerationPort:
    """FastAPI dependency: the settings-selected answer generator (overridable in tests)."""
    return build_answer_adapter(get_settings())


AnswerGeneration = Annotated[AnswerGenerationPort, Depends(get_answer_generation)]


def get_ask_question(conn: DbConnection, generation: AnswerGeneration) -> AskQuestion:
    """Wire ``AskQuestion`` on the request-scoped connection (QA-01..04, 07..08).

    Composes the source repo (ownership + readiness), the existing
    ``get_retrieve_evidence`` product (Phase-6 retrieval consumed whole), the
    process-wide answer generator, and the server-controlled ``qa_evidence_top_k``
    budget. Injecting ``generation`` via ``Depends`` keeps it test-overridable.
    """
    return AskQuestion(
        sources=SqlAlchemySourceRepository(conn),
        authorize=AuthorizeOwnership(),
        retrieve=get_retrieve_evidence(conn),
        generation=generation,
        evidence_top_k=get_settings().qa_evidence_top_k,
    )


# --- Teaching sessions (Phase 8) -----------------------------------------------
#
# The session start/read/list services are wired on the request-scoped connection,
# exactly like the Q&A path: the source repo enforces ownership, the corpus repo
# resolves the target section, and the teaching repos persist/read the aggregate.
# The turn service adds the scoped retrieval product and the teaching generator.


def get_start_teaching_session(conn: DbConnection) -> StartTeachingSession:
    """Wire ``StartTeachingSession`` on the request-scoped connection (TEACH-01..04)."""
    return StartTeachingSession(
        sources=SqlAlchemySourceRepository(conn),
        corpus=SqlAlchemyCorpusRepository(conn),
        sessions=SqlAlchemyTeachingSessionRepository(conn),
        authorize=AuthorizeOwnership(),
        clock=_clock,
        ids=uuid4,
    )


def get_read_teaching_session(conn: DbConnection) -> ReadTeachingSession:
    """Wire ``ReadTeachingSession`` on the request-scoped connection (TEACH-05/06/20)."""
    return ReadTeachingSession(
        sessions=SqlAlchemyTeachingSessionRepository(conn),
        turns=SqlAlchemyTeachingTurnRepository(conn),
        sources=SqlAlchemySourceRepository(conn),
        authorize=AuthorizeOwnership(),
    )


def get_list_teaching_sessions(conn: DbConnection) -> ListTeachingSessions:
    """Wire ``ListTeachingSessions`` on the request-scoped connection (TEACH-21)."""
    return ListTeachingSessions(
        sources=SqlAlchemySourceRepository(conn),
        sessions=SqlAlchemyTeachingSessionRepository(conn),
        authorize=AuthorizeOwnership(),
    )


# Process-wide teaching generator, selected from settings at first use (ADR-0020),
# governed by the same ``LEARNY_GENERATION_PROVIDER`` switch as the answer path (D-2):
# ``local`` (default) stays deterministic and network-free; ``anthropic`` builds the
# Claude teaching adapter. Cached like ``get_answer_generation`` so the provider is
# resolved once per process, and overridable in tests via
# ``dependency_overrides[get_teaching_generation]`` exactly as before.
@lru_cache
def get_teaching_generation() -> TeachingGenerationPort:
    """FastAPI dependency: the settings-selected teaching generator (overridable in tests)."""
    return build_teaching_adapter(get_settings())


TeachingGeneration = Annotated[TeachingGenerationPort, Depends(get_teaching_generation)]


def get_post_teaching_turn(
    conn: DbConnection, generation: TeachingGeneration
) -> PostTeachingTurn:
    """Wire ``PostTeachingTurn`` on the request-scoped connection (TEACH-07..17, 19, 24).

    Composes the teaching repos, the source repo (ownership + readiness), the
    corpus repo (target re-resolution + subtree), the Phase-6 retrieval product
    (scoped by the target subtree anchors), the process-wide teaching generator,
    and the server-controlled evidence-budget / history-turns settings. Injecting
    ``generation`` via ``Depends`` keeps it test-overridable.
    """
    settings = get_settings()
    return PostTeachingTurn(
        sessions=SqlAlchemyTeachingSessionRepository(conn),
        turns=SqlAlchemyTeachingTurnRepository(conn),
        sources=SqlAlchemySourceRepository(conn),
        corpus=SqlAlchemyCorpusRepository(conn),
        retrieve=get_retrieve_evidence(conn),
        generation=generation,
        authorize=AuthorizeOwnership(),
        clock=_clock,
        ids=uuid4,
        evidence_top_k=settings.teaching_evidence_top_k,
        history_turns=settings.teaching_history_turns,
    )


# --- Active recall (Cycle E) ---------------------------------------------------
#
# The deck POST mirrors the ingestion start path: the queued job must be committed
# before the synchronous enqueue (so the worker never dequeues a row that does not
# yet exist), and on an enqueue failure a second UoW compensates the job to
# terminal ``failed`` (so no phantom queued job blocks the QUIZ-04 single-in-flight
# guard forever). Both write UoWs go through the injectable ``get_quiz_uow``
# factory; tests override it to share the rolled-back ``db_conn``. The overview,
# due-queue, and review-submit paths are ordinary request-scoped reads/writes.


def _default_quiz_uow() -> AbstractContextManager[Connection]:
    """Production deck-POST UoW: a fresh ``engine.begin()`` (commit on clean exit)."""
    return get_engine().begin()


_quiz_uow: Callable[[], AbstractContextManager[Connection]] = _default_quiz_uow


def get_quiz_uow() -> Callable[[], AbstractContextManager[Connection]]:
    """FastAPI dependency: the deck-POST UoW factory (overridable in tests)."""
    return _quiz_uow


_quiz_enqueuer: QuizDeckEnqueuer = CeleryQuizDeckEnqueuer()


def get_quiz_deck_enqueuer() -> QuizDeckEnqueuer:
    """FastAPI dependency: the process-wide deck enqueuer (overridable in tests)."""
    return _quiz_enqueuer


def build_plan_deck_generation(conn: Connection) -> PlanDeckGeneration:
    """Wire ``PlanDeckGeneration`` on a deck-POST UoW connection (not request-scoped)."""
    return PlanDeckGeneration(
        sources=SqlAlchemySourceRepository(conn),
        jobs=SqlAlchemyQuizJobRepository(conn),
        authorize=AuthorizeOwnership(),
        clock=_clock,
        ids=uuid4,
    )


def build_deck_compensate(conn: Connection) -> RunDeckGeneration:
    """Wire the enqueue-failure compensation driver on a deck-POST UoW connection.

    Only ``RunDeckGeneration.fail`` is used on this path (it never starts a pass), so
    the concrete generation/embedding/scheduling adapters it also composes are
    inert here — they are built for parity with the worker's ``_build_run_deck``.
    """
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


def get_list_quiz_items(conn: DbConnection) -> ListQuizItems:
    """Wire ``ListQuizItems`` on the request-scoped connection (QUIZ-14)."""
    return ListQuizItems(
        sources=SqlAlchemySourceRepository(conn),
        items=SqlAlchemyQuizItemRepository(conn),
        jobs=SqlAlchemyQuizJobRepository(conn),
        authorize=AuthorizeOwnership(),
    )


def get_due_queue(conn: DbConnection) -> GetDueQueue:
    """Wire ``GetDueQueue`` on the request-scoped connection (QUIZ-13)."""
    return GetDueQueue(items=SqlAlchemyQuizItemRepository(conn), clock=_clock)


def get_export_quiz_deck(conn: DbConnection) -> ExportQuizDeck:
    """Wire ``ExportQuizDeck`` on the request-scoped connection (QUIZ-22)."""
    return ExportQuizDeck(
        sources=SqlAlchemySourceRepository(conn),
        items=SqlAlchemyQuizItemRepository(conn),
        authorize=AuthorizeOwnership(),
    )


def get_submit_review(conn: DbConnection) -> SubmitReview:
    """Wire ``SubmitReview`` on the request-scoped connection (QUIZ-12).

    A review is one atomic transaction (scheduling update + log append), so the
    ordinary auto-committing request connection is the unit of work — no separate
    commit-then-enqueue dance is needed as on the deck path.
    """
    return SubmitReview(
        items=SqlAlchemyQuizItemRepository(conn),
        sources=SqlAlchemySourceRepository(conn),
        scheduling=build_scheduling_adapter(get_settings()),
        authorize=AuthorizeOwnership(),
        clock=_clock,
    )
