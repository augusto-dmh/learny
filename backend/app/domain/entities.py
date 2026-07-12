"""Identity domain entities (design §3).

Pure domain objects: no FastAPI, SQLAlchemy, or provider-SDK imports
(ADR-007/009 — ``domain`` depends on nothing outward). Persistence,
hashing, and HTTP concerns live in ``app.infrastructure`` adapters that
implement the ports in ``app.domain.ports``.

Security invariants encoded here:
- ``User`` carries no password material (AD-006 / spec AC-4) — credentials
  live only on ``PasswordCredential``.
- ``Session`` carries only the *hash* of the opaque token; the raw token is
  returned once at creation time and never persisted on the entity (design §4).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class User:
    """An authenticated account holder.

    Deliberately holds no password/hash/secret field: password material is
    isolated on :class:`PasswordCredential` so a ``User`` is safe to surface in
    summaries and logs (spec AC-4 / NFR-SEC-004).
    """

    id: UUID
    email: str
    created_at: datetime


@dataclass(frozen=True)
class PasswordCredential:
    """An Argon2id password hash for a user (AD-006).

    ``algo_params`` captures the hashing parameters in effect when the hash was
    produced, enabling rehash-on-params-change (B2). The plaintext password is
    never stored on this entity — only the encoded ``password_hash``.
    """

    user_id: UUID
    password_hash: str
    algo_params: dict[str, object]
    updated_at: datetime


@dataclass(frozen=True)
class Session:
    """A server-side opaque session (AD-006/007).

    Only ``token_hash`` is persisted; the raw opaque token lives solely in the
    HTTP-only cookie and is resolved back to this row on each authenticated
    request. ``csrf_token`` is the session-bound synchronizer token (AD-007).
    """

    id: UUID
    user_id: UUID
    token_hash: str
    csrf_token: str
    expires_at: datetime
    created_at: datetime
    last_seen_at: datetime

    def is_expired(self, now: datetime) -> bool:
        """Return whether this session has passed its expiry at ``now``."""
        return now >= self.expires_at


@dataclass(frozen=True)
class IssuedSession:
    """A freshly created session plus its one-time raw token.

    Repositories return this from ``create`` so the web layer can set the cookie
    with the raw opaque token exactly once; the raw token is never stored.
    """

    session: Session
    raw_token: str


@dataclass(frozen=True)
class Source:
    """An uploaded source file owned by a user (Cycle 2, design §Components).

    Immutable record: the original bytes live in object storage under
    ``object_key``; this entity holds only the metadata PostgreSQL owns.
    ``object_key`` and ``checksum`` are internal — the web summary path never
    surfaces them (spec P1-Upload AC1). One EPUB file per source this cycle, so
    file attributes are inline rather than in a separate table.
    """

    id: UUID
    user_id: UUID
    title: str
    filename: str
    content_type: str
    byte_size: int
    checksum: str
    object_key: str
    status: str
    created_at: datetime
    updated_at: datetime


class IngestionStatus:
    """Ingestion job status vocabulary (spec §Assumptions).

    ``queued`` and ``running`` are the two *active* states; ``succeeded`` and
    ``failed`` are terminal. String constants (not an enum) because the DB column
    is free-text ``Text`` and ``source.status`` is a plain string projection.
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


# At most one job in these states may exist per source (ING-03 concurrency guard,
# enforced by a partial unique index at the persistence layer).
ACTIVE_STATUSES = frozenset({IngestionStatus.QUEUED, IngestionStatus.RUNNING})


class IngestionEventType:
    """Ordered lifecycle-event vocabulary for the ingestion progress log.

    A successful run appends ``[queued, started, succeeded]``; a failing run
    appends ``[queued, started, retrying..., failed]`` (spec P1 Observe / Retry).
    """

    QUEUED = "queued"
    STARTED = "started"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class IngestionJob:
    """A durable ingestion job driving one source through its lifecycle.

    Immutable record: the transition helpers return *new* instances so state
    changes are explicit and the persisted row is updated by the caller's
    unit of work. Ownership is reachable only via the parent ``source`` (which
    holds ``user_id``); the job carries no ``user_id`` (AD-014).
    """

    id: UUID
    source_id: UUID
    status: str
    attempts: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    def started(self, now: datetime) -> IngestionJob:
        """Begin an attempt: → ``running`` and increment ``attempts`` (ING-02)."""
        return replace(
            self,
            status=IngestionStatus.RUNNING,
            attempts=self.attempts + 1,
            updated_at=now,
        )

    def succeeded(self, now: datetime) -> IngestionJob:
        """Terminal success: → ``succeeded`` (ING-02)."""
        return replace(self, status=IngestionStatus.SUCCEEDED, updated_at=now)

    def retrying(self, now: datetime, error: str) -> IngestionJob:
        """Record a retryable failure: set ``last_error``, stay ``running`` (ING-07)."""
        return replace(self, last_error=error, updated_at=now)

    def failed(self, now: datetime, error: str) -> IngestionJob:
        """Terminal failure: → ``failed`` with a durable ``last_error`` (ING-08)."""
        return replace(
            self,
            status=IngestionStatus.FAILED,
            last_error=error,
            updated_at=now,
        )


@dataclass(frozen=True)
class IngestionEvent:
    """An append-only progress-log entry for an ingestion job (ING-06).

    ``message`` carries a redacted, non-secret summary (e.g. the error text on
    ``retrying``/``failed``); it is ``None`` for plain lifecycle transitions.
    """

    id: UUID
    job_id: UUID
    type: str
    message: str | None
    created_at: datetime


@dataclass(frozen=True)
class ParsedBlock:
    """A single content block extracted from an EPUB spine document (ADR-0002).

    Preserves the block's raw outer HTML (``html_fragment``) rather than a
    flattened text form, so the Markdown view can be re-derived later without
    re-ingesting (ADR-0002). ``position`` is the block's index in global reading
    order; ``block_type`` is the coarse element kind (``heading``/``paragraph``/
    ``list``/``table``/...). Library-free (ADR-0009): no ebooklib/bs4 type leaks
    across this boundary.
    """

    position: int
    block_type: str
    html_fragment: str


@dataclass(frozen=True)
class ParsedSection:
    """A TOC-derived section of a parsed book (A-1/A-2).

    A section corresponds to a table-of-contents entry (or an A-2 fallback for a
    spine document the TOC omits). ``section_path`` is the root-to-node tuple of
    TOC titles used for citations; ``anchor`` is ``href[#fragment]`` (A-4).
    ``blocks`` are this section's content blocks in reading order (ADR-0002).
    """

    position: int
    title: str
    depth: int
    section_path: tuple[str, ...]
    anchor: str
    blocks: tuple[ParsedBlock, ...]


@dataclass(frozen=True)
class ParsedBook:
    """The library-free result of parsing an EPUB (ADR-0009).

    Book-level OPF metadata plus the spine-ordered sections (A-3: linear items
    only). ``title``/``language`` are ``None`` and ``authors`` empty when the OPF
    omits them (CORP-01). This is the boundary DTO between the parser adapter and
    the ``BuildCorpus`` use case — no ebooklib/bs4 types cross it (ADR-0009).
    """

    title: str | None
    authors: tuple[str, ...]
    language: str | None
    sections: tuple[ParsedSection, ...]


@dataclass(frozen=True)
class SectionChunk:
    """A retrieval chunk carrying its section's citation anchors (CORP-05).

    A chunk never crosses a section boundary; it carries the section's
    ``section_path`` and ``anchor`` so retrieval results cite exact passages
    (ADR-0003). ``page_span`` is always ``None`` for EPUB (A-9) — the field is
    reserved for future PDF citations. ``index`` is the chunk's order within its
    section.
    """

    index: int
    text: str
    section_path: tuple[str, ...]
    anchor: str
    page_span: None


@dataclass(frozen=True)
class CorpusSectionRecord:
    """The persistable aggregate item for one section (CORP-04).

    Bundles a parsed section with its derived Markdown view and its retrieval
    chunks, so ``CorpusRepository.replace`` writes the whole section aggregate
    (document → sections → blocks → chunks) in one call.
    """

    section: ParsedSection
    markdown: str
    chunks: tuple[SectionChunk, ...]


@dataclass(frozen=True)
class StructureSection:
    """A flat, ordered section node in the structure read model (CORP-11).

    Depth/position-ordered; the TOC nesting tree is reconstructed at the web
    layer from ``depth`` (design keeps SQL and domain flat — no recursive query).
    """

    position: int
    title: str
    depth: int
    section_path: tuple[str, ...]
    anchor: str


@dataclass(frozen=True)
class CorpusStructure:
    """The book structure read model returned to its owner (CORP-11).

    Book metadata plus the flat, depth/position-ordered sections; the web layer
    nests them per the TOC hierarchy for the response.
    """

    title: str | None
    authors: tuple[str, ...]
    language: str | None
    sections: tuple[StructureSection, ...]


@dataclass(frozen=True)
class ChunkToEmbed:
    """The embed step's read DTO: one chunk's id and text to embed (design §4).

    Carried from the embedding-index repository to the ``EmbedCorpus`` service so
    the embedding path depends on no persistence types — only the chunk's stable
    ``id`` (for the write-back) and its ``text`` (the embedding input).
    """

    id: UUID
    text: str


@dataclass(frozen=True)
class Evidence:
    """A citation-ready retrieval result projecting a ``corpus_chunks`` row (ADR-0003).

    The fused hybrid query returns these ordered by descending RRF ``score``. Each
    carries the stable citation anchors (``chunk_id``, ``section_path``, ``anchor``,
    ``page_span``) so Q&A and teaching cite exact passages. ``page_span`` is ``None``
    for EPUB (A-9); ``snippet`` is the chunk ``text`` (no ``ts_headline`` this cycle).
    """

    chunk_id: UUID
    source_id: UUID
    section_path: tuple[str, ...]
    anchor: str
    page_span: dict | None
    snippet: str
    score: float


@dataclass(frozen=True)
class GeneratedAnswer:
    """The raw output of the answer-generation port (QA-05, ADR-0007 §4).

    A Learny-owned result so no provider response shape crosses the
    :class:`~app.domain.ports.AnswerGenerationPort` boundary. ``cited_chunk_ids``
    are the chunk ids the adapter drew on; the application service grounds them
    against the retrieved evidence. ``found`` is ``False`` when the evidence
    cannot support an answer (``text`` empty, ``cited_chunk_ids`` empty).
    """

    text: str
    cited_chunk_ids: tuple[UUID, ...]
    model: str
    found: bool


@dataclass(frozen=True)
class QuestionAnswer:
    """The application service's cited-answer result (QA-01..04, 13..16).

    ``status`` is one of ``"answered"`` or ``"not_found_in_source"``. Citations
    are grounded :class:`Evidence` items (no separate citation entity). The
    not-found contract is exact: ``status == "not_found_in_source"`` implies
    ``text == ""`` and ``citations == ()``. ``evidence_count`` and ``model`` are
    diagnostics carried on both outcomes (QA-04).
    """

    status: str
    text: str
    citations: tuple[Evidence, ...]
    evidence_count: int
    model: str


# --- Teaching sessions aggregate (Cycle 7, design §Components) -------------------
# A session anchors a bounded conversation to one corpus section of a source; its
# turns pair a user message with a generated response and carry citation snapshots
# so history survives corpus re-ingestion (AD-033).


@dataclass(frozen=True)
class TeachingSession:
    """A teaching conversation anchored to one corpus section (TEACH-01).

    The target is captured as a snapshot — the stable citation ``target_anchor``
    plus its ``target_section_path`` and ``target_title`` — so the session renders
    without re-reading the corpus (the anchor is re-resolved per turn, TEACH-16).
    """

    id: UUID
    source_id: UUID
    target_anchor: str
    target_section_path: tuple[str, ...]
    target_title: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class TeachingTurn:
    """One user message paired with its generated response (TEACH-07).

    ``answer_status`` is ``"answered"`` or ``"not_found_in_source"``; a not-found
    turn is still persisted with empty ``answer_text`` and no ``citations``
    (TEACH-14). ``citations`` are grounded :class:`Evidence` snapshots whose rank
    is their tuple position (``page_span`` is ``None`` for EPUB, A-9).
    """

    id: UUID
    session_id: UUID
    turn_index: int
    message: str
    answer_status: str
    answer_text: str
    model: str
    evidence_count: int
    citations: tuple[Evidence, ...]
    created_at: datetime


@dataclass(frozen=True)
class HistoryTurn:
    """A prior turn reduced to the pair a generation port needs (design §Components).

    Bounded conversation context (TEACH-12): the user ``message`` and the
    ``response_text`` (empty for a not-found turn). Statuses and citations are not
    needed for prompting, so they are omitted from this port DTO.
    """

    message: str
    response_text: str


@dataclass(frozen=True)
class TeachingSessionSummary:
    """A session plus its turn count for the per-source list read model (TEACH-21)."""

    session: TeachingSession
    turn_count: int
