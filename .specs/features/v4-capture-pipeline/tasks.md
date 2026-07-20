# v4-capture-pipeline Tasks

**Spec**: `spec.md` · **Design**: `design.md` · **Context**: `context.md`

Five phases, one worker each (A–E), sequential. Every task: tests from the spec's acceptance
criteria → gate green → one atomic commit. Gate scoping: affected module/test file per task,
full suite (+ `ruff` / `tsc` / `build`) at each phase boundary.

Environment: DB-gated backend tests need `LEARNY_TEST_DATABASE_URL`
(`postgresql+psycopg://learny:learny@localhost:5432/learny_test`). If `uv` is not on PATH, use
`backend/.venv/bin/python -m pytest`.

---

## Phase A — Schema and persistence

**A1 — Migration `0012_card_provenance`**
Add `quiz_items.origin` (TEXT NOT NULL DEFAULT `'deck'`) and
`note_anchor_id` (UUID NULL, FK `note_anchors.id` ON DELETE SET NULL, indexed); drop
`uq_quiz_items_source_id`; create partial unique indexes `uq_quiz_items_deck_content_key`
(`WHERE origin='deck'`) and `uq_quiz_items_highlight_anchor_key`
(`WHERE origin='highlight' AND note_anchor_id IS NOT NULL`). Mirror all of it in `metadata.py`
(`Index(..., unique=True, postgresql_where=...)` replacing the current `UniqueConstraint`).
`down_revision = "0011_reader_progress"`; downgrade restores the original constraint.
*Verify*: migration test upgrades then downgrades cleanly on a live DB; existing rows read back
with `origin='deck'`.
*Covers*: CAP-10 (schema half), CAP-13, CAP-14.

**A2 — Domain entities**
`QuizItemOrigin` constants beside `QuizItemStatus`; `QuizItem.origin` + `QuizItem.note_anchor_id`;
`SourceHighlight.note_title` + `.has_body`; provenance on `DueReviewItem`.
*Verify*: `tests/test_domain_quiz.py` — origin vocabulary, defaults, entity invariants.
*Covers*: CAP-10, CAP-16 (entity half), CAP-19.

**A3 — Repository: origin-aware writes and reads**
`SqlAlchemyQuizItemRepository.upsert` persists `origin`/`note_anchor_id` and keeps deck upsert
semantics unchanged; add `get_by_anchor_and_key(note_anchor_id, content_key)` and
`update_text(item_id, *, question, answer, content_key)`; `items_for_reconcile`/`get_by_id`/
`list_for_source` carry the new fields.
*Verify*: `tests/test_repositories_quiz.py` (DB-gated) — two deck rows with one `content_key`
collapse to one; two highlight rows with the same `content_key` under *different* anchors both
persist; the same anchor + same key returns the existing row; `update_text` leaves
`quiz_item_scheduling` and `review_log` byte-identical.
*Covers*: CAP-12, CAP-13, CAP-14.

**A4 — Repository: rail and provenance joins**
`highlights_for_source` joins `notes` for `note_title` + `has_body`; `due_for_user` joins
`note_anchors` → `notes` for provenance (NULL-safe when the link was severed).
*Verify*: `tests/test_repositories_notes.py` + `tests/test_repositories_quiz.py` (DB-gated) —
titles present; deleting the note leaves the card with NULL provenance and an intact excerpt.
*Covers*: CAP-15, CAP-16, CAP-19.

**Phase A gate**: full backend suite + `ruff`.

---

## Phase B — Generation and application

**B1 — `suggest_cards` on the port + both adapters + setting**
Port method `suggest_cards(section, quote, limit) -> list[QuizCandidate]`; deterministic adapter
narrows its existing construction to the quote; Anthropic adapter issues one Messages call reusing
`_items_schema` and the `source_chunk_id` enum. New setting `quiz_max_suggestions: int = 3`.
*Verify*: `tests/test_quiz_local.py`, `tests/test_quiz_anthropic.py` (stubbed client) — candidates
never exceed `limit`; the schema constrains `source_chunk_id` to the section's chunk ids.
*Covers*: CAP-02.

**B2 — `SuggestCards` use case**
New `app/application/cards.py`. Ownership + anchor validation (wrong owner or wrong source →
`QuizItemNotFound`), section load (missing → `StaleCaptureTarget`), generation, QC filter
(`quote_in_text`, `cloze_is_valid`), cap at `limit`.
*Verify*: `tests/test_application_cards.py` — ungrounded candidate dropped; invalid cloze dropped;
zero survivors returns `[]` and not an error; cross-owner anchor raises not-found.
*Covers*: CAP-01, CAP-02, CAP-03, CAP-04, CAP-09.

**B3 — `AcceptCard` use case**
Mint with `origin="highlight"`, provenance, citation fields from the anchor,
`chunk_hash = sha256(normalize_text(quote_exact))`, `generation_meta`; embed and store the
embedding but skip dedup; `create_scheduling(initial())`; idempotent re-accept returns the
existing item with `created=False`; empty/over-long text raises the validation error.
*Verify*: `tests/test_application_cards.py` — one row + scheduling due now; double accept yields
one row; a near-duplicate of an existing item is still stored (dedup asymmetry pinned);
empty question rejected.
*Covers*: CAP-05, CAP-06, CAP-07, CAP-10, CAP-11.

**B4 — `UpdateCard` use case**
Owner-scoped text update with recomputed `content_key`; rejects `deck`-origin items; never touches
scheduling or the review log.
*Verify*: `tests/test_application_cards.py` — id and `due` unchanged across an edit; deck item
rejected.
*Covers*: CAP-12.

**Phase B gate**: full backend suite + `ruff`.

---

## Phase C — API surface

**C1 — Card routes + DI**
New `app/infrastructure/web/cards.py` with the three routes from the design, registered in
`main.py`; `dependencies.py` builders; `rate_limit_quiz` + origin + CSRF on all three; error map
additions if any new exception type is introduced.
*Verify*: `tests/test_web_cards.py` (DB-gated) — 200/201/422/404/409 legs, CSRF rejection,
non-owner 404, idempotent re-accept returns 200 with the same id.
*Covers*: CAP-01, CAP-05..09.

**C2 — Provenance and rail fields on existing views**
`DueItemView.provenance`; `SourceHighlightView.note_title`/`has_body`.
*Verify*: `tests/test_web_quiz.py`, `tests/test_web_notes.py` — provenance present for a
highlight-derived card, `null` after the note is deleted; highlight rows carry titles.
*Covers*: CAP-16, CAP-19.

**C3 — Reconcile coverage and step-order pin**
Assert the existing ladder applies to highlight-origin rows (keep/stale/relocate/orphan) without
touching scheduling, and pin the shipped ingestion step order (quiz reconcile, then notes).
*Verify*: `tests/test_reconcile_quiz.py` (DB-gated) + a step-order assertion in the worker tests.
*Covers*: CAP-17.

**Phase C gate**: full backend suite + `ruff`.

---

## Phase D — Reader capture flow

**D1 — `lib/cards.ts`**
`suggestCards`, `acceptCard`, `CardError` with `kind`, each with the trailing `fetchImpl` seam.
(An `updateCard` helper was built here and then removed during review triage: no surface in this
cycle edits a saved card, so it was dead code. The backend `PATCH` route it targeted stays as the
contract RFC-003 Cycle F consumes — see CAP-A11.)
*Verify*: `tests/cards-client.test.ts` — URL/method/CSRF header per call; 409 → `stale_capture`;
422 → `invalid`.
*Covers*: CAP-01, CAP-08.

**D2 — `CardSuggestions` component**
Chip row with Accept / Edit / Discard; inline edit textarea; per-chip pending and error state;
discard is client-only.
*Verify*: `tests/card-suggestions.test.tsx` — accept posts once and reports the created card;
edit-then-accept posts the edited text; discard posts nothing; error renders and retries.
*Covers*: CAP-05, CAP-06, CAP-07, CAP-08.

**D3 — Wire the Create card verb**
Replace the disabled placeholder in `capture-popover.tsx:152` with a live verb; `chapter-reader.tsx`
sequences `captureHighlight` → `suggestCards` → renders `CardSuggestions`; 409 reuses the existing
reload message.
*Verify*: `tests/capture-popover.test.tsx` (verb enabled and wired) and
`tests/chapter-reader.test.tsx` — full path from selection to an accepted card; stale target shows
the reload message.
*Covers*: CAP-01, CAP-08.

**Phase D gate**: full frontend suite + `tsc` + `build`.

---

## Phase E — Rail, pin, shortcuts, budget

**E1 — `MarginRail`**
Chapter-scoped, document-ordered list; note titles; `AnchorStatusBadge` for non-active statuses;
orphan entries render from the quote snapshot and offer the note instead of a scroll; empty state;
hidden while the panel is open; collapsible below `lg`.
*Verify*: `tests/margin-rail.test.tsx` + a `chapter-reader.test.tsx` leg — ordering, orphan
treatment, jump scrolls and flashes, empty state, hidden with `?panel=ask`.
*Covers*: CAP-18..24.

**E2 — Review pin and provenance**
Replace the hand-built URL at `review-screen.tsx:265` with `readUrl`; render the pin control and,
when provenance exists, the origin note's title plus a link to it.
*Verify*: `tests/review-screen.test.tsx` — pin href matches `readUrl`; provenance title rendered;
absent provenance renders no note affordance.
*Covers*: CAP-25, CAP-26, CAP-27.

**E3 — `use-key-shortcuts` + bindings**
The guarded global hook; reader `h`/`c` while the capture popover is open; review `space` reveal and
`1`–`4` grade.
*Verify*: `tests/use-key-shortcuts.test.tsx` — modifier held ignored; input/textarea/contenteditable
target ignored; listener removed on unmount; `b` unbound. Plus binding legs in the reader and review
tests.
*Covers*: CAP-28..33.

**E4 — Friction budget tests**
Interaction-count assertions for the three budgeted paths.
*Verify*: `tests/friction-budget.test.tsx` — highlight from an existing selection is 1 action; card
is 2; review jump-back is 1.
*Covers*: CAP-34, CAP-35, CAP-36.

**Phase E gate**: full frontend suite + `tsc` + `build`, then the full backend suite + `ruff` as a
no-regression check.

---

## Coverage

36 requirements, all mapped:

| Phase | Requirements |
| --- | --- |
| A | CAP-10, 12, 13, 14, 15, 16, 19 |
| B | CAP-01..07, 09, 10, 11, 12 |
| C | CAP-01, 05..09, 16, 17, 19 |
| D | CAP-01, 05..08 |
| E | CAP-18..36 |

Unmapped: none.

---

## Verifier

Fresh sub-agent after E4, always on the session model. Spec-anchored outcome check across all 36
ACs plus a discrimination sensor. Priority mutation targets, chosen where a silent failure would be
most expensive:

1. Flip the deck partial index to cover all origins → the same-key-different-anchor test must fail.
2. Make `UpdateCard` rewrite scheduling → the unchanged-`due` test must fail.
3. Change the provenance FK to CASCADE → the card-survives-note-deletion test must fail.
4. Drop the QC filter in `SuggestCards` → the ungrounded-candidate test must fail.
5. Apply embedding dedup on accept → the near-duplicate-accepted test must fail.
6. Remove the shortcut input guard → the typing-in-textarea test must fail.
7. Make the rail render all sources' highlights → the chapter-scope test must fail.
