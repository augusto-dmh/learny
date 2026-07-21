# v3-notes-loop Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. If the skill cannot be activated, STOP.

---

**Design**: `.specs/features/v3-notes-loop/design.md`
**Status**: Build complete, pre-Verifier — Phase F done (T18 `10a3a26` README + v3 retrospective, T19 `c8cd488` version 0.3.0 incl. `test_versions.py` + uv.lock hand-sync per the 0.2.0 precedent; `frontend/package-lock.json` root version deliberately left at its historically-stale value, mirroring the 0.2.0 bump — flagged for an optional separate sync). Phase E report received post-record, matching the orchestrator's independent gates exactly (25 new tests, no existing-test changes, no deviations; `anchors_for_user` repo read added against N+1). Phase E done (T15 `2dd36e4`, T16 `ae83eae`, T17 `c9a3f29`; gates verified independently by the orchestrator: backend 1522/10 + ruff, frontend 494/50 + tsc + build; worker report pending at time of record). Phase D done (T12 `7b9b840`, T13 `5a33995`; frontend 493 passed / 50 files + tsc + build, verified independently by the orchestrator and by the worker's boundary run; +19 tests). Deviations: `DueItem.note_changed` required in client fixtures; `source_id` widened to `string|null`; ReviewCard confirm-state cleared via scoped `useEffect` on item change (a remount key aggravated the pre-existing revealed-reset race in the "grades each card" test — that flake predates this cycle and passed the full gate). Phase C done (T7 `1c778f0` predecessor / T8 `7be6df8` / T9 `eed0582` / T10 `7c14f93` / T11 `9f2a9d8`; full gate 1498/10 + ruff; ~94 new tests incl. the NL-10 byte-equal scheduling sensor). Recorded deviations: predecessor left the origin-vocabulary test red at T7, fixed in T8; `SubmitReview` authz rewired to `item.user_id` per AD-149 (source-less note cards were otherwise unreviewable), dropping sources/authorize from its constructor; `source_id` nullable in `CardView`/`DueItemView` with the "Your notes" source_title constant. The first Phase C worker died mid-T8 on a session interruption; relaunched worker adopted the tree (no collision). Phase B done (T4 `a75828a`, T5 `8be4367`, T6 `cbe5b4e`; backend 1399/10 + ruff, frontend 474 passed / 49 files + tsc + build; +10 backend +11 frontend tests; note fields emitted only for note evidence via a wrap-mode serializer so book citations stay byte-identical). Orchestrator fix `ec701dd`: the NL-02 rank-first test was a per-run RRF-tie coin flip ('simple' FTS doesn't stem "costs", so the note missed the lexical arm and tied the book's semantic hit, broken by random-UUID comparison) — query tokens aligned with the body + transactional HNSW REINDEX; assertions untouched; verified 5× isolation + full suite 1400/10. Phase A done (T1 `db0c509`, T2 `0995186`, T3 `bc6a145`; full gate 1390 passed / 10 skipped, ruff clean, +22 tests). Phase A contract notes: `UpdateNote` returns `(NoteView, body_changed)`; note evidence projects `chunk_id = source_id = note_id`; `refresh_note_cards` is a registered no-op stub for Phase C. Gate env: `LEARNY_EMBEDDING_PROVIDER=local LEARNY_GENERATION_PROVIDER=local` (backend/.env carries a real OpenAI key otherwise hit by one ingestion test).

---

## Test Coverage Matrix

> Guidelines found: `CLAUDE.md` (golden fixtures, citations/evaluation as core, worker-not-handler), `CONTRIBUTING.md`, CI `.github/workflows/ci.yml` (pytest -q · ruff check · vitest · tsc · next build). Existing depth sampled from `backend/tests/` (100 files) and `frontend/tests/` (48 files).

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| --- | --- | --- | --- | --- |
| Migrations / schema | integration | Chain + shape asserts (follows `test_migrations.py`); backfill correctness for 0014 | `backend/tests/test_migrations.py` | `cd backend && uv run pytest tests/test_migrations.py -q` |
| Application services | unit (fakes) | All branches, 1:1 to NL ACs, every listed edge case | `backend/tests/test_application_*.py`, `test_notes_*.py` | `cd backend && uv run pytest tests/<file> -q` |
| Repositories / hybrid SQL | integration (`requires_db`) | Key query paths + auth negatives + determinism | `backend/tests/test_repositories_*.py`, `test_retrieval.py` | same, needs `LEARNY_TEST_DATABASE_URL` |
| Web routes | integration (TestClient) | Every new route: happy + edge + error/authz | `backend/tests/test_web_*.py` | same |
| Worker tasks | unit (stubbed celery) | Idempotency + retry classification + invariants | `backend/tests/test_worker_*.py`, `test_reembed.py` | same |
| Export builder | unit (pure) | Byte-determinism, collisions, orphans, empty vault | `backend/tests/test_export_*.py` | same |
| Frontend lib/clients | unit (node env) | All branches per AC | `frontend/tests/*-client.test.ts`, `*.test.ts` | `cd frontend && npx vitest run <file>` |
| Frontend components | unit (jsdom pragma) | States: happy/empty/error/toggle/badge | `frontend/tests/*.test.tsx` | same |
| Docs / version bump | none | build gate only | — | full gates |

## Parallelism Assessment

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
| --- | --- | --- | --- |
| Backend unit (fakes) | Yes | In-memory fakes per test | `tests/fakes.py` pattern |
| Backend `requires_db` | No | Shared test DB, session-scoped engine, truncation | `conftest.py:44` `db_engine`/`db_conn` |
| Frontend vitest | Yes | Per-file env, no shared store | `vitest.config.ts` |

`[P]` within phases is ordering info only; each phase is one sequential worker (ship-cycle model), so DB-test serialization is automatic.

## Gate Check Commands

| Gate Level | When | Command |
| --- | --- | --- |
| Quick | per-task, affected modules | `cd backend && uv run pytest tests/<affected files> -q` / `cd frontend && npx vitest run <files>` |
| Full backend | phase boundary (backend phases) | `cd backend && uv run pytest -q && uv run ruff check` |
| Full frontend | phase boundary (frontend phases) | `cd frontend && npx vitest run && npx tsc --noEmit && npm run build` |
| Build (everything) | before publish + after fixes | both fulls |

**Verified baseline (v4-D close):** backend 1368 passed / 10 skipped + ruff clean; frontend 463 passed / 48 files + tsc + build. Env facts: backend runs via `uv` from `backend/`; DB-marked tests need `LEARNY_TEST_DATABASE_URL` against the dev Postgres (Docker Desktop; `learny_test` DB exists); CI deterministic adapters are default (no keys needed).

---

## Execution Plan

```
Phase A (backend, sequential):      T1 → T2 → T3
Phase B (full-stack, sequential):   T4 → T5 → T6      (needs A)
Phase C (backend, sequential):      T7 → T8 → T9 → T10 → T11   (independent of A/B except shared metadata file)
Phase D (frontend, sequential):     T12 → T13         (needs C)
Phase E (full-stack, sequential):   T15 → T16 → T17   (independent of A–D)
Phase F (docs/release, sequential): T18 → T19         (last)
Verifier: always, after T19.
```

Phases run sequentially A→F (one worker per phase; shared files — `metadata.py`, `ports.py`, `tasks.py`, quiz web/lib — make cross-phase parallelism not worth the merge risk).

---

## Task Breakdown

### T1: Notes retrieval index schema (migration 0013 + metadata)

**What**: `0013_notes_retrieval` — `notes.embedding VECTOR(1536)` (nullable), `notes.embedding_model text` (nullable), `notes.search_vector tsvector` + BEFORE trigger (`'simple'`; title `A`, body `D`) + backfill, HNSW (cosine, m=16/ef_construction=64) + GIN; mirrored in `metadata.py`.
**Where**: `backend/migrations/versions/0013_notes_retrieval.py`, `backend/app/infrastructure/db/metadata.py`
**Depends on**: None · **Requirement**: NL-01 · **Reuses**: 0006/AD-054 trigger shape, AD-020 index params
**Done when**: chain test passes with 0013 head; trigger maintains vector on insert/update (integration asserts); empty-body note yields empty tsvector.
**Tests**: integration · **Gate**: quick (`test_migrations.py` + new schema asserts)
**Commit**: `feat(notes): index notes for hybrid search`

### T2: embed_note task + NoteIndexEnqueuer

**What**: `NoteIndexEnqueuer` port (embed + refresh-cards), Celery impl, `embed_note(note_id)` task (idempotent, reads body at run time, empty body clears embedding, deterministic truncation, records `<model>@<dims>`), enqueue-after-commit from note create/update when body changed (AD-016 shape). `enqueue_refresh_cards` wired but the task body lands in T10 (no-op registration here).
**Where**: `backend/app/domain/ports.py`, `backend/app/worker/tasks.py`, `backend/app/infrastructure/worker/`, `backend/app/infrastructure/web/notes.py`
**Depends on**: T1 · **Requirement**: NL-01, NL-06(async-lag), NL-07
**Done when**: unit tests cover idempotency, empty-body clear, newest-body-wins (stale enqueue), enqueue-only-on-body-change; web tests assert enqueue after create/update.
**Tests**: unit + web integration · **Gate**: quick
**Commit**: `feat(notes): embed notes asynchronously on save`

### T3: Note arms in hybrid retrieval + Evidence origin

**What**: note_semantic/note_lexical CTEs fused with notes weight + `UNION ALL` projection + deterministic tie-break; `Evidence` gains `origin`/`note_id`/`note_title` (defaults); `RetrievalPort.search(user_id=None, include_notes=False)`; settings `retrieval_notes_{semantic_limit,lexical_limit,weight,snippet_chars}`; book-only path pinned byte-identical (regression test on emitted SQL or behavior).
**Where**: `backend/app/infrastructure/db/retrieval.py`, `backend/app/domain/{entities,ports}.py`, `backend/app/core/config.py`
**Depends on**: T1 · **Requirement**: NL-02, NL-05, NL-06, NL-07
**Done when**: DB tests: note+book fusion ranks distinctive note first; other-user note never returned (negative); NULL-embedding note still lexically retrievable; empty-body excluded; zero-notes user identical to book-only; deleted note gone; determinism (two runs, same order).
**Tests**: integration (`requires_db`) + unit · **Gate**: full backend (phase boundary)
**Commit**: `feat(retrieval): fuse the user's notes into hybrid search`

### T4: include_notes through Q&A, teaching, retrieve APIs

**What**: `RetrieveEvidence`/`AskQuestion`/teaching turn services take `include_notes`; web request models own defaults (Q&A absent→true; teaching absent→false; `/retrieve` default false); `EvidenceView` + streaming `data-citations` carry `origin`/`note_id`/`note_title`; grounding/citation contract untouched (note id = opaque evidence id).
**Where**: `backend/app/application/{retrieval,qa,teaching}.py`, `backend/app/infrastructure/web/{retrieval,questions,teaching}.py`, `ui_message_stream.py`
**Depends on**: T3 · **Requirement**: NL-03(backend), NL-04, NL-05
**Done when**: web tests: flag defaults per route (absent/true/false), false → zero note leakage into evidence/prompt/citations (assert against fake generation port capture); streamed citations carry origin; existing QA tests untouched-green.
**Tests**: unit + web integration · **Gate**: quick
**Commit**: `feat(qa): let answers draw on the user's notes behind a toggle`

### T5: Distinct note citations in the frontend

**What**: `Citation`/stream types gain `origin`/`noteId`/`noteTitle`; citation components render note citations as "Your note — <title>" linking `/notes/{id}` (no Open-in-book); book citations byte-identical (pin with existing tests).
**Where**: `frontend/app/lib/{questions,streaming}.ts`, `frontend/app/components/citations.tsx`, `frontend/components/ai-elements/inline-citation.tsx`
**Depends on**: T4 · **Requirement**: NL-03
**Done when**: component tests: note citation renders label+link, book citation unchanged, mixed list renders both.
**Tests**: unit (jsdom) · **Gate**: quick
**Commit**: `feat(ui): render note citations distinctly`

### T6: Include-my-notes toggles (Ask on, Teach off)

**What**: Toggle in Ask + Teach panels; versioned localStorage persistence (AD-125 pattern); flag sent only after explicit user choice (absent → server default); transports pass it through.
**Where**: `frontend/app/components/` panel files, `frontend/app/lib/` transports
**Depends on**: T5 · **Requirement**: NL-04
**Done when**: tests: default states differ per panel, choice persists, request body carries the flag only when chosen.
**Tests**: unit (jsdom) · **Gate**: full frontend + full backend (phase boundary)
**Commit**: `feat(ui): include-my-notes toggle for ask and teach`

### T7: Card ownership + note-card schema (migration 0014)

**What**: `0014_note_cards` — `quiz_items.user_id` backfilled from sources → NOT NULL FK CASCADE + index; `source_id` nullable + CHECK `source_id IS NOT NULL OR origin='note'`; `note_id` FK SET NULL + index; `note_changed_at` timestamptz; metadata + `QuizItem` entity fields; all quiz reads/authz switch to `user_id` with sources LEFT JOIN (`source_title` → `'Your notes'` for note rows).
**Where**: migration, `metadata.py`, `entities.py`, `backend/app/infrastructure/db/repositories.py`
**Depends on**: None (schema-independent of A/B) · **Requirement**: NL-09, NL-14, AD-149
**Done when**: migration chain + backfill test (pre-seeded rows get correct user_id); ownership negatives for deck/highlight/note reads (no cross-user leak); due queue green for source-less items; existing quiz tests green (count ≥ baseline).
**Tests**: integration + unit · **Gate**: quick (quiz + migration modules)
**Commit**: `feat(quiz): own cards by user so notes can feed review`

### T8: suggest_note_cards port method + adapters + QC

**What**: `QuizGenerationPort.suggest_note_cards(note_body, context, limit)`; local deterministic + Anthropic adapters (single Messages call, structured outputs, no chunk-id enum); QC = whitespace-normalized containment against the note body + cloze-mask validity (NL-08); anchored-note context carried when present.
**Where**: `backend/app/domain/ports.py`, `backend/app/infrastructure/quiz/{local,anthropic}.py`, `backend/app/application/quiz_qc.py`
**Depends on**: T7 · **Requirement**: NL-08
**Done when**: adapter tests (local exact; anthropic via stubbed client) + QC discard tests incl. all-fail-QC → empty.
**Tests**: unit · **Gate**: quick
**Commit**: `feat(quiz): generate card suggestions from a note`

### T9: Note promotion services + endpoints

**What**: `SuggestNoteCards` + `AcceptNoteCard` (`origin='note'`, minted id, `user_id`, `source_id=NULL`, `note_id`, fingerprint `content_key` no-unique, excerpt, fresh scheduling, stored embedding, per-note `content_key` dedup returns existing) + routes `POST /api/notes/{id}/cards/suggest` and `POST /api/notes/{id}/cards` (CSRF, quiz throttle, 404 non-disclosure, 502 provider failure).
**Where**: `backend/app/application/cards.py`, `backend/app/infrastructure/web/cards.py`
**Depends on**: T8 · **Requirement**: NL-08, NL-09, NL-15
**Done when**: web+service tests: accept→due-queue roundtrip, re-accept idempotent (NL-15), non-owner 404, un-anchored note works (source-less), QC-empty → 200 [].
**Tests**: unit + web integration · **Gate**: quick
**Commit**: `feat(quiz): promote a note to review cards in one action`

### T10: RefreshNoteCards task (edit-stability invariant)

**What**: worker task behind `enqueue_refresh_cards` (fires from note update only when the note has live note-origin items): regenerate → QC → greedy embedding match (`quiz_note_match_threshold=0.80`) → matched+changed update text/fingerprint/excerpt/embedding + `note_changed_at`; identical → untouched; unmatched item → `note_changed_at` only; leftover suggestions dropped; **scheduling + review_log byte-untouched — the cycle's core invariant, sensor mandatory**; newest-body-wins.
**Where**: `backend/app/application/cards.py`, `backend/app/worker/tasks.py`, `backend/app/infrastructure/web/notes.py` (enqueue gate)
**Depends on**: T9 · **Requirement**: NL-10, NL-11
**Done when**: tests assert scheduling/review_log rows byte-equal across a refresh that rewrites text; unmatched flags only; identical text sets no badge; unpromoted note save enqueues nothing; stale-enqueue converges to newest body.
**Tests**: unit + integration · **Gate**: quick
**Commit**: `feat(quiz): keep note cards current without touching their schedules`

### T11: note_changed badge data + explicit schedule reset

**What**: `DueReviewItem.note_changed` (`note_changed_at > COALESCE(last_review, created_at)`), `CardProvenance` via `notes` join for note cards; `ResetSchedule` service + `POST /api/quiz-items/{id}/schedule-reset` (fresh FSRS state, clears `note_changed_at`, review_log untouched, 409 non-active); `DueItemView.note_changed`.
**Where**: `repositories.py`, `entities.py`, `backend/app/application/reviews.py`, `backend/app/infrastructure/web/quiz.py`
**Depends on**: T10 · **Requirement**: NL-12(backend), NL-13, NL-14
**Done when**: due-queue tests: badge appears after refresh, retires after review, reset returns fresh state + clears badge + preserves log; severed note → provenance None, item still served.
**Tests**: unit + integration · **Gate**: full backend (phase boundary)
**Commit**: `feat(quiz): surface note changes at review with an explicit reset`

### T12: Note-detail promotion UI

**What**: "Add to review" on note detail → suggestions flow (v4-D card-suggestions pattern: edit-before-accept, accept per card), existing-cards count, empty/error states.
**Where**: `frontend/app/` note-detail screen + `frontend/app/lib/` cards client extension
**Depends on**: T11 · **Requirement**: NL-08, NL-15 (UI)
**Done when**: component tests: suggest→accept happy path, QC-empty message, error state, re-promotion shows count.
**Tests**: unit (jsdom + client) · **Gate**: quick
**Commit**: `feat(ui): add a note to review from its page`

### T13: Review badge + reset + note provenance UI

**What**: review screen renders "your note changed" badge (links note) when `note_changed`, "Reset schedule" confirm → reset endpoint; note provenance line via existing `card-provenance`; due-queue client types.
**Where**: `frontend/app/components/review-screen.tsx`, `frontend/app/lib/quiz.ts`
**Depends on**: T12 · **Requirement**: NL-12, NL-13
**Done when**: tests: badge shown/hidden per flag, reset calls endpoint + refreshes item, note provenance links `/notes/{id}`.
**Tests**: unit (jsdom) · **Gate**: full frontend (phase boundary)
**Commit**: `feat(ui): note-changed badge and schedule reset at review`

*(T14 intentionally unused — the due-queue client-types task was absorbed into T13.)*

### T15: Obsidian vault builder (pure)

**What**: `build_vault(...) -> bytes` — deterministic zip (fixed date_time, sorted entries, fixed compression), `Learny/Books/*.md` (callouts + `^lh-<id>`, position-ordered, orphans trailing) + `Learny/Notes/*.md` (learny-* frontmatter, verbatim body, anchor links/quotes), sanitization + deterministic de-collision.
**Where**: `backend/app/infrastructure/export/obsidian.py`
**Depends on**: None · **Requirement**: NL-17, NL-18, NL-19, NL-21
**Done when**: unit tests: two builds byte-identical; collision suffixes stable; orphan section; deleted-book snapshot rendering; empty vault valid; wikilinks verbatim.
**Tests**: unit (pure) · **Gate**: quick
**Commit**: `feat(export): deterministic obsidian vault builder`

### T16: ExportVault service + download route

**What**: `ExportVault(user)` gathering notes + anchors (repo read addition if needed), `GET /api/export/vault` zip download (auth, filename `learny-vault.zip`).
**Where**: `backend/app/application/vault.py`, `backend/app/infrastructure/web/vault.py`, `main.py`, `ports.py`/`repositories.py` (read)
**Depends on**: T15 · **Requirement**: NL-16, NL-20
**Done when**: web tests: roundtrip unzips to expected tree, only caller's data (negative), anonymous 401.
**Tests**: web integration · **Gate**: quick
**Commit**: `feat(export): download your notes and highlights as a vault`

### T17: Export button

**What**: "Export vault" download action on the notes list screen.
**Where**: `frontend/app/` notes screen
**Depends on**: T16 · **Requirement**: NL-16 (UI)
**Done when**: component test: link/action present, points at the endpoint.
**Tests**: unit (jsdom) · **Gate**: full backend + full frontend (phase boundary)
**Commit**: `feat(ui): export vault from the notes list`

### T18: README + retrospective

**What**: README second-brain feature-set refresh (capture → retrieve → reinforce → export; accurate to shipped behavior, no fabricated flags); `docs/retrospectives/2026-07-learny-v3.md` in the v2 form.
**Where**: `README.md`, `docs/retrospectives/`
**Depends on**: T13, T17 · **Requirement**: NL-22, NL-23
**Done when**: every env var / endpoint / command named in the diff exists in code (grep-verify).
**Tests**: none · **Gate**: build
**Commit**: `docs: describe the second-brain loop and record the v3 retrospective`

### T19: Version 0.3.0

**What**: `backend/pyproject.toml` + `frontend/package.json` (+ lockfiles) → `0.3.0`.
**Where**: those files
**Depends on**: T18 · **Requirement**: NL-24
**Done when**: both fulls green at 0.3.0.
**Tests**: none · **Gate**: build (both fulls)
**Commit**: `chore(release): version 0.3.0`

---

## Task Granularity Check

| Task | Scope | Status |
| --- | --- | --- |
| T1–T3 | 1 migration / 1 task+port / 1 query+entity widening | ✅ (T3 is one cohesive contract change) |
| T4–T6 | services+routes flag / citation rendering / toggles | ✅ |
| T7 | 1 migration + the ownership switch it forces | ✅ cohesive (schema+reads must move together) |
| T8–T11 | port / services+routes / task / badge+reset | ✅ |
| T12–T13, T15–T17 | 1 screen-flow or 1 module each | ✅ |
| T18–T19 | docs / bump | ✅ |

## Diagram-Definition Cross-Check

| Task | Depends on (body) | Diagram | Status |
| --- | --- | --- | --- |
| T1 none · T2 T1 · T3 T1 | A: T1→T2→T3 | ✅ (T3 needs only T1; runs after T2 in the sequential worker — no conflict) |
| T4 T3 · T5 T4 · T6 T5 | B after A | ✅ |
| T7 none · T8 T7 · T9 T8 · T10 T9 · T11 T10 | C chain | ✅ |
| T12 T11 · T13 T12 | D after C | ✅ |
| T15 none · T16 T15 · T17 T16 | E chain | ✅ |
| T18 T13,T17 · T19 T18 | F last | ✅ |

## Test Co-location Validation

| Task | Layer | Matrix requires | Task says | Status |
| --- | --- | --- | --- | --- |
| T1/T7 | migration+schema | integration | integration | ✅ |
| T2/T10 | worker+web enqueue | unit+integration | unit+integration | ✅ |
| T3/T11 | repo/query | integration | integration | ✅ |
| T4/T9/T16 | services+routes | unit+web | unit+web | ✅ |
| T8/T15 | adapters/builder | unit | unit | ✅ |
| T5/T6/T12/T13/T17 | frontend | unit | unit | ✅ |
| T18/T19 | docs/version | none | none (build gate) | ✅ |

## Tools

No MCPs. Skills per phase: `celery-workers` (T2, T10), `pgvector-hybrid-search` (T1, T3), `fastapi` (T4, T9, T11, T16), `ruff` + `uv` ambient. Selected by the orchestrator per the ship-cycle contract (no user prompt; logged here).
