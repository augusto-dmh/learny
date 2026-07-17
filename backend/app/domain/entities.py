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

from dataclasses import dataclass, field, replace
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
    across this boundary. ``page_span`` is the block's source page range
    ``(start, end)`` for paged formats (PDF) and ``None`` for EPUB.
    """

    position: int
    block_type: str
    html_fragment: str
    page_span: tuple[int, int] | None = None


@dataclass(frozen=True)
class ParsedSection:
    """A TOC-derived section of a parsed book (A-1/A-2).

    A section corresponds to a table-of-contents entry (or an A-2 fallback for a
    spine document the TOC omits). ``section_path`` is the root-to-node tuple of
    TOC titles used for citations; ``anchor`` is ``href[#fragment]`` (A-4).
    ``blocks`` are this section's content blocks in reading order (ADR-0002).
    ``anchor_aliases`` are anchors that normalization merged into this section
    (AD-085); they keep resolving to it so no saved citation dangles.
    """

    position: int
    title: str
    depth: int
    section_path: tuple[str, ...]
    anchor: str
    blocks: tuple[ParsedBlock, ...]
    anchor_aliases: tuple[str, ...] = ()


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
    (ADR-0003). ``page_span`` is the ``(start, end)`` page range rolled up from the
    chunk's source blocks for paged formats (PDF) and ``None`` for EPUB (A-9).
    ``index`` is the chunk's order within its section.
    """

    index: int
    text: str
    section_path: tuple[str, ...]
    anchor: str
    page_span: tuple[int, int] | None


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
class SectionContent:
    """One section's readable content, addressed by its anchor (A-4).

    The single-section read model behind the reader: the section's derived
    Markdown plus the citation metadata (``section_path``, ``title``) needed to
    render it in context. Keyed by the same ``anchor`` the structure read model
    and citations expose, so a citation round-trips to exactly this section.
    """

    anchor: str
    title: str
    section_path: tuple[str, ...]
    markdown: str


@dataclass(frozen=True)
class ReconcileSection:
    """One section's citation anchors plus its full chunk text, for reconciliation (QUIZ-16).

    The post-re-ingestion read model: ``text`` is the section's chunk text concatenated in
    reading order, so a quiz item's snapshotted ``source_excerpt`` (verified against a
    chunk at generation) can be re-checked for verbatim presence in the new corpus. Carries
    the ``anchor`` and ``section_path`` a relocated item adopts. ``anchor_aliases`` are the
    anchors normalization merged into this section, so an item snapshotted against a
    merged-away anchor reconciles to this surviving section (AD-085).
    """

    anchor: str
    section_path: tuple[str, ...]
    text: str
    anchor_aliases: tuple[str, ...] = ()


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


# The exact reply a generation adapter instructs the model to return, alone, when
# the evidence cannot support an answer — the Learny-owned not-found signal an
# adapter maps to ``GeneratedAnswer(found=False)`` (F5). Defined here (not in an
# adapter) because it is a cross-layer contract: the streaming answer path buffers
# text deltas while they remain a prefix of this string so the sentinel is never
# streamed to a client, independent of which provider produced it.
SENTINEL = "NOT_FOUND_IN_SOURCE"


@dataclass(frozen=True)
class AnswerTextDelta:
    """One incremental chunk of generated answer text (streaming path, §5).

    Carries the raw model text as it arrives; the streaming service assembles and,
    where needed, holds these back (sentinel guard) before presenting them.
    """

    text: str


@dataclass(frozen=True)
class AnswerCompleted:
    """The terminal, authoritative result of a generation stream (streaming path, §5).

    Emitted exactly once, always last. Its :class:`GeneratedAnswer` is the parsed,
    authoritative outcome (text, citations, ``found``) — the accumulated deltas are
    presentation only; grounding and the not-found decision use this ``answer``.
    """

    answer: GeneratedAnswer


# A generation stream yields zero or more :class:`AnswerTextDelta` then exactly one
# :class:`AnswerCompleted` (always last, authoritative). Shared by both generation
# ports' ``generate_stream`` so one capability has two consumption modes.
AnswerStreamEvent = AnswerTextDelta | AnswerCompleted


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


# --- Active recall aggregate (Cycle E, RFC-002; design §Domain) ------------------
# Citation-grounded quiz items per book section, scheduled by FSRS-6. Items snapshot
# their citation (no chunk FK) so they survive corpus re-ingestion (AD-078); scheduling
# and the append-only review log are never destroyed by generation or reconciliation.


class QuizItemType:
    """Quiz item kinds (QUIZ-10). Only these two — no MCQ anywhere (locked v2 decision).

    String constants (not an enum) mirroring the codebase's free-text status columns.
    ``free_recall`` is a question/answer pair; ``cloze`` masks a span of a passage
    sentence with ``____`` (A-5).
    """

    FREE_RECALL = "free_recall"
    CLOZE = "cloze"


class QuizItemStatus:
    """Quiz item lifecycle vocabulary (QUIZ-16).

    ``active`` items are reviewable; ``stale`` (anchor kept, quote gone) and
    ``orphaned`` (neither) are excluded from the due queue but still listed with their
    status (QUIZ-17). Reconciliation moves items between these on re-ingestion.
    """

    ACTIVE = "active"
    STALE = "stale"
    ORPHANED = "orphaned"


class QuizJobStatus:
    """Deck-generation job status vocabulary (mirrors :class:`IngestionStatus`).

    ``queued``/``running`` are the two *active* states; ``succeeded``/``failed`` are
    terminal.
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


# At most one deck job in these states may exist per source at a time (QUIZ-04 single
# in-flight guard, enforced by a repository query — there is no partial unique index).
ACTIVE_QUIZ_JOB_STATUSES = frozenset({QuizJobStatus.QUEUED, QuizJobStatus.RUNNING})


@dataclass(frozen=True)
class QuizSection:
    """One eligible book section handed to deck generation (design §Domain).

    A leaf section with enough text (A-3); carries its citation anchors and the
    section's retrieval chunks as ``(chunk_id, text)`` pairs so a candidate's
    ``source_chunk_id`` can be constrained to this section's chunks and its quote
    verified against the chunk text.
    """

    section_path: tuple[str, ...]
    anchor: str
    title: str
    chunks: tuple[tuple[UUID, str], ...]


@dataclass(frozen=True)
class QuizCandidate:
    """A raw generated item before quality control (design §Domain).

    Produced by a :class:`~app.domain.ports.QuizGenerationPort`; not yet grounded.
    ``anchor_quote`` is the verbatim passage the item claims to come from and
    ``source_chunk_id`` the chunk it cites — both re-verified by the QC pipeline
    (QUIZ-06/07) before an item is persisted.
    """

    item_type: str
    question: str
    answer: str
    source_chunk_id: UUID
    anchor_quote: str


@dataclass(frozen=True)
class QuizDeckResult:
    """A generation pass's outcome: accepted candidates plus per-section errors.

    ``candidates`` are all sections' candidates flattened (the QC pipeline grounds and
    dedups them); ``errors`` are per-section failure messages (schema/batch errors)
    counted into the job's ``failed_sections`` (partial-success edge case).
    """

    candidates: tuple[QuizCandidate, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class QuizDeckHandle:
    """A provider-agnostic handle to an in-flight (or inline) generation pass.

    Round-trips through Celery JSON between ``begin_deck`` and the polling task
    (:meth:`to_payload` / :meth:`from_payload`). ``batch_id`` identifies an Anthropic
    Message Batch (``None`` for the local adapter); ``payload`` is a provider-owned
    JSON-safe blob (the local adapter carries its inline result there; the Anthropic
    adapter carries per-section metadata for mapping batch results by ``custom_id``).
    """

    provider: str
    batch_id: str | None = None
    payload: dict = field(default_factory=dict)

    def to_payload(self) -> dict:
        """Serialize to a JSON-safe dict for the Celery poll task hand-off."""
        return {
            "provider": self.provider,
            "batch_id": self.batch_id,
            "payload": self.payload,
        }

    @classmethod
    def from_payload(cls, data: dict) -> QuizDeckHandle:
        """Reconstruct a handle from :meth:`to_payload` output."""
        return cls(
            provider=data["provider"],
            batch_id=data.get("batch_id"),
            payload=data.get("payload", {}),
        )


@dataclass(frozen=True)
class QuizItem:
    """A citation-grounded quiz card owned (via its source) by a user (QUIZ-06).

    Snapshots its citation (``section_path``, ``anchor``, ``source_excerpt``) and the
    ``chunk_hash`` of the chunk it was generated from, so it survives a corpus replace
    with no FK to the corpus (AD-078). ``content_key`` is the ``(source_id, content_key)``
    upsert identity (QUIZ-02). ``embedding`` is a persistence-only dedup detail and is
    not carried on this entity.
    """

    id: UUID
    source_id: UUID
    item_type: str
    question: str
    answer: str
    section_path: tuple[str, ...]
    anchor: str
    source_excerpt: str
    chunk_hash: str
    content_key: str
    status: str
    generation_meta: dict
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SchedulingSnapshot:
    """An FSRS-6 scheduling state persisted as real columns (QUIZ-11).

    Maps 1:1 to ``quiz_item_scheduling``: FSRS card ``state`` (enum int) and learning
    ``step``, ``stability``/``difficulty`` memory parameters, the ``due`` review time,
    and ``last_review`` (``None`` until first reviewed). All datetimes are UTC.
    """

    state: int
    step: int | None
    stability: float | None
    difficulty: float | None
    due: datetime
    last_review: datetime | None


@dataclass(frozen=True)
class ReviewLogEntry:
    """An append-only grade-history entry (QUIZ-12).

    ``rating`` is FSRS's Again(1)/Hard(2)/Good(3)/Easy(4); ``reviewed_at`` is when the
    review happened; ``review_duration_ms`` is the optional client-supplied timing. The
    scheduling port produces the rating/time pair; the review service attaches the
    duration before it is appended.
    """

    rating: int
    reviewed_at: datetime
    review_duration_ms: int | None = None


@dataclass(frozen=True)
class DueReviewItem:
    """A due quiz card plus the join fields the review queue needs (QUIZ-13/15).

    Bundles the reviewable :class:`QuizItem` with its owning source's ``source_title``
    (the queue spans all the caller's sources) and its scheduled ``due`` time.
    """

    item: QuizItem
    source_title: str
    due: datetime


@dataclass(frozen=True)
class QuizGenerationJob:
    """A durable deck-generation job driving one source's deck (mirrors :class:`IngestionJob`).

    Immutable record whose transition helpers return new instances; ownership is
    reachable only via the parent source (no ``user_id``, AD-014). ``generated_count``/
    ``discarded_count``/``failed_sections`` are the terminal-success counts (QUIZ-09);
    ``last_error`` is the terminal-failure reason.
    """

    id: UUID
    source_id: UUID
    status: str
    attempts: int
    generated_count: int
    discarded_count: int
    failed_sections: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    def started(self, now: datetime) -> QuizGenerationJob:
        """Begin an attempt: → ``running`` and increment ``attempts``."""
        return replace(
            self,
            status=QuizJobStatus.RUNNING,
            attempts=self.attempts + 1,
            updated_at=now,
        )

    def succeeded(
        self,
        now: datetime,
        *,
        generated_count: int,
        discarded_count: int,
        failed_sections: int,
    ) -> QuizGenerationJob:
        """Terminal success: → ``succeeded`` with the generation counts (QUIZ-09)."""
        return replace(
            self,
            status=QuizJobStatus.SUCCEEDED,
            generated_count=generated_count,
            discarded_count=discarded_count,
            failed_sections=failed_sections,
            updated_at=now,
        )

    def failed(self, now: datetime, error: str) -> QuizGenerationJob:
        """Terminal failure: → ``failed`` with a durable ``last_error`` (QUIZ-09)."""
        return replace(
            self,
            status=QuizJobStatus.FAILED,
            last_error=error,
            updated_at=now,
        )
