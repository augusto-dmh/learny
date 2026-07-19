# v4-capture-pipeline Specification

RFC-004 Cycle D — cards at the highlight, margin rail, review pins.

## Problem Statement

The reader can now highlight, note, explain, and ask, but the fifth selection verb
("Create card") ships visibly disabled (AD-131), and the only route to a quiz card is
whole-book deck generation. A student who meets one worth-remembering passage has no
one-gesture path from that passage to a scheduled card, no way to see what they have
already annotated in a chapter without leaving the reading column, and no way to get
from a card under review back to the sentence it came from without hand-navigating.

## Goals

- [ ] A highlighted quote produces card suggestions on demand, accepted/edited/discarded
      one at a time — never silently, never in bulk.
- [ ] Accepted cards carry a creation-minted stable identity and typed provenance back to
      the highlight they came from, so later edits never disturb FSRS scheduling.
- [ ] The reading view surfaces the chapter's own notes and orphaned highlights beside the
      text, without a page change.
- [ ] A card under review returns the student to its source passage in one click.
- [ ] The capture gestures meet a measured friction budget.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
| --- | --- |
| Inline card syntax inside note bodies | RFC-004 Cycle D explicit exclusion |
| Standalone card-authoring pages | RFC-004 Cycle D explicit exclusion; cards are created at the passage |
| Auto-highlight on selection | RFC-004 Cycle D explicit exclusion (see CAP-A4) |
| Priority-queue / card-ordering mechanics | RFC-004 Cycle D explicit exclusion; FSRS due order stands |
| Note-body → card generation, one-action promotion | ADR-026 decision 5's other half — RFC-003 Cycle F (see CAP-A1) |
| Notes joining hybrid retrieval; Obsidian export | ADR-026 decisions 4 and 6 — RFC-003 Cycle F |
| MCQ / distractor card types | Locked v2 decision (AD-074); `free_recall` + `cloze` only |
| Changing FSRS parameters or review grading | AD-076 stands untouched |

---

## Assumptions & Open Questions

Every ambiguity is resolved or recorded here — nothing is left silently unclear.

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| CAP-A1 — ADR-026 decision 5 (note→quiz) spans two cycles | This cycle ships the identity + provenance machinery for **highlight-quote-derived** cards only; RFC-003 Cycle F reuses it for **note-body-derived** cards plus one-action promotion | RFC-004 Cycle D names "stable IDs and typed provenance per ADR-026" as its own deliverable; splitting on the *source of the text* keeps each cycle a vertical slice and gives F a finished foundation rather than a half-built one | n (auto-decided) |
| CAP-A2 — Suggestion durability | Suggestions are **ephemeral**: generated per request, returned to the client, never persisted. Only an accepted card becomes a row | "No silent bulk generation" is satisfied structurally — nothing exists until the student accepts. Avoids a suggestion table, its lifecycle, and its cleanup | n (auto-decided) |
| CAP-A3 — Edited card text and QC | Server-side groundedness QC (verbatim-quote containment, cloze-mask validity) gates **generated suggestions**; a card the student edited before accepting is trusted as author-owned and is not re-gated | QC exists to catch model fabrication, not to overrule the person who owns the deck. The citation snapshot still comes from the highlight, so provenance stays honest | n (auto-decided) |
| CAP-A4 — Auto-highlight toggle | Not shipped at all this cycle | RFC-004 lists it under explicit exclusions; the "(toggle, default off)" parenthetical describes the only permissible future form, not a Cycle D deliverable. If added later it must default off | n (auto-decided) |
| CAP-A5 — Dedup on accept | Embedding dedup (AD-074, ≥0.90) is **not** applied to an explicitly accepted card; its embedding is still stored so future deck generation dedups against it | Dedup protects against bulk-generation noise; silently discarding a card the student just chose would be a correctness surprise. Asymmetry is deliberate and pinned by a test | n (auto-decided) |
| CAP-A6 — Suggestion count per request | Capped at 3 per quote, own setting `LEARNY_QUIZ_MAX_SUGGESTIONS` | A highlighted sentence does not support six distinct cards; a small cap bounds cost and keeps the chip row scannable. Separate from the per-section deck cap so tuning one never moves the other | n (auto-decided) |
| CAP-A7 — Rail scope | The rail shows annotations for the **currently loaded chapter only** | It is reading-column furniture, not a notes browser; `/notes` remains the cross-book surface | n (auto-decided) |
| CAP-A8 — Rail vs. panel coexistence | When the Ask/Teach panel is open the rail yields (panel wins); below the `lg` breakpoint the rail renders after the article as a collapsible region | Two simultaneous right-hand columns at `w-56` + `w-26rem` starve the 65ch reading measure that ADR-027 exists to protect | n (auto-decided) |
| CAP-A9 — Shortcut safety | A single global `keydown` listener, ignoring events when a modifier is held or the target is an input, textarea, or contenteditable; must not bind `b` (vendored sidebar owns Cmd/Ctrl+B) | The app has no shortcut precedent at all, so the guard is the load-bearing part | n (auto-decided) |
| CAP-A11 — Reword affordance | Not shipped this cycle; the backend `PATCH /api/quiz-items/{id}` and its guarantee ship, no client for it does | RFC-004 Cycle D's "edit" is editing a suggestion before acceptance, not a saved card. Shipping an unused client helper would be dead code; it arrives with the note-derived cards that need it (RFC-003 Cycle F) | n (auto-decided, post-verification) |
| CAP-A10 — Reconcile independence | Highlight-derived cards reconcile on their **own** snapshot via the existing `ReconcileQuizItems` ladder, independent of the linked note anchor's outcome; the current ingestion step order — **quiz reconcile first, then notes** (`app/worker/tasks.py`) — is pinned by a test | The two reconcilers have no ordering contract today; making cards depend on anchor outcomes would create one and couple two aggregates. Each carries its own excerpt, so each is self-consistent. The pin exists so a silent reorder fails loudly, not because either order is required | n (auto-decided) |

**Open questions:** none — all resolved or logged above.

---

## User Stories

### P1: Create a card from a highlighted passage ⭐ MVP

**User Story**: As a student, I want to turn a passage I just highlighted into a review
card without leaving the page, so that remembering it costs me two actions instead of a
detour through deck generation.

**Why P1**: This is the cycle's headline — the fifth verb has shipped disabled for a cycle
and the RFC names it as Cycle D's completion.

**Acceptance Criteria**:

1. WHEN the student selects text and activates "Create card" THEN the system SHALL request
   card suggestions scoped to that quote and render them as pending suggestion chips.
2. WHEN suggestions are generated THEN the system SHALL return at most `LEARNY_QUIZ_MAX_SUGGESTIONS`
   (default 3) candidates for that quote.
3. WHEN a generated candidate's `anchor_quote` is not contained verbatim in the highlighted
   quote's section text THEN the system SHALL discard that candidate and never return it.
4. WHEN a generated `cloze` candidate's mask is not valid against its anchor quote THEN the
   system SHALL discard that candidate and never return it.
5. WHEN the student accepts a suggestion THEN the system SHALL persist exactly one quiz item
   and create its initial FSRS scheduling, making it due immediately.
6. WHEN the student edits a suggestion's question or answer before accepting THEN the system
   SHALL persist the edited text.
7. WHEN the student discards a suggestion THEN the system SHALL persist nothing for it.
8. WHEN suggestion generation fails THEN the system SHALL surface a retryable error and leave
   the highlight untouched.
9. WHEN the request is not owned by the caller THEN the system SHALL respond 404.

**Independent Test**: Select a passage, click "Create card", accept one of the chips, and see
it appear in the source's quiz overview with a due date.

---

### P1: Stable identity and typed provenance ⭐ MVP

**User Story**: As a student, I want a card I made from a highlight to be identified by
something other than its own text, so that when a reword affordance arrives it cannot cost me
my memory history — and so that deleting the note it came from never destroys the card.

**Why P1**: ADR-026 decision 5 is binding, and the existing content-hash identity (AD-073)
actively breaks this — it is the one thing that cannot be retrofitted later without a data
migration.

**Scope note (CAP-A11)**: this cycle ships the identity, the provenance, and the API that
enforces the guarantee; it does *not* ship a UI for rewording a saved card, which RFC-004
Cycle D does not ask for (its "accept/edit/discard" is editing a *suggestion*, before
acceptance — CAP-06). No card in the product has ever been editable, so nothing regresses.
CAP-12 is therefore proven at the application, API, and database layers rather than through
the reader.

**Acceptance Criteria**:

1. WHEN a quiz item is created THEN the system SHALL record a typed origin of either `deck`
   (whole-source generation) or `highlight` (accepted from a passage).
2. WHEN a card is accepted from a highlight THEN the system SHALL link it to the originating
   note anchor as typed provenance.
3. WHEN a `highlight`-origin card's question or answer changes THEN the system SHALL keep the
   item's identity, its FSRS scheduling, and its review log unchanged.
4. WHEN two `deck`-origin items share a `content_key` for one source THEN the system SHALL
   treat them as the same item (existing upsert behaviour, unchanged).
5. WHEN a `highlight`-origin item shares a `content_key` with an item of a different origin, a
   different source, or a different originating anchor THEN the system SHALL still store it as
   a distinct row. (Re-accepting identical text from the *same* anchor is idempotent — see the
   double-submit edge case.)
6. WHEN the note or anchor a card came from is deleted THEN the system SHALL keep the card,
   clear the provenance link, and keep the card renderable from its own stored excerpt.
7. WHEN a card with provenance is shown at review THEN the system SHALL display its origin
   note's title.
8. WHEN a re-ingestion reconciles a `highlight`-origin card THEN the system SHALL apply the
   existing anchor/excerpt ladder to it and SHALL NOT modify its scheduling or review log.

**Independent Test**: Accept a card from a highlight, edit its text through the API, and
confirm the row id and its `due` value are unchanged; delete the source note and confirm the
card survives and stays due.

---

### P1: Margin rail ⭐ MVP

**User Story**: As a student, I want the notes and lost highlights for the chapter I am
reading visible beside the text, so that I can see my own trail through the book without
navigating away.

**Why P1**: The RFC names it; it is also the only surface where orphaned highlights — which
ADR-026 keeps forever — become visible to the person who made them.

**Acceptance Criteria**:

1. WHEN a chapter is displayed THEN the system SHALL show a rail listing that chapter's
   highlights and notes in document order.
2. WHEN a rail entry has a note body THEN the system SHALL show the note's title.
3. WHEN a highlight is orphaned THEN the system SHALL list it with an orphaned indicator and
   render it from its stored quote snapshot.
4. WHEN the student activates a rail entry whose highlight is painted in the loaded chapter
   THEN the system SHALL scroll to it and flash it.
5. WHEN the student activates an orphaned rail entry THEN the system SHALL NOT attempt to
   scroll, and SHALL offer the origin note instead.
6. WHEN the chapter has no annotations THEN the system SHALL render an empty state, not an
   empty column.
7. WHEN the Ask/Teach panel is open THEN the system SHALL hide the rail.

**Independent Test**: Highlight two passages in a chapter, reload, and see both in the rail;
clicking one scrolls the article to it.

---

### P1: Review pin ⭐ MVP

**User Story**: As a student grading a card, I want one click back to the passage it came
from, so that a card I failed becomes a re-read instead of a dead end.

**Why P1**: RFC-004 names it, and it closes the capture loop the rest of this cycle opens.

**Acceptance Criteria**:

1. WHEN a card is shown at review THEN the system SHALL render a pin control targeting its
   cited anchor in the reader.
2. WHEN the pin is activated THEN the system SHALL navigate to the reader at that source and
   anchor.
3. WHEN a card carries note provenance THEN the pin SHALL additionally offer the origin note.

**Independent Test**: Start a review, click the pin, and land in the reader scrolled to the
card's passage.

---

### P2: Single-key shortcuts

**User Story**: As a student, I want the capture and grading actions on single keys, so that
the common gestures cost no pointer travel.

**Why P2**: Real friction reduction, but the cycle's value survives without it.

**Acceptance Criteria**:

1. WHEN text is selected in the reader and the student presses the highlight key THEN the
   system SHALL perform the same action as the "Highlight" verb.
2. WHEN text is selected in the reader and the student presses the card key THEN the system
   SHALL perform the same action as the "Create card" verb.
3. WHEN a review card is unrevealed and the student presses the reveal key THEN the system
   SHALL reveal the answer.
4. WHEN a review card is revealed and the student presses a grade key (1–4) THEN the system
   SHALL submit that grade.
5. WHEN the event target is an input, textarea, or contenteditable element THEN the system
   SHALL ignore the key.
6. WHEN any of Ctrl, Meta, or Alt is held THEN the system SHALL ignore the key.

**Independent Test**: Select a passage, press the highlight key, and see the highlight
persist; type the same letter into the note textarea and see nothing happen.

---

### P2: Friction budget

**User Story**: As the product owner, I want the capture gestures held to a measured action
count, so that "low friction" is a property the suite defends rather than a claim.

**Why P2**: Enforcement mechanism rather than user-visible capability.

**Acceptance Criteria**:

1. WHEN a highlight is created from an existing selection THEN it SHALL cost at most 1
   pointer action.
2. WHEN a card is created from an existing selection THEN it SHALL cost at most 2 pointer
   actions (invoke, accept).
3. WHEN the student jumps from a review card to its passage THEN it SHALL cost 1 pointer
   action.

**Independent Test**: The suite counts the interactions in each path and fails if a
regression adds one.

---

## Edge Cases

- WHEN the selection cannot be located verbatim in the served Markdown THEN the system SHALL
  not offer card creation for it (existing `deriveCaptureSelection` null path).
- WHEN the underlying section changed since load and the anchor no longer binds THEN the
  system SHALL respond 409 and tell the student to reload.
- WHEN the generator returns zero usable candidates after QC THEN the system SHALL report
  "no cards for this passage", not an error.
- WHEN the same suggestion is accepted twice (double submit) THEN the system SHALL create one
  card and return the existing one on the second attempt, not a duplicate.
- WHEN a card is accepted with empty question or answer text THEN the system SHALL respond 422.
- WHEN accepted card text exceeds the configured length bound THEN the system SHALL respond 422.
- WHEN the student is over the quiz rate limit THEN suggestion generation SHALL be throttled
  on the same limiter as deck generation.
- WHEN the rail is rendered for a chapter whose highlights failed to load THEN the reader
  SHALL still render the text (non-blocking, existing highlight-load semantics).

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| --- | --- | --- | --- |
| CAP-01 | P1: Create a card | Design | Pending |
| CAP-02 | P1: Create a card | Design | Pending |
| CAP-03 | P1: Create a card | Design | Pending |
| CAP-04 | P1: Create a card | Design | Pending |
| CAP-05 | P1: Create a card | Design | Pending |
| CAP-06 | P1: Create a card | Design | Pending |
| CAP-07 | P1: Create a card | Design | Pending |
| CAP-08 | P1: Create a card | Design | Pending |
| CAP-09 | P1: Create a card | Design | Pending |
| CAP-10 | P1: Identity + provenance | Design | Pending |
| CAP-11 | P1: Identity + provenance | Design | Pending |
| CAP-12 | P1: Identity + provenance | Design | Pending |
| CAP-13 | P1: Identity + provenance | Design | Pending |
| CAP-14 | P1: Identity + provenance | Design | Pending |
| CAP-15 | P1: Identity + provenance | Design | Pending |
| CAP-16 | P1: Identity + provenance | Design | Pending |
| CAP-17 | P1: Identity + provenance | Design | Pending |
| CAP-18 | P1: Margin rail | Design | Pending |
| CAP-19 | P1: Margin rail | Design | Pending |
| CAP-20 | P1: Margin rail | Design | Pending |
| CAP-21 | P1: Margin rail | Design | Pending |
| CAP-22 | P1: Margin rail | Design | Pending |
| CAP-23 | P1: Margin rail | Design | Pending |
| CAP-24 | P1: Margin rail | Design | Pending |
| CAP-25 | P1: Review pin | Design | Pending |
| CAP-26 | P1: Review pin | Design | Pending |
| CAP-27 | P1: Review pin | Design | Pending |
| CAP-28 | P2: Shortcuts | Design | Pending |
| CAP-29 | P2: Shortcuts | Design | Pending |
| CAP-30 | P2: Shortcuts | Design | Pending |
| CAP-31 | P2: Shortcuts | Design | Pending |
| CAP-32 | P2: Shortcuts | Design | Pending |
| CAP-33 | P2: Shortcuts | Design | Pending |
| CAP-34 | P2: Friction budget | Design | Pending |
| CAP-35 | P2: Friction budget | Design | Pending |
| CAP-36 | P2: Friction budget | Design | Pending |

**ID mapping:** CAP-01..09 = P1 Create-a-card AC 1..9; CAP-10..17 = P1 Identity AC 1..8;
CAP-18..24 = P1 Rail AC 1..7; CAP-25..27 = P1 Pin AC 1..3; CAP-28..33 = P2 Shortcuts AC 1..6;
CAP-34..36 = P2 Friction AC 1..3.

**Status values:** Pending → In Design → In Tasks → Implementing → Verified

**Coverage:** 36 total, 0 mapped to tasks yet.

---

## Success Criteria

- [ ] A passage becomes a scheduled card in two pointer actions.
- [ ] Editing a highlight-derived card leaves its `due` value and review log byte-identical.
- [ ] Deleting a note leaves every card it produced intact and reviewable.
- [ ] Orphaned highlights are visible in the reader rather than only in `/notes`.
- [ ] Backend and frontend suites green; no regression in whole-deck generation behaviour.
