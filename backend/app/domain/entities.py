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
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
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
    (document → sections → blocks → chunks) in one call. ``block_hashes`` is the
    normalized-text sha256 of each block's derived Markdown, positionally aligned
    with ``section.blocks`` (NF-02); empty when the build did not compute them.
    """

    section: ParsedSection
    markdown: str
    chunks: tuple[SectionChunk, ...]
    block_hashes: tuple[str, ...] = ()

    @property
    def word_count(self) -> int:
        """Whitespace-token count of the derived section markdown (RD-14).

        Derived from ``markdown`` (its single source of truth) so build-time and
        stored counts never drift; a section with no prose counts 0, so downstream
        percent / minutes-left math never divides by zero (RD-16).
        """
        return len(self.markdown.split())


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
    # Widened for the notes-in-retrieval arms (ADR-0026 d4, NL-02). ``origin``
    # discriminates a book chunk from the user's own note; ``chunk_id`` remains the
    # opaque evidence id grounding matches on (the note's id for a note). ``note_id``/
    # ``note_title`` carry the note's identity for its distinct citation. All default
    # so every existing book construction stays valid (additive, frozen).
    origin: Literal["book", "note"] = "book"
    note_id: UUID | None = None
    note_title: str | None = None


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


class QuizItemOrigin:
    """How a quiz card came to exist (ADR-0026 decision 5).

    ``deck`` cards are minted by whole-source generation and keep the content-hash
    upsert identity (QUIZ-02). ``highlight`` cards are accepted by the student at a
    passage; their identity is the id minted at acceptance, so their text may be
    reworded without disturbing scheduling or the review log.
    """

    DECK = "deck"
    HIGHLIGHT = "highlight"
    # ``note`` cards are promoted from a note (RFC-003 Cycle F). Like ``highlight``
    # cards their identity is the minted id, so the note's text may be regenerated
    # without disturbing scheduling; they are the only source-less origin (AD-148/149).
    NOTE = "note"


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
    (QUIZ-06/07) before an item is persisted. ``source_chunk_id`` is ``None`` for a
    note candidate: a note is not chunked, so its ``anchor_quote`` is verified against
    the whole note body instead of a chunk (NL-08).
    """

    item_type: str
    question: str
    answer: str
    anchor_quote: str
    source_chunk_id: UUID | None = None


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
    with no FK to the corpus (AD-078). ``embedding`` is a persistence-only dedup detail
    and is not carried on this entity.

    ``origin`` selects the identity mode (:class:`QuizItemOrigin`). For ``deck`` items
    ``content_key`` is the ``(source_id, content_key)`` upsert identity (QUIZ-02); for
    ``highlight`` items the minted ``id`` is the identity and ``content_key`` is a
    rewritable fingerprint. ``note_anchor_id`` is the typed provenance back to the
    highlight a card was accepted from — ``None`` for deck items and for a card whose
    origin note has since been deleted, which the stored snapshot survives.
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
    # Default to the deck identity mode: every construction site that predates card
    # capture is whole-source generation, matching the column's server default.
    origin: str = QuizItemOrigin.DECK
    note_anchor_id: UUID | None = None
    # Denormalized owner (AD-149). Set explicitly on a source-less ``note`` card; for
    # deck/highlight cards it is derived from the source at persist time, so existing
    # construction sites leave it ``None`` and stay byte-compatible.
    user_id: UUID | None = None
    # Provenance back to the promoted note (``origin='note'``); ``None`` once the note
    # is deleted, which the stored snapshot survives (AD-145).
    note_id: UUID | None = None
    # When the origin note last changed under this card (AD-144); drives the review
    # badge. ``None`` until a regenerate-and-match flags the card.
    note_changed_at: datetime | None = None


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
class CardProvenance:
    """The origin note of a highlight- or note-derived card, for display at review.

    Read by join so a renamed note shows its current title. Absent (``None`` on the
    review item) for deck-origin cards and for cards whose origin note was deleted —
    a highlight card via its anchor (CAP-16), a note card via its ``note_id`` (NL-13).
    """

    note_id: UUID
    note_title: str


@dataclass(frozen=True)
class DueReviewItem:
    """A due quiz card plus the join fields the review queue needs (QUIZ-13/15).

    Bundles the reviewable :class:`QuizItem` with its owning source's ``source_title``
    (the queue spans all the caller's sources), its scheduled ``due`` time, the origin-note
    ``provenance`` when the card came from a highlight or a note and that note still exists,
    and ``note_changed`` — whether the origin note changed since the card was last reviewed
    or created (the "your note changed" review badge, NL-12).
    """

    item: QuizItem
    source_title: str
    due: datetime
    provenance: CardProvenance | None = None
    note_changed: bool = False


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


# --- Notes & second-brain aggregate (RFC-003 Cycle E; ADR-0026 §1-2) -------------
# Whole-Markdown notes owned by a user. Book citations live in ``NoteAnchor`` rows
# carrying the layered anchor payload (section anchor + snapshot, block hash/ordinal,
# in-block offsets, quote-with-context) that lets a highlight survive re-ingestion.
# Notes and anchors never cascade from corpus/source deletion (the inverse-cascade
# invariant); reconciliation moves an anchor's status, never a note's prose (NF-07).


class NoteAnchorStatus:
    """Note-anchor lifecycle vocabulary (NF-07), reusing the quiz vocabulary.

    ``active`` anchors resolve to a live passage; ``stale`` (the section still resolves
    but the quoted text is gone) and ``orphaned`` (nothing resolves) are kept forever and
    rendered from their quote snapshot. Reconciliation moves anchors between these on
    re-ingestion; a relocation stays ``active`` and rewrites the anchor payload (D-6).
    """

    ACTIVE = "active"
    STALE = "stale"
    ORPHANED = "orphaned"


@dataclass(frozen=True)
class Note:
    """A whole-Markdown note owned by a user (ADR-0026 §2).

    ``body_markdown`` is the single source of truth; the derived ``tags`` and
    wikilink ``note_links`` indexes are rebuilt from it on every save. A note carries
    0..N :class:`NoteAnchor` book citations (D-5); an empty body is allowed.
    """

    id: UUID
    user_id: UUID
    title: str
    body_markdown: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class NoteAnchor:
    """A book citation on a note — the layered, corpus-FK-free anchor (ADR-0026 §1).

    ``source_id`` is a bare value reference (no FK) and ``source_title`` a snapshot, so
    an orphaned anchor still renders after its source is gone. The block binding
    (``block_hash``/``block_ordinal``/``start_offset``/``end_offset``) is ``None`` when
    the owning block was unhashed or unresolved; the quote-with-context snapshot
    (``quote_exact`` + 32-char ``quote_prefix``/``quote_suffix``) then carries the anchor
    and drives the reconcile quote tiers. ``status`` is a :class:`NoteAnchorStatus`.
    """

    id: UUID
    note_id: UUID
    source_id: UUID
    source_title: str
    anchor: str
    section_path: tuple[str, ...]
    block_hash: str | None
    block_ordinal: int | None
    start_offset: int | None
    end_offset: int | None
    quote_exact: str
    quote_prefix: str
    quote_suffix: str
    status: str
    created_at: datetime
    updated_at: datetime


# --- Reader progress (RFC-004 Cycle B; design §Components/Data Models) -----------
# The chapter-flow reader assembles a whole chapter per request from a lightweight
# section index (no per-request re-parse). ``ChapterIndexRow`` is the flat, position-
# ordered read model chapter partitioning and percent math run over; ``ChapterSection``
# and ``ChapterContent`` are the assembled read model the web layer projects; and
# ``ReadingPosition`` is where the reader stopped (anchor + server-computed percent).


@dataclass(frozen=True)
class ChapterIndexRow:
    """One row of the flat, position-ordered chapter index (RD-01, design §Components).

    The lightweight read model chapter partitioning (`partition`), anchor resolution
    (`locate`), and whole-book percent (`percent_at`) run over — no section markdown,
    so building the index and computing progress never loads chapter bodies.
    ``anchor_aliases`` mirrors ``get_section``'s alias resolution; ``word_count`` is
    the persisted per-section token count.
    """

    position: int
    depth: int
    title: str
    section_path: tuple[str, ...]
    anchor: str
    anchor_aliases: tuple[str, ...]
    word_count: int


@dataclass(frozen=True)
class ChapterSection:
    """One section of an assembled chapter, with its readable markdown (RD-01/03).

    The reader renders these in order inside one continuous article; ``anchor`` is the
    section's DOM id and citation target, ``word_count`` feeds the live minutes-left math.
    """

    anchor: str
    title: str
    section_path: tuple[str, ...]
    markdown: str
    word_count: int


@dataclass(frozen=True)
class ChapterContent:
    """A whole chapter assembled for the reader (RD-01, design §Data Models).

    ``chapter_index`` is 0-based within ``chapter_count`` chapters; ``prev_anchor``/
    ``next_anchor`` are the adjacent chapters' canonical anchors (``None`` at a book
    edge). ``words_before_chapter``/``chapter_word_count``/``total_word_count`` let the
    client compute whole-book percent and chapter minutes-left as the reader scrolls.
    """

    chapter_title: str
    chapter_anchor: str
    chapter_index: int
    chapter_count: int
    prev_anchor: str | None
    next_anchor: str | None
    words_before_chapter: int
    chapter_word_count: int
    total_word_count: int
    sections: tuple[ChapterSection, ...]


@dataclass(frozen=True)
class ReadingPosition:
    """Where the reader stopped in a source (RD-08/10): resolved anchor + percent.

    ``anchor`` is the canonical section anchor; ``percent`` is the server-computed
    whole-book percent at it (0.00–100.00). Returned to the reader for its progress
    display and to resume the right chapter on open.
    """

    anchor: str
    percent: Decimal
    updated_at: datetime


@dataclass(frozen=True)
class RecentReadingPosition:
    """The caller's single most-recently-updated reading position across all sources.

    The read model behind the Home continue-reading hero (HOME-01): the owning
    ``source_id`` and its ``source_title`` (joined in SQL), the stored ``anchor`` and
    server-computed ``percent``, and the ``updated_at`` that made it the most recent.
    Chapter-title resolution against the source's chapter index is the application
    service's job, not the repository's, so this carries the anchor rather than a title.
    """

    source_id: UUID
    source_title: str
    anchor: str
    percent: Decimal
    updated_at: datetime


@dataclass(frozen=True)
class StudyDay:
    """One user-local day of study activity, with per-kind counters (HOME-07/08).

    The durable rollup row keyed ``(user_id, day)``: ``reviews_count`` and
    ``reading_updates`` are incremented atomically as reviews are submitted and reading
    positions saved (AD-151). Adherence ("Studied X of the last 14 days") and the heatmap
    are derived from these rows at read time — no streak/adherence value is ever stored.
    """

    user_id: UUID
    day: date
    reviews_count: int
    reading_updates: int


@dataclass(frozen=True)
class StudySummary:
    """The adherence read model for the Home stats block (HOME-11).

    ``days`` are the caller's study-day rows within the requested window (day-ordered);
    ``studied_last_14`` is the count of distinct days with any activity in the 14-day
    window ending on the caller's local today. Both are computed at read time from the
    ``study_days`` rollup — nothing derived is persisted (I-4).
    """

    days: tuple[StudyDay, ...]
    studied_last_14: int


@dataclass(frozen=True)
class ContinuePoint:
    """The resolved continue-reading hero (HOME-01): where to resume, in one click.

    The caller's most-recent reading position with its ``chapter_title`` resolved from the
    stored anchor against the source's chapter index, plus the ``source_title``,
    server-computed ``percent``, and ``updated_at``.
    """

    source_id: UUID
    source_title: str
    chapter_title: str
    percent: Decimal
    updated_at: datetime


@dataclass(frozen=True)
class SourceHighlight:
    """One of the caller's highlights on a source, for inline reader painting (RD-28).

    The read model behind ``GET /sources/{id}/highlights``: the owning ``note_id`` and
    the anchor's quote-with-context (``quote_exact`` + ``quote_prefix``/``quote_suffix``)
    plus its ``status`` so the reader paints ``active`` quotes and ignores stale/orphaned
    ones (RD-29). Carries no note prose — only what the painter needs, plus the origin
    note's ``note_title`` and a ``has_body`` flag so the margin rail can label each entry
    and tell a bare highlight from an annotated one without a second request.
    """

    note_id: UUID
    anchor: str
    quote_exact: str
    quote_prefix: str
    quote_suffix: str
    status: str
    # Rail labelling. Defaulted so the painter's existing construction sites are
    # unaffected; the owner-scoped query populates both from the joined note.
    note_title: str = ""
    has_body: bool = False


@dataclass(frozen=True)
class Tag:
    """A first-class, user-owned label (ADR-0026 §2), unique per user by lowercased name."""

    id: UUID
    user_id: UUID
    name: str


@dataclass(frozen=True)
class DerivedNoteLink:
    """A ``[[wikilink]]`` derived from a note body on save (NF-05).

    ``target_text`` is the raw link text (always kept so a broken/unresolved link still
    renders); ``target_note_id`` is the resolved target when the text matches another of
    the user's notes by title (case-insensitive), else ``None`` (D-4).
    """

    target_text: str
    target_note_id: UUID | None


@dataclass(frozen=True)
class Backlink:
    """One inbound wikilink for the backlinks panel (NF-10/13): the linking note."""

    note_id: UUID
    title: str


@dataclass(frozen=True)
class NoteSummary:
    """The notes-list read model (NF-13): a note with its tags and anchor statuses.

    ``anchor_statuses`` carries one status per anchor (any order) so the list can render
    active/stale/orphaned badges without loading the anchor payloads.
    """

    note: Note
    tags: tuple[str, ...]
    anchor_statuses: tuple[str, ...]


@dataclass(frozen=True)
class NoteView:
    """The note-detail read model (NF-05/10/13): a note with its tags and anchors."""

    note: Note
    tags: tuple[str, ...]
    anchors: tuple[NoteAnchor, ...]


@dataclass(frozen=True)
class AnchorBlockSnapshot:
    """One corpus block as the highlight-anchoring read path sees it (NF-03/06/07).

    Carries the block's stored ``content_hash`` (NF-02; ``None`` for a pre-0010 block)
    and its preserved ``html_fragment``. The anchoring use cases derive the block's
    Markdown from the fragment — the same conversion the corpus build used — so the
    resolver matches a selection against the exact text the ``content_hash`` and
    in-block offsets were computed from.
    """

    ordinal: int
    content_hash: str | None
    html_fragment: str


@dataclass(frozen=True)
class AnchorSection:
    """A section's blocks plus its citation anchors, for highlight anchoring (NF-06/07).

    ``anchor``/``section_path`` are the section's canonical citation; ``anchor_aliases``
    are the anchors normalization merged into it (AD-085), so an anchor snapshotted
    against a merged-away section reconciles here. ``blocks`` are in reading order.
    """

    anchor: str
    section_path: tuple[str, ...]
    anchor_aliases: tuple[str, ...]
    blocks: tuple[AnchorBlockSnapshot, ...]
