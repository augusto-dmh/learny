# v4-capture-pipeline — Decision Context

Auto-decided per the learny-ship-cycle autonomy contract (recommended option chosen, full
option set recorded for audit). None met the escalation rule: no product-direction change
beyond the cycle (RFC-004 Cycle D and ADR-026 are both accepted), no new provider or
dependency (Anthropic is already the accepted generation provider per ADR-0020, and the quiz
model setting already exists), and every decision has a defensible recommendation.

## D-0 — Cycle ordering: RFC-004 D before RFC-003 F (AD-133)

- **(a) Run `v4-capture-pipeline` (RFC-004 D) now, `v3-notes-loop` (RFC-003 F) next — CHOSEN.**
  Why: RFC-004 §"Sequencing against RFC-003" says F waits for Cycle C "(ideally D)", and
  Cycle D's own entry says it "completes the review-provenance half of the RFC-003 Cycle F
  unblock"; F also carries an open follow-up ("scope confirmation against the shipped reader
  surfaces") that D's surfaces settle. Why not: RFC-003's table lists F above the v4 rows, so
  a reader scanning top-down sees F first — mitigated by this record and the ROADMAP note.
- (b) Run F now. Why: finishes RFC-003 and reaches v0.3.0 sooner. Why not: F would build
  note→quiz promotion on top of an identity/provenance foundation that does not exist yet,
  which either duplicates D's work or forces D to retrofit F's rows.

## D-1 — Quote-scoped generation transport → synchronous port method (AD-134)

- **(a) New `suggest_cards(section, quote, limit)` on `QuizGenerationPort`, called
  synchronously from a request handler; local adapter computes inline, Anthropic adapter
  issues a single Messages call with the existing structured-output schema — CHOSEN.**
  Why: the interaction is foreground — the student is staring at the popover — and the batch
  path's SLA is measured in hours; a single-quote request is one small call, so the batching
  economics that justified `begin_deck`/`collect_deck` (AD-075) simply do not apply. The
  structured-output schema and the `source_chunk_id` enum grounding constraint are reused
  as-is. Why not: adds a third generation call site and the first *synchronous* LLM call in a
  request handler — bounded by the existing `generation_max_tokens`, the 3-suggestion cap, and
  `rate_limit_quiz`.
- (b) Reuse `begin_deck`/`collect_deck` with a synthesized single-section list, driven through
  Celery + polling. Why: zero port change, identical machinery. Why not: Message Batches are
  asynchronous by construction — the student would wait on a poll loop for a card they asked
  for a moment ago; it also mints a `quiz_generation_jobs` row per highlight.
- (c) Client-side generation via the existing streaming answer endpoint with a prompt asking
  for cards. Why: no backend change at all. Why not: bypasses every QC guarantee (AD-074) and
  the structured-output contract; the resulting text would need parsing we deliberately do not
  do anywhere else.

## D-2 — Suggestion durability → ephemeral (AD-134)

- **(a) Suggestions are returned to the client and held in component state; only acceptance
  writes a row — CHOSEN.** Why: makes "no silent bulk generation" a structural property rather
  than a policy — nothing exists until the student says so; no suggestion table, no TTL, no
  orphan sweep. Why not: navigating away loses un-accepted suggestions (acceptable — they are
  cheap to regenerate, and persisting them would be exactly the silent accumulation the RFC
  forbids).
- (b) Persist suggestions as `quiz_items` with a `pending` status, accepted = status change.
  Why: survives navigation; reuses the items table. Why not: a fourth status leaks into the
  reconcile ladder, the due queue, the export, and every count — a large blast radius for a
  transient object; and un-accepted rows *are* silent bulk generation by another name.
- (c) Persist to a dedicated `card_suggestions` table. Why: clean separation. Why not: a whole
  table plus lifecycle for data whose useful life is one popover session.

## D-3 — Card identity → partial unique index on origin (AD-135)

- **(a) Add `quiz_items.origin` (`deck` | `highlight`, NOT NULL, default `deck`); replace the
  `(source_id, content_key)` unique constraint with a **partial** unique index
  `WHERE origin = 'deck'`; `highlight`-origin rows are identified by their minted `id` —
  CHOSEN.** Why: this is exactly ADR-026 decision 5 ("creation-minted stable ID… `content_key`
  demoted to a rewritable uniqueness fingerprint") expressed in one index, and it leaves the
  whole-deck upsert path (AD-073) byte-identical. `content_key` stays populated for
  highlight-origin rows so deck generation can still dedup against them. Why not: partial
  unique indexes are easy to overlook when reading the schema — mitigated by an explicit test
  asserting two same-`content_key` highlight rows coexist while two deck rows collapse.
- (b) Drop the unique constraint entirely, dedup in application code. Why: uniform identity.
  Why not: removes the database-level guarantee that makes `upsert` idempotent under Celery
  redelivery — a real correctness property the deck pipeline depends on.
- (c) Separate `highlight_cards` table. Why: cleanest isolation. Why not: forks the due queue,
  scheduling, review log, reconcile, and export in five places; ADR-026 explicitly routes note-
  derived items through "the existing quiz pipeline".

## D-4 — Provenance link → nullable FK to `note_anchors`, SET NULL (AD-136)

- **(a) `quiz_items.note_anchor_id UUID NULL REFERENCES note_anchors(id) ON DELETE SET NULL`,
  with the origin note's title read by join for display — CHOSEN.** Why: typed and
  referentially honest; the cascade direction respects ADR-026's invariant that nothing outside
  the notes aggregate may destroy user prose, and severing the link leaves the card fully
  renderable from its own `source_excerpt`/`anchor` snapshot. Why not: the quiz aggregate now
  holds a foreign key into the notes aggregate — accepted, because the dependency points from
  the derived object to its origin, never the reverse.
- (b) Store provenance untyped in the existing `generation_meta` JSONB. Why: zero migration.
  Why not: "typed provenance" is the literal requirement; a JSONB string cannot be joined for
  the note title and goes stale silently when the note is deleted.
- (c) Denormalize note id + title onto the item. Why: no join at review. Why not: the title
  drifts the moment the note is renamed, and the RFC wants provenance shown at review, which
  means it should be current.

## D-5 — Reconcile semantics → independent, order pinned (AD-137)

- **(a) Highlight-origin cards reconcile through the existing `ReconcileQuizItems` ladder on
  their own anchor + excerpt snapshot, independent of the linked anchor's fate; a test pins the
  current ingestion step order (notes reconcile before quiz) — CHOSEN.** Why: the two
  reconcilers have no ordering contract today, and giving cards a data dependency on note-anchor
  outcomes would create one, coupling two aggregates across an ingestion pipeline. Each object
  carries its own snapshot, so each converges on the same corpus independently. Why not: a card
  and its origin highlight can briefly disagree (card `active`, anchor `orphaned`) — visible
  only in the rail, and self-correcting on the next reconcile.
- (b) Make quiz reconcile read the linked anchor's post-reconcile state and adopt it. Why: one
  consistent answer per passage. Why not: introduces the ordering contract, a cross-aggregate
  join in the ingestion hot path, and a new failure mode when the link is NULL.
- (c) Merge the two reconcilers. Why: one ladder. Why not: far beyond this cycle's boundary and
  would rewrite shipped, verified behaviour (AD-078).

## D-6 — QC and dedup on accept → gate generation, trust the author (AD-138)

- **(a) QC (verbatim containment, cloze-mask validity) filters candidates server-side *before*
  they are returned; on accept, the submitted text is stored as-is and embedding dedup is
  skipped, while the embedding is still computed and stored — CHOSEN.** Why: QC's purpose is
  catching model fabrication (AD-074), which is a property of generated text, not of text the
  student wrote; silently discarding a card the student just chose would be an inexplicable
  no-op. Storing the embedding keeps future deck runs deduping against it. Why not: a student
  can author a near-duplicate card deliberately — which is their prerogative.
- (b) Apply full QC + dedup on accept. Why: uniform quality bar. Why not: an accepted card
  vanishing with no visible cause is the worst failure mode in the flow.
- (c) Skip QC entirely for this path. Why: simplest. Why not: drops the grounding guarantee for
  model-generated text, which is precisely where it is needed.

## D-7 — Rail layout → sibling column, panel wins (AD-139)

- **(a) The rail is a `lg`-and-up flex sibling to the right of the article, hidden while the
  Ask/Teach panel is open; below `lg` it renders after the article as a collapsible region —
  CHOSEN.** Why: composes with the reader's existing three-column flex row; keeps the 65ch
  measure that ADR-027 protects; entries sit in document order and are trivially assertable in
  jsdom. Why not: not true marginalia — entries align to the list, not to their line of text.
- (b) Absolutely-positioned marginalia in the article's right gutter, vertically aligned to each
  painted highlight. Why: this is what "margin rail" most literally evokes. Why not: alignment
  requires real layout measurement, and jsdom reports zero-size boxes for everything — the
  behaviour would be untestable in the suite that gates this repo, which for a cycle whose
  Verifier runs a discrimination sensor is a sensor-blind spot rather than a cosmetic tradeoff.
- (c) Fold the rail into the existing `ReaderPanel` as a third mode. Why: no new column. Why
  not: the rail is ambient context meant to be visible *while* reading, not a mode you switch
  into at the cost of the text.

## D-8 — Rail data → extend the highlights endpoint (AD-140)

- **(a) Extend `GET /api/sources/{id}/highlights` (and `SourceHighlight`) with the origin note's
  title and a has-body flag — CHOSEN.** Why: one owner-scoped query already returns exactly the
  right rows in the right scope; the reader already calls it non-blocking, so the rail costs no
  additional round trip. Why not: widens a DTO the painter also consumes — additive only, and
  the painter ignores the new fields.
- (b) Client-side join of `listNotes()` + `listHighlights()`. Why: no backend change. Why not:
  pulls every note the user owns across every book to label a handful of chapter highlights.
- (c) New dedicated rail endpoint. Why: purpose-built. Why not: a second endpoint returning a
  near-identical row set, kept in sync forever.

## D-9 — Shortcuts → one guarded global listener (AD-141)

- **(a) A `use-key-shortcuts` hook installing a single `window` `keydown` listener, ignoring the
  event when any of Ctrl/Meta/Alt is held or when the target is `input`/`textarea`/
  `contenteditable`; reader keys act only while a selection popover is open; `b` is never bound
  — CHOSEN.** Why: the app has no shortcut precedent, so the guard is the load-bearing part and
  belongs in exactly one place; scoping reader keys to an open popover means a bare letter press
  can never fire an action the student cannot see. Why not: a global listener is easy to leak —
  pinned by an unmount-cleanup test, matching the polling-hook precedent.
- (b) Per-component `onKeyDown` handlers. Why: no global state. Why not: only fires when the
  component holds focus, which the reading article never does; and the input guard would be
  duplicated at each site.
- (c) Adopt a shortcut library. Why: batteries included. Why not: a new dependency for one
  listener and one guard, against the vendored-UI discipline this repo keeps.

## D-10 — Friction budget → assert interaction counts in tests (AD-142)

- **(a) Encode each budgeted path as a test that performs the minimum interactions and asserts
  the outcome, so adding a step breaks the test — CHOSEN.** Why: turns an RFC prose constraint
  into a regression sensor at nearly zero cost, using the RTL patterns already in the suite. Why
  not: counts clicks, not cognitive load — a partial proxy, and honestly labelled as one.
- (b) Document the budget in the RFC only. Why: no test coupling. Why not: unenforced, so it
  decays on the first convenient exception.

## Execution decisions

- Worker-per-phase (5 phases A–E), session model for every worker (v4-B/v4-C precedent);
  Verifier always fresh and always on the session model.
- Full-stack cycle: backend gate = `pytest` on affected modules per task, full backend suite +
  `ruff` at phase boundaries; frontend gate = `vitest` on affected files per task, full frontend
  suite + `tsc` + `build` at phase boundaries.
- The DB-gated suites need `LEARNY_TEST_DATABASE_URL`; per the v4-B handoff, `uv` may be absent
  from PATH — use `backend/.venv/bin/python -m pytest`.

## Deviations

_None yet — recorded here as phases report._
