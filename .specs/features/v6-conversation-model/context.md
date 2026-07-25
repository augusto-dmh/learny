# Context — `v6-conversation-model` (auto-decisions per ship-cycle contract)

Each decision: options considered (why-recommend / why-not), the pick, and the
STATE.md row. No user prompts were spent; escalation rule not triggered — every
decision below either transcribes RFC-006/ADR-0029 content the driver already
pinned, or is an implementation choice with a clear recommendation.

## D-1 · ADR-0029 acceptance mechanics → AD-192

- **(a) Author in-cycle, Status Accepted, merge gate = acceptance** ⭐ — why:
  content decisions (scope × mode, migration shape, scope-is-a-promise, teach
  invariant, retirement plan, single rate limit) were all made by the driver in
  merged RFC-006; precedent ADR-0020/0021/0023 shipped Accepted inside cycle
  PRs. Why-not: a merge-gate rejection means rework of a built cycle.
- (b) Pause for explicit ADR acceptance first — why: cleanest reading of
  "Depends on: ADR-0029 accepted"; ADR-0026 precedent. Why-not: violates the
  ship-cycle autonomy contract for a decision with nothing left to decide.
- **Chosen: (a).**

## D-2 · Scope representation → AD-193

- **(a) `scope_anchors` JSONB list, `[]` = whole book, never NULL** ⭐ — one
  representation; JSONB matches `target_section_path` precedent in the same
  table. Why-not: TEXT[] is the more natural pg array (aliases use it).
- (b) Nullable column (`NULL` = whole book) — literal RFC wording. Why-not:
  two spellings of "no scope" invite drift; ADR records the rejection.
- **Chosen: (a).**

## D-3 · Teach target → AD-194

- **(a) Keep `target_*` as nullable snapshot of scope head, set at creation**
  ⭐ — teach invariant + legacy views need a target without per-read corpus
  joins. Why-not: denormalized (can go stale on corpus replace — mitigated by
  per-turn re-resolution for teach turns).
- (b) Drop target columns, derive from scope at read — why: normal form.
  Why-not: corpus join on every session read; legacy `SessionView.target` is
  non-null on the wire today.
- (c) Per-turn target column — why: most general. Why-not: no consumer;
  RFC's model puts mode, not target, on the turn.
- **Chosen: (a).**

## D-4 · Legacy ask persistence → AD-195

- **(a) One whole-book conversation per question, title = truncated
  question; legacy per-source teach list filters `target_anchor IS NOT
  NULL`** ⭐ — each legacy ask sends no history so it *is* an independent
  conversation; the filter keeps ask litter out of the old Teach panel.
  Why-not: many single-turn conversations until Cycle D's UI manages them.
- (b) One per-source "default ask thread" — why: no litter. Why-not: fakes a
  thread out of unrelated questions; history-aware answer mode would then
  contaminate answers with unrelated context.
- (c) Don't persist via legacy endpoints — why: least churn. Why-not:
  violates the RFC's "Q&A turns persisted from the first release".
- **Chosen: (a).**

## D-5 · Status vocabulary & collapse → AD-196

- **(a) Service produces `answered | not_found_in_source | not_found_in_scope`;
  legacy presenters collapse scope→source on the wire** ⭐ — precise domain
  truth, shipped panels keep their vocabulary. Why-not: legacy wire hides the
  distinction until Cycle D (accepted — panels have no copy for it).
- (b) Legacy emits the new status too — why: honest wire. Why-not: breaks
  shipped panel copy/status handling; violates I-CM-4.
- **Chosen: (a).**

## D-6 · Answer-mode history → AD-197

- **(a) `AnswerGenerationPort` gains `history: Sequence[HistoryTurn] = ()`;
  Anthropic answer adapter assembles alternating history (teaching's shape);
  deterministic adapter ignores it** ⭐ — Cycle D ships chat on this model; a
  history-blind mode forgets follow-ups and forces a port change later anyway.
  Why-not: widens this cycle by one port + adapter change (contained, offline-
  tested).
- (b) History-blind answer mode — why: strictly minimal for C. Why-not: D
  builds a chat UI that forgets; the port churns twice.
- (c) Merge both generation ports into one — why: ultimate unification.
  Why-not: prompts/caching semantics differ; blast radius exceeds the cycle.
- **Chosen: (a).** First-turn history is empty ⇒ I-CM-8 byte-stability holds.

## D-7 · Settings → AD-198

- **(a) New `conversation_evidence_top_k=8`, `conversation_history_turns=6`,
  `conversation_message_max_chars=2000`; legacy `qa_evidence_top_k`,
  `teaching_evidence_top_k`, `teaching_history_turns` deprecated in place
  (fields kept, no longer read)** ⭐ — deployed `.env` files keep validating;
  removal rides Cycle D's retirement. Why-not: three dormant fields until D.
- (b) Reuse teaching settings for the unified service — why: zero new keys.
  Why-not: names lie (`teaching_*` governing answer turns) and retirement
  gets harder.
- **Chosen: (a).** Legacy request models keep `qa_question_max_chars` /
  `teaching_message_max_chars` (still live on the legacy wire).

## D-8 · Rate limiting → AD-199

- **(a) One `rate_limit_conversations` on all unified mutating routes; legacy
  endpoints keep `rate_limit_questions`/`rate_limit_teaching` until they
  retire** ⭐ — implements ADR-0029's single policy without touching shipped
  behavior. Why-not: two policies co-exist until D (bounded, recorded).
- (b) Point legacy deps at the new limiter now — why: one policy everywhere.
  Why-not: changes shipped 429 windows (per-IP+route keys shift) for zero
  user value pre-retirement.
- **Chosen: (a).**

## D-9 · Migration mechanics → AD-200

- **(a) In-place `ALTER TABLE RENAME` (+ index/constraint renames), column
  adds, SQL backfill, reversible downgrade** ⭐ — preserves rows, FKs, and
  the turn arbiter; "a migration, not a rewrite" per RFC Assumption 2.
  Why-not: rename choreography (constraints/indexes) needs care in tests.
- (b) New tables + copy + drop — why: clean slate. Why-not: adds a copy
  failure surface for zero benefit at this data size; rejected in ADR-0029.
- **Chosen: (a).**

## D-10 · Error codes → AD-201

- **(a) 422 unresolvable scope anchor at start; 409 teach turn without a
  resolvable target; 409 turn-index race (unchanged)** ⭐ — 422 = bad request
  content, 409 = well-formed request against wrong state; matches existing
  conventions. Why-not: none material.
- **Chosen: (a).**

## D-11 · Execution shape → AD-202

- **(a) 4 phases (A schema+domain, B services+ports, C unified web, D legacy
  compat+goldens), one Opus worker each, fresh Opus Verifier** ⭐ — every
  phase carries correctness invariants (migration/backfill, scope promise,
  wire parity) → no Haiku-safe unit; >3 phases ⇒ worker-per-phase, accepted
  as standing by the ship-cycle invocation. Why-not: worker coordination
  overhead vs inline (paid willingly for fresh-context phases + verifier
  independence).
- (b) 3 fatter phases inline — why: fewer handoffs. Why-not: compat parity
  (D) deserves its own fresh context; inline execution burns orchestrator
  context needed for review/triage stages.
- **Chosen: (a).**
