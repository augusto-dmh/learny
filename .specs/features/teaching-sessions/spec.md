# Teaching Sessions Specification

Cycle 7 — TDD-001 Phase 8. Structured teaching sessions around a source target
(chapter or section), with bounded conversation context, cited teaching
responses, and session state reads.

## Problem Statement

Cited Q&A (Phase 7) answers one-off questions against a whole source, but a
learner working through a book needs to *stay* on a chapter or section, ask
follow-ups that remain scoped to that target, and come back to the
conversation later. Nothing today persists a conversation or scopes evidence
to a part of the book.

## Goals

- [ ] A user can start a teaching session anchored to a chapter/section of a ready source and exchange turns that stay scoped to that target.
- [ ] Every teaching response is grounded in retrieved evidence from the target subtree, with citations that survive re-ingestion.
- [ ] A user can reopen a session and see the full prior conversation.

## Out of Scope

| Feature | Reason |
| --- | --- |
| Passage/chunk-level targets | No chunk-selection UI primitive exists; chapter/section covers the MVP teaching flow (TDD allows follow-up). |
| Whole-source (no-target) sessions | Whole-source Q&A already exists (Phase 7); the point of a session is a bounded target. |
| Session lifecycle ops (close/archive/delete, expiry) | No consumer yet; add with a lifecycle decision when one exists. |
| Cloud LLM teaching prose | Blocked on the provider ADR (mirrors AD-024); deterministic local adapter ships the contract. |
| Long-context fallback path | TDD marks retrieval as the default; fallback needs the provider ADR first. |
| Cross-source or global session list UI | Only a per-source list is needed for the teach flow. |
| Explicit mid-session scope change | TDD mentions explicit scope change; deferred — start a new session instead. |

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| Target model | One corpus section (chapter = depth-0 section), by stable `anchor` | Sections carry stable `anchor` + `section_path`; passage targets deferred | auto (D-1) |
| Turn shape | One row = user message + generated response (not per-role rows) | Simplest relational model; matches request/response API shape | auto (D-4) |
| Session status column | Omitted this cycle | No lifecycle ops exist; adding a dead column violates YAGNI (AD-025 spirit) | auto (D-4) |
| not_found turns | Persisted like answered turns | They are part of the conversation history the user saw | auto (D-5) |
| 502 turns | Not persisted (rollback) | Safe retry; nothing was shown to the user | auto (D-5) |
| Sessions after re-ingest | Survive; citations are denormalized snapshots; new turns 409 if target anchor vanished | Corpus replace (AD-018) deletes chunk/section rows; history must not break | auto (D-4/D-5) |
| Session list endpoint | `GET /api/sources/{id}/teaching-sessions` (additive to TDD contract) | Without a list, sessions are unreachable after navigation | auto (D-6) |

**Open questions:** none — all resolved or logged above.

## User Stories

### P1: Start a teaching session ⭐ MVP

**User Story**: As a reader, I want to start a teaching session on a chapter or section of my book so that follow-up teaching stays focused there.

**Acceptance Criteria**:

1. WHEN the owner POSTs `/api/teaching-sessions` with `{source_id, target_anchor}` where the source is theirs, `ready`, and `target_anchor` matches a section of its corpus THEN the system SHALL create the session and return 201 with `{id, source_id, target: {anchor, section_path, title}, created_at}` (TEACH-01)
2. WHEN `source_id` is missing or owned by another user THEN the system SHALL return 404 without disclosing existence (TEACH-02)
3. WHEN the source exists but `status != ready` THEN the system SHALL return 409 (TEACH-03)
4. WHEN `target_anchor` does not match any section of the source's corpus THEN the system SHALL return 422 (TEACH-04)

**Independent Test**: Create user + ready source with corpus; POST with a real section anchor → 201; assert the three error paths.

### P1: Exchange cited teaching turns ⭐ MVP

**User Story**: As a reader, I want to send a message in my session and get a teaching response cited to exact passages of my target so that I can trust and follow up on it.

**Acceptance Criteria**:

1. WHEN the owner POSTs `/api/teaching-sessions/{id}/turns` with a valid `{message}` THEN the system SHALL persist and return 201 with the turn: `{turn_index, message, answer_status, text, citations, evidence_count, model, created_at}` where `answer_status ∈ {answered, not_found_in_source}` (TEACH-07)
2. WHEN `message` (trimmed) is empty or exceeds `LEARNY_TEACHING_MESSAGE_MAX_CHARS` THEN the system SHALL return 422 (TEACH-08)
3. WHEN a turn runs THEN retrieval SHALL be restricted to chunks whose section is the target or a descendant of the target, and no citation SHALL reference a chunk outside that subtree (TEACH-09)
4. WHEN the generation port cites chunk ids outside the retrieved evidence, returns `found=false`, or returns blank text THEN the system SHALL apply the grounding rules of AD-027 and produce `not_found_in_source` with `text == ""` and `citations == ()` (TEACH-10)
5. WHEN scoped retrieval returns no evidence THEN the system SHALL return `not_found_in_source` without invoking the generation port (TEACH-11)
6. WHEN a turn is generated THEN the port SHALL receive at most the last `LEARNY_TEACHING_HISTORY_TURNS` prior turns of the session as bounded context (TEACH-12)
7. WHEN the generation port raises THEN the system SHALL return 502 and persist no turn (TEACH-13)
8. WHEN a turn results in `not_found_in_source` THEN the turn SHALL still be persisted with empty text and no citations (TEACH-14)
9. WHEN the session's source is no longer `ready` THEN the system SHALL return 409 (TEACH-15)
10. WHEN the session's `target_anchor` no longer resolves in the current corpus (re-ingestion changed structure) THEN the system SHALL return 409 with a readable detail (TEACH-16)
11. WHEN two turns race on one session THEN at most one SHALL win a given `turn_index`; the loser SHALL return 409 (TEACH-17)
12. WHEN turn or session creation exceeds the rate limit THEN the system SHALL return 429 (TEACH-18)
13. WHEN a turn completes THEN the system SHALL log exactly one content-free line (outcome, session id, evidence count, model — never message/answer text) (TEACH-19)
14. WHEN a turn completes (either outcome) THEN the response SHALL carry the adapter's `model` identity (TEACH-24)

**Independent Test**: Seed session over a fixture corpus; post turns hitting answered / not-found / each error path; assert scoping by planting matching text outside the target subtree.

### P1: Read session state ⭐ MVP

**User Story**: As a reader, I want to reopen a session and see the whole conversation with its citations so that I can continue where I left off.

**Acceptance Criteria**:

1. WHEN the owner GETs `/api/teaching-sessions/{id}` THEN the system SHALL return 200 with the session (`id, source_id, target, created_at`) and all turns ordered by `turn_index` ascending, each with its citations (TEACH-05)
2. WHEN the session is missing or owned by another user THEN the system SHALL return 404 (TEACH-06)
3. WHEN the source was re-ingested after turns were recorded THEN previously stored turns SHALL still return their full citation snapshots (TEACH-20)

**Independent Test**: Create session + turns, GET → full ordered history; re-run ingestion, GET again → citations intact.

### P2: List a source's sessions

**User Story**: As a reader, I want to see my previous sessions for a book so that I can resume one.

**Acceptance Criteria**:

1. WHEN the owner GETs `/api/sources/{source_id}/teaching-sessions` THEN the system SHALL return 200 with that source's sessions, newest first, each with `{id, target, created_at, turn_count}` (TEACH-21)
2. WHEN the source is missing or non-owned THEN the system SHALL return 404 (TEACH-02 semantics)

**Independent Test**: Two sessions on one source, one on another user's source → list returns exactly the owner's two, newest first.

### P1: Teach in the browser ⭐ MVP (vertical slice, AD-010)

**User Story**: As a reader, I want a Teach screen for a ready book where I pick a chapter/section, start a session, and converse with cited responses.

**Acceptance Criteria**:

1. WHEN a source row is `ready` THEN the sources list SHALL link to a Teach screen for it (TEACH-22)
2. WHEN the Teach screen loads THEN it SHALL offer the book's sections (from the existing structure endpoint) as targets and list previous sessions for resume (TEACH-22)
3. WHEN the user starts a session and sends messages THEN the screen SHALL render the conversation: user messages, cited responses (citation section path + snippet), an explicit not-found state, and readable error states for 409/422/429/502 (TEACH-22)
4. WHEN the user opens an existing session THEN the prior conversation SHALL render from the GET endpoint (TEACH-22)

**Independent Test**: Component tests drive the flow against a mocked client: pick target → start → send → cited response renders; resume renders history; each error state renders.

## Edge Cases

- WHEN the target section has descendants THEN their chunks are in scope (chapter teaching covers its subsections) (TEACH-09)
- WHEN the corpus was re-ingested and the anchor survived THEN turns continue against the new corpus rows (anchors are the stable citation identity, AD-018)
- WHEN `history_turns` exceeds stored turns THEN all prior turns are passed (no error)
- WHEN a session create races a source status change THEN the readiness check is per-request; a stale-ready race resolves at the next turn's 409 (TEACH-15)
- WHEN the request body is malformed (missing fields, bad UUID) THEN 422 via standard validation

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| --- | --- | --- | --- |
| TEACH-01..04 | P1 Start session | Done | ✅ Verified |
| TEACH-05..06, 20 | P1 Read state | Done | ✅ Verified |
| TEACH-07..19, 24 | P1 Turns | Done | ✅ Verified |
| TEACH-21 | P2 List | Done | ✅ Verified |
| TEACH-22 | P1 Frontend | Done | ✅ Verified |
| TEACH-23 | All (auth+CSRF on every endpoint; POSTs origin-checked like existing routers) | Done | ✅ Verified |

**Coverage:** 24 total, 24 mapped to tasks, 0 unmapped. Verifier PASS (`validation.md`, 6/6 mutants killed).

## Success Criteria

- [ ] Full teach flow works in the browser against a fixture EPUB: pick chapter → session → cited, target-scoped responses → resume later.
- [ ] All gates green: backend pytest, ruff; frontend vitest, tsc.
- [ ] Verifier PASS with every TEACH AC evidenced.
