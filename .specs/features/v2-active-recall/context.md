# v2-active-recall — Context & Decisions (RFC-002 Cycle E)

Gray areas resolved via the ship-cycle auto-decision protocol (options formulated with
why-recommend AND why-not; recommended option chosen; auditable here + STATE.md AD rows).
Escalation rule checked for each: none changes product direction beyond the cycle (RFC-002
Cycle E names the scope; the two research docs carry the trade-off evidence), the only new
external dependencies are specialized edge libraries (py-fsrs, genanki — permitted by
ADR-0009's "specialized libraries at edges" rule; the generation provider was ratified in
ADR-0020), and every decision has a clear defensible recommendation — no user prompt required.

## D-1 — Scope: full vertical slice + two edge libraries (→ AD-072)

- **Chosen:** Ship RFC-002 Cycle E whole: schema (4 tables), ports/adapters, Celery deck
  pipeline, review endpoints, review UI, genanki `.apkg` export, PR + nightly evals,
  ADR-0021. New deps: `fsrs>=6,<7` (py-fsrs, MIT), `genanki` (MIT) — both deterministic,
  network-free edge libraries behind Learny-owned code.
- **Why:** the flagship cycle; splitting it leaves either an unreviewable backend-only
  slice (7th in a row) or a UI over nothing. Full slice restores AD-010 cadence and the
  RFC costed it as one cycle.
- **Why not backend-first split:** review flow is the product value; without UI the FSRS
  loop is untestable by a human and the merge gate would flag another partial slice.
- **Why not deferring export/evals:** RFC lists both in-cycle; evals are a durable
  project principle ("citations, evaluation, traceability are core, not late polish").

## D-2 — Schema: content/scheduling/history split, ownership via source (→ AD-073)

- **Chosen:** `quiz_items` (content + citation snapshot + `content_key` + status
  active|stale|orphaned) / `quiz_item_scheduling` (1:1, real FSRS columns, indexed `due`)
  / `review_log` (append-only) / `quiz_generation_jobs` (deck job state, mirrors
  `ingestion_jobs`). Ownership via `source_id` FK only (AD-014 — no `user_id` on child
  entities); **no FK to `corpus_chunks`** (chunk ids are regenerated on re-ingest —
  replace() is delete-then-insert), citation lives as anchor + section_path +
  source_excerpt + chunk_hash snapshot (teaching-turn precedent, AD-033). Upsert on
  `(source_id, content_key)` preserves scheduling. No distractor columns (locked v2
  decision; `generation_meta` JSONB absorbs future metadata).
- **Why:** the Anki-validated content/scheduling/history split is the research's core
  recommendation; real columns keep `WHERE due <= now()` indexable; the jobs table reuses
  the proven ingestion-jobs pattern for progress/failure visibility (Postgres = source of
  truth).
- **Why not user_id on quiz tables (research sketch):** violates AD-014; source join is
  the established ownership path.
- **Why not FK to corpus_chunks:** re-ingest would cascade-delete or orphan every item —
  exactly the failure the snapshot pattern exists to prevent.
- **Why not JSONB card state / py-fsrs to_dict():** unindexable due query; migration pain
  later.

## D-3 — Generation: Haiku structured outputs + deterministic QC (→ AD-074)

- **Chosen:** `QuizGenerationPort` with a deterministic `local` adapter (CI default) and
  an Anthropic adapter on `LEARNY_QUIZ_MODEL` (default `claude-haiku-4-5`), selected by the
  existing `LEARNY_GENERATION_PROVIDER` switch. Structured outputs per the `judge.py`
  pattern (citations API and structured outputs are mutually exclusive — adapter models on
  the judge, not the answer adapter): JSON schema with `source_chunk_id` enum restricted to
  the section's chunk ids, `anchor_quote` required verbatim. QC is deterministic and
  server-side: quote containment (whitespace-normalized), cloze-mask-in-quote, length caps,
  embedding dedup ≥0.90 via existing `EmbeddingPort`, `content_key` exact dedup. Item
  types: `free_recall` + single-mask `cloze` (A-5). Discard, never repair.
- **Why:** verbatim-quote-then-verify is the highest-leverage grounding trick (no second
  LLM call); enum-constrained chunk ids make citations structurally valid; Haiku is the
  RFC's costed model for this workload; reusing the provider switch keeps one offline
  toggle for CI.
- **Why not citations API for generation:** mutually exclusive with structured outputs;
  quiz items need schema-shaped output more than span citations — the quote check covers
  grounding.
- **Why not a separate LEARNY_QUIZ_PROVIDER:** another knob with no divergent use case;
  provider direction is already ratified (ADR-0020).
- **Why not LLM critique pass (Savaal rubric) in-cycle:** a second model pass doubles cost
  and latency for uncertain gain at MVP; the nightly answerability judge (D-9) is the
  quality sensor. Recorded as a future upgrade in ADR-0021.

## D-4 — Deck pipeline: Batch API behind a deck-shaped port (→ AD-075)

- **Chosen:** Port shape `begin_deck(sections) → DeckHandle` / `collect_deck(handle) →
  pending | results`. Local adapter returns results synchronously; Anthropic adapter
  submits one Message Batches request per eligible section and `collect_deck` polls. Celery:
  `generate_quiz_deck` task creates/upserts the job row, begins the deck, and a poll task
  re-schedules itself (countdown, bounded by `LEARNY_QUIZ_BATCH_TIMEOUT_S`, default 3600)
  until the batch ends, then validates/dedups/persists. One in-flight job per source (409).
  Partial per-section failures are counted, not fatal.
- **Why:** deck generation is offline-by-nature; Batch API halves token cost (the RFC's
  ~$1.80/book figure assumes it); the two-method port keeps batch semantics out of the
  domain (local adapter never fakes async).
- **Why not synchronous per-section Messages calls:** 2× cost on the highest-volume
  generation workload; long-running task holds a worker slot for the whole book.
- **Why not a per-section port (batch as adapter internal magic):** `generate_items(section)`
  forces the adapter to either block on the whole batch per call or maintain hidden global
  state — both worse than an honest deck-level contract.

## D-5 — Scheduling: py-fsrs behind SchedulingPort (→ AD-076)

- **Chosen:** `SchedulingPort` (initial state + `review(snapshot, rating, at)`), py-fsrs
  adapter with FSRS-6 defaults: `desired_retention=0.9`, default learning steps,
  `maximum_interval=36500`, fuzzing on in prod / off under test via `LEARNY_FSRS_FUZZING`.
  Ratings 1–4 map 1:1 to Again/Hard/Good/Easy. New items start due-now (Learning). Review
  updates scheduling + appends log atomically. No idempotency key (A-2). Early review
  allowed (A-4).
- **Why:** py-fsrs is the maintainer-org implementation of the algorithm Anki ships;
  deterministic and network-free (matches the deterministic-adapter house style);
  inventing scheduling math in-house is the one clearly wrong option.
- **Why not optimizer now:** pulls torch/pandas; defaults are what every new Anki user
  runs; needs months of review history to pay off.
- **Why not custom rating scales/auto-grading:** FSRS weights are trained on the 4-button
  self-grade signal; free-recall reveal-then-self-grade is the format the evidence backs.

## D-6 — API surface (→ AD-077)

- **Chosen:** `POST /api/sources/{id}/quiz/deck` (202, job view), `GET
  /api/sources/{id}/quiz` (items + job state + counts; deck-progress polling target),
  `GET /api/reviews/due` (cross-source, optional `source_id` filter, limit default 20 max
  100), `POST /api/quiz-items/{id}/reviews` (rating 1–4), `GET
  /api/sources/{id}/quiz/export` (.apkg). Ownership via parent source everywhere; 404
  non-disclosure; origin+CSRF+`rate_limit_quiz` on the two state-changing routes.
- **Why:** mirrors every existing router convention (AD-014, AD-067 semantics); a global
  due queue is how SRS is actually used (interleaving across books for free) while
  deck/list/export stay source-scoped.
- **Why not source-scoped-only due queue:** forces per-book review sessions, losing the
  cross-book interleaving the research calls a free win; the user-scoped join through
  sources keeps the ownership rule intact.

## D-7 — Re-ingest reconciliation (→ AD-078)

- **Chosen:** A reconciliation step inside the existing ingestion pipeline, after corpus
  replace: per item — anchor exists ∧ excerpt present → keep; anchor exists ∧ excerpt gone
  → `stale`; anchor gone ∧ excerpt found verbatim elsewhere → relocate (update anchor,
  keep active); else `orphaned`. Scheduling + review_log are never modified or deleted.
  Stale/orphaned drop out of the due queue but stay listed.
- **Why:** FSRS state describes the user's memory, not the document (research §5, Anki
  GUID principle); running inside `run_ingestion` reuses its job/retry/trace machinery and
  guarantees reconciliation is never skipped.
- **Why not delete-and-regenerate on re-ingest:** destroys scheduling/history — the
  explicit failure mode this design exists to prevent.
- **Why not a separate user-triggered reconcile task:** re-ingest is the only event that
  invalidates anchors; making it manual guarantees it gets forgotten.

## D-8 — Review UI (→ AD-079)

- **Chosen:** Global `/review` route (due queue across books) + per-source entry points;
  card flow: question (cloze rendered with blank) → Reveal → answer + citation footnote
  ("Open in book" → existing reader anchor navigation; snapshot excerpt + "source changed"
  note when the anchor no longer resolves) → 4-button grade bar → auto-advance →
  session summary (counts per rating). Library/source UI gains "Generate quiz deck" with
  the AD-070 3s-polling pattern against `GET .../quiz`. Plain fetch clients (`lib/quiz.ts`)
  — no streaming (reviews are request/response). shadcn components only; tests per AD-071
  conventions.
- **Why:** Anki-shaped reveal-then-grade is the flow FSRS is trained on and users know;
  reusing reader navigation closes the citation loop this product is about.
- **Why not streaming/useChat for reviews:** nothing streams; `useChat` adds state
  machinery for a fetch-shaped interaction.
- **Why not a per-book-only review page:** loses interleaving (see D-6).

## D-9 — Evals: deterministic PR gate + nightly answerability judge (→ AD-080)

- **Chosen:** PR-suite deterministic eval over golden book + local adapter: 100%
  groundedness (excerpt containment), cloze mask validity, anchor resolvability. Nightly
  (`live and eval`, existing `eval.yml`): answerability round-trip judge — can the item be
  answered from its cited excerpt alone — structured outputs on `LEARNY_JUDGE_MODEL`,
  versioned prompt file, JSONL results (judge.py house pattern). Replaces the dropped
  distractor checks per followup research.
- **Why:** deterministic checks are free and binary (the golden-fixtures principle,
  AD-036); answerability is the one quality axis that needs a model and it maps to the
  Savaal groundedness/objectivity rubric.
- **Why not judge-as-PR-gate:** nightly-signal-never-PR-gate is the calibrated AD-063
  position; no reason to diverge.

## D-10 — Anki export: genanki .apkg with content_key GUIDs (→ AD-081)

- **Chosen:** `GET /api/sources/{id}/quiz/export` streams a genanki-built `.apkg`; note
  GUID = stable digest of (source_id, content_key) so re-import updates in place; Basic
  model for free_recall, Cloze model for cloze; citation footnote (book title + section
  path) on every note.
- **Why:** .apkg is the lossless Anki path and GUID stability is exactly the Anki-native
  upsert identity the research recommends; genanki is the de-facto MIT library, pure
  Python, edge-only.
- **Why not CSV:** loses note identity (re-import duplicates), loses cloze typing, saves
  one small dependency for a worse artifact.

### Agent's Discretion

Prompt wording for quiz generation, exact Pydantic view shapes, shadcn component
composition, eval case counts, and genanki model IDs/templates — within the decisions
above.

### Declined / Undiscussed Gray Areas → Assumptions

All resolved above or logged as A-1..A-6 in spec.md (ship-cycle auto-decision mode — no
user discussion round).

## Specific References

Anki reveal-then-grade review loop; Anki GUID import semantics; Savaal rubric for the
judge prompt; existing Learny patterns AD-014/AD-033/AD-070/AD-071 and `judge.py`
structured outputs.

## Deferred Ideas

FSRS optimizer (per-user weights, Celery beat); LLM critique pass at generation time
(Savaal 3-stage); MCQ exam-prep mode with mandatory feedback; user suspend/dismiss +
item editing; shared decks; multi-mask cloze; review-submit idempotency keys.
