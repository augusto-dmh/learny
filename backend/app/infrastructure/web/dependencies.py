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
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Request
from sqlalchemy import Connection

from app.application.corpus import ReadSourceStructure
from app.application.identity import (
    AuthenticateUser,
    AuthorizeOwnership,
    CurrentUser,
    Logout,
    RegisterUser,
)
from app.application.ingestion import ReadIngestion, RunIngestion, StartIngestion
from app.application.qa import AskQuestion
from app.application.retrieval import RetrieveEvidence
from app.application.sources import CreateSource, GetSource, ListSources
from app.core.config import Settings, get_settings
from app.domain.entities import Session, User
from app.domain.ports import AnswerGenerationPort, IngestionEnqueuer, StoragePort
from app.infrastructure.answering import DeterministicAnswerAdapter
from app.infrastructure.clock import SystemClock
from app.infrastructure.db.engine import get_engine
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemyCredentialRepository,
    SqlAlchemyIngestionEventRepository,
    SqlAlchemyIngestionJobRepository,
    SqlAlchemySessionRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyUserRepository,
)
from app.infrastructure.db.retrieval import SqlAlchemyRetrievalRepository
from app.infrastructure.embeddings import DeterministicEmbeddingAdapter
from app.infrastructure.security.password_hasher import Argon2PasswordHasher
from app.infrastructure.security.tokens import SecretsTokenGenerator
from app.infrastructure.storage.s3 import S3StorageAdapter
from app.infrastructure.worker.enqueuer import CeleryIngestionEnqueuer
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


def get_retrieve_evidence(conn: DbConnection) -> RetrieveEvidence:
    """Wire ``RetrieveEvidence`` on the request-scoped connection (RET-13/20).

    Mirrors ``get_read_source_structure``: the source repo enforces ownership, the
    hybrid retrieval repo and the deterministic embedding adapter drive the query,
    and the per-arm limits / RRF ``k`` / HNSW ``ef_search`` / default ``top_k`` are
    all sourced from ``LEARNY_``-prefixed settings (never hard-coded).
    """
    settings = get_settings()
    return RetrieveEvidence(
        sources=SqlAlchemySourceRepository(conn),
        retrieval=SqlAlchemyRetrievalRepository(conn),
        embeddings=DeterministicEmbeddingAdapter(),
        authorize=AuthorizeOwnership(),
        semantic_limit=settings.retrieval_semantic_limit,
        lexical_limit=settings.retrieval_lexical_limit,
        rrf_k=settings.retrieval_rrf_k,
        ef_search=settings.hnsw_ef_search,
        default_top_k=settings.retrieval_top_k,
    )


# Process-wide default answer generator (deterministic, network-free — AD-024).
# Overridable in tests via ``get_answer_generation``, exactly like ``get_storage``;
# swapping in a provider adapter later is a one-line change here (ADR-0007/0009).
_answering: AnswerGenerationPort = DeterministicAnswerAdapter()


def get_answer_generation() -> AnswerGenerationPort:
    """FastAPI dependency: the process-wide answer generator (overridable in tests)."""
    return _answering


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
