# LESSONS — auto-maintained by scripts/lessons.py

> Machine-owned. Do NOT hand-edit. Changes are overwritten on the next `lessons.py` write.
> Canonical state lives in `.specs/lessons.json`. Edit lessons only via the script.
> promote_threshold=2 distinct features · window_days=45 · quarantine_threshold=2

## Confirmed (load these at Specify/Design)

Corroborated across multiple features. Safe to apply as guidance.

_none_

## Candidates (under observation — do NOT load as guidance yet)

Seen once or not yet corroborated. Tracked, not trusted.

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

### L-023 — When a spec clause demands a failure log without secrets (DOOR-40), pair the swallow-and-continue test with a caplog assertion naming the log record and asserting the raw token is absent — session-still-created tests alone do not pin the log contract.
- signal: `spec_precision_gap` · recurrence: 1 feature(s) · scope: `backend/tests` · harmful: 0
- features: safe-to-open-the-doors
- evidence: DOOR-40 / backend/tests/test_application_email.py:200 (backend/tests)
- last seen: 2026-09-06T23:47:27Z

### L-024 — A spec outcome phrased as an HTTP status for a public route (DOOR-27 return 200) needs at least one route-level request assertion; jsdom render tests only pin content and silently assume the routing/status half.
- signal: `spec_precision_gap` · recurrence: 1 feature(s) · scope: `frontend/tests` · harmful: 0
- features: safe-to-open-the-doors
- evidence: DOOR-27 / frontend/tests/legal-pages.test.tsx:23 (frontend/tests)
- last seen: 2026-09-06T23:47:27Z

### L-025 — When sibling quota errors assert their honest-copy body, a new quota error (DOOR-18 in-flight copy) must assert its copy too — status-plus-side-effect assertions let the copy regress unnoticed.
- signal: `spec_precision_gap` · recurrence: 1 feature(s) · scope: `backend/tests` · harmful: 0
- features: safe-to-open-the-doors
- evidence: DOOR-18 / backend/tests/test_web_ingestion.py:394 (backend/tests)
- last seen: 2026-09-06T23:47:27Z

### L-026 — When a spec enumerates edge cases explicitly, pin each one with a direct test — a sectionless source under a position bound (empty evidence + warning) was left to subsumption reasoning instead of an assertion.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `backend/db-gated retrieval tests` · harmful: 0
- features: v5-spoiler-safe-retrieval
- evidence: SPOILER Edge Cases / backend/tests/test_retrieval.py (backend/db-gated retrieval tests)
- last seen: 2026-09-08T17:32:10Z

### L-027 — Pin spec edge fixtures with their literal boundary values: no test saved percent=0.00 to prove the anchor (not the percent) defines the reading-position bound, even though the SQL never reads percent.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `backend/db-gated retrieval tests` · harmful: 0
- features: v5-spoiler-safe-retrieval
- evidence: SPOILER Edge Cases / backend/tests/test_retrieval.py (backend/db-gated retrieval tests)
- last seen: 2026-09-08T17:32:10Z

## Quarantined (failed when applied — ignore)

A confirmed lesson that recurred alongside failure. Kept for the maintainer to review.

_none_
