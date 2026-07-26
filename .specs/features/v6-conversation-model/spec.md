# Unified Grounded Conversations (`v6-conversation-model`) — Specification

RFC-006 Cycle C. Implements ADR-0029 backend-first: one conversation model
(scope × mode) replacing the Ask/Teach split, with the legacy panels kept
working against compatibility endpoints. No frontend changes this cycle.

## Problem Statement

Ask conversations evaporate on reload (nothing persisted); Teach sessions are
persisted but unmanageable (no global list, rename, or delete). Both are one
product idea — a grounded conversation about a book — split across two stacks.
Cycle D's workspace must be built against the unified model, so it lands now,
invisible to the UI.

## Goals

- [x] One `conversations` aggregate (scope × per-turn mode) owns all grounded
      conversations; Q&A turns persist from this release.
- [x] Unified management API: global list, start, read, rename, delete, turn,
      turn stream.
- [x] Scope enforcement in retrieval with `not_found_in_scope` distinguished
      from `not_found_in_source`.
- [x] Legacy Ask/Teach endpoints keep working bit-for-bit; frontend untouched
      and its full suite green without edits.

## Out of Scope

| Feature | Reason |
|---|---|
| Any frontend/UI change (dock, lists, redirects, copy) | RFC-006 Cycle D consumes this model; review here is data modeling alone |
| Page-range scoping; PDF true-page preference | Deferred in ADR-0029 until the page unit maps stably to sections |
| Scope editing after creation | No UI needs it yet; recorded in ADR-0029 |
| Retiring the legacy endpoints | Cycle D deletion, after panels re-point |
| Generation config (thinking, max_tokens, effort) | RFC-006 Cycle E |
| Provider SDK or prompt-content changes | ADR-0019/0020 hold; ports evolve, prompts do not |
| Retrieval-engine changes (ranking, arms, indexes) | RFC-005 ground; `anchors` support already exists |

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|
| ADR-0029 acceptance mechanics | Authored in-cycle, Status Accepted, user's merge-gate approval = acceptance | Content decisions pre-pinned by driver in merged RFC-006; precedent ADR-0020/0021/0023 | auto (AD-192) |
| Scope representation | `scope_anchors` JSONB, `[]` = whole book; never NULL | One spelling of "no scope"; matches JSONB precedent in the table | auto (AD-193) |
| Teach target derivation | `target_*` kept as nullable snapshot of the scope head, resolved at creation | Teach invariant + legacy views without per-read corpus joins | auto (AD-194) |
| Legacy ask persistence mapping | One whole-book conversation per question, `title` = truncated question | Each legacy ask is genuinely independent (no history sent); honest mapping | auto (AD-195) |
| Legacy teach list vs ask litter | Per-source legacy list filters `target_anchor IS NOT NULL` | Keeps ask-created conversations out of the old Teach panel until retirement | auto (AD-195) |
| Answer-mode history | `AnswerGenerationPort` gains `history` kwarg (default empty); Anthropic answer adapter assembles alternating history like teaching; deterministic ignores it | Cycle D ships chat on this model; a history-blind answer mode forgets follow-ups | auto (AD-197) |
| Settings | New `conversation_evidence_top_k=8`, `conversation_history_turns=6`, `conversation_message_max_chars=2000`; legacy `qa_evidence_top_k`/`teaching_evidence_top_k`/`teaching_history_turns` deprecated in place (fields kept, unread) | Env files keep validating; removal rides Cycle D retirement | auto (AD-198) |
| Rate limiting | One `rate_limit_conversations` on all unified mutating routes; legacy endpoints keep their limiters until retirement | ADR-0029 single-policy rule | auto (AD-199) |
| Migration mechanics | In-place renames + column adds + backfill; no copy tables | Preserves data, FKs, arbiter; zero-benefit copy avoided | auto (AD-200) |
| Error codes | Unresolvable scope anchor at start → 422; teach turn without a resolvable target → 409; turn-index race → 409 (existing behavior) | 422 = bad request content; 409 = valid request, wrong state | auto (AD-201) |

**Open questions:** none — all resolved or logged above.

## User Stories

### P1: One conversation model in the schema ⭐ MVP

**User Story**: As the product, I want teaching sessions generalized into
conversations so that every grounded exchange lives in one aggregate.

**Acceptance Criteria**:

1. WHEN migration `0017` runs against a database at `0016_reading_volume` THEN
   the three teaching tables SHALL be renamed to `conversations`,
   `conversation_turns`, `conversation_turn_citations` with `title` (TEXT NOT
   NULL), `scope_anchors` (JSONB NOT NULL), `include_notes` (BOOLEAN NOT
   NULL) added, `target_anchor`/`target_section_path`/`target_title` made
   nullable, and `mode` (TEXT NOT NULL) added to turns. (CONV-01)
2. WHEN the migration backfills existing rows THEN each pre-existing session
   SHALL have `scope_anchors == [target_anchor]`, `title == target_title`,
   `include_notes == false`, and each pre-existing turn SHALL have
   `mode == 'teach'`. (CONV-01)
3. WHEN the migration downgrades THEN the `0016` shape SHALL be restored, and
   the upgrade SHALL preserve `UNIQUE(conversation_id, turn_index)` and the
   FK-less citation snapshot. (CONV-01, I-CM-1, I-CM-2)
4. WHEN `metadata.py` is compared to the migrated database THEN table and
   column definitions SHALL match. (CONV-02)

**Independent Test**: `test_migrations.py` round-trips 0016→0017→0016 with
seeded teaching rows and asserts the backfill values.

### P1: Unified conversation services ⭐ MVP

**User Story**: As a student, I want to start, list, read, rename, and delete
conversations so that no conversation is ever unmanageable again.

**Acceptance Criteria**:

1. WHEN `StartConversation` is called with an owned source, a scope list, and
   an explicit notes choice THEN a conversation SHALL be created with the
   given scope, `include_notes` as given, `target_*` snapshotted from the
   scope head (alias-aware) when the scope is non-empty and NULL when empty,
   and `title` defaulting to the target title (scoped) or the source title
   (whole-book) when not given. (CONV-05)
2. WHEN any scope anchor fails to resolve to a live section (alias-aware)
   THEN start SHALL fail with the validation error mapped to 422 and create
   nothing. (CONV-05)
3. WHEN `ListConversations` is called THEN it SHALL return the caller's
   conversations across all sources, newest activity first (`updated_at`
   desc), each with `source_title` and `turn_count`, optionally filtered by
   `source_id`. (CONV-06)
4. WHEN `RenameConversation` is called with a 1–200-char trimmed title THEN
   the stored title SHALL change and `updated_at` SHALL bump; empty/oversize
   titles SHALL be rejected. (CONV-08)
5. WHEN `DeleteConversation` succeeds THEN the conversation, its turns, and
   citations SHALL be gone; a second delete SHALL report not-found. (CONV-09)
6. WHEN any service is called for a conversation the caller does not own THEN
   the outcome SHALL be indistinguishable from the conversation not existing.
   (CONV-07, I-CM-6)

### P1: Turns with scope × mode ⭐ MVP

**User Story**: As a student, I want to post answer- or teach-mode turns in a
scoped conversation so that replies stay grounded in exactly my selection.

**Acceptance Criteria**:

1. WHEN a turn is posted THEN the scope SHALL be expanded per turn via
   `expand_anchors` (subtrees + aliases) and retrieval SHALL be called with
   those anchors (`None` when scope is empty) and the conversation's stored
   `include_notes`. (CONV-10, CONV-11)
2. WHEN `mode == 'answer'` THEN generation SHALL go through
   `AnswerGenerationPort` with the conversation's recent history (limit
   `conversation_history_turns`); WHEN `mode == 'teach'` THEN through
   `TeachingGenerationPort` with the target section path and history, exactly
   as teaching does today. (CONV-10, CONV-14)
3. WHEN grounding fails (or retrieval is empty) in a conversation with
   non-empty scope THEN the persisted turn's `answer_status` SHALL be
   `not_found_in_scope`; with empty scope it SHALL remain
   `not_found_in_source`. A scoped turn SHALL never silently search the whole
   book. (CONV-11, I-CM-3)
4. WHEN `mode == 'teach'` and the conversation's scope is empty or its target
   no longer resolves THEN the turn SHALL be rejected as a state conflict
   (409) and nothing persisted. (CONV-12, I-CM-7)
5. WHEN a turn completes THEN it SHALL be persisted only after grounding with
   the next `turn_index`, citations snapshotted in rank order, and the
   conversation's `updated_at` bumped; a concurrent duplicate index SHALL
   surface as a conflict, never a gap or duplicate. (CONV-10, CONV-13,
   I-CM-2, I-CM-5)
6. WHEN the same inputs run through the streaming path THEN the persisted
   turn and terminal status SHALL equal the non-streaming result, and the
   frame sequence SHALL be `start`, `text-start`, deltas, `text-end`,
   `data-citations`, `data-answer-status`, `finish`, `[DONE]`. (CONV-21,
   I-CM-5)

### P1: Unified web surface ⭐ MVP

**User Story**: As the future workspace, I want one `/api/conversations`
resource so the dock has a single API to consume.

**Acceptance Criteria**:

1. WHEN the router is mounted THEN it SHALL expose: `POST
   /api/conversations` (201), `GET /api/conversations[?source_id=]` (200),
   `GET /api/conversations/{id}` (200, with turns incl. `mode` and
   citations), `PATCH /api/conversations/{id}` (200, rename), `DELETE
   /api/conversations/{id}` (204), `POST /api/conversations/{id}/turns`
   (201), `POST /api/conversations/{id}/turns/stream` (200 SSE). (CONV-15..21)
2. WHEN a unified start request omits `include_notes` THEN it SHALL be
   rejected 422 — the notes choice is explicit per conversation (ADR-0029).
   (CONV-15)
3. WHEN a mutating unified route is hit THEN origin + CSRF enforcement and
   the single `rate_limit_conversations` policy SHALL apply (429 +
   `Retry-After` past the window); unauthenticated calls SHALL get 401.
   (CONV-22)
4. WHEN a turn request carries an unknown `mode` or an over-limit message
   THEN it SHALL be rejected 422 using `conversation_message_max_chars`.
   (CONV-20)
5. WHEN generation fails mid-turn THEN the non-streaming path SHALL map to
   the established 502 answer-generation error and the streaming path SHALL
   emit the error frame then `[DONE]`, persisting nothing. (CONV-20, CONV-21)

### P1: Legacy compatibility ⭐ MVP

**User Story**: As the current Ask/Teach panels, I want the old endpoints
unchanged on the wire so this cycle ships invisibly.

**Acceptance Criteria**:

1. WHEN any of the five legacy teaching paths or two legacy questions paths
   is called THEN method, path, status code, response field set, and SSE
   frame sequence SHALL be unchanged from today, now backed by the unified
   model. (CONV-23, CONV-24, I-CM-4)
2. WHEN `POST /api/sources/{id}/questions[/stream]` is called THEN a
   whole-book conversation SHALL be created (title = question truncated to
   80 chars, `include_notes` = request value else true per AD-147) and the
   answer persisted as its `answer`-mode turn 0 — reloading loses nothing.
   (CONV-24)
3. WHEN a legacy teaching session is started THEN the created conversation
   SHALL have `scope_anchors == [target_anchor]`, `include_notes == false`
   (absent an explicit request value), and target snapshot as today; legacy
   turn requests carrying `include_notes` SHALL override the stored choice
   for that request only. (CONV-23)
4. WHEN a scoped legacy turn resolves to `not_found_in_scope` THEN the legacy
   presenters SHALL collapse it to `not_found_in_source` on the wire (JSON
   and SSE both). (CONV-23, CONV-24)
5. WHEN `GET /api/sources/{id}/teaching-sessions` is called THEN only
   conversations with a non-null teach target SHALL appear — ask-created
   conversations stay out of the old panel. (CONV-23)
6. WHEN the frontend test suite runs unmodified THEN it SHALL pass. (I-CM-4)

### P2: Deterministic-provider stability

**Acceptance Criteria**:

1. WHEN the golden citation and generation-invariant suites run under the
   local provider THEN they SHALL pass with answer output for a first
   (history-less) answer turn byte-identical to today's ask output. (CONV-26,
   I-CM-8)
2. WHEN the Anthropic answer adapter receives history THEN it SHALL emit
   alternating prior turns ahead of the current question with system prompt
   and citation mechanics unchanged (asserted against the recorded-request
   shape, offline). (CONV-14)

## Edge Cases

- WHEN a turn is posted to a deleted/unknown/unowned conversation THEN 404.
- WHEN the unified start names an unowned source THEN 404 (not 422).
- WHEN `scope_anchors` contains duplicates THEN expansion dedupes (existing
  `expand_anchors` semantics); stored scope keeps the given order.
- WHEN a corpus replace removes a scoped section THEN answer-mode turns
  proceed against surviving anchors (aliases expand); a teach turn whose
  target is gone gets 409.
- WHEN `include_notes` is true THEN note arms join retrieval un-scoped (notes
  are never anchor-filtered — existing engine semantics).
- WHEN rename/delete race a turn post THEN the arbiter and FK cascade decide;
  no partial states.

## Invariants

| ID | Invariant | Sensor required |
|---|---|---|
| I-CM-1 | Citation snapshots have no corpus FK and survive corpus replace | yes |
| I-CM-2 | `UNIQUE(conversation_id, turn_index)` arbiters concurrency: conflict, never gap/duplicate | yes |
| I-CM-3 | Scope is a promise: a scoped turn never returns evidence from outside its expanded scope and never silently widens | yes |
| I-CM-4 | Legacy wire compatibility: response field sets, statuses, SSE frames unchanged; frontend suite passes unedited | yes |
| I-CM-5 | Turns persist only after grounding; stream and non-stream persist identical turns | yes |
| I-CM-6 | Ownership failures indistinguishable from absence (404) | yes |
| I-CM-7 | Teach-mode turns require a resolvable target | yes |
| I-CM-8 | First-turn answer output under the local provider is byte-identical to the pre-cycle ask path | yes |

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
|---|---|---|---|
| CONV-01..02 | Schema | A | Verified |
| CONV-03..04 | Schema/repos | A | Verified |
| CONV-05..09, CONV-13 | Services (management) | B | Verified |
| CONV-10..12, CONV-14 | Services (turns) | B | Verified |
| CONV-15..22 | Unified web | C | Verified |
| CONV-23..25 | Legacy compat | D | Verified |
| CONV-26 | Goldens/stability | D | Verified |

## Success Criteria

- [x] Backend suite green (target: prior count + new coverage), ruff clean.
- [x] Frontend suite passes with zero edits.
- [x] A legacy ask question is visible in `GET /api/conversations` afterward.
- [x] ADR-0029 in the PR; RFC-006 action item flipped.
