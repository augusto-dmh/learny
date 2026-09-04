# review-worth-returning Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user — do not proceed without it.**

---

**Design**: `.specs/features/review-worth-returning/design.md`
**Status**: Approved

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec. Guidelines: `CLAUDE.md` (`make infra`, `make test-backend`, `make test-frontend`, `make lint`), pytest under `backend/tests/`, vitest + Testing Library under `frontend/tests/`.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Formulation QC | unit | Every REV-10..18 code rejects; legal fixtures pass; author-edited path not called | `backend/tests/test_application_quiz_qc.py` | `cd backend && uv run pytest tests/test_application_quiz_qc.py` |
| Prompts / local adapter | unit | REV-20 tokens in section and quote prompts; local candidates `discard_reason is None` | `backend/tests/test_quiz_anthropic.py` `test_quiz_local.py` | `cd backend && uv run pytest tests/test_quiz_anthropic.py tests/test_quiz_local.py` |
| Deck finalize reasons | unit/DB | JSONB sums to discarded_count; discarded text absent; empty-eligible triple | `backend/tests/test_application_quiz.py` | `cd backend && uv run pytest tests/test_application_quiz.py` |
| Highlight/note generated QC | unit | Generated fail `generic_stem`; PATCHed long answer persists | `backend/tests/test_application_cards.py` | `cd backend && uv run pytest tests/test_application_cards.py` |
| Undo / flag / due | unit/DB | Restore snapshot; log kept; 409 empty/legacy; study-day floor; flagged absent from due; Anki omits | `backend/tests/test_application_reviews.py` `test_repositories_quiz.py` `test_web_quiz.py` | `cd backend && uv run pytest tests/test_application_reviews.py tests/test_web_quiz.py tests/test_export_anki.py` |
| Preview / session | unit | Buckets; preview writes nothing; due page size = session setting; labels on wire | `backend/tests/test_scheduling_fsrs.py` `test_web_quiz.py` | `cd backend && uv run pytest tests/test_scheduling_fsrs.py tests/test_web_quiz.py tests/test_config.py` |
| Library honesty | unit (jsdom) | REV-03..06 copy from job counts | `frontend/tests/library-screen.test.tsx` | `cd frontend && npm test -- library-screen` |
| Review session UX | unit (jsdom) | Labels; requeue; undo; flag; edit; Space=Good; done/keep going | `frontend/tests/review-screen.test.tsx` | `cd frontend && npm test -- review-screen` |
| Home session job | unit (jsdom) | Session count vs pile; caught-up when total_due=0 | `frontend/tests/home-screen.test.tsx` | `cd frontend && npm test -- home-screen` |

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

Four phases, sequential. One Opus worker per phase (QC wiring, undo snapshot, due predicate, and content/schedule split are quiet-failure invariants). No Haiku-safe unit. Verifier after T14.

### Phase 1 — Formulation bar

```
T1 → T2 → T3
```

### Phase 2 — Schema, reasons, undo, flag

```
T4 → T5 → T6 → T7 → T8
```

### Phase 3 — Preview and session wire

```
T9 → T10
```

### Phase 4 — Library, review, Home

```
T11 → T12 → T13 → T14
```

---

## Task Breakdown

### Phase 1 — Formulation bar

### T1: Deterministic formulation gates

**What**: Add `discard_reason` to `quiz_qc.py` covering REV-10..18 plus existing empty/ungrounded/cloze-blank mapped to `empty`/`ungrounded`. EN∪PT stopword frozenset; 1–2 letter cloze answers fail `cloze_stopword`. Return `None` when the candidate may persist (duplicate cosine stays caller-side).
**Where**: `backend/app/application/quiz_qc.py`
**Depends on**: None
**Reuses**: `normalize_text`, `quote_in_text`, `cloze_is_valid`
**Requirement**: REV-02, REV-08, REV-09, REV-10, REV-11, REV-12, REV-13, REV-14, REV-15, REV-16, REV-17, REV-18

**Tools**: Skill `ruff`

**Done when**:

- [x] One unit per reason code fails that code and no other
- [x] A legal one-word cloze and a short free-recall return `None`
- [x] Gate: `uv run pytest tests/test_application_quiz_qc.py`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(quiz): reject poorly formulated generated cards`

---

### T2: Formulation instructions on Anthropic quiz prompts

**What**: Rewrite `_section_prompt` and `_quote_prompt` so both instruct: one fact per card, short answer, blank the key term not a function word, no lists, no yes/no, answerable without the book. Keep chunk labels, `source_chunk_id`, `anchor_quote`, and item_type vocabulary.
**Where**: `backend/app/infrastructure/quiz/anthropic.py`
**Depends on**: T1
**Reuses**: existing structured output schema
**Requirement**: REV-20

**Tools**: Skill `ruff`

**Done when**:

- [x] Prompt tests assert the rubric tokens on both helpers
- [x] Citations/item schema tests still pass
- [x] Gate: `uv run pytest tests/test_quiz_anthropic.py`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(quiz): ask the model for atomic cards`

---

### T3: Legal local-adapter fixtures

**What**: Rewrite `_candidates_from` so every emitted candidate passes `discard_reason`. Prefer a cloze on the longest non-stopword token (≥3 letters) and a free-recall whose question is not a generic stem and whose answer is that term. If the section has no legal term, emit nothing for it.
**Where**: `backend/app/infrastructure/quiz/local.py`
**Depends on**: T2
**Reuses**: `CLOZE_BLANK`; stopword set from `quiz_qc`
**Requirement**: REV-21

**Tools**: Skill `ruff`

**Done when**:

- [x] Every local candidate from the golden fixture sections has `discard_reason is None`
- [x] Existing groundedness eval still sees ≥1 persisted item on the standard fixture book (adjust assertions to yield, not to the old generic stem)
- [x] Gate: `uv run pytest tests/test_quiz_local.py tests/eval/test_quiz_groundedness.py tests/test_worker_quiz.py`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(quiz): emit reviewable local deck fixtures`

---

### Phase 2 — Schema, reasons, undo, flag

### T4: Review-quality schema

**What**: Migration `0021_review_quality`: `discard_reasons` JSONB on jobs (default `{}`); `flagged_at` on `quiz_items`; `undone_at` plus previous scheduling columns on `review_log`. Update `metadata.py` and entities. Downgrade drops the new columns.
**Where**: `backend/migrations/versions/0021_review_quality.py`
**Depends on**: T3
**Reuses**: 0008/0014 column style; reversible like 0017
**Requirement**: REV-01, REV-22, REV-28, REV-34

**Tools**: Skill `ruff`

**Done when**:

- [x] Upgrade/downgrade round-trip on `learny_test`
- [x] Entities accept the new fields with defaults that keep old constructors compiling
- [x] Gate: `uv run pytest tests/test_migrations.py tests/test_domain_quiz.py`

**Tests**: integration
**Gate**: full
**Commit**: `feat(quiz): store discard reasons, flags, and undo snapshots`

---

### T5: Persist discard reasons on deck finalize

**What**: `_ground` calls `discard_reason` and returns the code; finalize tallies JSONB so counts sum to `discarded_count`; cosine rejects are `duplicate`; `QuizJobView` exposes `discard_reasons`. Discarded text is never upserted.
**Where**: `backend/app/application/quiz.py`
**Depends on**: T4
**Reuses**: existing generated/discarded/failed counters
**Requirement**: REV-01, REV-02, REV-07, REV-08, REV-09, REV-18

**Tools**: Skill `ruff`

**Done when**:

- [x] A generic-stem candidate increments `generic_stem` and not `quiz_items`
- [x] Eligible-empty still succeeds with all-zero counts and `{}` reasons
- [x] Gate: `uv run pytest tests/test_application_quiz.py tests/test_web_quiz.py tests/test_domain_quiz.py`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(quiz): record why generated cards were dropped`

---

### T6: Same gates on highlight and note generation

**What**: Generated highlight `suggest_cards` and note `suggest_note_cards` discard via `discard_reason`. `UpdateCard` and accept-after-edit stay ungated (AD-138). `note_card_passes_qc` may delegate to `discard_reason is None` for the generated path only.
**Where**: `backend/app/application/cards.py`
**Depends on**: T5
**Reuses**: AD-138 author-owned text
**Requirement**: REV-09, REV-19

**Tools**: Skill `ruff`

**Done when**:

- [x] A generated generic stem does not appear in suggestions
- [x] PATCH of a 200-character answer still 200s and does not change scheduling
- [x] Gate: `uv run pytest tests/test_application_cards.py tests/test_web_cards.py`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(quiz): apply formulation gates to suggested cards`

---

### T7: Compensating review undo

**What**: `SubmitReview` stores the pre-grade snapshot on the log row. `UndoLastReview` restores that snapshot, sets `undone_at`, decrements the credited study day (UPDATE existing row, `GREATEST(count-1,0)`, never insert). `POST /api/reviews/undo` with CSRF + `rate_limit_quiz` + `X-Client-Timezone`. 409 when nothing to undo or snapshot is NULL.
**Where**: `backend/app/application/reviews.py`
**Depends on**: T6
**Reuses**: AD-149 ownership collapse; AD-153 same-transaction study day
**Requirement**: REV-22, REV-23, REV-24, REV-25, REV-26, REV-27, REV-28

**Tools**: Skill `ruff`

**Done when**:

- [x] Grade then undo restores due/stability/step; log row remains with `undone_at`
- [x] Second undo is 409; legacy NULL snapshot is 409
- [x] `reviews_count` drops by one and never goes negative
- [x] Gate: `uv run pytest tests/test_application_reviews.py tests/test_web_quiz.py tests/test_repositories_quiz.py`

**Tests**: unit
**Gate**: full
**Commit**: `feat(quiz): undo the last review without deleting history`

---

### T8: Flag out of the due queue

**What**: `FlagCard` sets/clears `flagged_at` without touching scheduling or `review_log`. Due query adds `flagged_at IS NULL`. `POST /api/quiz-items/{id}/flag` body `{flagged: bool}`. Anki export skips flagged cards. Reconcile still only writes `active|stale|orphaned`.
**Where**: `backend/app/application/reviews.py`
**Depends on**: T7
**Reuses**: `due_for_user` predicate list
**Requirement**: REV-34, REV-35, REV-36, REV-38, REV-39

**Tools**: Skill `ruff`

**Done when**:

- [x] Flagged active past-due item is absent from due; scheduling bytes unchanged
- [x] Unflag restores due membership; stale+flagged stays out after unflag
- [x] Export GUID list excludes the flagged id
- [x] Gate: `uv run pytest tests/test_application_reviews.py tests/test_web_quiz.py tests/test_export_anki.py tests/test_reconcile_quiz.py`

**Tests**: unit
**Gate**: full
**Commit**: `feat(quiz): flag cards out of review without touching FSRS`

---

### Phase 3 — Preview and session wire

### T9: FSRS interval preview

**What**: `SchedulingPort.preview(snapshot, reviewed_at) -> dict[int, datetime]` for ratings 1–4 using a throwaway scheduler with fuzzing off. Pure `interval_bucket(delta) ->` one of the nine labels. Preview must not be usable as a persist path.
**Where**: `backend/app/infrastructure/scheduling/fsrs.py`
**Depends on**: T8
**Reuses**: `_to_card` / `_to_snapshot`
**Requirement**: REV-29, REV-30, REV-33

**Tools**: Skill `ruff`

**Done when**:

- [x] Four ratings return four dues; calling preview leaves DB log length unchanged
- [x] Bucket table pins the nine labels at the documented boundaries
- [x] Gate: `uv run pytest tests/test_scheduling_fsrs.py`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(quiz): preview next intervals without recording a review`

---

### T10: Session page and labels on the due wire

**What**: `LEARNY_REVIEW_SESSION_SIZE` (default 20, cap 100) is `GetDueQueue`'s default limit; `LEARNY_REVIEW_REQUEUE_MINUTES` default 15 is returned on the due view for the client. Each `DueItemView` includes `interval_labels` for 1–4. `SubmitReview` / undo responses include labels for the restored/advanced snapshot. Document both knobs in `.env.example`.
**Where**: `backend/app/infrastructure/web/quiz.py`
**Depends on**: T9
**Reuses**: existing `total_due` vs `items` split
**Requirement**: REV-29, REV-31, REV-40

**Tools**: Skill `ruff`

**Done when**:

- [x] 25 due with default session returns 20 items and `total_due=25` plus `session_size` and `requeue_minutes`
- [x] Each item has four bucket labels; submit returns labels for the new snapshot
- [x] Gate: `uv run pytest tests/test_web_quiz.py tests/test_config.py tests/test_application_reviews.py`

**Tests**: unit
**Gate**: full
**Commit**: `feat(quiz): cap today's session and show interval labels`

---

### Phase 4 — Library, review, Home

### T11: Honest empty-deck copy

**What**: `QuizDeckControls` renders REV-03..06 from `latest_job` counts (and discarded footnote). Succeeded-empty is visible. Failed jobs keep `job.error`. Generate remains.
**Where**: `frontend/app/components/library-screen.tsx`
**Depends on**: T10
**Reuses**: existing overview fetch / polling
**Requirement**: REV-03, REV-04, REV-05, REV-06, REV-07

**Tools**: none

**Done when**:

- [x] Tests cover the three count triples plus a quiet discarded footnote
- [x] Gate: `cd frontend && npm test -- library-screen`

**Tests**: unit
**Gate**: full
**Commit**: `feat(library): explain empty and thin quiz decks`

---

### T12: Interval labels, requeue, and Space-as-Good

**What**: Review buttons show `interval_labels`. After a grade, if `due` is within `requeue_minutes`, insert the card into the remaining session queue with the new labels. Space after reveal grades Good. While requeued cards remain, do not show Done-for-today; show the short-term-review count.
**Where**: `frontend/app/components/review-screen.tsx`
**Depends on**: T11
**Reuses**: existing 1–4 buttons and `useKeyShortcuts`; shared by the dock tab (AD-213)
**Requirement**: REV-29, REV-31, REV-32, REV-33, REV-44

**Tools**: none

**Done when**:

- [x] Labels render per rating; a ~1m due reappears; a ~4d due does not
- [x] Space after reveal submits 3; Space before reveal still reveals
- [x] Gate: `cd frontend && npm test -- review-screen`

**Tests**: unit
**Gate**: full
**Commit**: `feat(review): show intervals and requeue learning steps`

---

### T13: Undo, flag, and edit in review

**What**: Ctrl/Cmd+Z and `u` call undo and put the restored card back as current. `f` flags (drops from the local queue). `e` opens content edit via existing `updateCard`. Submit errors for 409 empty-undo stay on-screen.
**Where**: `frontend/app/components/review-screen.tsx`
**Depends on**: T12
**Reuses**: `PATCH /api/quiz-items/{id}`; new undo/flag clients in `lib/quiz.ts`
**Requirement**: REV-22, REV-37, REV-45

**Tools**: none

**Done when**:

- [x] Undo restores the prior card into view; flag removes it; edit keeps the same card id
- [x] Gate: `cd frontend && npm test -- review-screen`

**Tests**: unit
**Gate**: full
**Commit**: `feat(review): undo, flag, and edit the current card`

---

### T14: Bounded Done-for-today

**What**: Home Reviews card shows `min(session_size, total_due)` as the job while `total_due > 0`. When the session page is exhausted and `total_due > 0`, Review shows Done-for-today, Keep going (next due page), and a continue-reading link when `/api/reading/continue` is non-null. When `total_due` is 0, keep the existing caught-up copy and hide Keep going.
**Where**: `frontend/app/components/home-screen.tsx`
**Depends on**: T13
**Reuses**: `getContinueReading`; due client already used by Home
**Requirement**: REV-40, REV-41, REV-42, REV-43

**Tools**: none

**Done when**:

- [ ] Home with 25 due / session 20 shows 20 as the job
- [ ] Review done-state with remaining due offers Keep going + book link; zero due does not
- [ ] Gate: `cd frontend && npm test -- home-screen review-screen`

**Tests**: unit
**Gate**: full
**Commit**: `feat(review): finish today's session and return to the book`

---
