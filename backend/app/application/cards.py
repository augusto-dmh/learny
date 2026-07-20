"""Card-capture use-case services (RFC-004 Cycle D, design §Components).

The passage-scoped half of active recall, kept out of ``quiz.py`` (which already owns
deck planning, running, listing, export, and reconcile). Framework-free like every other
application module: nothing here imports FastAPI, SQLAlchemy, or Celery.

:class:`SuggestCards` generates candidates for a single highlighted quote and gates them
through the same groundedness QC the deck pipeline applies (QUIZ-06/07), because those
checks catch model fabrication rather than police the student. :class:`AcceptCard` mints
the one card the student chose — ``origin="highlight"`` under a creation-minted id, with
typed provenance back to the note anchor and a citation snapshot taken from it — and
deliberately does *not* apply the embedding dedup guard (AD-138), while still storing the
embedding so later deck runs dedup against it. :class:`UpdateCard` rewrites a highlight
card's text under that stable id, never touching its scheduling or review log.

:class:`SuggestNoteCards` and :class:`AcceptNoteCard` are the note→quiz siblings (NL-08/09,
RFC-003 Cycle F): the promoted note *is* the source, so groundedness QC verifies against
the note body rather than a section, and an accepted card is source-less — ``origin='note'``
owned by the reader directly (AD-149), its identity the minted id (AD-148) so the note's
text may be regenerated later without disturbing scheduling. Re-promoting the same text
from one note is idempotent (NL-15): a service-level ``content_key`` dedup returns the
existing card, since note cards carry no partial unique index. :class:`RefreshNoteCards`
is the worker-invoked edit-stability step (NL-10/11): it regenerates from the note's
current body, greedily pairs the live cards to the QC-passing suggestions by embedding
similarity, rewrites matched cards' text in place and flags them, flags the unmatched, and
never touches scheduling or the review log — a note edit costs no card its memory history.

Ownership is reachable through the parent source for deck/highlight cards (AD-014) and
directly through the note for note cards; every ownership failure collapses to
``QuizItemNotFound`` → 404 so no anchor's, note's, or card's existence is disclosed.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Sequence
from uuid import UUID

from app.application.errors import (
    CardAlreadyExists,
    CardNotEditable,
    InvalidCardText,
    NotAuthorized,
    QuizItemNotFound,
    StaleCaptureTarget,
)
from app.application.identity import AuthorizeOwnership
from app.application.ingestion import authorized_source
from app.application.quiz_qc import (
    cloze_is_valid,
    content_key,
    normalize_text,
    note_card_passes_qc,
    quote_in_text,
)
from app.domain.entities import (
    Note,
    NoteAnchor,
    QuizCandidate,
    QuizItem,
    QuizItemOrigin,
    QuizItemStatus,
    QuizItemType,
    QuizSection,
    User,
)
from app.domain.ports import (
    Clock,
    EmbeddingPort,
    NoteRepository,
    QuizGenerationPort,
    QuizItemRepository,
    SchedulingPort,
    SourceRepository,
)

# The two item kinds accepted anywhere in the quiz pipeline (QUIZ-10 — no MCQ).
_VALID_ITEM_TYPES = frozenset({QuizItemType.FREE_RECALL, QuizItemType.CLOZE})


def _owned_anchor(
    notes: NoteRepository, user: User, source_id: UUID, note_anchor_id: UUID
) -> NoteAnchor:
    """Return the caller's note anchor on ``source_id``, else ``QuizItemNotFound``.

    A missing anchor, an anchor citing a different source, and an anchor whose note
    belongs to someone else all collapse to the same 404 (CAP-09): the card surfaces
    must never reveal that another user's highlight exists.
    """
    anchor = notes.get_anchor(note_anchor_id)
    if anchor is None or anchor.source_id != source_id:
        raise QuizItemNotFound("Highlight not found.")
    note = notes.get_by_id(anchor.note_id)
    if note is None or note.user_id != user.id:
        raise QuizItemNotFound("Highlight not found.")
    return anchor


def _section_text(section: QuizSection) -> str:
    """Return the section's full text — the corpus a candidate must be grounded in."""
    return "\n".join(text for _chunk_id, text in section.chunks)


def _passes_qc(candidate: QuizCandidate, section_text: str) -> bool:
    """Return whether a generated candidate survives groundedness QC (CAP-03/04).

    The deck pipeline's checks narrowed to one section: a known item type, non-empty
    text, an ``anchor_quote`` contained verbatim in the section (QUIZ-06), and for a
    cloze a mask that is valid against that quote (QUIZ-07). Applied to *generated*
    text only — text the student edited before accepting is author-owned and is not
    re-gated (AD-138).
    """
    if candidate.item_type not in _VALID_ITEM_TYPES:
        return False
    if not (candidate.question.strip() and candidate.answer.strip()):
        return False
    if not candidate.anchor_quote.strip():
        return False
    if not quote_in_text(candidate.anchor_quote, section_text):
        return False
    if candidate.item_type == QuizItemType.CLOZE:
        return cloze_is_valid(candidate.question, candidate.answer, candidate.anchor_quote)
    return True


def _validated_text(value: str, field: str, max_chars: int) -> str:
    """Return ``value`` stripped, or raise ``InvalidCardText`` (CAP-05/06 → 422).

    Empty (or whitespace-only) text has nothing to review, and text past the configured
    bound is rejected before any write rather than truncated silently.
    """
    text = value.strip()
    if not text:
        raise InvalidCardText(f"A card's {field} cannot be empty.")
    if len(text) > max_chars:
        raise InvalidCardText(f"A card's {field} is longer than {max_chars} characters.")
    return text


class SuggestCards:
    """Generate QC-passing card candidates for one highlighted passage (CAP-01..04, 09).

    Authorizes the source, resolves the anchor to the caller's own highlight on it,
    loads that anchor's section, and asks the generation port for at most
    ``max_suggestions`` candidates scoped to the highlighted quote. Every candidate is
    re-verified against the section text here rather than trusted from the adapter, so
    grounding holds for any provider.

    Nothing is persisted: suggestions are ephemeral by construction (AD-134), so "no
    silent bulk generation" is a structural property — only acceptance writes a row. A
    pass where no candidate survives QC returns an empty list, which is an outcome
    ("no cards for this passage"), not an error.
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        notes: NoteRepository,
        items: QuizItemRepository,
        generation: QuizGenerationPort,
        authorize: AuthorizeOwnership,
        max_suggestions: int,
    ) -> None:
        self._sources = sources
        self._notes = notes
        self._items = items
        self._generation = generation
        self._authorize = authorize
        self._max_suggestions = max_suggestions

    def __call__(
        self, *, user: User, source_id: UUID, note_anchor_id: UUID
    ) -> list[QuizCandidate]:
        authorized_source(
            user=user,
            source_id=source_id,
            sources=self._sources,
            authorize=self._authorize,
        )
        anchor = _owned_anchor(self._notes, user, source_id, note_anchor_id)

        section = self._items.section_for_anchor(source_id, anchor.anchor)
        if section is None:
            # The corpus was replaced under the highlight; nothing to generate from.
            raise StaleCaptureTarget("The selected passage no longer matches the source.")

        candidates = self._generation.suggest_cards(
            section, anchor.quote_exact, self._max_suggestions
        )
        section_text = _section_text(section)
        survivors = [c for c in candidates if _passes_qc(c, section_text)]
        return survivors[: self._max_suggestions]


class AcceptCard:
    """Mint the one card the student accepted from a highlight (CAP-05..07, 10..12).

    Authorizes the source and the anchor exactly as :class:`SuggestCards` does, validates
    the submitted text (empty or over-long → ``InvalidCardText`` → 422), and mints a
    ``highlight``-origin item whose identity is its **created** id, not its content hash
    (ADR-0026 decision 5) — so later edits never disturb its scheduling. Provenance is the
    typed ``note_anchor_id`` link, and the citation (``anchor``, ``section_path``,
    ``source_excerpt``) is snapshotted from the anchor so the card stays renderable even
    after the origin note is deleted.

    Accepting the same text from the same highlight twice is idempotent: the existing card
    is returned with ``created=False`` and no second row appears (double-submit edge
    case). The submitted text is stored as the student sent it — generated candidates were
    already gated by :class:`SuggestCards`, and text the student edited is author-owned
    (AD-138). Embedding dedup is deliberately **not** applied here: silently discarding a
    card someone just chose would be an inexplicable no-op. The embedding is still computed
    and stored so future deck generation dedups against this card.
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        notes: NoteRepository,
        items: QuizItemRepository,
        generation: QuizGenerationPort,
        embeddings: EmbeddingPort,
        scheduling: SchedulingPort,
        authorize: AuthorizeOwnership,
        clock: Clock,
        ids: Callable[[], UUID],
        max_card_chars: int,
    ) -> None:
        self._sources = sources
        self._notes = notes
        self._items = items
        self._generation = generation
        self._embeddings = embeddings
        self._scheduling = scheduling
        self._authorize = authorize
        self._clock = clock
        self._ids = ids
        self._max_card_chars = max_card_chars

    def __call__(
        self,
        *,
        user: User,
        source_id: UUID,
        note_anchor_id: UUID,
        item_type: str,
        question: str,
        answer: str,
    ) -> tuple[QuizItem, bool]:
        authorized_source(
            user=user,
            source_id=source_id,
            sources=self._sources,
            authorize=self._authorize,
        )
        anchor = _owned_anchor(self._notes, user, source_id, note_anchor_id)

        if item_type not in _VALID_ITEM_TYPES:
            raise InvalidCardText(f"Unsupported card type: {item_type}.")
        question = _validated_text(question, "question", self._max_card_chars)
        answer = _validated_text(answer, "answer", self._max_card_chars)

        key = content_key(item_type, question, answer)
        existing = self._items.get_by_anchor_and_key(note_anchor_id, key)
        if existing is not None:
            return existing, False

        now = self._clock.now()
        item = QuizItem(
            id=self._ids(),
            source_id=source_id,
            origin=QuizItemOrigin.HIGHLIGHT,
            note_anchor_id=note_anchor_id,
            item_type=item_type,
            question=question,
            answer=answer,
            section_path=anchor.section_path,
            anchor=anchor.anchor,
            source_excerpt=anchor.quote_exact,
            # The highlighted quote *is* the text this card was made from, so the
            # NOT NULL chunk snapshot keeps its meaning for a card with no chunk.
            chunk_hash=hashlib.sha256(
                normalize_text(anchor.quote_exact).encode("utf-8")
            ).hexdigest(),
            content_key=key,
            status=QuizItemStatus.ACTIVE,
            generation_meta={"model": self._generation.model},
            created_at=now,
            updated_at=now,
        )
        embedding = self._embeddings.embed_documents([f"{question}\n{answer}"])[0]

        if not self._items.upsert(item, embedding=list(embedding)):
            # Lost a double-submit race at the partial unique index: the winner's row
            # is the card, so return it rather than reporting a conflict.
            stored = self._items.get_by_anchor_and_key(note_anchor_id, key)
            if stored is not None:
                return stored, False
            # The winner has not committed yet, so its row is invisible here. Falling
            # through would schedule against an id that was never inserted — an FK
            # violation reported as a 201 for a card that does not exist. The other
            # request is creating that card; say so instead of inventing one.
            raise CardAlreadyExists("This card is already being saved.")
        self._items.create_scheduling(item.id, self._scheduling.initial())
        return item, True


class UpdateCard:
    """Rewrite a highlight card's text under its stable id (CAP-12).

    Loads the card (missing → ``QuizItemNotFound`` → 404) and authorizes through its
    parent source, where a non-owner collapses to the same 404 (no disclosure). Only a
    ``highlight``-origin card may be edited: a ``deck`` card's identity *is* its content
    hash, so rewriting its text would move which row the next regeneration upserts into
    — that is ``CardNotEditable`` → 409.

    Writes the question, the answer, and the recomputed ``content_key`` fingerprint and
    nothing else. The row's id, its scheduling snapshot, and its review log are all left
    exactly as they were, so editing a card never costs its memory history (ADR-0026
    decision 5).
    """

    def __init__(
        self,
        *,
        sources: SourceRepository,
        items: QuizItemRepository,
        authorize: AuthorizeOwnership,
        max_card_chars: int,
    ) -> None:
        self._sources = sources
        self._items = items
        self._authorize = authorize
        self._max_card_chars = max_card_chars

    def __call__(
        self, *, user: User, item_id: UUID, question: str, answer: str
    ) -> QuizItem:
        item = self._items.get_by_id(item_id)
        if item is None:
            raise QuizItemNotFound("Quiz item not found.")

        # Ownership is reachable only via the parent source (AD-014).
        source = self._sources.get_by_id(item.source_id)
        if source is None:
            raise QuizItemNotFound("Quiz item not found.")
        try:
            self._authorize(user=user, owner_id=source.user_id)
        except NotAuthorized as exc:
            raise QuizItemNotFound("Quiz item not found.") from exc

        if item.origin != QuizItemOrigin.HIGHLIGHT:
            raise CardNotEditable("Only cards created from a highlight can be edited.")

        question = _validated_text(question, "question", self._max_card_chars)
        answer = _validated_text(answer, "answer", self._max_card_chars)
        key = content_key(item.item_type, question, answer)

        # Cards from one highlight are unique per text, so rewording this one into a
        # sibling's exact wording collides at the index. Check first: reaching the
        # database would surface a unique violation as a 500 rather than a conflict.
        # Matching this card's own key is a no-op edit, not a collision.
        if item.note_anchor_id is not None:
            clash = self._items.get_by_anchor_and_key(item.note_anchor_id, key)
            if clash is not None and clash.id != item.id:
                raise CardAlreadyExists(
                    "Another card from this highlight already has that text."
                )

        self._items.update_text(
            item.id,
            question=question,
            answer=answer,
            content_key=key,
        )
        # ``update_text`` writes without returning; re-read so the caller sees the row
        # as persisted (including its untouched id and created_at).
        updated = self._items.get_by_id(item.id)
        if updated is None:  # pragma: no cover — the row was just written
            raise QuizItemNotFound("Quiz item not found.")
        return updated


def _owned_note(notes: NoteRepository, user: User, note_id: UUID) -> Note:
    """Return the caller's note, else ``QuizItemNotFound`` (NL-08 non-disclosure).

    A missing note and another user's note collapse to the same 404 so the promotion
    surfaces never reveal that a note exists.
    """
    note = notes.get_by_id(note_id)
    if note is None or note.user_id != user.id:
        raise QuizItemNotFound("Note not found.")
    return note


def _note_context(anchors: list[NoteAnchor]) -> str:
    """Render an anchored note's book context for generation, empty when unanchored.

    A generation hint only (NL-08): the deterministic offline adapter ignores it and QC
    always re-verifies against the note body alone, so the context can never smuggle in
    text the card is then "grounded" against. Each anchor contributes its source title,
    section path, and the quoted passage — the book the note is talking about.
    """
    lines = [
        f"{anchor.source_title} — {' > '.join(anchor.section_path)}: {anchor.quote_exact}"
        for anchor in anchors
    ]
    return "\n".join(lines)


class SuggestNoteCards:
    """Generate QC-passing card candidates from one owned note (NL-08).

    The note→quiz mirror of :class:`SuggestCards`: authorizes the note, carries the note's
    book-anchor context into generation when the note is anchored, and asks the generation
    port for at most ``max_suggestions`` candidates grounded in the note body. Every
    candidate is re-verified against the note body here (the note *is* the source), so
    grounding holds for any provider. Nothing is persisted (AD-134); a pass where no
    candidate survives QC returns an empty list — an outcome ("no cards for this note"),
    not an error.
    """

    def __init__(
        self,
        *,
        notes: NoteRepository,
        generation: QuizGenerationPort,
        max_suggestions: int,
    ) -> None:
        self._notes = notes
        self._generation = generation
        self._max_suggestions = max_suggestions

    def __call__(self, *, user: User, note_id: UUID) -> list[QuizCandidate]:
        note = _owned_note(self._notes, user, note_id)
        context = _note_context(self._notes.anchors_for_note(note_id))

        candidates = self._generation.suggest_note_cards(
            note.body_markdown, context, self._max_suggestions
        )
        survivors = [c for c in candidates if note_card_passes_qc(c, note.body_markdown)]
        return survivors[: self._max_suggestions]


class AcceptNoteCard:
    """Mint the one card the reader promoted from a note (NL-09, NL-15).

    Authorizes the note as :class:`SuggestNoteCards` does, validates the submitted text
    (empty or over-long → ``InvalidCardText`` → 422), and mints a source-less
    ``note``-origin item owned by the reader directly (AD-149) whose identity is its
    **created** id, not its content hash (AD-148) — so a later regenerate never disturbs
    its scheduling. Provenance is the typed ``note_id`` link plus a snapshot (the note
    title as the citation path, a bounded body excerpt) so the card stays renderable after
    the note is deleted; the live note-title provenance line is join-based (NL-14).

    Re-promoting the same text from the same note is idempotent (NL-15): the existing card
    is returned with ``created=False`` and no second row appears, since note cards carry no
    partial unique index and dedup is service-level on ``(note_id, content_key)``. The
    submitted text is stored as the reader sent it — generated candidates were already
    gated by :class:`SuggestNoteCards`, edited text is author-owned (AD-138). Embedding
    dedup is deliberately **not** applied, but the embedding is computed and stored so the
    regenerate-and-match step and later deck runs can match against it.
    """

    def __init__(
        self,
        *,
        notes: NoteRepository,
        items: QuizItemRepository,
        generation: QuizGenerationPort,
        embeddings: EmbeddingPort,
        scheduling: SchedulingPort,
        clock: Clock,
        ids: Callable[[], UUID],
        max_card_chars: int,
        excerpt_chars: int,
    ) -> None:
        self._notes = notes
        self._items = items
        self._generation = generation
        self._embeddings = embeddings
        self._scheduling = scheduling
        self._clock = clock
        self._ids = ids
        self._max_card_chars = max_card_chars
        self._excerpt_chars = excerpt_chars

    def __call__(
        self,
        *,
        user: User,
        note_id: UUID,
        item_type: str,
        question: str,
        answer: str,
    ) -> tuple[QuizItem, bool]:
        note = _owned_note(self._notes, user, note_id)

        if item_type not in _VALID_ITEM_TYPES:
            raise InvalidCardText(f"Unsupported card type: {item_type}.")
        question = _validated_text(question, "question", self._max_card_chars)
        answer = _validated_text(answer, "answer", self._max_card_chars)

        key = content_key(item_type, question, answer)
        existing = self._items.get_by_note_and_key(note_id, key)
        if existing is not None:
            return existing, False

        now = self._clock.now()
        # The note is the whole source, so the excerpt is a bounded body prefix — the
        # standalone citation snapshot that survives the note's deletion (NL-14).
        excerpt = note.body_markdown.strip()[: self._excerpt_chars]
        item = QuizItem(
            id=self._ids(),
            source_id=None,
            user_id=user.id,
            origin=QuizItemOrigin.NOTE,
            note_id=note_id,
            item_type=item_type,
            question=question,
            answer=answer,
            # The note title is the card's citation path (title snapshot, NL-09); the
            # synthetic anchor keeps the NOT NULL column meaningful for a source-less card.
            section_path=(note.title,),
            anchor=f"note:{note_id}",
            source_excerpt=excerpt,
            chunk_hash=hashlib.sha256(normalize_text(excerpt).encode("utf-8")).hexdigest(),
            content_key=key,
            status=QuizItemStatus.ACTIVE,
            generation_meta={"model": self._generation.model},
            created_at=now,
            updated_at=now,
        )
        embedding = self._embeddings.embed_documents([f"{question}\n{answer}"])[0]
        # Note cards have no partial unique index, so the upsert is always a plain insert
        # under the minted id; the pre-insert dedup above carries NL-15's idempotency.
        self._items.upsert(item, embedding=list(embedding))
        self._items.create_scheduling(item.id, self._scheduling.initial())
        return item, True


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity of two equal-length vectors (0.0 if either is a zero vector).

    A tiny pure helper (the deck dedup path has its own copy — no shared cosine utility
    exists): regenerate-and-match pairs a live card's stored embedding to a fresh
    suggestion's embedding (NL-10).
    """
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _greedy_note_matches(
    items: list[tuple[QuizItem, list[float] | None]],
    suggestions: list[tuple[QuizCandidate, list[float]]],
    threshold: float,
) -> list[tuple[int, int]]:
    """Greedily pair live cards to suggestions by cosine, one-to-one (NL-10).

    Returns ``(item_index, suggestion_index)`` pairs. Every eligible pair with similarity
    ``>= threshold`` is ranked by similarity descending, ties broken by ``(item_index,
    suggestion_index)`` so the pairing is deterministic; pairs are then taken in order,
    skipping any card or suggestion already used. A card with no stored embedding is
    unmatchable (it never enters a pair) and takes the note-changed flag path.
    """
    ranked = sorted(
        (
            (_cosine(emb, cand_emb), item_idx, sug_idx)
            for item_idx, (_item, emb) in enumerate(items)
            if emb is not None
            for sug_idx, (_cand, cand_emb) in enumerate(suggestions)
            if _cosine(emb, cand_emb) >= threshold
        ),
        key=lambda triple: (-triple[0], triple[1], triple[2]),
    )
    used_items: set[int] = set()
    used_suggestions: set[int] = set()
    matches: list[tuple[int, int]] = []
    for _sim, item_idx, sug_idx in ranked:
        if item_idx in used_items or sug_idx in used_suggestions:
            continue
        used_items.add(item_idx)
        used_suggestions.add(sug_idx)
        matches.append((item_idx, sug_idx))
    return matches


class RefreshNoteCards:
    """Regenerate-and-match a promoted note's derived cards after an edit (NL-10/11).

    Worker-invoked (behind ``enqueue_refresh_cards``, fired only when the note has live
    note cards). Reads the note's **current** body at run time — a stale enqueue that
    lands after a newer save converges on the newest body — regenerates suggestions,
    QC-filters them against that body, embeds the survivors, and greedily pairs the live
    cards to them by embedding cosine (``quiz_note_match_threshold``). A matched card whose
    text changed is rewritten in place under its own id and flagged ``note_changed_at``; a
    matched-but-identical card is left entirely untouched (no badge); an unmatched card is
    flagged only. Leftover suggestions are dropped — a refresh never creates or deletes a
    card. Scheduling and the review log are never touched (the cycle's core invariant): a
    note edit costs no card its memory history (ADR-0026 d5).
    """

    def __init__(
        self,
        *,
        notes: NoteRepository,
        items: QuizItemRepository,
        generation: QuizGenerationPort,
        embeddings: EmbeddingPort,
        clock: Clock,
        max_suggestions: int,
        excerpt_chars: int,
        match_threshold: float,
    ) -> None:
        self._notes = notes
        self._items = items
        self._generation = generation
        self._embeddings = embeddings
        self._clock = clock
        self._max_suggestions = max_suggestions
        self._excerpt_chars = excerpt_chars
        self._match_threshold = match_threshold

    def __call__(self, *, note_id: UUID) -> None:
        note = self._notes.get_by_id(note_id)
        if note is None:
            return  # deleted before the task ran — its cards survive untouched (AD-145)
        live = self._items.note_items_with_embeddings(note_id)
        if not live:
            return  # nothing promoted (defensive; the enqueue gate already checks)

        context = _note_context(self._notes.anchors_for_note(note_id))
        candidates = self._generation.suggest_note_cards(
            note.body_markdown, context, self._max_suggestions
        )
        survivors = [c for c in candidates if note_card_passes_qc(c, note.body_markdown)]
        embeddings = (
            self._embeddings.embed_documents(
                [f"{c.question}\n{c.answer}" for c in survivors]
            )
            if survivors
            else []
        )
        suggestions = [
            (cand, list(emb)) for cand, emb in zip(survivors, embeddings, strict=True)
        ]

        matches = _greedy_note_matches(live, suggestions, self._match_threshold)
        now = self._clock.now()
        excerpt = note.body_markdown.strip()[: self._excerpt_chars]
        matched_items = {item_idx for item_idx, _sug_idx in matches}
        for item_idx, sug_idx in matches:
            item, _emb = live[item_idx]
            cand, cand_emb = suggestions[sug_idx]
            # Identity mode is the minted id (AD-148), so item_type is preserved and the
            # fingerprint is recomputed from the item's type with the new text.
            new_key = content_key(item.item_type, cand.question, cand.answer)
            if new_key == item.content_key:
                continue  # matched + identical → untouched, no badge (NL-11)
            self._items.update_note_card(
                item.id,
                question=cand.question,
                answer=cand.answer,
                content_key=new_key,
                source_excerpt=excerpt,
                embedding=cand_emb,
                note_changed_at=now,
            )
        for item_idx, (item, _emb) in enumerate(live):
            if item_idx not in matched_items:
                self._items.flag_note_changed(item.id, now)  # unmatched → flag only
