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

from collections.abc import Iterator, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import (
    AnchorSection,
    AnswerStreamEvent,
    Backlink,
    ChapterIndexRow,
    ChapterSection,
    ChunkToEmbed,
    CorpusSectionRecord,
    CorpusStructure,
    DerivedNoteLink,
    DueReviewItem,
    Evidence,
    GeneratedAnswer,
    HistoryTurn,
    IngestionEvent,
    IngestionJob,
    Note,
    NoteAnchor,
    NoteSummary,
    ParsedBook,
    PasswordCredential,
    QuizCandidate,
    QuizDeckHandle,
    QuizDeckResult,
    QuizGenerationJob,
    QuizItem,
    QuizSection,
    ReadingPosition,
    ReconcileSection,
    ReviewLogEntry,
    SchedulingSnapshot,
    SectionContent,
    Session,
    Source,
    SourceHighlight,
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
    durable row; the queue message carries only ids (AD-014). ``content_type``
    selects the destination queue so a heavy PDF parse never lands on the default
    worker (ING-17); the queue message itself still carries only ids.
    """

    def enqueue_ingestion(
        self, *, source_id: UUID, job_id: UUID, content_type: str
    ) -> None:
        """Enqueue the background ingestion task for ``job_id`` / ``source_id``.

        ``content_type`` is the source's stored type, used only to pick the queue.
        """
        ...


@runtime_checkable
class NoteIndexEnqueuer(Protocol):
    """The Celery boundary for maintaining a note's retrieval index (AD-016).

    Called *after* the note write is committed so the worker always reads a durable
    row (mirrors :class:`IngestionEnqueuer`); only the note id rides the queue. The
    embed task re-reads the body at run time, so a stale enqueue still embeds the
    newest body. ``enqueue_refresh_cards`` exists for the note→quiz loop (its task
    body lands in a later cycle); the web layer gates it on promoted notes.
    """

    def enqueue_embed(self, note_id: UUID) -> None:
        """Enqueue the whole-note (re)embed for ``note_id`` (empty body clears it)."""
        ...

    def enqueue_refresh_cards(self, note_id: UUID) -> None:
        """Enqueue regenerate-and-match for a promoted note's derived cards."""
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
class DocumentParserPort(Protocol):
    """Structure-preserving document parse port (ADR-0002, AD-083).

    The single format-agnostic seam each concrete parser adapter sits behind
    (ADR-0009); application code depends on this protocol and the library-free
    :class:`~app.domain.entities.ParsedBook` DTO, never on parsing libraries. A
    format-dispatch factory picks the adapter (ebooklib for EPUB, Docling for
    PDF) from the source's content type at the worker composition root.
    """

    def parse(self, source_bytes: bytes, *, filename: str) -> ParsedBook:
        """Parse document bytes into a :class:`ParsedBook`.

        Raises :class:`~app.application.errors.InvalidDocumentError` for anything
        that is not a parseable document of the adapter's format (bad bytes,
        corrupt archive, unresolvable structure) so the ingestion step can treat
        it as terminal (CORP-06).
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

    def get_section(self, source_id: UUID, anchor: str) -> SectionContent | None:
        """Return ``source_id``'s section at ``anchor``, or ``None`` if none matches."""
        ...

    def get_chapter_index(self, source_id: UUID) -> tuple[ChapterIndexRow, ...] | None:
        """Return ``source_id``'s flat, position-ordered section index, or ``None`` (RD-01).

        The lightweight read model chapter partitioning and percent math run over:
        one row per section with its position/depth/title/section_path/anchor/aliases
        and persisted ``word_count`` — deliberately *not* the section markdown, so
        building the index and computing progress never loads chapter bodies. Returns
        ``None`` when the source has no corpus (no document); an empty tuple for a
        document with no sections.
        """
        ...

    def get_sections_span(
        self, source_id: UUID, first_position: int, last_position: int
    ) -> tuple[ChapterSection, ...]:
        """Return ``source_id``'s sections in the inclusive ``[first, last]`` position span.

        The chapter-body read: each :class:`~app.domain.entities.ChapterSection` carries
        its anchor/title/section_path plus the derived ``markdown`` and ``word_count``,
        position-ordered. Loads markdown for one chapter's span only (not the whole book).
        """
        ...

    def section_texts(self, source_id: UUID) -> list[ReconcileSection]:
        """Return every section's anchor/path plus its chunk text, in reading order (QUIZ-16).

        The corpus text index quiz reconciliation reads after a corpus replace: each
        :class:`~app.domain.entities.ReconcileSection` carries the section's concatenated
        chunk text so a snapshotted ``source_excerpt`` can be re-checked for presence, plus
        its ``anchor_aliases`` so an item snapshotted against a merged-away anchor reconciles
        to the surviving section (AD-085). All sections (leaf or not) are returned so a
        relocated quote can be found anywhere.
        """
        ...

    def expand_anchors(
        self, source_id: UUID, anchors: Sequence[str]
    ) -> tuple[str, ...]:
        """Grow ``anchors`` to include the aliases of the sections they resolve to (AD-085).

        Returns the input anchors plus, for every section whose canonical anchor is in
        ``anchors`` or that carries one of ``anchors`` as an alias, that section's canonical
        anchor and all its aliases (deduplicated, input order preserved). Teaching-scoped
        retrieval expands its target subtree through this so evidence from a section that
        normalization merged away is still reachable (ING-23). An empty input returns empty.
        """
        ...

    def blocks_for_section(self, source_id: UUID, anchor: str) -> AnchorSection | None:
        """Return the section addressed by ``anchor`` with its blocks, or ``None`` (NF-06).

        Resolves the section canonical-first then by alias (like :meth:`get_section`) and
        returns its canonical anchor, ``section_path``, aliases, and reading-order blocks
        (ordinal + stored ``content_hash`` + preserved ``html_fragment``). The highlight
        capture path derives each block's Markdown from the fragment to bind a selection.
        """
        ...

    def blocks_for_reconcile(self, source_id: UUID) -> list[AnchorSection]:
        """Return every section with its blocks, in reading order, for reconcile (NF-07).

        The block-level analogue of :meth:`section_texts`: each :class:`AnchorSection`
        carries its canonical anchor/path, ``anchor_aliases``, and reading-order blocks so
        the 4-tier cascade can match a stored anchor by block hash and rebind its quote.
        """
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

    def stale_chunks_for_source(
        self, source_id: UUID, model: str, limit: int
    ) -> list[ChunkToEmbed]:
        """Return up to ``limit`` of ``source_id``'s chunks needing (re)embedding.

        Selects the not-yet-embedded (``embedding IS NULL``) and stale-model
        (``embedding_model`` distinct from ``model``) chunks, stably ordered like
        :meth:`chunks_for_source`, bounded to ``limit`` rows in SQL. The caller
        re-queries per committed batch, so committed progress shrinks this set as it
        lands (idempotent + resumable, ADR-0019); pushing the batch bound into the
        query keeps each pass O(limit) instead of scanning the whole remaining set.
        """
        ...

    def set_embeddings(
        self, items: Sequence[tuple[UUID, list[float]]], *, model: str
    ) -> None:
        """Write each ``(chunk_id, vector)`` plus ``model`` to ``corpus_chunks``.

        Persists the vector and the active adapter's stable ``model`` identity into
        ``embedding`` and ``embedding_model`` in the one write, so every embedded
        chunk records which model produced it (per-chunk model versioning, ADR-0019).
        """
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
        user_id: UUID | None = None,
        include_notes: bool = False,
    ) -> list[Evidence]:
        """Return up to ``top_k`` fused ``Evidence`` for ``source_id``, RRF-ordered.

        When ``anchors`` is given, both book arms are restricted to chunks whose section
        ``anchor`` is in the set — the target-subtree scope for teaching (TEACH-09,
        AD-031). ``None`` (the default) keeps the whole-source behaviour unchanged.

        When ``include_notes`` and ``user_id`` are both provided, two additional RRF
        arms over that user's own notes (semantic + lexical) are fused into the same
        ranking behind a notes weight (ADR-0026 d4, NL-02); note evidence carries
        ``origin='note'`` and the note's identity. Either omitted keeps the book-only
        behaviour byte-identical (the anchors, if any, constrain only the book arms —
        notes have no anchors).
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

    def generate_stream(
        self, *, question: str, evidence: Sequence[Evidence]
    ) -> Iterator[AnswerStreamEvent]:
        """Stream the same answer as :meth:`generate`, incrementally (GEN-12).

        Yields zero or more :class:`~app.domain.entities.AnswerTextDelta` then
        exactly one :class:`~app.domain.entities.AnswerCompleted` (always last),
        whose ``answer`` is authoritative. Closing the iterator early cancels the
        underlying generation; raises for operational failure like
        :meth:`generate`.
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

    def generate_stream(
        self,
        *,
        message: str,
        target_section_path: tuple[str, ...],
        history: Sequence[HistoryTurn],
        evidence: Sequence[Evidence],
    ) -> Iterator[AnswerStreamEvent]:
        """Stream the same teaching response as :meth:`generate`, incrementally (GEN-12).

        Yields zero or more :class:`~app.domain.entities.AnswerTextDelta` then
        exactly one :class:`~app.domain.entities.AnswerCompleted` (always last),
        whose ``answer`` is authoritative. Closing the iterator early cancels the
        underlying generation; raises for operational failure like
        :meth:`generate`.
        """
        ...


# --- Active recall ports (Cycle E, RFC-002; design §Domain) ----------------------


@runtime_checkable
class QuizGenerationPort(Protocol):
    """Deck-generation port — the single seam for quiz item candidates (QUIZ-05).

    Provider SDKs, model names, and structured-output shapes live only in the concrete
    adapter (ADR-0007/0009); callers pass eligible :class:`~app.domain.entities.QuizSection`
    and receive Learny-owned candidates. The default adapter is deterministic and
    network-free; the Anthropic adapter drives the Message Batches API, so generation is
    asynchronous: :meth:`begin_deck` starts a pass and returns a
    :class:`~app.domain.entities.QuizDeckHandle`, and :meth:`collect_deck` is polled
    until it returns a result (``None`` while still pending).

    ``model`` is the adapter's stable model identity, readable without a network call so
    the job can record which model produced the deck.
    """

    model: str

    def begin_deck(self, sections: Sequence[QuizSection]) -> QuizDeckHandle:
        """Start a generation pass over ``sections``; return a handle to collect from.

        The local adapter computes results inline and carries them on the handle; the
        Anthropic adapter submits one batch request per section and carries the batch id.
        """
        ...

    def collect_deck(self, handle: QuizDeckHandle) -> QuizDeckResult | None:
        """Return the pass's :class:`~app.domain.entities.QuizDeckResult`, or ``None``.

        ``None`` means the underlying batch is still in progress and the caller should
        poll again later; a result means the pass finished (per-request failures are
        surfaced as the result's ``errors``).
        """
        ...

    def suggest_cards(
        self, section: QuizSection, quote: str, limit: int
    ) -> list[QuizCandidate]:
        """Return at most ``limit`` candidates scoped to ``quote`` within ``section``.

        The foreground counterpart of the batched deck path (AD-134): the student is
        waiting on a popover, so this is synchronous — the local adapter derives its
        candidates inline and the Anthropic adapter issues one Messages call with the
        same structured-output schema, its ``source_chunk_id`` enum still constrained to
        ``section``'s chunks. Candidates are ungrounded until the caller's QC pipeline
        re-verifies them; a ``quote`` that appears in none of ``section``'s chunks yields
        an empty list rather than an error.
        """
        ...


@runtime_checkable
class SchedulingPort(Protocol):
    """FSRS-6 spaced-repetition port (QUIZ-11 — py-fsrs adapter in Phase D).

    The scheduling library lives only in the adapter; callers work with the Learny-owned
    :class:`~app.domain.entities.SchedulingSnapshot`. All datetimes are UTC.
    """

    def initial(self) -> SchedulingSnapshot:
        """Return the initial scheduling state for a new item (``due`` now, Learning)."""
        ...

    def review(
        self, snapshot: SchedulingSnapshot, rating: int, reviewed_at: datetime
    ) -> tuple[SchedulingSnapshot, ReviewLogEntry]:
        """Apply a grade to ``snapshot`` at ``reviewed_at``.

        Returns the advanced snapshot and the review-log entry to append (rating +
        ``reviewed_at``; the service attaches any client-supplied duration). ``rating``
        is FSRS's Again(1)/Hard(2)/Good(3)/Easy(4).
        """
        ...


@runtime_checkable
class QuizDeckEnqueuer(Protocol):
    """The Celery boundary for deck generation (mirrors :class:`IngestionEnqueuer`).

    Called *after* the queued job is committed so the worker always sees a durable row;
    the queue message carries only ids (AD-014).
    """

    def enqueue_quiz_deck(self, *, source_id: UUID, job_id: UUID) -> None:
        """Enqueue the background deck-generation task for ``job_id`` / ``source_id``."""
        ...


@runtime_checkable
class QuizJobRepository(Protocol):
    """Persistence port for :class:`~app.domain.entities.QuizGenerationJob`.

    Mirrors :class:`IngestionJobRepository`; the active-job guard (QUIZ-04) is a query
    (:meth:`get_active_for_source`) rather than a partial unique index.
    """

    def add(self, job: QuizGenerationJob) -> QuizGenerationJob:
        """Insert a new deck-generation job."""
        ...

    def get_by_id(self, job_id: UUID) -> QuizGenerationJob | None:
        """Return the job with ``job_id``, or ``None`` if absent."""
        ...

    def get_active_for_source(self, source_id: UUID) -> QuizGenerationJob | None:
        """Return the source's queued/running job if one exists (QUIZ-04), else ``None``."""
        ...

    def get_latest_for_source(self, source_id: UUID) -> QuizGenerationJob | None:
        """Return the newest job for ``source_id`` (by ``created_at``), or ``None``."""
        ...

    def update(self, job: QuizGenerationJob) -> QuizGenerationJob:
        """Persist ``status``/``attempts``/counts/``last_error``/``updated_at``."""
        ...


@runtime_checkable
class QuizItemRepository(Protocol):
    """Persistence port for the quiz-item aggregate (design §Repositories).

    Ownership is reachable only via the parent source (AD-014) — read/due methods key on
    ``source_id``/``user_id`` through the sources join. Upsert never touches an existing
    item's scheduling or review log (QUIZ-02).
    """

    def sections_for_generation(self, source_id: UUID, *, min_chars: int) -> list[QuizSection]:
        """Return ``source_id``'s eligible leaf sections (≥ ``min_chars`` of text, A-3).

        Each carries the section's citation anchors and its ``(chunk_id, text)`` chunks
        for candidate grounding.
        """
        ...

    def section_for_anchor(self, source_id: UUID, anchor: str) -> QuizSection | None:
        """Return the single section ``anchor`` cites, or ``None`` if it resolves to none.

        The quote-scoped counterpart of :meth:`sections_for_generation`: a highlight
        names exactly one section, and neither the leaf test nor the ``min_chars`` floor
        applies — those bound whole-deck density, whereas a passage the student chose is
        eligible whatever section it sits in. Resolution is canonical-anchor-first then
        by alias, matching the note-anchoring reads, and the section carries its
        ``(chunk_id, text)`` chunks so a candidate's citation stays constrained to them.
        """
        ...

    def existing_embeddings(self, source_id: UUID) -> list[tuple[UUID, list[float]]]:
        """Return ``(item_id, embedding)`` for the source's already-embedded items.

        The dedup back-catalog a new pass compares candidates against (QUIZ-08); items
        without a stored embedding are omitted.
        """
        ...

    def upsert(self, item: QuizItem, *, embedding: Sequence[float] | None) -> bool:
        """Upsert on the item's origin-scoped identity; update content fields only.

        Returns ``True`` when a new row was inserted (the caller creates its initial
        scheduling row) and ``False`` when an existing row's content was updated — in
        which case its scheduling and review-log rows are left untouched (QUIZ-02).

        ``deck`` items collapse on ``(source_id, content_key)``; ``highlight`` items
        collapse on ``(note_anchor_id, content_key)``, so re-accepting the same text
        from one highlight is idempotent while two highlights may share a key.
        """
        ...

    def get_by_anchor_and_key(
        self, note_anchor_id: UUID, content_key: str
    ) -> QuizItem | None:
        """Return the ``highlight`` card already stored for this anchor + fingerprint.

        ``None`` when the student has not accepted this text from this highlight yet.
        """
        ...

    def update_text(
        self, item_id: UUID, *, question: str, answer: str, content_key: str
    ) -> None:
        """Rewrite a card's text and fingerprint, keeping its identity (CAP-12).

        Never touches the item's scheduling snapshot or its review log, so editing a
        card costs none of its memory history.
        """
        ...

    def create_scheduling(self, quiz_item_id: UUID, snapshot: SchedulingSnapshot) -> None:
        """Insert the initial scheduling row for a newly created item (QUIZ-09)."""
        ...

    def get_scheduling(self, quiz_item_id: UUID) -> SchedulingSnapshot | None:
        """Return the item's current scheduling snapshot, or ``None`` if absent."""
        ...

    def update_scheduling(self, quiz_item_id: UUID, snapshot: SchedulingSnapshot) -> None:
        """Replace the item's scheduling snapshot after a review (QUIZ-12)."""
        ...

    def append_log(self, quiz_item_id: UUID, entry: ReviewLogEntry) -> None:
        """Append an immutable review-log entry for the item (QUIZ-12)."""
        ...

    def list_for_source(self, source_id: UUID) -> list[QuizItem]:
        """Return all of ``source_id``'s items (any status), for the overview (QUIZ-14)."""
        ...

    def due_map(self, source_id: UUID) -> dict[UUID, datetime]:
        """Return ``item_id → due`` for ``source_id``'s items — the overview's due column."""
        ...

    def counts_by_status(self, source_id: UUID) -> dict[str, int]:
        """Return ``status → count`` for ``source_id``'s items (QUIZ-14)."""
        ...

    def due_for_user(
        self,
        user_id: UUID,
        *,
        now: datetime,
        limit: int,
        source_id: UUID | None = None,
    ) -> tuple[int, list[DueReviewItem]]:
        """Return the caller's due queue: total due count and up to ``limit`` items.

        Active items with ``due <= now`` across the user's sources (optionally filtered
        to one ``source_id``), ordered ``due ASC, id ASC`` (A-6). Stale/orphaned items
        are excluded (QUIZ-17). The count is the full due total before the limit.
        """
        ...

    def get_by_id(self, item_id: UUID) -> QuizItem | None:
        """Return the item with ``item_id``, or ``None`` if absent."""
        ...

    def items_for_reconcile(self, source_id: UUID) -> list[QuizItem]:
        """Return ``source_id``'s items for post-re-ingestion reconciliation (QUIZ-16)."""
        ...

    def update_reconciliation(
        self,
        item_id: UUID,
        *,
        anchor: str,
        section_path: Sequence[str],
        status: str,
    ) -> None:
        """Update only an item's ``anchor``/``section_path``/``status`` (QUIZ-16).

        Reconciliation touches these three fields only — scheduling and review-log rows
        are never modified or deleted.
        """
        ...


# --- Notes & second-brain ports (RFC-003 Cycle E; ADR-0026 §1-2) -----------------


@runtime_checkable
class NoteRepository(Protocol):
    """Persistence port for the notes aggregate (ADR-0026 §2, design §Repositories).

    Owner scoping is the application service's job (AD-014) — these methods key on ids
    and ``user_id``. Notes and anchors never cascade from corpus/source deletion (the
    inverse-cascade invariant lives in the schema); reconciliation and the source-delete
    orphan flip are explicit writes here. Operates on the caller's ``Connection`` so the
    transaction boundary (e.g. atomic note+anchor create) lives at the composition root.
    """

    def add(self, note: Note) -> Note:
        """Insert a new note."""
        ...

    def get_by_id(self, note_id: UUID) -> Note | None:
        """Return the note with ``note_id``, or ``None`` if absent."""
        ...

    def update(
        self, note_id: UUID, *, title: str, body_markdown: str, updated_at: datetime
    ) -> None:
        """Persist a note's ``title``/``body_markdown``/``updated_at`` (NF-05)."""
        ...

    def set_embedding(
        self, note_id: UUID, *, embedding: list[float] | None, model: str | None
    ) -> None:
        """Write (or clear) a note's whole-note ``embedding`` + ``embedding_model`` (NL-01).

        ``None``/``None`` clears both, so an emptied note leaves the semantic arm
        (async embed maintenance, never a note write's concern).
        """
        ...

    def delete(self, note_id: UUID) -> None:
        """Delete a note; its anchors/tags/links cascade, inbound links SET NULL (NF-01)."""
        ...

    def list_summaries(
        self, user_id: UUID, *, tag: str | None = None
    ) -> list[NoteSummary]:
        """Return the user's notes (newest-edited first) with tags and anchor statuses.

        When ``tag`` (already lowercased) is given, only notes carrying that tag are
        returned; every returned summary still lists all of its tags (NF-13).
        """
        ...

    def tags_for_note(self, note_id: UUID) -> list[str]:
        """Return a note's tag names, sorted."""
        ...

    def anchors_for_note(self, note_id: UUID) -> list[NoteAnchor]:
        """Return a note's anchors in creation order (NF-10)."""
        ...

    def backlinks(self, note_id: UUID) -> list[Backlink]:
        """Return the distinct notes whose wikilinks resolve to ``note_id`` (NF-10)."""
        ...

    def resolve_titles(
        self, user_id: UUID, titles: Sequence[str]
    ) -> dict[str, UUID]:
        """Map each lowercased title to the user's earliest note of that title (NF-05).

        The wikilink resolver: a ``[[title]]`` matches case-insensitively; ties resolve
        to the earliest-created note. Titles with no match are absent from the result.
        """
        ...

    def set_tags(self, note_id: UUID, user_id: UUID, names: Sequence[str]) -> None:
        """Replace a note's tags with ``names`` (already lowercased/deduped by the caller).

        Get-or-creates each tag under ``(user_id, name)`` so two casings never coexist,
        then rewires ``note_tags`` for the note (the derived-index rewrite, NF-05).
        """
        ...

    def set_links(self, note_id: UUID, links: Sequence[DerivedNoteLink]) -> None:
        """Replace a note's derived wikilinks (NF-05) — delete-then-insert."""
        ...

    def add_anchor(self, anchor: NoteAnchor) -> NoteAnchor:
        """Insert a note anchor (NF-06)."""
        ...

    def get_anchor(self, anchor_id: UUID) -> NoteAnchor | None:
        """Return the anchor with ``anchor_id``, or ``None`` if absent.

        Owner-agnostic like the rest of this port: the caller authorizes through the
        anchor's note (CAP-09 — a cross-owner anchor is a 404, never a 403).
        """
        ...

    def anchors_for_source(self, source_id: UUID) -> list[NoteAnchor]:
        """Return every anchor citing ``source_id`` for reconciliation (NF-07)."""
        ...

    def highlights_for_source(
        self, user_id: UUID, source_id: UUID
    ) -> tuple[SourceHighlight, ...]:
        """Return the caller's highlights on ``source_id`` for inline painting (RD-28).

        Scoped to ``(user_id, source_id)`` — a note anchor belongs to its note's owner,
        so this joins ``note_anchors`` to ``notes`` and filters by ``user_id`` (unlike the
        reconciliation-scoped :meth:`anchors_for_source`, which spans all owners of a
        source). Returns each anchor's quote-with-context + status as a lightweight
        :class:`~app.domain.entities.SourceHighlight`; the reader paints ``active`` ones.
        """
        ...

    def update_anchor_reconciliation(
        self,
        anchor_id: UUID,
        *,
        anchor: str,
        section_path: Sequence[str],
        block_hash: str | None,
        block_ordinal: int | None,
        start_offset: int | None,
        end_offset: int | None,
        status: str,
    ) -> None:
        """Write only an anchor's payload fields + status (NF-07); never the note body."""
        ...

    def orphan_anchors_for_source(self, source_id: UUID) -> None:
        """Flip every non-orphaned anchor citing ``source_id`` to ``orphaned`` (NF-08)."""
        ...


# --- Reader progress (RFC-004 Cycle B; design §Ports) ----------------------------


@runtime_checkable
class ReadingPositionRepository(Protocol):
    """Persistence port for :class:`~app.domain.entities.ReadingPosition` (RD-08/12).

    Owner scoping is the application service's job (AD-014) — these methods key on
    ``(user_id, source_id)``. ``upsert`` is a last-write-wins ``INSERT ... ON CONFLICT
    DO UPDATE`` on that primary key, so two concurrent sessions never conflict: the
    later write by server time wins (RD-12) with no error surfaced.
    """

    def get(self, user_id: UUID, source_id: UUID) -> ReadingPosition | None:
        """Return the caller's stored position for ``source_id``, or ``None`` if none."""
        ...

    def upsert(
        self,
        user_id: UUID,
        source_id: UUID,
        *,
        anchor: str,
        percent: Decimal,
        updated_at: datetime,
    ) -> ReadingPosition:
        """Insert or overwrite the caller's position for ``source_id`` (last-write-wins).

        Writes ``anchor``/``percent``/``updated_at`` for ``(user_id, source_id)`` and
        returns the stored :class:`~app.domain.entities.ReadingPosition`.
        """
        ...
