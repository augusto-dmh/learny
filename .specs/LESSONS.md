# LESSONS — auto-maintained by scripts/lessons.py

> Machine-owned. Do NOT hand-edit. Changes are overwritten on the next `lessons.py` write.
> Canonical state lives in `.specs/lessons.json`. Edit lessons only via the script.
> promote_threshold=2 distinct features · window_days=45 · quarantine_threshold=2

## Confirmed (load these at Specify/Design)

Corroborated across multiple features. Safe to apply as guidance.

_none_

## Candidates (under observation — do NOT load as guidance yet)

Seen once or not yet corroborated. Tracked, not trusted.

### L-001 — For every threshold comparison, add a test at the exact boundary value, not only past it, so a > vs >= regression is caught.
- signal: `surviving_mutant` · recurrence: 1 feature(s) · scope: `validation` · harmful: 0
- features: source-storage
- evidence: backend/app/application/validation.py:75 (validation)
- last seen: 2026-07-05T02:09:04Z

### L-002 — When a store-then-persist flow has a rollback edge case, test the persist-failure path directly, not just the store-failure path.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `web` · harmful: 0
- features: source-storage
- evidence: backend/tests/test_web_sources.py (INSERT-fail edge, spec Edge Cases / SRC-09) (web)
- last seen: 2026-07-05T02:09:04Z

### L-003 — Before designing resource-specific proxy/adapter routes, check for an existing generic catch-all that already covers them to avoid speculative duplication.
- signal: `spec_deviation` · recurrence: 1 feature(s) · scope: `frontend` · harmful: 0
- features: source-storage
- evidence: .specs/features/source-storage/tasks.md T7 SPEC_DEVIATION (frontend)
- last seen: 2026-07-05T02:09:04Z

### L-004 — When a UI control renders conditionally on a status, flip that status on success (post-await) rather than optimistically pre-await, or the optimistic flip unmounts the control and makes its in-flight disabled state unobservable/untestable.
- signal: `spec_deviation` · recurrence: 1 feature(s) · scope: `frontend/react` · harmful: 0
- features: worker-foundation
- evidence: frontend/app/components/SourcesPanel.tsx SPEC_DEVIATION (frontend/react)
- last seen: 2026-07-11T14:37:59Z

### L-005 — A new DB-using test whose filename sorts before test_migrations becomes the first db_conn consumer, so the session-scoped db_engine upgrade runs before test_migrations downgrades to base — leaving later modules with no schema; and alembic env.py's fileConfig clobbers app-owned root logging. Guard: env.py must not call fileConfig, and test_migrations must restore head on teardown.
- signal: `spec_deviation` · recurrence: 1 feature(s) · scope: `backend/tests` · harmful: 0
- features: golden-fixtures
- evidence: backend/migrations/env.py:20 + tests/test_migrations.py (backend/tests)
- last seen: 2026-07-12T21:31:04Z

### L-006 — A 'citations bounded to source anchors' assertion is structurally trivial while the answer adapter is the deterministic extractive one (it can only cite retrieved, source-scoped evidence); it becomes a real guard only once a generative adapter that can cite freely lands — revisit the golden then.
- signal: `spec_precision_gap` · recurrence: 1 feature(s) · scope: `backend/tests/evaluation` · harmful: 0
- features: golden-fixtures
- evidence: EVAL-07 / test_golden_citations.py (backend/tests/evaluation)
- last seen: 2026-07-12T21:31:04Z

### L-007 — When trace/context fields are auto-injected by a logging filter, assert them on a record emitted WITHOUT explicit extra= so a broken binding is detectable, not on a record that also passes the fields via extra=
- signal: `surviving_mutant` · recurrence: 1 feature(s) · scope: `observability` · harmful: 0
- features: production-readiness
- evidence: M4 worker arm — test_worker_tasks.py:650 (observability)
- last seen: 2026-07-12T23:06:52Z

### L-008 — A recall@k retrieval-gate threshold is vacuous when k is greater than or equal to the eval corpus size; size the corpus or set top_k below the item count so recall@k measures ranking, not mere presence.
- signal: `spec_precision_gap` · recurrence: 1 feature(s) · scope: `eval` · harmful: 0
- features: v2-embeddings
- evidence: validation.md EMB-22 / sensor mutation 5 / test_eval_retrieval_metrics.py:41-43 (eval)
- last seen: 2026-07-16T00:25:51Z

### L-009 — Test a per-batch-committed resumable task with more rows than one batch (or a tiny batch size) and a mid-pass interruption, so partial-progress resume is exercised rather than inferred from unit selection alone.
- signal: `spec_precision_gap` · recurrence: 1 feature(s) · scope: `worker` · harmful: 0
- features: v2-embeddings
- evidence: validation.md EMB-17 / test_reembed.py:144-187 / tasks.py:291-300 (worker)
- last seen: 2026-07-16T00:25:51Z

### L-010 — When pinning a script's safety-critical flag as text, assert it on the extracted command line, not as a whole-file substring that doc-comments or dry-run echoes also satisfy
- signal: `surviving_mutant` · recurrence: 1 feature(s) · scope: `backend/tests, shell-script-pins` · harmful: 0
- features: v3-ops-maturity
- evidence: backend/tests/test_backup_stack.py:228 (mutant #1, restore.sh:71 --if-exists) (backend/tests, shell-script-pins)
- last seen: 2026-07-17T21:45:05Z

### L-011 — Pin externally-derived constants (calibrated thresholds, measured baselines) with an exact-value offline test — the deriving runs are keyed/manual, so nothing else catches a typo. When one assert enforces multiple thresholds, add a single-failure test per threshold; a both-bad case cannot attribute, so an inverted comparison survives masked.
- signal: `surviving_mutant` · recurrence: 1 feature(s) · harmful: 0
- features: v3-eval-maturity
- evidence: validation.md 2026-07-18 (M2a/M2b)
- last seen: 2026-07-18T20:22:44Z

### L-012 — Visual-persistence ACs (sticky/fixed/receding chrome) need an explicit class+structure assertion in jsdom — positional CSS behavior slips spec coverage when only content rendering is tested.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `frontend/tests` · harmful: 0
- features: v4-reader-core
- evidence: spec RD-05 / validation.md round 1 (frontend/tests)
- last seen: 2026-07-19T17:15:07Z

### L-013 — Verify error-kind and enum string values against their defining module before naming them in design; do not guess them from memory.
- signal: `spec_deviation` · recurrence: 1 feature(s) · scope: `frontend` · harmful: 0
- features: v4-reader-apparatus
- evidence: frontend/app/lib/answer-notes.ts:81-83 (SPEC_DEVIATION) (frontend)
- last seen: 2026-07-19T20:05:19Z

## Quarantined (failed when applied — ignore)

A confirmed lesson that recurred alongside failure. Kept for the maintainer to review.

_none_
