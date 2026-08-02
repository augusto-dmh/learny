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

### L-014 — For a preservation AC ('X keeps working' / 'reachable from the header'), add a direct positive assertion — an untouched code path plus a green regression suite is not evidence for the clause.
- signal: `spec_precision_gap` · recurrence: 1 feature(s) · scope: `coverage` · harmful: 0
- features: v4-home-ia
- evidence: HOME-19 (coverage)
- last seen: 2026-07-21T15:35:08Z

### L-015 — A conditional guard (e.g. only-set-if-absent) whose protected branch is DB/key-gated needs its own offline discriminating test that reproduces the pre-condition ordering — e.g. a class-scoped fixture presetting the value before the function-scoped autouse fixture — or the discrimination sensor flags the guard as uncovered.
- signal: `surviving_mutant` · recurrence: 1 feature(s) · scope: `backend/tests/conftest-fixtures` · harmful: 0
- features: v5-offline-suite-honesty
- evidence: M3 (test_offline_provider_pin.py) (backend/tests/conftest-fixtures)
- last seen: 2026-07-24T16:53:30Z

### L-016 — When an implicit-requirement sweep resolves a bounds/limits dimension, name the concrete bound (page size, cap, or 'deliberately unbounded because X') — 'bounded like the shipped list conventions' names no assertion, and WSN-11 shipped with the validation half sensed and the bounds half neither implemented nor tested.
- signal: `spec_precision_gap` · recurrence: 1 feature(s) · scope: `backend/app/infrastructure/web` · harmful: 0
- features: v6-workspace-notes
- evidence: spec.md:59 (WSN-11); backend/app/infrastructure/web/notes.py:302 (backend/app/infrastructure/web)
- last seen: 2026-07-27T02:58:13Z

### L-017 — A .get(key, default) fallback whose only caller always writes the key is untestable through the public path — pin it with a direct unit test or delete it, else a mutation of the default survives.
- signal: `surviving_mutant` · recurrence: 1 feature(s) · scope: `backend/tests` · harmful: 0
- features: v5-opus-judge-recalibration
- evidence: backend/app/eval/judge.py:427 (M6) (backend/tests)
- last seen: 2026-07-31T17:03:23Z

### L-018 — Before any paid live eval run, assert every model identity the spec pins (judge and generation) against the resolved settings, not just the prompt hash — a git-ignored .env override can silently swap the model and the resume mismatch guard compares against the same drifted value.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `backend/tests/eval` · harmful: 0
- features: v5-generation-denoise
- evidence: DENOISE-10 / evals/results/2026-07-31-e9d9fbab-generation-denoise.jsonl (backend/tests/eval)
- last seen: 2026-07-31T19:13:22Z

### L-019 — When a spec AC requires an observable side channel (progress/log lines), add a test capturing its output — passing a discard callback in every test leaves the AC with zero evidence.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `backend/tests/eval` · harmful: 0
- features: v5-generation-denoise
- evidence: DENOISE-09 AC8 / backend/tests/eval/test_study_runner.py:88 (backend/tests/eval)
- last seen: 2026-07-31T19:13:22Z

### L-020 — Paid multi-run live studies should verify the provider credit balance covers the modeled estimate before the first unit — a mid-study credit exhaustion truncates the final run and turns the planned evidence into a recorded deviation.
- signal: `spec_deviation` · recurrence: 1 feature(s) · scope: `backend/tests/eval` · harmful: 0
- features: v5-generation-denoise
- evidence: spec.md Recorded deviations / AD-238 (backend/tests/eval)
- last seen: 2026-08-02T01:50:35Z

### L-021 — When a feature reads committed data files, derive fixtures from the newest real file, not just the oldest: the de-noise study file repeats each case across two model arms and three runs, so a case+run_index React key collided on all 36 rows while every fixture used run_index null and passed.
- signal: `spec_precision_gap` · recurrence: 1 feature(s) · scope: `eval,fixtures` · harmful: 0
- features: v5-eval-dashboard
- evidence: backend/tests/test_eval_results.py:180 (eval,fixtures)
- last seen: 2026-08-02T04:03:24Z

### L-022 — Before documenting a shape as unproducible, grep every writer into that directory, not just the obvious one: the study runner writes status-error lines with no citation_valid into the same results dir the judge writes, which a missing-key-means-violation rule turned into a false citation failure.
- signal: `spec_precision_gap` · recurrence: 1 feature(s) · scope: `eval,judge` · harmful: 0
- features: v5-eval-dashboard
- evidence: backend/app/eval/results.py:207 (eval,judge)
- last seen: 2026-08-02T04:03:24Z

## Quarantined (failed when applied — ignore)

A confirmed lesson that recurred alongside failure. Kept for the maintainer to review.

_none_
