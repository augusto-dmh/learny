# Workspace: the notes & review surface — Specification

RFC-006 Cycle D, second half (see `v6-workspace-conversations/context.md` D-1 / AD-203
for the split decision).

## Problem Statement

The reader became the hub for *conversations* last cycle, but two of the four dock tabs
the workspace design calls for are still missing: a reader cannot see this book's notes
or this book's due cards without leaving the book. Meanwhile `/notes` is still the only
way to see a book's notes, and it carries a title-only creation form that mints notes
with no reading context at all — the rootless notes dogfood finding 6 names. The
capture machinery to fix this already exists; nothing consumes it from the dock.

## Goals

- [ ] A reader can see this book's notes in the dock, each showing the passage it came from.
- [ ] A reader can see how many cards are due from this book and start reviewing them, without leaving the book.
- [ ] Every newly created note carries a reading anchor — the title-only path is gone.
- [ ] `/notes` becomes the cross-book surface it claims to be: it can be filtered to one book, and it is no longer the only door to a book's notes.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
| --- | --- |
| Thinking/streaming states, inline numbered citations, app-wide loading pattern | RFC-006 Cycle E. The workspace artifact shows them in the Ask tab; they are explicitly E's scope |
| Ask/Teach dock behaviour, conversation list/rename/delete | Shipped by `v6-workspace-conversations` (PR #53); this cycle adds tabs beside it and does not modify it |
| Grading UI reimplemented inside the dock | The review flow exists; rebuilding it in a 372px column is the "no UI built twice" failure criterion 1 forbids (D-3) |
| A notes editor rework, CodeMirror upgrade, wikilink autocomplete | ADR-0026 decision 3 names these as a later, additive upgrade with its own trigger |
| Deleting or migrating existing anchorless notes | ADR-0026: user prose is never destroyed. Only *creation* is constrained (D-2) |
| Retrieval-ranking, eval-stack, worker, or provider changes | RFC-006 exclusions; ADR-0009/0019/0020 hold |
| Streaks, badges, "you're behind" copy on the due count | I-7 gamification cap binds every touched surface |

---

## Assumptions & Open Questions

Every ambiguity is resolved or recorded here — nothing is left silently unclear.

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| Where provenance is enforced | **Server-side**: note creation requires an anchor; the API rejects an anchorless create | A UI-only retirement leaves the rootless path one `curl` away and gives the invariant no sensor. The finding is about what a note *is*, which is a domain rule, not a form layout (D-2) | n — design decision |
| Existing anchorless notes | Keep, readable and editable; only creation is constrained | ADR-0026: notes and anchors never cascade-destroy user prose. A migration that deleted them would destroy work to satisfy a UI rule | y — ADR-0026 |
| Which creation paths survive | Passage selection (reader capture) **and** save-an-answer | RFC-006 §Cycle D resolves finding 6's open question explicitly in favour of "anchored, not strictly reader-only" | y — RFC-recorded |
| What the dock Review tab does | Renders the **shipped** `ReviewScreen` scoped to this book, so grading happens in the dock | `ReviewScreen` already accepts an optional `sourceId` and passes it to `getDueReviews` (`review-screen.tsx:60,85`), so in-place review is reuse of the existing grading UI rather than a second implementation — and it delivers the artifact's "reviewable without leaving it" instead of a navigation away (D-3) | n — design decision |
| Notes-by-source filtering shape | A `source_id` query parameter on the existing notes list endpoint, matching `GET /api/reviews/due?source_id=` | One shipped convention already answers this exact question for cards; a second shape would be gratuitous | n — pending survey confirmation of the current endpoint |
| Tab count badges | Notes tab shows this book's note count; Review tab shows this book's due count | Both are queue counts the artifact specifies, not achievement figures — I-7 forbids streaks/badges, not inventory | y — artifact + I-7 |
| Anchor displayed on a note row | Section title + page number + the quote snapshot | The artifact's row meta is `Prefácio · p. 62` with the quote beneath; the page unit shipped in Cycle B (AD-189, book-global numbering) | y — artifact + AD-189 |
| Cross-book `/notes` filter control | A source picker that filters the existing list; no route change | `/notes` "keeps, re-scoped" per the artifact's route table — it stays the second-brain entry point | y — artifact |

**Open questions:** none — all resolved or logged above.

### Implicit-requirement dimensions sweep (Large ⇒ every dimension)

| Dimension | Resolution |
| --- | --- |
| Input validation & bounds | `source_id` must be a UUID the caller owns; the notes list keeps its existing body/tag validation; the dock's list is bounded like the shipped list conventions — WSN-11 |
| Failure / partial-failure | Anchored creation is already atomic (note + anchor in one transaction, `StaleCaptureTarget` → 409); making anchors mandatory must not introduce a half-created note — WSN-12 |
| Idempotency / retry / duplicate | Re-submitting the same capture creates a second note (existing behaviour, unchanged); no new dedup rule is introduced — N/A beyond WSN-12 |
| Auth boundaries & rate limits | Every new/changed route authorizes by owner and collapses missing/non-owner to 404 (the shipped disclosure rule); creation keeps its existing limiter — WSN-13 |
| Concurrency / ordering | Notes list ordering stays newest-edited-first and must be total so the dock list is stable — WSN-14 |
| Data lifecycle / expiry | Anchors may orphan on re-ingest and are kept forever (ADR-0026); an orphaned anchor must still render its quote — WSN-15 |
| Observability | Covered by the shipped instrument (RFC-006 Cycle A); no new logging required — N/A |
| External-dependency failure | No provider or network call is added by this cycle — N/A |
| State-transition integrity | A note's anchored/anchorless state is set at creation and never transitions; legacy anchorless notes stay anchorless — WSN-16 |

---

## User Stories

### P1: This book's notes, in the dock ⭐ MVP

**User Story**: As a reader, I want this book's notes beside the page I'm reading, so that I can see what I've already written without leaving the book.

**Why P1**: It is half the reason the cycle exists; the dock is the workspace's whole premise.

**Acceptance Criteria**:

1. WHEN the reader opens the dock's Notes tab for a book THEN the system SHALL list only notes anchored to that book, newest-edited first.
2. WHEN a note row is rendered THEN the system SHALL show the note's title, the anchored section's title and page number, and the anchored quote snapshot.
3. WHEN a note is anchored to the book more than once THEN the system SHALL list that note exactly once.
4. WHEN the book has no anchored notes THEN the system SHALL render the empty state "Notes on this book only. Select a passage to start a new one — every note keeps the passage it came from." and no note rows.
5. WHEN the Notes tab is rendered THEN the system SHALL show this book's note count on the tab.
6. WHEN a listed note's anchor has orphaned THEN the system SHALL still render the row from its stored quote snapshot, with no page number, and SHALL NOT drop the note from the list.

**Independent Test**: Seed a book with two anchored notes (one double-anchored) and one anchorless note; open the dock's Notes tab; exactly two rows appear, each with its quote.

---

### P2: What's due from this book ⭐ MVP

**User Story**: As a reader, I want to see how many cards are due from this book and start reviewing them in place, so that reviewing doesn't mean abandoning my reading.

**Why P2**: Second half of the dock; smaller because the grading UI already exists and is reused rather than rebuilt.

**Acceptance Criteria**:

1. WHEN the reader opens the dock's Review tab THEN the system SHALL show the count of cards due from this book and the caption "cards due from this book".
2. WHEN at least one card is due THEN the system SHALL let the reader grade those cards from within the dock, without navigating away from the reader.
3. WHEN no card is due from this book THEN the system SHALL show an empty state and SHALL NOT offer the review action.
4. WHEN the Review tab is rendered THEN the system SHALL show the due count on the tab.
5. WHEN the due count is shown THEN the system SHALL present it as a queue count only — no streak, badge, or fallen-behind copy (I-7).

**Independent Test**: Seed a book with 3 due cards; the tab reads 3, the panel reads "3 / cards due from this book", and a card can be graded in the dock with the reader still mounted.

---

### P3: Every note keeps where it came from ⭐ MVP

**User Story**: As a reader, I want notes to be inseparable from the passage that prompted them, so that my notes stay meaningful months later.

**Why P3 (still MVP)**: Ordered last because it is a contract change the two tabs depend on for their meaning, not because it is optional.

**Acceptance Criteria**:

1. WHEN a note-creation request carries no reading anchor THEN the system SHALL reject it and SHALL NOT persist a note.
2. WHEN a note is created from a passage selection THEN the system SHALL persist the note and its anchor atomically, as it does today.
3. WHEN a note is created by saving an answer THEN the system SHALL persist it with the answer's citation anchor.
4. WHEN a note created before this change has no anchor THEN the system SHALL continue to return, render, edit, and delete it unchanged.
5. WHEN the notes screen is rendered THEN the system SHALL NOT offer a title-only creation control.

**Independent Test**: `POST` a note with no anchor → rejected, note count unchanged; capture from a passage → 201; a pre-existing anchorless note still opens and saves.

---

### P4: `/notes` as the cross-book surface

**User Story**: As a note-keeper, I want `/notes` to stay my everything view but let me narrow to one book, so that it stops being the only door to a book's notes.

**Why P4**: The route already exists and works; this is a re-scoping, not a build.

**Acceptance Criteria**:

1. WHEN `/notes` loads with no filter THEN the system SHALL list the caller's notes across every book, as it does today.
2. WHEN a book filter is applied THEN the system SHALL list only notes anchored to that book.
3. WHEN a filter is applied and then cleared THEN the system SHALL return to the unfiltered cross-book list.
4. WHEN the notes list is requested with a `source_id` the caller does not own THEN the system SHALL respond 404, disclosing nothing about the source's existence.

**Independent Test**: With notes across two books, `/notes` shows both; filtering to book A shows only A's; clearing restores both.

---

## Edge Cases

- WHEN a `source_id` filter names a source with zero notes THEN the system SHALL return an empty list, not an error.
- WHEN a note is anchored to a book the caller no longer owns THEN the system SHALL NOT return it under that book's filter.
- WHEN the dock's Notes tab is open and a new note is captured from the page THEN the system SHALL reflect the new note without a full page reload.
- WHEN a book's note count is zero THEN the system SHALL render the tab without a count rather than a "0".
- WHEN the review action is taken and every due card has since been reviewed elsewhere THEN the existing review flow SHALL handle the empty queue with no new failure mode.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| --- | --- | --- | --- |
| WSN-01 | P1: dock Notes tab lists this book's anchored notes | Design | Pending |
| WSN-02 | P1: note row shows title, section, page, quote | Design | Pending |
| WSN-03 | P1: a multi-anchored note appears once | Design | Pending |
| WSN-04 | P1: empty state copy, verbatim | Design | Pending |
| WSN-05 | P1/P2: tab count badges | Design | Pending |
| WSN-06 | P2: due count + caption for this book | Design | Pending |
| WSN-07 | P2: grading happens in the dock, reusing the shipped review screen | Design | Pending |
| WSN-08 | P3: anchorless creation rejected, nothing persisted | Design | Pending |
| WSN-09 | P3: legacy anchorless notes keep working | Design | Pending |
| WSN-10 | P4: `source_id` filter on the notes list; unowned → 404 | Design | Pending |
| WSN-11 | Bounds: `source_id` validation and list bounds | Design | Pending |
| WSN-12 | Atomicity: no half-created note under the new rule | Design | Pending |
| WSN-13 | Authorization: owner-scoped, 404 collapse, limiter kept | Design | Pending |
| WSN-14 | Ordering: total, stable newest-edited-first | Design | Pending |
| WSN-15 | Orphaned anchor still renders from its quote | Design | Pending |
| WSN-16 | Anchored/anchorless never transitions | Design | Pending |

**Coverage:** 16 total, 0 mapped to tasks yet (Tasks phase pending).

---

## Success Criteria

- [ ] From an open book, its notes and its due-card count are both reachable without a navigation away from the reader.
- [ ] No API request can create a note without a reading anchor, and a test proves it.
- [ ] Existing anchorless notes still open, render, and save.
- [ ] `/notes` can be narrowed to a single book and still defaults to every book.
- [ ] Backend and frontend suites green against the recorded baseline (see below); no test weakened or deleted to achieve it.

## Verification baseline (recorded 2026-07-27, clean `main` @ fcb545d6)

- Frontend: **665 passed, 67 files** (`make test-frontend`).
- Backend: **1858 passed, 11 skipped, 1 failed** (`make test-backend`).
  The single failure is **pre-existing and local-only**:
  `tests/test_eval_retrieval_metrics.py::TestDeterministicRetrievalMetrics::test_metrics_meet_thresholds`
  (`recall@1 = 0.857 < 0.9`). CI is green on the same commit; the local
  `pgvector` build (0.8.4, image built 2026-06-30) differs from the one CI pulls.
  It is outside this cycle's scope (RFC-006 excludes retrieval-ranking work).
  **Do not "fix" it, do not weaken its threshold, and do not count it as a regression.**
