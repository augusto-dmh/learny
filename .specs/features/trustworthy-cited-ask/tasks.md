# trustworthy-cited-ask Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user - do not proceed without it.**

---

**Design**: `.specs/features/trustworthy-cited-ask/design.md`
**Status**: Approved

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec. Guidelines found: `CLAUDE.md` (verification vocabulary: `make infra`, `make test-backend`, `make test-frontend`, `make lint`, `make check`), `backend/tests/` pytest layout, `frontend/tests/*.test.tsx` vitest + Testing Library, architecture-boundaries in `make lint`.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Domain entities | unit | New constants/DTOs pinned; `failed` is a distinct wire string | `backend/tests/test_domain_conversations.py` | `cd backend && uv run pytest tests/test_domain_conversations.py tests/test_domain_entities.py` |
| Anthropic answering adapter | unit | Span mapping, offset identity, 4xx log redaction, citations request has no `output_config.format` | `backend/tests/test_answering_anthropic.py` | `cd backend && uv run pytest tests/test_answering_anthropic.py` |
| Quiz/judge adapter | unit | Structured-output request has no citations-enabled documents | `backend/tests/test_quiz_anthropic.py` | `cd backend && uv run pytest tests/test_quiz_anthropic.py tests/eval/test_judge.py` |
| Conversation application | unit | Failed persist on sync+stream; prior turns untouched; no delete | `backend/tests/test_application_conversations.py` | `cd backend && uv run pytest tests/test_application_conversations.py` |
| Conversation HTTP | integration | GET after failed stream still returns the conversation + failed turn | `backend/tests/test_web_conversations.py` | `cd backend && uv run pytest tests/test_web_conversations.py` |
| Migration / metadata | integration | 0018 upgrade/downgrade; nullable span columns | `backend/tests/test_migrations.py` (or sibling) | `cd backend && uv run pytest tests/test_migrations.py` |
| Frontend thread hook | unit (jsdom) | Stream error does not call `deleteConversation`; retry resends; error in thread | `frontend/tests/ask-panel.test.tsx` | `cd frontend && npm test -- ask-panel` |
| Frontend citations | unit (jsdom) | Hover shows `quoted_text`; Show in book uses span quote | `frontend/tests/` citation + highlight tests | `cd frontend && npm test -- citations highlight-paint cited-answer` |

## Gate Check Commands

> `uv` may be off PATH: `backend/.venv/bin/python -m pytest` / `backend/.venv/bin/ruff`. DB-gated tests need `make infra` and `LEARNY_TEST_DATABASE_URL`. Prefix `LEARNY_GENERATION_PROVIDER=local LEARNY_EMBEDDING_PROVIDER=local` if `backend/.env` leaks real providers (conftest pin exists; still honor it).

| Gate Level | When to Use | Command |
| ---------- | ----------- | ------- |
| Quick | After a backend unit task | `cd /home/augusto/projects/learny/backend && uv run pytest <touched test module>` |
| Full | After HTTP, migration, or frontend tasks | backend module + `cd /home/augusto/projects/learny/frontend && npm test -- <file>` |
| Build | Phase boundary | `cd /home/augusto/projects/learny && make lint` and the cycle's backend + frontend suites (`make test-backend`, `make test-frontend`) |

---

## Execution Plan

Phases run sequentially. Tasks inside a phase run in order. One Opus worker per phase (all four carry correctness invariants: persist, grounding, request shape). Verifier after T13, always Opus/Fable.

### Phase 1

```
T1 -> T2 -> T3 -> T4 -> T5
```

### Phase 2

```
T6 -> T7 -> T8
```

### Phase 3

```
T9 -> T10 -> T11
```

### Phase 4

```
T12 -> T13
```

---

## Task Breakdown

### Phase 1

### T1: Draft RFC-0007 public-launch roadmap ✅

**What**: Distill `docs/research/2026-09-03/synthesis.md` into a Draft RFC with seven bets as cycles; name this slug as Cycle A / Bet 1.
**Where**: `docs/rfc/0007-public-launch-roadmap.md`
**Depends on**: None
**Reuses**: RFC-005/006 Draft shape; synthesis must-be-true / out-of-scope tables
**Requirement**: ASK-11 (process: the arc this dump belongs to)

**Tools**:

- MCP: NONE
- Skill: `create-rfc` (project-local)

**Done when**:

- [x] RFC exists as Draft, sequenced 1 → {2,3,4,5,7} → 6
- [x] Bet 1 matches this spec's boundary (no Haiku routing, no autorater)

**Tests**: none (docs layer)
**Gate**: build

---

### T2: Domain `CitedSpan`, `FAILED`, and `GeneratedAnswer.spans`

**What**: Add Learny-owned `CitedSpan`, `FAILED = "failed"`, and optional `spans` on `GeneratedAnswer`; pin the four answer statuses.
**Where**: `backend/app/domain/entities.py`
**Depends on**: T1
**Reuses**: `GeneratedAnswer`, `ANSWERED` / not-found constants
**Requirement**: ASK-12, ASK-02

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `document_index` does not appear on the domain types
- [ ] Domain test asserts `failed` is distinct from the three existing statuses
- [ ] Deterministic default `spans=()` keeps existing constructors valid

**Tests**: unit
**Gate**: quick

---

### T3: Map Citations API spans inside the answering adapter

**What**: Resolve `document_index` to `chunk_id` as today, and map in-range `cited_text` / char offsets onto `CitedSpan` against the document body; drop out-of-range spans.
**Where**: `backend/app/infrastructure/answering/anthropic.py`
**Depends on**: T2
**Reuses**: `_CitationMarks`, `_parse_message`, `_build_documents`
**Requirement**: ASK-12, ASK-13, ASK-14

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Golden test: offsets are indices into the exact `source.data` string sent
- [ ] Out-of-range offsets drop the span but keep the chunk id
- [ ] Grounding discards spans whose chunk did not survive (sensor in application test or adapter+ground helper)

**Tests**: unit
**Gate**: quick

---

### T4: Pin the citations-enabled Anthropic request shape

**What**: Assert the answering `messages.create` / `stream` kwargs include citations-enabled documents and do not include `output_config.format`.
**Where**: `backend/tests/test_answering_anthropic.py`
**Depends on**: T3
**Reuses**: existing request-capture tests (`test_request_sends_one_citations_enabled_document_per_chunk_in_order`)
**Requirement**: ASK-07, ASK-09

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Buffered and stream paths are both pinned
- [ ] A mutant that adds `output_config.format` fails this test

**Tests**: unit
**Gate**: quick

---

### T5: Pin the structured-output Anthropic request shape

**What**: Assert quiz (and judge if in-scope of the same pin) requests send JSON schema and do not send citations-enabled documents.
**Where**: `backend/tests/test_quiz_anthropic.py`
**Depends on**: T4
**Reuses**: `test_begin_deck_submits_one_request_per_section_with_constrained_schema`
**Requirement**: ASK-08, ASK-09

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] The forbidden citations-document key is asserted absent
- [ ] Mixing the two shapes cannot pass both T4 and T5

**Tests**: unit
**Gate**: quick

---

### Phase 2

### T6: Log Anthropic 4xx with shape, status, and request_id

**What**: On answering-adapter HTTP 4xx, emit one redacted log line with request shape `citations`, status, and `request_id`; never document bodies or prompts.
**Where**: `backend/app/infrastructure/answering/anthropic.py`
**Depends on**: T5
**Reuses**: `_log_call`
**Requirement**: ASK-10

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Test captures the log line for a fake 4xx with `request_id`
- [ ] Test asserts snippet/prompt text is absent even when the exception body contains it
- [ ] Missing `request_id` still logs status + shape

**Tests**: unit
**Gate**: quick

---

### T7: Persist a `failed` turn when generation fails

**What**: On `AnswerGenerationFailed` after a user message is known, persist the turn (`failed`, empty answer, no citations) then still surface the 502 / stream error. Prior turns stay untouched.
**Where**: `backend/app/application/conversations.py`
**Depends on**: T6
**Reuses**: `PostConversationTurn._persist`
**Requirement**: ASK-01, ASK-02, ASK-05

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Application tests cover sync and stream failure
- [ ] GET after failure returns the conversation and the user message
- [ ] Existing "502 persists nothing" assertions are updated to the new contract, not deleted to go green

**Tests**: unit
**Gate**: full

---

### T8: Store optional citation spans on turn snapshots

**What**: Additive nullable `quoted_text`, `start_char`, `end_char` on `conversation_turn_citations`; serialize only when set.
**Where**: `backend/app/infrastructure/db/metadata.py`
**Depends on**: T7
**Reuses**: AD-033 snapshot table; EvidenceView wrap-serializer pattern
**Requirement**: ASK-12, ASK-17

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Migration `0018` upgrades and downgrades
- [ ] Wire JSON omits the three keys when null (book payload size unchanged)
- [ ] Failed turns still write zero citation rows

**Tests**: integration
**Gate**: full

---

### Phase 3

### T9: Stop deleting the conversation on first-turn stream failure

**What**: Remove provisional `deleteConversation` on abort, disconnect, and error. Keep the conversation id. Add a test that fails if delete is called on stream error.
**Where**: `frontend/app/components/use-conversation-thread.ts`
**Depends on**: T8
**Reuses**: `onFinish` / `onError` in the same hook
**Requirement**: ASK-01, ASK-04, ASK-06

**Tools**:

- MCP: NONE
- Skill: `vercel-react-best-practices`

**Done when**:

- [ ] `deleteConversation` is not invoked from this hook on error/abort/disconnect
- [ ] ASK-06 sensor exists and would fail if the DELETE is restored
- [ ] Teach panel shares the hook, so both surfaces keep the thread

**Tests**: unit
**Gate**: full

---

### T10: Error state in the thread with retry

**What**: After a failed send, the thread shows the readable error on that turn and a Retry control that calls `send` with the same user text.
**Where**: `frontend/app/components/ask-panel.tsx`
**Depends on**: T9
**Reuses**: `errorMessageFor`, existing `role="alert"` copy
**Requirement**: ASK-03

**Tools**:

- MCP: NONE
- Skill: `vercel-composition-patterns`

**Done when**:

- [ ] Retry is disabled while `isStreaming`
- [ ] Retry does not create a second conversation
- [ ] Teach panel shows the same failure/retry (shared hook or shared piece)

**Tests**: unit
**Gate**: full

---

### T11: Restore failed turns into the thread

**What**: GET/history mapping includes `answer_status=failed` turns as a user message plus a failed assistant state, so reload matches persist.
**Where**: `frontend/app/components/use-conversation-thread.ts`
**Depends on**: T10
**Reuses**: `turnsToUIMessages` / initialMessages mapping
**Requirement**: ASK-02

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] A fixture conversation with one failed turn renders the user text and the error, not an empty shell
- [ ] `answered` / `not_found_*` mapping is unchanged

**Tests**: unit
**Gate**: full

---

### Phase 4

### T12: Hover `[^n]` shows the cited sentence

**What**: Focusing or hovering a citation mark shows `quoted_text` when the citation carries a span.
**Where**: `frontend/app/components/cited-answer.tsx`
**Depends on**: T11
**Reuses**: `CitationMark`; shadcn hover/tooltip already in the app. Do not force unused `inline-citation.tsx`.
**Requirement**: ASK-15, ASK-17

**Tools**:

- MCP: NONE
- Skill: `vercel-composition-patterns`

**Done when**:

- [ ] Test asserts the hover/focus accessible name or content equals `quoted_text`
- [ ] Missing span: no empty hover card (today's mark still clicks open the passage)

**Tests**: unit
**Gate**: full

---

### T13: "Show in book" highlights the cited span

**What**: When a citation has `quoted_text`, the reader highlight needle is that quote (`findQuoteOffset`); otherwise keep section-level flash.
**Where**: `frontend/app/components/citations.tsx`
**Depends on**: T12
**Reuses**: `findQuoteOffset`, `handleShowInBook` / flash path
**Requirement**: ASK-16, ASK-17

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Test that Show in book with a span calls the highlight path with that quote
- [ ] Null span keeps the previous section-flash behavior
- [ ] Offset-identity remains owned by T3's golden; this task does not reimplement offsets

**Tests**: unit
**Gate**: build

---

## Verifier

Fresh agent, author ≠ verifier. Spec-anchored check on ASK-01..17. Discrimination mutations that must die:

1. Restore `deleteConversation` on stream error (ASK-06).
2. Shift `CitedSpan.start` by 1 relative to document `data` (ASK-13).
3. Skip `_persist` on `AnswerGenerationFailed` (ASK-01).
4. Put `output_config.format` on the answering request (ASK-07).

ASK-11 (live dump) is recorded in the PR body; the Verifier checks that the shape sensors exist, not that a paid call was made.

---

## Diagram-definition cross-check

| Phase | Diagram edge | `Depends on` |
|---|---|---|
| 1 | T1 → T2 | T2 Depends on T1 |
| 1 | T2 → T3 | T3 Depends on T2 |
| 1 | T3 → T4 | T4 Depends on T3 |
| 1 | T4 → T5 | T5 Depends on T4 |
| 2 | T6 → T7 | T7 Depends on T6 |
| 2 | T7 → T8 | T8 Depends on T7 |
| 3 | T9 → T10 | T10 Depends on T9 |
| 3 | T10 → T11 | T11 Depends on T10 |
| 4 | T12 → T13 | T13 Depends on T12 |

Cross-phase: T6 Depends on T5, T9 Depends on T8, T12 Depends on T11 — backward only, no diagram arrow required.

## Test co-location

| Task | Layer | Tests field | Matrix |
|---|---|---|---|
| T1 | docs | none | none for RFC prose |
| T2 | domain | unit | domain entities |
| T3–T6 | adapter | unit | answering / 4xx |
| T5 | quiz adapter | unit | quiz anthropic |
| T7 | application | unit | conversation application |
| T8 | migration + wire | integration | migrations |
| T9–T13 | frontend | unit | ask-panel / citations |
