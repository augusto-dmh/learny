"""Identity domain ports (design §3).

Structural interfaces (``typing.Protocol``) that application services depend on.
Concrete adapters live in ``app.infrastructure`` (B2 hasher, B3 repositories,
later the storage adapter) and are wired at the composition root. No FastAPI /
SQLAlchemy / SDK imports here (ADR-007/009).

Conventions:
- Repositories return ``None`` (not raise) on a missing lookup, so application
  services control error semantics (e.g. uniform login failure, AC-3).
- Session creation goes through the raw opaque token: callers pass the raw
  token, the adapter persists only its hash, and returns the persisted
  :class:`~app.domain.entities.Session`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import (
    ChunkToEmbed,
    CorpusSectionRecord,
    CorpusStructure,
    Evidence,
    GeneratedAnswer,
    HistoryTurn,
    IngestionEvent,
    IngestionJob,
    ParsedBook,
    PasswordCredential,
    Session,
    Source,
    TeachingSession,
    TeachingSessionSummary,
    TeachingTurn,
    User,
)


@runtime_checkable
class Clock(Protocol):
    """Source of the current time — injected so time is deterministic in tests."""

    def now(self) -> datetime:
        """Return the current timezone-aware UTC time."""
        ...


@runtime_checkable
class TokenGenerator(Protocol):
    """Source of high-entropy opaque tokens (session + CSRF).

    Injected so application services stay free of the token-generation adapter
    and so tests can supply deterministic tokens.
    """

    def generate(self) -> str:
        """Return a new high-entropy URL-safe token."""
        ...


@runtime_checkable
class PasswordHasher(Protocol):
    """Password hashing/verification port (AD-006 — Argon2id adapter in B2)."""

    def hash(self, password: str) -> str:
        """Return an encoded hash of ``password``. Never logs the input."""
        ...

    def verify(self, password: str, encoded_hash: str) -> bool:
        """Return whether ``password`` matches ``encoded_hash`` (constant-time)."""
        ...

    def needs_rehash(self, encoded_hash: str) -> bool:
        """Return whether ``encoded_hash`` was produced with outdated parameters."""
        ...

    def dummy_hash(self) -> str:
        """Return a valid encoded hash in this adapter's own format.

        Login verifies against this on the unknown-email path so the code path
        and work stay uniform (no user enumeration). Sourcing it from the port
        keeps the concrete hash encoding out of the application layer and
        guarantees it matches the active adapter, so ``verify`` does real work
        rather than failing fast on a foreign format if the adapter is swapped.
        """
        ...


@runtime_checkable
class UserRepository(Protocol):
    """Persistence port for :class:`~app.domain.entities.User`."""

    def add(self, user: User) -> User:
        """Persist a new user. Raises on duplicate email (unique constraint)."""
        ...

    def get_by_id(self, user_id: UUID) -> User | None:
        """Return the user with ``user_id``, or ``None`` if absent."""
        ...

    def get_by_email(self, email: str) -> User | None:
        """Return the user with ``email`` (case-insensitive), or ``None``."""
        ...


@runtime_checkable
class CredentialRepository(Protocol):
    """Persistence port for :class:`~app.domain.entities.PasswordCredential`."""

    def add(self, credential: PasswordCredential) -> PasswordCredential:
        """Persist a new credential for a user."""
        ...

    def get_by_user_id(self, user_id: UUID) -> PasswordCredential | None:
        """Return the credential for ``user_id``, or ``None`` if absent."""
        ...

    def update(self, credential: PasswordCredential) -> PasswordCredential:
        """Replace the stored hash/params for the credential's user."""
        ...


@runtime_checkable
class SessionRepository(Protocol):
    """Persistence port for :class:`~app.domain.entities.Session`.

    The adapter is responsible for hashing the raw opaque token at rest; callers
    work with raw tokens and never see ``token_hash`` directly except via lookup.
    """

    def create(
        self,
        *,
        user_id: UUID,
        raw_token: str,
        csrf_token: str,
        expires_at: datetime,
    ) -> Session:
        """Persist a new session, storing only the hash of ``raw_token``."""
        ...

    def get_by_raw_token(self, raw_token: str) -> Session | None:
        """Resolve a raw opaque token to its session row, or ``None``."""
        ...

    def touch(self, session_id: UUID, last_seen_at: datetime) -> None:
        """Update ``last_seen_at`` for an active session."""
        ...

    def delete(self, session_id: UUID) -> None:
        """Remove a session (instant revocation / logout)."""
        ...


@runtime_checkable
class SourceRepository(Protocol):
    """Persistence port for :class:`~app.domain.entities.Source`, owner-scoped."""

    def add(self, source: Source) -> Source:
        """Insert a source. Raises on unique ``object_key`` violation."""
        ...

    def list_by_user(self, user_id: UUID) -> list[Source]:
        """Return ``user_id``'s sources, newest first (owner-scoped)."""
        ...

    def get_by_id(self, source_id: UUID) -> Source | None:
        """Return the source with ``source_id``, or ``None`` if absent."""
        ...

    def set_status(self, source_id: UUID, status: str, updated_at: datetime) -> None:
        """Update the ``source.status`` projection alongside a job transition.

        Keeps the sources-list badge (``uploaded``/``processing``/``ready``/
        ``failed``) correct without joining the ingestion tables (design fork).
        """
        ...


@runtime_checkable
class IngestionJobRepository(Protocol):
    """Persistence port for :class:`~app.domain.entities.IngestionJob`."""

    def add(self, job: IngestionJob) -> IngestionJob:
        """Insert a job. Raises on the active partial-unique violation (ING-03)."""
        ...

    def get_by_id(self, job_id: UUID) -> IngestionJob | None:
        """Return the job with ``job_id``, or ``None`` if absent."""
        ...

    def get_latest_for_source(self, source_id: UUID) -> IngestionJob | None:
        """Return the newest job for ``source_id`` (by ``created_at``), or ``None``."""
        ...

    def update(self, job: IngestionJob) -> IngestionJob:
        """Persist ``status``/``attempts``/``last_error``/``updated_at``."""
        ...


@runtime_checkable
class IngestionEventRepository(Protocol):
    """Persistence port for :class:`~app.domain.entities.IngestionEvent`."""

    def append(self, event: IngestionEvent) -> IngestionEvent:
        """Append a progress-log entry for a job."""
        ...

    def list_for_job(self, job_id: UUID) -> list[IngestionEvent]:
        """Return a job's events in chronological order (ING-06)."""
        ...


@runtime_checkable
class IngestionStep(Protocol):
    """The Phase-5 seam run inside the ingestion task (design §Components).

    The default adapter is a no-op this cycle (``# TODO(Phase 5): parse EPUB``).
    Contract: raise a retryable error for transient failures and any other
    exception for terminal failures, so the task can classify retries.
    """

    def run(self, *, source: Source, job: IngestionJob) -> None:
        """Perform the ingestion work for ``source`` under ``job``."""
        ...


@runtime_checkable
class IngestionEnqueuer(Protocol):
    """The Celery boundary — keeps ``apply_async`` out of application code.

    Called *after* the queued job is committed so the worker always sees a
    durable row; the queue message carries only ids (AD-014).
    """

    def enqueue_ingestion(self, *, source_id: UUID, job_id: UUID) -> None:
        """Enqueue the background ingestion task for ``job_id`` / ``source_id``."""
        ...


@runtime_checkable
class StoragePort(Protocol):
    """S3-compatible object-storage port (AD-008).

    Defined now so the domain boundary is stable; the MinIO adapter is minimal
    this cycle (uploads land in a later cycle). Object keys and metadata are
    owned by PostgreSQL; this port handles only blob bytes.
    """

    def put_object(self, key: str, data: bytes, *, content_type: str) -> None:
        """Store ``data`` under ``key``."""
        ...

    def get_object(self, key: str) -> bytes:
        """Return the bytes stored under ``key``. Raises if absent."""
        ...


@runtime_checkable
class EpubParserPort(Protocol):
    """Structure-preserving EPUB parse port (ADR-0002, ADR-0011 — EPUB only).

    The only seam the ebooklib/BeautifulSoup adapter sits behind (ADR-0009);
    application code depends on this protocol and the library-free
    :class:`~app.domain.entities.ParsedBook` DTO, never on parsing libraries.
    """

    def parse(self, source_bytes: bytes, *, filename: str) -> ParsedBook:
        """Parse EPUB bytes into a :class:`ParsedBook`.

        Raises :class:`~app.application.errors.InvalidEpubError` for anything
        that is not a parseable EPUB (non-EPUB bytes, corrupt archive,
        unresolvable spine) so the ingestion step can treat it as terminal
        (CORP-06).
        """
        ...


@runtime_checkable
class MarkupConverterPort(Protocol):
    """Preserved-HTML → Markdown derivation port (CORP-04, A-6).

    Kept behind a port so the concrete BeautifulSoup walker stays in
    ``app.infrastructure`` (ADR-0009). The input is the stored HTML fragment,
    never the EPUB, so the Markdown view is a derived projection of the
    canonical corpus (ADR-0002).
    """

    def to_markdown(self, html: str) -> str:
        """Return the Markdown rendering of an HTML fragment (A-6 element set)."""
        ...


@runtime_checkable
class CorpusRepository(Protocol):
    """Persistence port for the canonical corpus aggregate (ADR-0002).

    ``replace`` is delete-then-insert inside the caller's transaction so a
    re-ingestion atomically rebuilds the corpus (CORP-09) and a mid-build failure
    rolls back with no partial data (CORP-08). Ownership is reachable only via the
    parent source (AD-014) — these methods key on ``source_id``.
    """

    def replace(
        self,
        source_id: UUID,
        *,
        title: str | None,
        authors: Sequence[str],
        language: str | None,
        schema_version: int,
        sections: Sequence[CorpusSectionRecord],
    ) -> None:
        """Replace ``source_id``'s corpus with the given aggregate (CORP-09).

        Deletes any existing corpus document for the source (cascade clears its
        sections/blocks/chunks) and inserts the new document/sections/blocks/
        chunks. Runs inside the caller's transaction.
        """
        ...

    def get_structure(self, source_id: UUID) -> CorpusStructure | None:
        """Return the book structure for ``source_id``, or ``None`` if no corpus."""
        ...


@runtime_checkable
class EmbeddingPort(Protocol):
    """Text → vector port (ADR-0007 — provider behind a Learny seam).

    The provider SDK and model name live only in the adapter; callers receive
    plain ``list[float]`` vectors, so no query/repository code imports a provider
    SDK. The default adapter is deterministic and network-free (D-1).

    ``model`` is the adapter's stable model identity (model **and** dims, since
    ``large@1536`` ≠ ``large@3072``). It must be readable without a network call so
    the embed step can stamp each chunk's ``embedding_model`` for per-chunk model
    versioning (ADR-0019).
    """

    model: str

    def embed_query(self, text: str) -> list[float]:
        """Embed a single search query into one vector."""
        ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of chunk texts, returning one vector per input in order."""
        ...


@runtime_checkable
class EmbeddingIndexRepository(Protocol):
    """Persistence port for reading chunks to embed and writing their vectors.

    Ownership is reachable only via the parent source (AD-014) — both methods key
    on ``source_id`` (via the chunks→sections→documents join).
    """

    def chunks_for_source(self, source_id: UUID) -> list[ChunkToEmbed]:
        """Return ``source_id``'s chunks (id + text) to embed, stably ordered."""
        ...

    def set_embeddings(self, items: Sequence[tuple[UUID, list[float]]]) -> None:
        """Write each ``(chunk_id, vector)`` to ``corpus_chunks.embedding``."""
        ...


@runtime_checkable
class RetrievalPort(Protocol):
    """Hybrid retrieval port returning citation-ready evidence (ADR-0006).

    One statement runs the semantic (pgvector) and lexical (Postgres FTS) arms,
    fuses them with Reciprocal Rank Fusion, and projects citation anchors into
    frozen :class:`~app.domain.entities.Evidence`. Scoped to one ``source_id`` so
    there is no cross-source leakage (RET-17). Tuning knobs come from settings.
    """

    def search(
        self,
        *,
        source_id: UUID,
        query_text: str,
        query_vec: list[float],
        top_k: int,
        semantic_limit: int,
        lexical_limit: int,
        rrf_k: int,
        ef_search: int,
        anchors: Sequence[str] | None = None,
    ) -> list[Evidence]:
        """Return up to ``top_k`` fused ``Evidence`` for ``source_id``, RRF-ordered.

        When ``anchors`` is given, both arms are restricted to chunks whose section
        ``anchor`` is in the set — the target-subtree scope for teaching (TEACH-09,
        AD-031). ``None`` (the default) keeps the whole-source behaviour unchanged.
        """
        ...


@runtime_checkable
class AnswerGenerationPort(Protocol):
    """Answer-generation port — the single seam for the answer path (QA-05).

    Provider SDKs, model names, and citation formats live only in the concrete
    adapter (ADR-0007/0009); callers pass the trimmed question and the retrieved
    :class:`~app.domain.entities.Evidence`, and receive a Learny-owned
    :class:`~app.domain.entities.GeneratedAnswer`. No SQL/HTTP/SDK type crosses
    this boundary. The default adapter is deterministic and network-free (D-1).

    ``model`` is the adapter's stable model identity. It must be readable
    without calling ``generate`` because the not-found short-circuit reports a
    model identity while never invoking generation (QA-04 + QA-13).
    """

    model: str

    def generate(
        self, *, question: str, evidence: Sequence[Evidence]
    ) -> GeneratedAnswer:
        """Generate an answer grounded in ``evidence``.

        Returns ``found=False`` when the evidence cannot support an answer;
        raises for operational failure (the application service maps any raise
        to :class:`~app.application.errors.AnswerGenerationFailed`, QA-17).
        """
        ...


@runtime_checkable
class TeachingSessionRepository(Protocol):
    """Persistence port for :class:`~app.domain.entities.TeachingSession`.

    Ownership is reachable only via the parent source (AD-014) — the application
    service does the authorization; these methods key on ids.
    """

    def add(self, session: TeachingSession) -> TeachingSession:
        """Persist a new teaching session."""
        ...

    def get_by_id(self, session_id: UUID) -> TeachingSession | None:
        """Return the session with ``session_id``, or ``None`` if absent."""
        ...

    def list_for_source(self, source_id: UUID) -> list[TeachingSessionSummary]:
        """Return ``source_id``'s sessions with turn counts, newest first (TEACH-21)."""
        ...


@runtime_checkable
class TeachingTurnRepository(Protocol):
    """Persistence port for :class:`~app.domain.entities.TeachingTurn`."""

    def add(self, turn: TeachingTurn) -> TeachingTurn:
        """Persist a turn and its citation snapshots (rank = tuple position).

        Raises :class:`~app.application.errors.TeachingTurnConflict` when the
        ``(session_id, turn_index)`` unique is violated — the turn-index race
        loser (TEACH-17).
        """
        ...

    def list_for_session(self, session_id: UUID) -> list[TeachingTurn]:
        """Return a session's turns by ``turn_index`` ascending, citations loaded."""
        ...

    def recent_history(
        self, session_id: UUID, limit: int
    ) -> tuple[int, list[HistoryTurn]]:
        """Return the turn count and the last ``limit`` history pairs, oldest first.

        The turn path needs only the total (the next ``turn_index``) and the
        bounded ``(message, response_text)`` context — never the citation
        payloads — so this read skips the citation join that
        ``list_for_session`` pays for.
        """
        ...


@runtime_checkable
class TeachingGenerationPort(Protocol):
    """Teaching-response generation port — the seam for the turn path (AD-032).

    Mirrors :class:`AnswerGenerationPort`: provider SDKs, model names, and citation
    formats live only in the adapter (ADR-0007/0009); callers pass the message, the
    target section path, bounded prior ``history`` (TEACH-12), and the retrieved
    :class:`~app.domain.entities.Evidence`, and receive a Learny-owned
    :class:`~app.domain.entities.GeneratedAnswer`. The default adapter is
    deterministic and network-free (D-1).

    ``model`` is the adapter's stable model identity, readable without calling
    ``generate`` so the not-found short-circuit can report it (TEACH-11 + TEACH-24).
    """

    model: str

    def generate(
        self,
        *,
        message: str,
        target_section_path: tuple[str, ...],
        history: Sequence[HistoryTurn],
        evidence: Sequence[Evidence],
    ) -> GeneratedAnswer:
        """Generate a teaching response grounded in ``evidence``.

        Returns ``found=False`` when the evidence cannot support a response;
        raises for operational failure (the application service maps any raise
        to :class:`~app.application.errors.AnswerGenerationFailed`, TEACH-13).
        """
        ...
