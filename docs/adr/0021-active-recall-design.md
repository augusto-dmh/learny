# ADR-021: Active Recall Design (Free-Recall/Cloze Quizzes With FSRS-6 Scheduling)

- **Date**: 2026-07-16
- **Status**: Accepted
- **Deciders**: Augusto, Codex
- **Tags**: architecture, ai, quizzes, spaced-repetition, fsrs, citations, anthropic, evaluation

## Context and Problem Statement

Learny ingests books and answers or teaches with citations (ADR-0010/0020), but
nothing closes the learning loop: readers forget what they read. RFC-002 Cycle E
adds the flagship retention feature — citation-grounded quiz items generated per
book section, scheduled for review with spaced repetition — while keeping every
item traceable to an exact passage and never destroying a learner's review history.

The decisions to make are: what *kind* of quiz item to generate; how to schedule
reviews; how to lay out the schema so content regeneration never disturbs progress;
how to keep items grounded when a book is re-ingested and its corpus ids change; how
to run generation against a real provider affordably; and how to let a learner take
their deck elsewhere.

Research evidence: `docs/research/2026-07-12/active-recall-srs.md`,
`docs/research/2026-07-12/followup-quiz-item-format.md`.

## Decision Drivers

- Highest-evidence retention per unit of build effort (active recall + spaced
  repetition), not recognition.
- Every item traceable to a verbatim passage; grounding enforced by Learny, never
  trusted from the provider (ADR-0003).
- A learner's scheduling and review history are sacred: regenerating or re-ingesting
  content must never reset or delete them.
- Keep the provider SDK and model names behind Learny-owned ports (ADR-0007/0009);
  keep CI and local development offline and key-free.
- Keep operating cost negligible at hobby scale.

## Considered Options

- **Item format**: free-recall + cloze (self-graded) vs. adding multiple-choice
  questions with distractors.
- **Scheduler**: FSRS-6 via `py-fsrs` defaults vs. a classic SM-2 interval scheme
  vs. FSRS with the parameter optimizer enabled from day one.
- **Generation transport**: Anthropic Message Batches with structured outputs vs.
  synchronous per-section calls.
- **Re-ingest handling**: snapshot + reconcile (keep/stale/relocate/orphan) vs. an
  FK to corpus chunks vs. regenerating the whole deck.
- **Export**: genanki `.apkg` vs. CSV.

## Decision Outcome

Chosen option: **free-recall and cloze items only, self-graded on a 4-button scale
and scheduled by FSRS-6 (`py-fsrs` defaults) behind a Learny `SchedulingPort`, with
every item grounded in a server-verified verbatim quote, a content/scheduling/history
schema split that lets content upsert without touching progress, snapshot-based
re-ingest reconciliation that never modifies scheduling or review history, batched
Haiku generation with structured outputs, and genanki `.apkg` export with stable
GUIDs.** The pieces:

1. **Item types: free-recall and cloze only — no MCQ, no distractors, anywhere in the
   schema or the ports.** FSRS is trained on recall ratings; recognition (MCQ) adds no
   retention benefit in the RCT evidence and its distractors are ungroundable — the
   single biggest LLM quality/faithfulness risk (followup-quiz-item-format). A cloze
   item is single-mask: the `question` is the passage sentence with the masked span
   replaced by `____` and the `answer` is that span, so both types share one
   `(question, answer)` shape.

2. **Scheduling: FSRS-6 via `py-fsrs` behind `SchedulingPort`.** The port exposes
   `initial()` and `review(snapshot, rating 1-4, reviewed_at)`; the adapter wraps one
   `fsrs.Scheduler` with population defaults (`desired_retention=0.9`, default learning
   steps, `maximum_interval=36500`). Fuzzing is on in production and off in tests
   (`LEARNY_FSRS_FUZZING`) so scheduling assertions test monotonic behavior, not exact
   intervals. Snapshots persist as real columns (`state, step, stability, difficulty,
   due, last_review`), all UTC.

3. **Schema split: content, scheduling, and history are three tables.** `quiz_items`
   holds content plus its citation snapshot; `quiz_item_scheduling` holds the FSRS
   state; `review_log` is an append-only grade history. Item identity is
   `(source_id, content_key)` where `content_key = sha256(item_type · norm(question) ·
   norm(answer))`; regenerating an existing item **upserts its content fields only and
   never touches its scheduling or review-log rows** — the cardinal invariant of this
   cycle. `content_key` includes `item_type` so a free-recall and a cloze item derived
   from the same sentence never collide.

4. **Grounding is server-verified and snapshotted.** A candidate is persisted only
   when its `anchor_quote` appears verbatim (whitespace/case-normalized) in the chunk
   it cites; a cloze's masked span must appear in that quote and the question must carry
   the blank. Accepted items snapshot `anchor`, `section_path`, `source_excerpt` (the
   verified quote), and `chunk_hash` — with **no foreign key to the corpus tables**,
   because re-ingestion replaces chunk ids. The provider is never trusted to
   self-police; the same QC pipeline runs regardless of adapter.

5. **Generation: Anthropic Message Batches on `claude-haiku-4-5` with structured
   outputs.** The `anthropic` adapter submits one batch request per eligible leaf
   section, each a single structured-output message whose json_schema constrains
   `source_chunk_id` to that section's chunk ids; a poll task re-schedules itself until
   the batch ends, then maps results by `custom_id`. Verified at install
   (`anthropic==0.116`): `messages.batches.create` accepts `output_config`, so
   structured outputs are legal inside a batch and the documented prompt-JSON fallback
   was not needed. Per-request errors count as failed sections (partial success). The
   deterministic `local` adapter is the CI/offline default, so the whole pipeline is
   testable with no key.

6. **Duplicate suppression via embeddings.** A candidate whose embedding cosine
   similarity to an already-accepted item in the same source is ≥
   `LEARNY_QUIZ_DEDUP_THRESHOLD` (default 0.90, `EmbeddingPort` over `question + answer`)
   is discarded. The dedup embedding is stored on the item so regeneration does not
   re-embed the back-catalog.

7. **Re-ingest reconciliation: keep / stale / relocate / orphan, progress untouched.**
   After a corpus replace, a reconciliation step compares each item's snapshotted
   `source_excerpt` against the new corpus: anchor present and quote still there → keep
   `active`; anchor present but quote gone → `stale`; anchor gone but quote found
   verbatim elsewhere → relocate (adopt the new anchor/section_path, stay `active`);
   otherwise → `orphaned`. It writes only `anchor`/`section_path`/`status` and **never
   modifies or deletes `quiz_item_scheduling` or `review_log`**. Stale/orphaned items
   are excluded from the due queue but still listed with their status.

8. **Export: genanki `.apkg` with stable GUIDs.** Each note's GUID derives from
   `(source_id, content_key)` so re-import updates in place rather than duplicating;
   free-recall maps to a Basic model, cloze to a Cloze model, each carrying the citation
   footnote. Stale/orphaned items are exported too (still valid learning material),
   footnoted as such.

Settings are `LEARNY_`-prefixed and swappable (`quiz_model`, `quiz_min_section_chars`,
`quiz_dedup_threshold`, batch timeout/poll, `fsrs_desired_retention`, `fsrs_fuzzing`).
Provider keys stay environment-only.

### Positive Consequences

- The learning loop closes with the highest-evidence method, and every card is
  traceable to an exact passage a reader can open in the book.
- Regeneration and re-ingestion are safe by construction: content can change freely
  while scheduling and review history are structurally protected.
- The provider stays behind ports; batched Haiku keeps generation cheap and the
  deterministic adapter keeps CI offline and key-free.
- A learner can export to Anki without losing card identity across re-exports.

### Negative Consequences

- Self-graded recall depends on learner honesty (no objective correctness signal);
  accepted as inherent to active recall and cheaper than ungroundable auto-grading.
- FSRS runs on population defaults, not per-user-optimized parameters, so early
  intervals are approximate until enough reviews accrue (optimizer deferred).
- Batch generation is asynchronous (submit → poll), adding a polling task and a
  timeout path the worker must manage.
- A bag-of-tokens local embedding makes a section's free-recall and cloze items near
  duplicates, so one may be dedup-discarded offline; the groundedness eval therefore
  asserts invariants over persisted items, not fixed per-section counts.

## Pros and Cons of the Options

### Free-recall + cloze, self-graded, FSRS-6 ✅ Chosen

- ✅ Recall + spaced repetition is the highest-evidence retention intervention;
  ratings feed FSRS directly.
- ✅ Both item types are groundable in a verbatim span and share one schema.
- ❌ No objective grade — relies on learner self-assessment.

### Add multiple-choice questions with distractors ❌ Rejected

- ✅ Objective grading; familiar format.
- ❌ Recognition adds no measured retention benefit over recall; distractors are
  ungroundable and the largest LLM faithfulness risk. Excluded from schema and ports
  entirely (followup-quiz-item-format).

### Classic SM-2 / FSRS optimizer from day one ❌ Rejected / Deferred

- ✅ SM-2 is simple; the optimizer fits parameters to the individual.
- ❌ FSRS-6 outperforms SM-2 on the same ratings; the optimizer (`fsrs[optimizer]`,
  torch) only pays off after hundreds of reviews and adds a heavy dependency. Deferred
  until the review volume justifies it.

### An LLM critique/verification pass over generated items ❌ Deferred

- ✅ Could catch subtly weak items the deterministic QC accepts.
- ❌ Server-side verbatim grounding + cloze-mask + dedup already reject the failure
  modes that matter, at zero extra token cost; a critique pass doubles generation cost
  for unproven marginal quality. Deferred.

### CSV export ❌ Rejected

- ✅ Trivially simple.
- ❌ Loses card identity: re-import duplicates rather than updates, and cloze/citation
  structure is flattened. genanki `.apkg` with GUID-stable notes preserves identity.

## References

- [ADR-003: Citations And Evaluation Are Core Requirements](0003-citations-and-evaluation-are-core-requirements.md)
- [ADR-007: Use Learny-Owned Ports For AI Provider Integration](0007-use-learny-owned-ports-for-ai-provider-integration.md)
- [ADR-009: Use Learny-Owned Orchestration With Specialized Edge Libraries](0009-use-learny-owned-orchestration-with-specialized-edge-libraries.md)
- [ADR-016: Use Golden Fixtures For MVP Evaluation](0016-use-golden-fixtures-for-mvp-evaluation.md)
- [ADR-019: Use OpenAI Embeddings With Per-Chunk Model Versioning](0019-use-openai-embeddings-with-per-chunk-model-versioning.md)
- [ADR-020: Use Anthropic Claude For Cited Answer And Teaching Generation](0020-use-anthropic-claude-for-generation.md)
- [RFC-002: Learny v2 Roadmap](../rfc/0002-learny-v2-roadmap.md)
- Active recall & spaced-repetition research (2026-07-12): `../research/2026-07-12/active-recall-srs.md`
- Quiz item-format research (2026-07-12): `../research/2026-07-12/followup-quiz-item-format.md`
- Anthropic Message Batches guide: https://platform.claude.com/docs/en/build-with-claude/batch-processing
- Anthropic Structured Outputs guide: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- py-fsrs: https://github.com/open-spaced-repetition/py-fsrs
