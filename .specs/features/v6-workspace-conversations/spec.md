# Workspace: the conversation surface — Specification

RFC-006 Cycle D, first half (see `context.md` D-1 for the split decision).

## Problem Statement

Cycle C built the unified conversation model and `/api/conversations`, but nothing
uses it: the Ask and Teach panels still talk to the frozen legacy endpoints, so the
product still behaves as if Q&A evaporates and teaching sessions are unmanageable.
Meanwhile the compatibility layer — two web modules, two application adapter modules,
a status-collapsing presenter, a legacy repository method, and three retired settings
knobs — is dead weight that forces every conversation change to be made twice and
keeps two generation ports alive that describe one capability.

## Goals

- [ ] The reader's Ask and Teach panels run entirely on `/api/conversations`; a Q&A
      thread survives a page reload.
- [ ] A reader can find, resume, rename, and delete this book's conversations from
      the dock — the management surface finding 7 says is missing.
- [ ] The legacy compatibility surface is deleted outright, with no behavior lost
      that a test still needs to protect.
- [ ] One `GenerationPort` replaces the answer/teaching pair, and the turn service
      stops branching on mode to pick a port.

## Out of Scope

| Feature | Reason |
| --- | --- |
| Dock **Notes** and **Review** tabs; `/notes` per-book filter; notes provenance (title-only creation retirement) | The second half of Cycle D — `v6-workspace-notes`. Independent axis; no shared seam beyond `reader-panel.tsx` (D-1) |
| Thinking/streaming visible states, inline numbered citations, app-wide loading pattern | RFC-006 Cycle E. The book-workspace artifact shows them; they are explicitly E's scope |
| Contents rail, `/ask` + `/teach` redirects, per-source due-cards filter | Already shipped (`TocPanel`; route tombstones RA-04; `GET /api/reviews/due?source_id=`) |
| Page-range conversation scoping; PDF true-page preference | Deferred by ADR-0029 |
| Any provider SDK, retrieval-ranking, eval-stack, or worker change | RFC-006 exclusions; ADR-0019/0020/0009 hold |
| Migration / schema change | 0017 already carries every column this cycle needs; no DDL is required |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| Splitting Cycle D | Split at the pre-identified seam; this cycle is the conversation axis | RFC-006 §Cycle D pre-authorizes the split at spec time; three deliverables already shipped, so the residue is two clean halves (D-1) | y — RFC-authorized |
| No external consumer of the legacy routes | Delete outright, no deprecation window | RFC-006 Assumption 5: the author is the only user; nothing is owed beyond redirects for retired *frontend* routes, and those already exist | y — RFC-recorded |
| Mode discriminator on the converged port | Mode is passed explicitly; target-presence is **not** the discriminator | A whole-book *ask* conversation may still carry a target-trio snapshot (AD-194 sets it from the scope head), so target-presence cannot mean "teach". Design must pin this (D-3) | n — design decision |
| `not_found_in_scope` becomes wire-visible | Frontend renders it as a distinct, scope-aware message | The collapse presenter (AD-196) exists only for the frozen wire; deleting it is the point of retirement. The status vocabulary was always domain truth | y — ADR-0029 |
| Pagination shape | `limit`/`offset` with bounded `limit` | Matches the shipped `GET /api/reviews/due` convention (`limit: int = 20, ge=1, le=100`); the `(updated_at DESC, id DESC)` index already makes the order total, so offset paging is stable (D-4) | y — convention |
| Ask conversations appear in the dock list | Yes — the list is per-book and mode-agnostic | Persisting Q&A is worthless if it is unreachable; `list_for_user(source_id=...)` already returns both modes. The old `target_anchor IS NOT NULL` filter existed only to keep ask threads out of the *legacy* teach panel and dies with it | y — ADR-0029 |
| Retired-knob machinery | Delete the three knobs **and** `_RETIRED_KNOBS` + `_warn_about_retired_knobs` if it is left with nothing to warn about | The warning loop's only purpose was easing this exact removal; leaving dead scaffolding is the thing this cycle exists to stop | n — design detail |

**Open questions:** none — all resolved or logged above.

### Implicit-requirement dimensions sweep (Large ⇒ every dimension)

| Dimension | Resolution |
| --- | --- |
| Input validation & bounds | Rename title bounds; pagination `limit`/`offset` bounds; message max chars (existing `conversation_message_max_chars`) — WSC-11, WSC-12 |
| Failure / partial-failure | Persist-only-after-grounding stream parity must survive the re-point; a failed stream leaves no orphan conversation — WSC-13 |
| Idempotency / retry / duplicate | Turn-index race → 409 preserved through port convergence — WSC-14 |
| Auth boundaries & rate limits | Every surviving mutating route keeps a limiter; deleting the legacy limiters must not leave any route unthrottled — WSC-15 |
| Concurrency / ordering | List order `(updated_at DESC, id DESC)` is total, so pagination cannot drop or duplicate a row — WSC-12 |
| Data lifecycle / expiry | Deleting a conversation removes its turns and citations; deleting the last conversation is not an error — WSC-06 |
| Observability | Cycle A timings are keyed by route template; retiring routes retires their series. N/A as a *requirement* — no instrumentation code changes, the series simply stop |
| External-dependency failure | Anthropic adapter failure/timeout behavior must be preserved verbatim across port convergence — WSC-10 |
| State-transition integrity | Teach-target staleness → 409 and unresolvable-scope → 422 preserved (AD-201) — WSC-14 |

---

## User Stories

### P1: Ask and Teach run on the unified API ⭐ MVP

**User Story**: As a reader, I want my questions and teaching turns to go through one
conversation surface so that a thread I start survives a reload instead of evaporating.

**Why P1**: This is the entire payoff of Cycle C. Until the panels move, the unified
model is unreachable product-side and the legacy surface cannot be deleted.

**Acceptance Criteria**:

1. WHEN the Ask panel submits a question in a book with no active thread THEN the system SHALL create a conversation via `POST /api/conversations` and post the question as its first turn.
2. WHEN the Ask panel submits a follow-up in an active thread THEN the system SHALL post it to that same conversation, and the answer SHALL be generated with the thread's prior turns as history.
3. WHEN a reader reloads the reader with an active Ask thread THEN the system SHALL restore that thread's turns from the server, not from client state.
4. WHEN the Teach panel starts or resumes a session THEN the system SHALL use `/api/conversations` for start, read, turn, and turn-stream.
5. WHEN a streamed turn completes THEN the rendered answer, citations, and answer-status SHALL be the same as before the re-point for an identical grounded request.
6. WHEN a turn's retrieval finds nothing inside the conversation's scope THEN the panel SHALL render a scope-specific message distinct from the whole-book "not found in this book" message.

**Independent Test**: Ask a question, reload the page, see the thread; start a teach session and post a turn — both with the legacy routes absent.

---

### P1: Conversations are manageable from the dock ⭐ MVP

**User Story**: As a reader, I want to see, resume, rename, and delete this book's
conversations from the dock so that a thread I started is something I can return to.

**Why P1**: Finding 7 — sessions are persisted and resumable but have no management
surface. The endpoints shipped in Cycle C; without UI they stay invisible.

**Acceptance Criteria**:

1. WHEN the dock opens THEN the system SHALL list this book's conversations, newest activity first, showing each conversation's title and turn count.
2. WHEN a reader selects a listed conversation THEN the system SHALL load its turns and continue it in place.
3. WHEN a reader renames a conversation THEN the system SHALL persist the new title and show it in the list without a reload.
4. WHEN a reader deletes a conversation THEN the system SHALL remove it from the list, and its turns SHALL no longer be retrievable.
5. WHEN a book has no conversations THEN the system SHALL show an empty state rather than an error or a blank panel.
6. WHEN a conversation is created by asking a question THEN it SHALL appear in the same list as one created by teaching.

**Independent Test**: Create two conversations in one book, rename one, delete the other, reload — the list reflects both actions.

---

### P1: The legacy compatibility surface is deleted ⭐ MVP

**User Story**: As the maintainer, I want the compatibility layer gone so that a
conversation change is made once instead of twice.

**Why P1**: Carrying two wires is the cost ADR-0029 accepted only "until the panels
move". Once P1-1 lands, every day the layer survives is duplicated work.

**Acceptance Criteria**:

1. WHEN a request hits `POST/GET /api/teaching-sessions*`, `GET /api/sources/{id}/teaching-sessions`, or `POST /api/sources/{id}/questions[/stream]` THEN the system SHALL respond 404.
2. WHEN the codebase is searched after this cycle THEN the legacy web modules, the legacy application adapter modules, the status-collapse presenter, and `ConversationRepository.list_for_source_with_target` SHALL NOT exist.
3. WHEN the settings module is loaded THEN the three superseded knobs SHALL NOT exist as fields.
4. WHEN a deployment still sets one of those three environment variables THEN startup SHALL NOT fail.
5. WHEN the suite runs THEN no test SHALL exercise a legacy route, and every behavior those tests protected that still exists SHALL be asserted against the unified surface.

**Independent Test**: `grep` finds no legacy module; the app boots with the retired env vars set; the legacy paths 404.

---

### P1: One generation port ⭐ MVP

**User Story**: As the maintainer, I want a single `GenerationPort` so that the turn
service stops branching on mode purely to rename an argument.

**Why P1**: ADR-0029 names this as riding retirement; the union return type and the
unreachable teaching generator handed to the ask path are live defects today.

**Acceptance Criteria**:

1. WHEN the turn service generates a turn THEN it SHALL call one port, with no branch that selects a port by mode.
2. WHEN the converged port is called for a teach turn THEN the target section path SHALL be supplied, and for an answer turn it SHALL be absent — without either case being inferred from the target-trio snapshot.
3. WHEN the model identity is read for a turn THEN the value SHALL come from a single non-union type.
4. WHEN an identical grounded request is generated before and after convergence THEN the produced answer text and citations SHALL be byte-identical for the deterministic adapter.
5. WHEN `TeachingGenerationPort` is searched for after this cycle THEN it SHALL NOT exist.

**Independent Test**: The deterministic adapter's golden output is unchanged; the protocol is gone; the composition root wires one generator.

---

### P2: The conversation list is paginated

**User Story**: As a reader with a long history, I want the conversation list to load a
bounded page so that the dock stays fast as threads accumulate.

**Why P2**: Deferred into this cycle by Cycle C's triage because this cycle owns the
list's shape. Not MVP — correctness of the list matters more than its length today.

**Acceptance Criteria**:

1. WHEN `GET /api/conversations` is called without pagination parameters THEN the system SHALL return a bounded default page, not the full history.
2. WHEN `limit` and `offset` are supplied THEN the system SHALL return exactly that window of the `(updated_at DESC, id DESC)` order.
3. WHEN `limit` is outside its allowed bounds THEN the system SHALL reject the request with 422.
4. WHEN paging through a list whose rows have equal `updated_at` THEN no row SHALL be skipped or returned twice.

**Independent Test**: Seed more conversations than the default page; page through them and assert the union is the full set with no duplicates.

---

### P2: The notes-scope control says what it does

**User Story**: As a reader, I want the notes toggle to tell me it changes what gets
searched so that I understand why answers differ.

**Why P2**: Finding 12. Cosmetic relative to the re-point, but it is the copy change
RFC-006 assigns to this cycle and it rides the same component.

**Acceptance Criteria**:

1. WHEN the notes-scope control is rendered THEN its label SHALL read "Search my notes too".
2. WHEN a reader inspects the control THEN an explanatory description SHALL be available describing that it adds the reader's own notes to what the answer is grounded in.
3. WHEN a conversation is started THEN its notes choice SHALL be sent explicitly rather than relying on a per-surface implicit default.

**Independent Test**: Render the control and assert the label text and the description; assert the start request carries an explicit boolean.

---

## Edge Cases

- WHEN a rename submits an empty or whitespace-only title THEN the system SHALL reject it and leave the stored title unchanged.
- WHEN a rename submits a title longer than the stored column allows THEN the system SHALL reject it with 422 rather than truncating.
- WHEN a reader deletes the conversation that is currently open in the dock THEN the panel SHALL return to its empty state without leaving a stale thread rendered.
- WHEN a conversation is deleted while one of its turns is streaming THEN the stream SHALL terminate without persisting an orphan turn. **Covered by WSC-13** — sensed at the persistence seam (`test_a_turn_cannot_be_written_into_a_conversation_that_was_deleted`): a turn is written only after grounding, and by then the row it would attach to is gone, so the write is refused rather than swallowed. What is *not* sensed end-to-end is the shape of the response the reader's open stream then receives — driving a delete between two SSE frames needs a second connection the test fixtures deliberately do not have (one transaction is shared). Recorded rather than claimed.
- WHEN `offset` exceeds the number of conversations THEN the system SHALL return an empty page, not an error.
- WHEN a teach conversation's target section can no longer be resolved THEN posting a turn SHALL still fail with 409 after port convergence.
- WHEN a conversation belongs to another user THEN every conversation route SHALL fail identically to a non-existent conversation.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| --- | --- | --- | --- |
| WSC-01 | P1: Unified API | Execute | Verified |
| WSC-02 | P1: Unified API (persistence across reload) | Execute | Verified |
| WSC-03 | P1: Unified API (stream parity) | Execute | Verified |
| WSC-04 | P1: Unified API (scope-miss surfaced) | Execute | Verified |
| WSC-05 | P1: Dock management (list + resume) | Execute | Verified |
| WSC-06 | P1: Dock management (rename + delete + empty) | Execute | Verified |
| WSC-07 | P1: Legacy deletion (routes 404) | Execute | Verified |
| WSC-08 | P1: Legacy deletion (modules + knobs gone, boot survives) | Execute | Verified |
| WSC-09 | P1: Legacy deletion (coverage re-anchored, not lost) | Execute | Verified |
| WSC-10 | P1: One port (convergence + output parity) | Execute | Verified |
| WSC-11 | P2: Copy + explicit notes choice | Execute | Verified |
| WSC-12 | P2: Pagination | Execute | Verified |
| WSC-13 | Edge: partial-failure / no orphan turn | Execute | Verified |
| WSC-14 | Edge: 409/422 state-transition integrity preserved | Execute | Verified |
| WSC-15 | Edge: no surviving route loses its rate limiter | Execute | Verified |

**ID format:** `WSC-NN`

**Coverage:** 15 total, 15 mapped to tasks, 0 unmapped — all Verified (round 2 PASS).

---

## Success Criteria

- [ ] A question asked in the reader is still there after a reload.
- [ ] This book's conversations can be listed, resumed, renamed, and deleted from the dock.
- [ ] The legacy routes 404 and their modules are gone from the tree.
- [ ] `TeachingGenerationPort` no longer exists and the turn service has no port-selection branch.
- [ ] `make check` is green, with the legacy wire-freeze tests replaced — not merely deleted — by equivalent assertions on the unified surface.
