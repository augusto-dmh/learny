# Reader Apparatus Specification (RFC-004 Cycle C)

## Problem Statement

Ask and Teach live on standalone sibling pages, so studying means leaving the book: citations navigate away from the answer, selections can't become questions, and answers can't become notes. The reading-first IA (RFC-004) requires Ask/Teach to become non-modal panel modes inside the chapter reader, citations to resolve as passages that open the book in place, and a selection popover that carries the full verb set.

## Goals

- [ ] Ask and Teach run as side-panel modes inside the chapter reader; the standalone pages are gone and their URLs redirect into the reader.
- [ ] Citations render as verbatim passages with section-path locators and jump the reader to the anchor while the answer stays visible.
- [ ] Selecting text offers five verbs (Highlight · Note · Explain · Ask · Create card), all inheriting the selection's anchor context.
- [ ] Ask/Teach answers can be saved as anchored notes.
- [ ] Unblocks RFC-003 Cycle F (panel + citation-passage component exist).

## Out of Scope

| Feature | Reason |
|---|---|
| Per-selection quiz-card generation (Create card behavior) | RFC-004 Cycle D scope; this cycle ships the verb as a disabled placeholder |
| Margin rail, review pins, friction budget | Cycle D |
| Home/IA rewire, nav collapse | Cycle E |
| Anchor-scoped retrieval changes for Ask | Retrieval architecture frozen (RFC-004 boundary); Explain/Ask scope via prompt context |
| Backend schema or endpoint additions | All needed seams exist (chapter, section, capture, notes, streams); frontend-only cycle |
| Position-scoped ("spoiler-safe") retrieval | RFC-004 explicit exclusion |
| Mobile-specific panel layout | Desktop-web first per RFC-004; responsive degradation only |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|
| Panel state representation | URL query `?panel=ask\|teach` on the read route | Deep-linkable; redirects map cleanly; back button works (D-1) | auto (AD-129) |
| Old-route redirect mechanism | Server `redirect()` in the page files | Keeps dynamic `[id]`, no config coupling (D-2) | auto (AD-129) |
| Citation passage source | Stored citation `snippet` (verbatim corpus chunk text), restyled; no popover-open fetch | Snippet IS verbatim book text; avoids network dependency + long-section slicing (D-3) | auto (AD-130) |
| Cross-chapter citation jump | Same-chapter → scroll; else navigate with `anchor` + panel params preserved | Server resolves aliases on navigation (D-4) | auto (AD-130) |
| Explain/Ask selection scoping | Quote embedded in the submitted question text | Hybrid lexical search matches exact quotes; no API change (D-6) | auto (AD-131) |
| Create card "thin" | Visible but disabled with "coming soon" hint | Ships the five-verb contract without fake behavior (D-5) | auto (AD-131) |
| Save-to-note mechanism | `POST /sources/{id}/highlights` capture with first citation's anchor + first-paragraph quote; plain-note fallback on bind failure | Atomic note+anchor with zero backend change; honest degradation (D-7) | auto (AD-132) |
| Teach entry point | Panel mode switch (not a selection verb) | RFC's five verbs exclude Teach (D-8) | auto |
| Suggested prompts | Fixed static list in ask empty state | RFC asks only for suggestions; no personalization machinery | auto |
| Sidebar links this cycle | Ask/Teach entries deep-link into reader panel modes | Nav collapse is Cycle E; links must not 404 meanwhile | auto |

**Open questions:** none — all resolved or logged above.

---

## User Stories

### P1: Ask & Teach as reader panel modes ⭐ MVP

**User Story**: As a reader, I want Ask and Teach beside the book so that I never leave the page to use them.

**Acceptance Criteria**:

1. **RA-01** WHEN `/sources/[id]/read?panel=ask` loads THEN the reader SHALL render the chapter with a side panel open in Ask mode.
2. **RA-02** WHEN `?panel=teach` is present THEN the panel SHALL open in Teach mode.
3. **RA-03** WHEN the user closes the panel or switches modes THEN the URL SHALL update via shallow `router.replace` (no chapter refetch) and closing SHALL restore full reading width.
4. **RA-04** WHEN `/sources/[id]/ask` or `/sources/[id]/teach` is visited THEN the server SHALL redirect to `/sources/[id]/read?panel=ask` (resp. `teach`).
5. **RA-05** WHEN the app renders navigation THEN sidebar Ask/Teach entries SHALL link to the reader panel deep links, and the standalone AskScreen/TeachScreen components SHALL no longer exist.
6. **RA-06** WHEN the panel is open THEN reading SHALL remain non-modal: chapter scroll, position saving, and highlight painting keep working.

**Independent Test**: Open a ready book at `?panel=ask`, see chapter + panel; visit old `/ask` URL, land in the reader.

### P1: Ask mode parity + streaming polish ⭐ MVP

**User Story**: As a reader, I want to ask questions from the panel with the same streaming, citations, and error behavior as before.

**Acceptance Criteria**:

1. **RA-07** WHEN a question is submitted in Ask mode THEN the panel SHALL stream via the existing question transport and render citations and not-found terminal states exactly as the old screen did (parity: same transports, same `assistantView` semantics, same error messages).
2. **RA-08** WHEN Ask mode is empty (no messages) THEN the panel SHALL show suggested prompts, and clicking one SHALL submit it as a question.
3. **RA-09** WHEN an assistant response is streaming THEN a caret indicator SHALL be visible at the end of the streaming text and SHALL disappear when the message completes.

**Independent Test**: Submit a question in the panel against a fake SSE fixture; observe deltas, caret, citations.

### P1: Teach mode parity ⭐ MVP

**User Story**: As a reader, I want teaching sessions in the panel with the taught passage visible in the book.

**Acceptance Criteria**:

1. **RA-10** WHEN Teach mode opens THEN the panel SHALL support target selection, session start, resume of prior sessions, and streamed turns (parity with the old TeachScreen behavior).
2. **RA-11** WHEN a teaching session starts or resumes with a target anchor THEN the reader SHALL scroll to that anchor once (taught passage visible) while the panel stays open.

**Independent Test**: Start a session in the panel; the article scrolls to the target section; turns stream.

### P1: Citations as passages ⭐ MVP

**User Story**: As a reader, I want citations to show the actual passage and open the book at it, without losing the answer.

**Acceptance Criteria**:

1. **RA-12** WHEN a citation is opened THEN it SHALL render the verbatim passage text in the reading serif (`.prose-reading`) with a section-path locator, and SHALL NOT render chunk ids or scores.
2. **RA-13** WHEN "Show in book" is activated and the anchor belongs to the loaded chapter THEN the reader SHALL scroll to the anchor with the transient flash treatment and the panel SHALL remain open with the answer.
3. **RA-14** WHEN the anchor is not in the loaded chapter THEN the reader SHALL navigate to `?anchor=<anchor>` with panel params preserved and the chapter SHALL load scrolled to the anchor.

**Independent Test**: Click a citation for a different chapter while the panel streams an answer; book switches chapter, panel intact.

### P1: Selection popover with five verbs ⭐ MVP

**User Story**: As a reader, I want selecting text to offer Highlight, Note, Explain, Ask, and Create card, all tied to where I am.

**Acceptance Criteria**:

1. **RA-15** WHEN text is selected inside a chapter section THEN the popover SHALL offer exactly five verbs: Highlight, Note, Explain, Ask, Create card.
2. **RA-16** WHEN Highlight or Note is used THEN the existing capture flow SHALL run unchanged (anchor + quote + context resolution, 409 stale handling, painted highlight on success).
3. **RA-17** WHEN Explain is tapped THEN the panel SHALL open in Ask mode and immediately submit a fixed prompt containing the verbatim selection quote — one tap, no typing.
4. **RA-18** WHEN Ask (verb) is tapped THEN the panel SHALL open in Ask mode with the selection attached as quoted context, and the user's typed question SHALL be submitted together with that context.
5. **RA-19** WHEN Create card is shown THEN it SHALL be disabled with a "coming soon"-style hint and SHALL trigger no action.

**Independent Test**: Select a sentence, tap Explain; panel opens and streams an answer about that sentence.

### P2: Save answer to anchored note

**User Story**: As a reader, I want to keep a good answer as a note anchored to the passage it cites.

**Acceptance Criteria**:

1. **RA-20** WHEN "Save to note" is activated on a completed assistant answer that has ≥1 citation THEN the client SHALL call the highlight-capture endpoint with the first citation's anchor and a quote derived from that citation's snippet (first paragraph), with the answer text as the note body, and SHALL confirm success in the UI.
2. **RA-21** WHEN capture binding fails (409 stale) THEN the client SHALL fall back to creating a plain note whose body contains the answer and a jump-back link to the anchor, and the action SHALL still succeed.
3. **RA-22** WHEN the answer has no citations or ended not-found THEN the save action SHALL NOT be offered.

**Independent Test**: Save a cited answer; a note exists with an anchor (or fallback link) and the answer body.

---

## Edge Cases

- WHEN the session is unauthenticated THEN any panel action SHALL route through the existing `onRequireAuth` behavior (401 → login), matching the old screens.
- WHEN a stream errors (network / 4xx / 5xx) THEN the panel SHALL show the existing `errorMessageFor` messages (parity).
- WHEN the selection is empty, collapses, or is formatting-only THEN the popover SHALL NOT offer capture-dependent verbs beyond what the existing capture rules allow (existing `deriveCaptureSelection` null ⇒ popover hidden, as today).
- WHEN `?panel=` has an unknown value THEN the reader SHALL render with the panel closed.
- WHEN a citation snippet yields no non-empty first paragraph THEN save-to-note SHALL use the plain-note fallback directly.
- WHEN the source has no ready corpus (chapter 404) THEN the read route behaves as today; panel params are ignored on the not-found state.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
|---|---|---|---|
| RA-01..RA-06 | P1 Panel modes | A | Pending |
| RA-07..RA-09 | P1 Ask parity | B | Pending |
| RA-10..RA-11 | P1 Teach parity | B | Pending |
| RA-12..RA-14 | P1 Citations as passages | C | Pending |
| RA-15..RA-19 | P1 Selection verbs | C | Pending |
| RA-20..RA-22 | P2 Save to note | D | Pending |

**Coverage:** 22 total, mapped to phases A–D.

## Implicit-Requirement Dimensions Sweep

| Dimension | Resolution |
|---|---|
| Input validation & bounds | Question/quote lengths ride existing backend validation (422 paths unchanged); N/A beyond parity |
| Failure / partial-failure | Stream errors per `errorMessageFor` parity; save-to-note 409 fallback (RA-21) |
| Idempotency / retry | N/A — no new mutating endpoints; capture/create are existing single-shot actions |
| Auth boundaries & rate limits | Existing CSRF headers + `rate_limit_notes`/questions limits untouched; 401 → `onRequireAuth` |
| Concurrency / ordering | N/A — single-user UI; streaming ordering owned by existing transports |
| Data lifecycle / expiry | N/A — no new persisted state; notes lifecycle per ADR-0026 unchanged |
| Observability | N/A — frontend-only; no logging surface change |
| External-dependency failure | Provider failures surface through existing stream error frames (parity) |
| State-transition integrity | Panel mode transitions are pure URL state; unknown value ⇒ closed (edge case) |

## Success Criteria

- [ ] No standalone Ask/Teach pages remain; their URLs redirect into the reader.
- [ ] A full study action (read → select → Explain → citation jump → save note) completes without leaving the reader.
- [ ] Frontend suite green (incl. migrated parity tests), tsc clean, build passes; backend suite untouched and green.
