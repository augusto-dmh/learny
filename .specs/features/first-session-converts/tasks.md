# first-session-converts Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user — do not proceed without it.**

---

**Design**: `.specs/features/first-session-converts/design.md`
**Status**: Approved

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec. Guidelines: `CLAUDE.md` (`make infra`, `make test-backend`, `make test-frontend`, `make lint`), pytest under `backend/tests/`, vitest + Testing Library under `frontend/tests/`.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Schema | integration | `is_sample` default false; one-sample unique; activation unique pair; downgrade | `backend/tests/test_migrations.py` | `cd backend && uv run pytest tests/test_migrations.py` |
| Source ACL | unit/DB | list includes sample; readable non-owner; mutate 404; unauthenticated 401; no corpus clone | `backend/tests/test_application_sources.py` `test_web_sources.py` | `cd backend && uv run pytest tests/test_application_sources.py tests/test_web_sources.py` |
| Starter deck | unit/DB | five clones; idempotent; non-sample 404; grade does not touch templates | `backend/tests/test_application_quiz.py` `test_web_quiz.py` | `cd backend && uv run pytest tests/test_application_quiz.py tests/test_web_quiz.py` |
| Activation | unit/DB | first_cited_answer only Ask+answered+citations; teach/fail/empty skip; account_created; sample_opened; first_review; conflict no second row | `backend/tests/test_application_activation.py` `test_application_conversations.py` | `cd backend && uv run pytest tests/test_application_activation.py tests/test_application_conversations.py tests/test_application_reviews.py` |
| Seed | unit | second call is no-op; enqueue failure does not mark ready | `backend/tests/test_application_sample.py` | `cd backend && uv run pytest tests/test_application_sample.py` |
| Library / naming | unit (jsdom) | Open; overflow; PDF accept; wait copy; no empty-when-sample; Library heading | `frontend/tests/library-screen.test.tsx` `app-shell.test.tsx` | `cd frontend && npm test -- library-screen app-shell` |
| Notes export label | unit (jsdom) | Download notes | `frontend/tests/notes-screen.test.tsx` | `cd frontend && npm test -- notes-screen` |
| Home Ask-first | unit (jsdom) | Ask sample when due 0; due card when due > 0 | `frontend/tests/home-screen.test.tsx` | `cd frontend && npm test -- home-screen` |
| Ask highlight | unit (jsdom) | canned question highlighted for sample | `frontend/tests/ask-panel.test.tsx` | `cd frontend && npm test -- ask-panel` |
| Landing | unit (jsdom) | proof quote + locator + title; Create account; no generation fetch | `frontend/tests/landing-page.test.tsx` | `cd frontend && npm test -- landing-page` |

## Parallelism Assessment

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
| --------- | -------------- | --------------- | -------- |
| backend unit (no DB) | Yes | in-process fakes | `tests/fakes.py` |
| backend DB-gated | No across workers sharing `learny_test` | one pytest process per gate | `conftest.py` |
| frontend vitest | Yes within one `npm test` | jsdom per file | `frontend/tests/` |

## Gate Check Commands

> `uv` may be off PATH: `backend/.venv/bin/python -m pytest` / `backend/.venv/bin/ruff`. Prefix `LEARNY_GENERATION_PROVIDER=local LEARNY_EMBEDDING_PROVIDER=local` if the local `.env` leaks real providers. `jq` is not installed.

| Gate Level | When to Use | Command |
| ---------- | ----------- | -------- |
| Quick | After a backend unit task | `cd /home/augusto/projects/learny/backend && uv run pytest <touched module>` |
| Full | After HTTP or frontend tasks | touched backend module and/or `cd /home/augusto/projects/learny/frontend && npm test -- <file>` |
| Build | Phase boundary | `cd /home/augusto/projects/learny && make lint` plus the cycle's backend + frontend suites |

---

## Execution Plan

Three phases, sequential. One Opus worker per phase (ACL, clone uniqueness, and persist-hook events are quiet-failure invariants). No Haiku-safe unit. Verifier after T16.

### Phase 1 — Sample ACL

```
T1 → T2 → T3 → T4 → T5
```

### Phase 2 — Starter deck, events, seed

```
T5 → T6 → T7 → T8 → T9 → T10
```

### Phase 3 — Library, Home, Ask, landing

```
T10 → T11 → T12 → T13 → T14 → T15 → T16
```

---

## Task Breakdown

### T1: Add sample and activation schema

**What**: Migration `0022` adds `sources.is_sample` (boolean not null default false), a partial unique index that allows only one true sample, and `activation_events` with unique `(user_id, name)` and users FK CASCADE.
**Where**: `backend/migrations/versions/0022_sample_and_activation.py`
**Depends on**: None
**Reuses**: `0021_review_quality.py` revision chain
**Requirement**: FS-01, FS-12

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Upgrade then downgrade leaves the prior schema
- [x] A second `is_sample=true` insert fails
- [x] A second activation row for the same `(user_id, name)` fails

**Tests**: integration
**Gate**: full
**Commit**: `feat(library): add a shared-sample flag and activation events`

---

### T2: Carry is_sample on the source entity

**What**: `Source` gains `is_sample: bool` default false; constructors and `_to_source` map the column.
**Where**: `backend/app/domain/entities.py`
**Depends on**: T1
**Reuses**: existing `Source` dataclass
**Requirement**: FS-01

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] A loaded source round-trips `is_sample`
- [x] Ordinary uploads remain `is_sample=false`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(library): record whether a source is the shared sample`

---

### T3: List the sample and insert activation rows

**What**: Source repository lists the caller's rows union the sample; activation repository inserts-on-conflict-do-nothing.
**Where**: `backend/app/infrastructure/db/repositories.py`
**Depends on**: T2
**Reuses**: `list_by_user`; existing Connection repos
**Requirement**: FS-02, FS-12

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Two users each see their books plus one shared sample id
- [x] Two inserts of the same event name leave one row

**Tests**: integration
**Gate**: full
**Commit**: `feat(library): list the shared sample beside owned books`

---

### T4: Read the sample without widening ownership

**What**: Add `readable_source` (owner or `is_sample`, else `SourceNotFound`). `ListSources`/`GetSource` use it. `authorized_source` stays owner-only. First successful sample read records `sample_opened`.
**Where**: `backend/app/application/ingestion.py`
**Depends on**: T3
**Reuses**: `authorized_source` 404 collapse
**Requirement**: FS-03, FS-04, FS-29

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Non-owner GetSource on sample succeeds when ready
- [x] Non-owner StartIngestion-style authorized_source on sample raises SourceNotFound
- [x] First readable sample stamps `sample_opened` once

**Tests**: unit
**Gate**: quick
**Commit**: `feat(library): let any signed-in user read the sample book`

---

### T5: Expose sample fields on the sources API

**What**: `SourceSummary` includes `is_sample` and `suggested_question` (canned string when sample, null otherwise). List/get tests pin 401 unauthenticated and 404 mutate-style routes still collapsed.
**Where**: `backend/app/infrastructure/web/sources.py`
**Depends on**: T4
**Reuses**: `SourceSummary.from_entity`
**Requirement**: FS-05, FS-07

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [x] GET list JSON has `is_sample` and the canned question on the sample row
- [x] Unauthenticated GET sample is 401
- [x] Conversations/read paths that still used `authorized_source` for sample reads are switched to `readable_source` in this task if T4's helper is not yet wired there — keep mutate routes on `authorized_source`

**Tests**: integration
**Gate**: full
**Commit**: `feat(library): return sample flags and the canned question`

---

### T6: Clone five starter cards for the caller

**What**: `EnsureStarterDeck` copies five operator templates onto the caller with new ids and `initial()` scheduling; second call is a no-op on count and schedules.
**Where**: `backend/app/application/quiz.py`
**Depends on**: T5
**Reuses**: quiz item insert, `SchedulingPort.initial`
**Requirement**: FS-14, FS-15, FS-16, FS-18

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] First call inserts five active items for the caller
- [x] Second call leaves scheduling byte-equal
- [x] Grading a clone does not change the template snapshot
- [x] Overlap cannot yield ten clones (unique or equivalent)

**Tests**: unit
**Gate**: full
**Commit**: `feat(review): clone five sample cards without sharing schedules`

---

### T7: POST starter on the sample only

**What**: `POST /api/sources/{id}/quiz/starter` runs `EnsureStarterDeck`; non-sample id is 404; CSRF/origin/rate_limit_quiz match other quiz POSTs.
**Where**: `backend/app/infrastructure/web/quiz.py`
**Depends on**: T6
**Reuses**: quiz router deps
**Requirement**: FS-17

**Tools**:

- MCP: NONE
- Skill: fastapi

**Done when**:

- [x] Sample POST 200 with five items
- [x] Owned non-sample POST 404
- [x] Unauthenticated 401

**Tests**: integration
**Gate**: full
**Commit**: `feat(review): add an idempotent sample starter endpoint`

---

### T8: Stamp account_created on register

**What**: `RecordActivation` service; `RegisterUser` inserts `account_created` once.
**Where**: `backend/app/application/activation.py`
**Depends on**: T7
**Reuses**: activation repository from T3
**Requirement**: FS-28

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Register inserts one `account_created` row
- [x] A second explicit RecordActivation of the same name does not add a row

**Tests**: unit
**Gate**: quick
**Commit**: `feat(auth): record account creation as an activation event`

---

### T9: Stamp first_cited_answer after a cited Ask

**What**: After persist of an Ask turn that is answered with at least one citation, insert `first_cited_answer`. Teach, failed, not-found, and zero-citation turns do not. JSON and stream share the hook.
**Where**: `backend/app/application/conversations.py`
**Depends on**: T8
**Reuses**: persist completion used by stream and JSON
**Requirement**: FS-09, FS-10, FS-11, FS-12, FS-13

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Cited Ask persist inserts one row
- [x] Second cited Ask does not insert
- [x] Teach-answered with empty citations inserts none
- [x] Failed Ask inserts none

**Tests**: unit
**Gate**: full
**Commit**: `feat(ask): stamp first cited answer only after a successful persist`

---

### T10: Stamp first_review and seed the sample once

**What**: `SubmitReview` inserts `first_review` once. `SeedSample` is idempotent: existing sample is a no-op; storage/enqueue failure does not mark a new row ready. Tests use fakes, not the 24k-word EPUB ingest.
**Where**: `backend/app/application/sample.py`
**Depends on**: T9
**Reuses**: AD-016 enqueue-after-commit; SubmitReview success path
**Requirement**: FS-06, FS-32

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] First successful review inserts `first_review`; second does not
- [ ] Seed when sample exists returns that source without a second insert
- [ ] Enqueue failure leaves no ready `is_sample` source

**Tests**: unit
**Gate**: full
**Commit**: `feat(library): seed one sample book and record the first review`

---

### T11: One Open, overflow verbs, wait copy, PDF picker

**What**: Library primary CTA is Open to `/read`. Overflow: Ask, Tutor, Review; Re-ingest only for owned non-sample. Picker accepts `.epub,.pdf`. Processing non-sample shows sample-while-waiting copy. Sample in list means no “No sources yet.”
**Where**: `frontend/app/components/library-screen.tsx`
**Depends on**: T10
**Reuses**: existing row status badges and ingest controls
**Requirement**: FS-19, FS-20, FS-21, FS-22, FS-23

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Ready row’s primary name is Open and href is the read URL
- [ ] Overflow has Ask, Tutor, Review; sample has no Re-ingest
- [ ] Input accept includes `.pdf`
- [ ] Processing own book plus sample shows wait copy
- [ ] Sample-only list does not show “No sources yet.”

**Tests**: unit
**Gate**: full
**Commit**: `feat(library): open one book and point waiters at the sample`

---

### T12: Name the shelf Library

**What**: Sidebar nav and the `/sources` page heading read Library.
**Where**: `frontend/app/(app)/sources/page.tsx`
**Depends on**: T11
**Reuses**: existing nav item and page heading
**Requirement**: FS-24

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] The `/sources` h1 reads Library
- [ ] The sidebar nav label that pointed at `/sources` reads Library
- [ ] Tests that looked for “Your bookshelf” or “Bookshelf” as that label are updated

**Tests**: unit
**Gate**: full
**Commit**: `feat(library): call the shelf Library`

---

### T13: Name the vault download Download notes

**What**: Notes export control label is Download notes.
**Where**: `frontend/app/components/notes/notes-screen.tsx`
**Depends on**: T12
**Reuses**: existing vault href
**Requirement**: FS-26

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Accessible name is Download notes
- [ ] href still hits `/api/export/vault`

**Tests**: unit
**Gate**: full
**Commit**: `feat(notes): call the vault download Download notes`

---

### T14: Send a new Home to Ask on the sample

**What**: WHILE due is 0 and continue-reading is null, Home offers Ask on the sample (uses `is_sample` from the sources list). WHEN due > 0, the due card still leads.
**Where**: `frontend/app/components/home-screen.tsx`
**Depends on**: T13
**Reuses**: existing due and continue fetches
**Requirement**: FS-30, FS-31

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Zero due + no resume + sample in list → Ask control to the sample
- [ ] total_due > 0 still shows the due-session card

**Tests**: unit
**Gate**: full
**Commit**: `feat(home): start the first session on Ask for the sample`

---

### T15: Highlight the canned sample question

**What**: Sample Ask highlights `suggested_question` from the source payload.
**Where**: `frontend/app/components/ask-panel.tsx`
**Depends on**: T14
**Reuses**: existing suggested-prompt UI if any
**Requirement**: FS-08

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Sample source renders the canned string as the highlighted prompt
- [ ] Non-sample Ask does not show that string as the highlight

**Tests**: unit
**Gate**: full
**Commit**: `feat(ask): highlight the canned question on the sample`

---

### T16: Put cited-answer proof on the signed-out landing page

**What**: `/` shows a static passage quote, citation locator, and *The Art of War* above Create account and Log in. No generation fetch.
**Where**: `frontend/app/page.tsx`
**Depends on**: T15
**Reuses**: existing Create account / Log in links
**Requirement**: FS-27

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Proof strings are in the document
- [ ] Render does not call a generation or conversation URL

**Tests**: unit
**Gate**: full
**Commit**: `feat(web): show a cited-answer proof above the fold`

---

## Phase Execution Map

```
Phase 1 → Phase 2 → Phase 3

Phase 1:  T1 → T2 → T3 → T4 → T5
Phase 2:  T5 → T6 → T7 → T8 → T9 → T10
Phase 3:  T10 → T11 → T12 → T13 → T14 → T15 → T16
```

Execution is strictly sequential. One Opus worker per phase. Verifier after T16.

---

## Task Granularity Check

| Task | Scope | Status |
| --- | --- | --- |
| T1 migration | 1 file | Granular |
| T2 Source field | 1 entity | Granular |
| T3 repository | 1 file | Granular |
| T4 readable_source | 1 module | Granular |
| T5 SourceSummary | 1 adapter | Granular |
| T6 EnsureStarterDeck | 1 use case | Granular |
| T7 starter route | 1 endpoint | Granular |
| T8 RecordActivation | 1 service | Granular |
| T9 persist hook | 1 module | Granular |
| T10 seed + first_review | 1 seed module (review hook in same commit if it is one call site) | OK cohesive |
| T11 library CTAs | 1 component | Granular |
| T12 sidebar name | 1 component | Granular |
| T13 notes label | 1 component | Granular |
| T14 Home Ask-first | 1 component | Granular |
| T15 Ask highlight | 1 component | Granular |
| T16 landing | 1 page | Granular |

---

## Diagram-Definition Cross-Check

| Task | Depends On (task body) | Diagram Shows | Status |
| --- | --- | --- | --- |
| T1 | None | (start) | Match |
| T2 | T1 | T1 → T2 | Match |
| T3 | T2 | T2 → T3 | Match |
| T4 | T3 | T3 → T4 | Match |
| T5 | T4 | T4 → T5 | Match |
| T6 | T5 | T5 → T6 (phase 2 after T5) | Match |
| T7 | T6 | T6 → T7 | Match |
| T8 | T7 | T7 → T8 | Match |
| T9 | T8 | T8 → T9 | Match |
| T10 | T9 | T9 → T10 | Match |
| T11 | T10 | T10 → T11 | Match |
| T12 | T11 | T11 → T12 | Match |
| T13 | T12 | T12 → T13 | Match |
| T14 | T13 | T13 → T14 | Match |
| T15 | T14 | T14 → T15 | Match |
| T16 | T15 | T15 → T16 | Match |

---

## Test Co-location Validation

| Task | Code Layer Created/Modified | Matrix Requires | Task Says | Status |
| --- | --- | --- | --- | --- |
| T1 | Schema | integration | integration | OK |
| T2 | Entity | unit | unit | OK |
| T3 | Repository | integration | integration | OK |
| T4 | Application ACL | unit | unit | OK |
| T5 | HTTP sources | integration | integration | OK |
| T6 | Starter use case | unit | unit | OK |
| T7 | HTTP quiz | integration | integration | OK |
| T8 | Activation service | unit | unit | OK |
| T9 | Conversations persist | unit | unit | OK |
| T10 | Seed + review hook | unit | unit | OK |
| T11 | Library UI | unit (jsdom) | unit | OK |
| T12 | Sidebar | unit (jsdom) | unit | OK |
| T13 | Notes UI | unit (jsdom) | unit | OK |
| T14 | Home UI | unit (jsdom) | unit | OK |
| T15 | Ask UI | unit (jsdom) | unit | OK |
| T16 | Landing | unit (jsdom) | unit | OK |
