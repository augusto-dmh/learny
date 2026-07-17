# v2-active-recall Specification (RFC-002 Cycle E)

**Cycle:** `v2-active-recall` — RFC-002 Cycle E "Flagship: active recall (quizzes + FSRS)"
**Scope class:** Complex (new domain: quiz generation + spaced repetition; schema + backend + worker + frontend + eval)
**Evidence:** `docs/research/2026-07-12/active-recall-srs.md`, `docs/research/2026-07-12/followup-quiz-item-format.md`
**Decisions:** `.specs/features/v2-active-recall/context.md` (D-1..D-10 → AD-072..AD-081)

## Problem Statement

Learny ingests books and answers/teaches with citations, but nothing closes the learning loop: readers forget what they read. Active recall with spaced repetition is the highest-evidence retention intervention. This cycle generates citation-grounded quiz items per book section and schedules reviews with FSRS-6, keeping every item traceable to an exact passage.

## Goals

- [ ] A user can generate a quiz deck for any ingested book (offline-deterministic in CI; batched Haiku in production) where every item is grounded in a verbatim source quote.
- [ ] A user can review due items with 4-button self-grading; FSRS-6 schedules the next review; review history is append-only and never destroyed.
- [ ] Quiz items survive re-ingestion without losing scheduling state (keep/stale/orphaned reconciliation).
- [ ] Deterministic groundedness evals run on every PR; an answerability judge runs nightly.

## Out of Scope

| Feature | Reason |
|---|---|
| MCQ / distractors (incl. schema columns) | Locked v2 decision; recognition adds no retention benefit, distractors ungroundable (followup-quiz-item-format) |
| FSRS parameter optimizer | Separate `fsrs[optimizer]` extra (torch); pays off only after hundreds of reviews. Defer. |
| Per-user desired-retention settings, deck/tag organization, leech detection | Not MVP; FSRS defaults are the population fit |
| Manual item editing / user suspend-dismiss | Defer; statuses are system-managed this cycle |
| Shared decks across users | Items are per-user-per-book (via source ownership); table split future-proofs sharing |
| CSV export | `.apkg` via genanki chosen (stable GUID upsert); CSV loses scheduling identity |
| Eval dashboards / Ragas | Locked v2 decision (AD in RFC-002) |
| Review-submit idempotency keys | Assumption A-2 below |

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|
| A-1 Items-per-section count | Prompt asks 3–6 per eligible leaf section; server caps at `LEARNY_QUIZ_MAX_ITEMS_PER_SECTION` (default 6) | Research heuristic (not evidence); density follows concepts | auto (ship-cycle) |
| A-2 Duplicate review submits | No idempotency key; each accepted POST is one review | Append-only log tolerates it; UI advances on success; FSRS re-review is well-defined. Revisit if analytics show doubles | auto (ship-cycle) |
| A-3 Section eligibility | Leaf sections with ≥ `LEARNY_QUIZ_MIN_SECTION_CHARS` (default 200) of text | Avoid degenerate items from stub sections | auto (ship-cycle) |
| A-4 Reviewing not-yet-due active items | Allowed (cramming); FSRS handles early review via `review_datetime` | Anki permits it; blocking adds state for no benefit | auto (ship-cycle) |
| A-5 Cloze shape | Single-mask cloze: `question` = passage sentence with the masked span replaced by `____`, `answer` = the masked span | Uniform (question, answer) schema for both types; multi-mask deferred | auto (ship-cycle) |
| A-6 Due-queue order | `ORDER BY due ASC, id ASC` (deterministic); no server-side shuffle | Testable; FSRS fuzzing already spreads due dates (interleaving for free) | auto (ship-cycle) |

**Open questions:** none — all resolved or logged above.

## User Stories

### P1: Generate a grounded quiz deck ⭐ MVP

As a reader, I want Learny to generate a quiz deck for a book I ingested so that I can practice active recall on it.

**Acceptance Criteria**

1. (QUIZ-01) WHEN migration 0008 is applied THEN the DB SHALL contain `quiz_items`, `quiz_item_scheduling`, `review_log`, `quiz_generation_jobs` per design.md §Schema, and `alembic downgrade` SHALL cleanly remove them (migration round-trip test passes).
2. (QUIZ-02) WHEN deck generation produces an item whose `content_key` (SHA-256 of normalized `question`+`answer`) already exists for that source THEN the system SHALL upsert content fields onto the existing row and SHALL NOT modify its `quiz_item_scheduling` row or `review_log` rows.
3. (QUIZ-03) WHEN `POST /api/sources/{id}/quiz/deck` is called by the owner on a source with corpus-ready status THEN the system SHALL create a `quiz_generation_jobs` row (status `queued`) and enqueue the deck Celery task after commit, returning 202 with the job view.
4. (QUIZ-04) WHEN a deck job is already `queued` or `running` for that source THEN a second `POST .../quiz/deck` SHALL return 409.
5. (QUIZ-05) WHEN the deck task runs with `LEARNY_GENERATION_PROVIDER=local` THEN the deterministic quiz adapter SHALL produce items offline (no network) so the full pipeline is CI-testable; WHEN provider is `anthropic` THEN the adapter SHALL submit one Message Batches request per eligible section on `LEARNY_QUIZ_MODEL` (default `claude-haiku-4-5`) with structured outputs constraining `source_chunk_id` to the section's chunk ids, and a poll task SHALL re-schedule itself until the batch ends, then persist results. 
6. (QUIZ-06) WHEN a candidate item's `anchor_quote` does not appear verbatim (whitespace-normalized) in the referenced chunk's text THEN the item SHALL be discarded (not persisted); accepted items SHALL store `anchor`, `section_path`, `source_excerpt` (the verified quote), and `chunk_hash`.
7. (QUIZ-07) WHEN a candidate cloze item's masked span does not appear in its `anchor_quote` THEN the item SHALL be discarded.
8. (QUIZ-08) WHEN a candidate's embedding cosine similarity to an already-accepted item in the same source is ≥ `LEARNY_QUIZ_DEDUP_THRESHOLD` (default 0.90, via `EmbeddingPort` on `question + answer`) THEN the candidate SHALL be discarded.
9. (QUIZ-09) WHEN the deck task completes THEN the job row SHALL be `succeeded` with generated/discarded counts recorded, each persisted item SHALL have a `quiz_item_scheduling` row with FSRS initial state (`due` = now, state Learning), and re-running the task for the same source SHALL be idempotent (upserts, no scheduling resets); WHEN the task fails after retries THEN the job SHALL be `failed` with `last_error` set.
10. (QUIZ-10) WHEN generation runs THEN item candidates SHALL be typed `free_recall` or `cloze` only; no MCQ fields exist anywhere in schema or ports.

**Independent test:** with the golden EPUB ingested and provider `local`, POST deck → poll job → items exist, all grounded, dedup + scheduling rows present.

### P1: Review due items with FSRS scheduling ⭐ MVP

As a learner, I want a due queue and 4-button grading so that my reviews are scheduled by FSRS.

**Acceptance Criteria**

11. (QUIZ-11) `SchedulingPort` SHALL expose initial-state creation and `review(scheduling_snapshot, rating 1-4, reviewed_at) → (new snapshot, log entry)`; the py-fsrs adapter SHALL use FSRS-6 defaults (`desired_retention=0.9`, default learning steps, `maximum_interval=36500`), with fuzzing controlled by `LEARNY_FSRS_FUZZING` (default true, false in tests); scheduling snapshots persist as real columns (`state, step, stability, difficulty, due, last_review`).
12. (QUIZ-12) WHEN `POST /api/quiz-items/{id}/reviews` is called by the owner with rating ∈ {1,2,3,4} on an `active` item THEN the system SHALL atomically update `quiz_item_scheduling` and append a `review_log` row (rating, reviewed_at, optional `review_duration_ms`), returning the updated scheduling view; rating outside 1–4 SHALL return 422; item status `stale`/`orphaned` SHALL return 409.
13. (QUIZ-13) WHEN `GET /api/reviews/due` is called THEN the system SHALL return the caller's `active` items with `due <= now` across all their sources (optional `source_id` filter), ordered per A-6, with `limit` (default 20, max 100) and total due count.
14. (QUIZ-14) WHEN `GET /api/sources/{id}/quiz` is called by the owner THEN the system SHALL return the source's items (id, type, question, status, due) plus latest deck job state and counts by status — the polling target for deck progress.

**Independent test:** seed items via deterministic deck; GET due → review each with each rating → scheduling advances (due moves forward for Good/Easy), log rows appended.

### P1: Citations + re-ingest survival ⭐ MVP

As a learner, I want every quiz item tied to its passage and to survive book re-ingestion so that trust and progress are never lost.

**Acceptance Criteria**

15. (QUIZ-15) WHEN a review card is revealed THEN the response/view SHALL include the citation (section_path, anchor, source_excerpt) and the reader link resolves `anchor` via the existing section endpoint; WHEN the anchor no longer resolves THEN the UI SHALL show the snapshotted `source_excerpt` with a "source changed" indication.
16. (QUIZ-16) WHEN a source is re-ingested THEN a reconciliation step (after corpus replace, same pipeline) SHALL, per item: keep `active` when the anchor exists and `source_excerpt` is still present in the section's text; mark `stale` when the anchor exists but the quote is gone; relocate (update anchor, keep `active`) when the quote is found verbatim elsewhere in the new corpus; else mark `orphaned`. `quiz_item_scheduling` and `review_log` rows SHALL never be modified or deleted by reconciliation.
17. (QUIZ-17) WHEN items are `stale` or `orphaned` THEN they SHALL be excluded from `GET /api/reviews/due` but included (with status) in `GET /api/sources/{id}/quiz`.

**Independent test:** ingest golden book, generate deck, review one item, re-ingest a mutated EPUB → statuses split as designed, scheduling/log untouched.

### P1: Ownership, auth, limits ⭐ MVP

18. (QUIZ-18) All quiz endpoints SHALL require authentication (401 otherwise); non-owner or missing resources SHALL return 404 (no existence disclosure); state-changing endpoints (`deck`, `reviews`) SHALL enforce origin + CSRF and a new `rate_limit_quiz` (429 over limit).

### P1: Review UI ⭐ MVP

19. (QUIZ-19) The frontend SHALL provide a review screen: due queue entry (global `/review` route + per-source entry), card showing the question (cloze rendered with blank), a Reveal action showing answer + citation footnote with "Open in book" navigation, a 4-button grade bar (Again/Hard/Good/Easy) that submits the review and advances, and an end-of-session summary (counts per rating).
20. (QUIZ-20) The library/source UI SHALL offer "Generate quiz deck" with in-progress (polling per AD-070 pattern) / failed / done states and show item + due counts and stale/orphaned badges.
21. (QUIZ-21) New frontend clients (`lib/quiz.ts`) and screens SHALL have vitest coverage per repo conventions (fetchImpl-injected client tests; jsdom component tests).

### P2: Anki export

22. (QUIZ-22) WHEN `GET /api/sources/{id}/quiz/export` is called by the owner and items exist THEN the system SHALL stream a genanki-built `.apkg` where each note's GUID derives from (source_id, content_key) so re-import updates in place; free_recall → Basic-style model, cloze → Cloze model; each note carries the citation footnote (book title + section path). 404 when no items.

### P2: Quiz evals

23. (QUIZ-23) A deterministic quiz eval SHALL run in the PR suite: over the golden book + deterministic adapter, assert 100% groundedness (excerpt containment in chunk), cloze mask validity, and anchor resolvability of persisted items.
24. (QUIZ-24) An answerability round-trip judge eval (`@pytest.mark.live and eval`) SHALL score whether items are answerable from their cited excerpt alone (structured-outputs judge on `LEARNY_JUDGE_MODEL`, versioned prompt file, JSONL results), picked up by the existing nightly `eval.yml`.

### P2: ADR

25. (QUIZ-25) ADR-0021 "Active recall design" (free-recall/cloze, FSRS-6 via py-fsrs, snapshot/reconciliation model, Batch API pipeline, genanki export) SHALL be added as Accepted, cross-referencing RFC-002.

## Edge Cases

- WHEN a source has no corpus or ingestion is not ready THEN deck POST SHALL return 409 with a clear error.
- WHEN no sections are eligible (A-3) THEN the job SHALL succeed with zero items and the UI SHALL show an empty-deck message.
- WHEN the Anthropic batch has per-request errors THEN failed sections are recorded in job counts; successful sections persist (partial success, job `succeeded` with discard/failure counts).
- WHEN the batch does not end within `LEARNY_QUIZ_BATCH_TIMEOUT_S` (default 3600) THEN the poll task SHALL mark the job `failed` with a timeout error.
- WHEN a due-queue `limit` exceeds the max THEN 422.
- WHEN structured output fails schema validation THEN that section's candidates are discarded and counted, never persisted.

## Requirement Traceability

| ID | Story | Phase | Status |
|---|---|---|---|
| QUIZ-01..02 | Deck schema | A (A2), B (B1) | Verified |
| QUIZ-03..10 | Deck generation | A–C | Verified |
| QUIZ-11..14 | Review + due queue | D | Verified |
| QUIZ-15..17 | Citations + reconciliation | C (C3), E (E2) | Verified |
| QUIZ-18 | AuthZ/limits | D (D3) | Verified |
| QUIZ-19..21 | Review UI | E | Verified |
| QUIZ-22 | Anki export | D (D4) | Verified |
| QUIZ-23..24 | Evals | F | Verified |
| QUIZ-25 | ADR | F (F3) | Verified |

**Coverage:** 25 total, mapped to phases in tasks.md.

## Implicit-Requirement Dimensions Sweep (Complex — all dimensions)

| Dimension | Resolution |
|---|---|
| Input validation & bounds | QUIZ-12 (rating), QUIZ-13 (limit caps), A-1/A-3 caps, structured-output schema validation (edge case) |
| Failure / partial-failure | QUIZ-09 (job failed + last_error), batch partial-success + timeout edge cases |
| Idempotency / retry / dedup | QUIZ-02 (content_key upsert), QUIZ-08 (embedding dedup), QUIZ-09 (idempotent re-run), A-2 (review submits — logged assumption) |
| Auth boundaries & rate limits | QUIZ-18 |
| Concurrency / ordering | QUIZ-04 (single in-flight job), A-6 (deterministic order); concurrent reviews: last-write-wins on scheduling, both logged (append-only) |
| Data lifecycle / expiry | QUIZ-16 (never delete review state); source deletion cascades quiz rows (owner deleted the book) |
| Observability | Deck task uses the existing trace-scope + structured logging pattern; job rows carry counts/last_error (N/A beyond this — no new metrics surface this cycle, consistent with AD-041) |
| External-dependency failure | QUIZ-05/09 + batch edge cases; `local` provider is the CI/offline default (no keys required) |
| State-transition integrity | QUIZ-16 status transitions; QUIZ-12 (409 on non-active review); job status machine queued→running→succeeded/failed |

## Success Criteria

- [ ] Full offline demo: golden EPUB → deck → due queue → 4-button reviews → summary, with zero network.
- [ ] All 25 QUIZ ACs verified; backend + frontend gates green; migration round-trips.
- [ ] Re-ingest demo preserves scheduling for kept items and never loses review history.
