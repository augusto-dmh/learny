# Spoiler-Safe Retrieval Specification

**Cycle**: `v5-spoiler-safe-retrieval` (RFC-005 Cycle F) · **Un-paused**: AD-346
**RFC**: `docs/rfc/0005-evidence-gated-hardening-roadmap.md` §Cycle F

## Problem Statement

A reader halfway through a book can ask a question and receive a cited answer that quotes the
book's ending — Ask, Teach, and the citation-retrieval endpoint all retrieve over the whole
source with no awareness of `reading_position`. Verified net-new in RFC-005: nothing filters by
reading position today (zero retrieval call sites consult it). Spoiler safety is the one
reader-touching capability RFC-005 grafts onto the hardening roadmap, and it is
competitively distinctive for an unfinished-book reader.

## Goals

- [x] Q&A, teaching, and citation retrieval never surface book content past the reader's saved
      position (section-entry granularity — the position model's native resolution).
- [x] Implemented as a filter inside the shipped hybrid RRF query — no new retrieval component
      (ADR-0006), no re-ranking path (RFC-005 assumption).
- [x] Every existing caller and eval path is behavior-identical when the filter is not engaged.

## Out of Scope

| Feature | Reason |
| --- | --- |
| Quiz generation / card-suggestion section reads | They read whole sections via `QuizItemRepository.sections_for_generation`, not hybrid retrieval; RFC-005 Cycle F scopes the filter to retrieval. Deferred. |
| Finer-than-section filtering (in-section word offsets) | The shipped position model stores section-entry percent only (AD-189 / RFC-0006); inventing in-section offsets is a position-model change, not a retrieval filter. |
| Frontend changes | Citations flow through existing views; they simply never include future content. No FE surface changes. |
| Re-ranking / recall compensation | RFC-005 assumption: the filter is over shipped RRF. If recall degrades enough to need re-ranking, that reopens an ADR amendment — not this cycle. |
| Eval harness changes | The eval runner wires the real retrieval service and adapter, but never enables the position flag, so its behavior is unchanged — the out-of-scope point (no eval behavior change) still holds. |
| Deploy/rollout | Merging to `main` auto-deploys (GHCR→VPS); the rollout decision is presented at the ship-cycle merge gate per AD-346. |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| Filter granularity | Section-order comparison: a chunk is admissible iff its section's document-order index ≤ the bound anchor's section index | Exact, arithmetic-free; the stored percent is measured at section entry (`percent_at`), so section-entry IS the recorded resolution — anything finer would invent data | y (AD-347) |
| Application scope | Uniform on all three book-retrieval sites (ask turns, teach turns, `POST /api/sources/{id}/retrieve`) whenever a saved position exists; book arms only | RFC names ask+teach+citations literally; any bypass surface becomes a spoiler path | y (AD-348) |
| No saved position | Filter inactive (unfiltered) | A reader with no position has an unread book; filter-everything would brick first-session canned Ask and sample-book ask (shipped activation surfaces, RFC-0007 Bet 5) | y (AD-349) |
| Bound anchor matches no section (re-ingestion drift) | Fail-closed: zero book evidence + warning log; never fall back to unfiltered | "Never surface past" is the promise; an unmatched anchor means the bound is unknown and the safe direction is withholding | y (AD-349) |
| Teach scoped to an ahead-of-position chapter | Yields the existing zero-evidence turn outcome — accepted cost; no bypass | Design phase verifies what tutor-opens scopes to and reports the honest-turn envelope behavior | y (AD-348) |
| Teach-opening turn (query = target title) | Same bound as any other turn | Opening a teach session is not a spoiler exemption | y (AD-348) |

**Open questions:** none — all resolved or logged above (ship-cycle auto-decision rule; user was
not available; auditable in context.md + STATE.md AD-347..AD-349).

---

## User Stories

### P1: Ask is spoiler-safe ⭐ MVP

**User Story**: As a reader partway through a book, I want Ask to cite only what I've reached so
that a question about the material never reveals how the book ends.

**Why P1**: The core RFC-005 Cycle F promise; Ask is the highest-traffic retrieval surface.

**Acceptance Criteria**:

1. WHEN a conversation turn (ask or teach mode) retrieves evidence for a source where the
   calling user has a saved reading position THEN the system SHALL restrict book-arm evidence to
   chunks in sections at or before the position anchor's section, enforced inside the single
   retrieval statement (scoped CTE), not by post-filtering fetched rows. (SPOILER-01)
2. WHEN a chunk's section is the bound anchor's section or any earlier section in document order
   THEN it SHALL remain admissible; WHEN the chunk's section is any later section THEN it SHALL
   be inadmissible. (SPOILER-02)
3. WHEN the source is a PDF THEN the same section-order bound SHALL apply (`page_span` plays no
   part in the predicate). (SPOILER-03)
4. WHEN the filter is engaged THEN admissible evidence rows SHALL carry unchanged scores and
   ordering semantics (the bound shrinks the candidate pool; it never perturbs RRF scoring).
   (SPOILER-04)
5. WHEN the calling user has no saved reading position for that source THEN retrieval SHALL run
   exactly as today (no bound, identical statement behavior). (SPOILER-05)
6. WHEN the bound applies THEN it SHALL be derived only from the calling user's own position row
   for that source (per `(user_id, source_id)`); no cross-user position is ever read. (SPOILER-06)

**Independent Test**: Seed a corpus of ≥3 sections; save a position anchored in section 2; ask a
query whose best lexical+semantic matches live in section 3; assert zero section-3 evidence and
that the identical query without a position returns it.

### P1: Teach is spoiler-safe ⭐ MVP

**User Story**: As a reader in a teaching session, I want tutor retrieval to respect my position
so that Socratic tutoring cannot pull passages from unread chapters.

**Why P1**: RFC names teaching explicitly; teach shares the turn retrieval path.

**Acceptance Criteria**:

1. WHEN a teach turn has conversation scope anchors AND a position bound applies THEN evidence
   SHALL satisfy both predicates (logical AND). (SPOILER-07)
2. WHEN the intersection of scope anchors and the position bound is empty THEN the turn SHALL
   take the existing zero-evidence outcome (honest grounded turn) — the system SHALL NOT bypass
   the bound or fall back to unfiltered retrieval. (SPOILER-08)
3. WHEN the teach-opening turn retrieves with `query = target title` THEN the same bound SHALL
   apply as for any other turn. (SPOILER-09)

**Independent Test**: Scoped teach conversation anchored in a later section than the position →
turn completes via the existing zero-evidence path; scoped to a section at-or-before the position
→ evidence flows normally.

### P1: Citation retrieval is spoiler-safe ⭐ MVP

**User Story**: As a reader opening the citations panel, I want passage retrieval to respect my
position so that citations-as-passages cannot surface unread text.

**Why P1**: The reader-facing retrieval endpoint is a first-class RFC-named surface.

**Acceptance Criteria**:

1. WHEN `POST /api/sources/{source_id}/retrieve` runs for a user with a saved position on that
   source THEN the same section-order bound SHALL apply with the same semantics as SPOILER-01.
   (SPOILER-10)

**Independent Test**: Endpoint call with a position saved mid-book → no later-section passages in
the response.

### P1: Notes and no-position behavior unchanged ⭐ MVP

**User Story**: As a user, I want my own notes searchable regardless of position and my unread
books fully askable so that the filter only ever withholds unread book text.

**Why P1**: The filter must be tight enough to never leak and narrow enough to never over-reach.

**Acceptance Criteria**:

1. WHEN `include_notes` is true THEN note-arm results SHALL NOT be restricted by the position
   bound (the user's own notes are not book spoilers). (SPOILER-11)
2. WHEN `not_past_anchor` is absent or `None` THEN `RetrievalPort.search` SHALL behave
   byte-identically to the pre-cycle implementation (statement selection, `anchors` scope filter,
   notes arms, settings-sourced knobs all unchanged). (SPOILER-12)
3. WHEN `respect_reading_position` is false (default) THEN the retrieval service SHALL NOT read
   the position repository at all. (SPOILER-13)

**Independent Test**: Notes-included search with a mid-book position returns notes matching the
query from any section; `None`-bound retrieval matches pre-cycle fixtures.

### P2: Stale bound degrades closed

**User Story**: As an operator, I want a corrupted or drifted position anchor to fail safe so
that a broken bound can never silently become "no bound".

**Why P2**: Rare (anchors are canonical and stable across re-ingestion), but the failure mode is
the exact leak this cycle exists to kill.

**Acceptance Criteria**:

1. WHEN the bound anchor matches no section of the source THEN book-arm evidence SHALL be empty
   AND a warning SHALL be logged identifying the source and the unmatched anchor. (SPOILER-14)
2. WHEN that warning condition fires THEN note arms SHALL remain unaffected. (SPOILER-15)

**Independent Test**: Save a position with an anchor absent from the corpus; retrieve → zero book
evidence, warning logged, notes unaffected.

---

## Edge Cases

- WHEN the position anchor is the book's first section THEN only first-section chunks are
  admissible.
- WHEN the position anchor is the book's last section THEN the whole book is admissible.
- WHEN the book has a single section THEN all chunks are admissible (bound present).
- WHEN the source has no sections/chunks THEN behavior is as today (no evidence either way).
- WHEN percent reads `0.00` (book start or prose-free book) THEN the anchor — not the percent —
  defines the bound.
- WHEN a position exists for source A and retrieval targets source B THEN B's retrieval is
  unaffected (the bound is per `(user_id, source_id)`).

---

## Implicit-Requirement Dimensions Sweep

| Dimension | Resolution |
| --- | --- |
| Input validation & bounds | Bound originates from stored canonical anchor (SaveReadingPosition canonicalizes); unmatched anchor → SPOILER-14. `top_k` bounds unchanged. |
| Failure / partial-failure states | Position-repository read failure propagates through the existing turn/endpoint error envelope — it MUST NOT degrade to unfiltered retrieval (fail-closed parity with SPOILER-14). |
| Idempotency / retry / duplicate handling | N/A — read-only filter; no writes introduced. |
| Auth boundaries & rate limits | N/A — no new endpoints; existing `readable_source` ownership check unchanged; bound is per-user (SPOILER-01.6). |
| Concurrency / ordering | Position is last-write-wins (existing); a turn reads the position once at retrieval time; a concurrent save affects only later turns. |
| Data lifecycle / expiry | N/A — positions already lifecycle-managed by the reader flow. |
| Observability | Warning log on stale bound (SPOILER-14); no other new signals. |
| External-dependency failure | N/A — no new external dependencies. |
| State-transition integrity | N/A — no new state transitions; the filter reads existing state. |

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| --- | --- | --- | --- |
| SPOILER-01..06 | P1: Ask is spoiler-safe | Design | Verified |
| SPOILER-07..09 | P1: Teach is spoiler-safe | Design | Verified |
| SPOILER-10 | P1: Citation retrieval is spoiler-safe | Design | Verified |
| SPOILER-11..13 | P1: Notes and no-position behavior | Design | Verified |
| SPOILER-14..15 | P2: Stale bound degrades closed | Design | Verified |

**Coverage:** 15 ACs across 5 requirement groups — all mapped to tasks in `tasks.md`; 0 unmapped.

---

## Success Criteria

- [x] On a book with a mid-book saved position, ask, teach, and `/retrieve` return zero chunks
      from later sections, with notes and no-position behavior unchanged.
- [x] All pre-cycle callers are behavior-identical when the filter is not engaged (port default).
- [x] Boundary gates green: `make lint` + full backend suite (db-gated tests included) +
      frontend suite; CI 4/4 on the PR.
