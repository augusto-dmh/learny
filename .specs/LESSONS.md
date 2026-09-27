# LESSONS - auto-maintained by scripts/lessons.py

> Machine-owned. Do NOT hand-edit. Changes are overwritten on the next `lessons.py` write.
> Canonical state lives in `.specs/lessons.json`. Edit lessons only via the script.
> promote_threshold=2 distinct features · window_days=45 · quarantine_threshold=2

## Confirmed (load these at Specify/Design)

Corroborated across multiple features. Safe to apply as guidance.

_none_

## Candidates (under observation - do NOT load as guidance yet)

Seen once or not yet corroborated. Tracked, not trusted.

### L-023 - When a spec clause demands a failure log without secrets (DOOR-40), pair the swallow-and-continue test with a caplog assertion naming the log record and asserting the raw token is absent — session-still-created tests alone do not pin the log contract.
- signal: `spec_precision_gap` · recurrence: 1 feature(s) · scope: `backend/tests` · harmful: 0
- features: safe-to-open-the-doors
- evidence: DOOR-40 / backend/tests/test_application_email.py:200 (backend/tests)
- last seen: 2026-09-06T23:47:27Z

### L-024 - A spec outcome phrased as an HTTP status for a public route (DOOR-27 return 200) needs at least one route-level request assertion; jsdom render tests only pin content and silently assume the routing/status half.
- signal: `spec_precision_gap` · recurrence: 1 feature(s) · scope: `frontend/tests` · harmful: 0
- features: safe-to-open-the-doors
- evidence: DOOR-27 / frontend/tests/legal-pages.test.tsx:23 (frontend/tests)
- last seen: 2026-09-06T23:47:27Z

### L-025 - When sibling quota errors assert their honest-copy body, a new quota error (DOOR-18 in-flight copy) must assert its copy too — status-plus-side-effect assertions let the copy regress unnoticed.
- signal: `spec_precision_gap` · recurrence: 1 feature(s) · scope: `backend/tests` · harmful: 0
- features: safe-to-open-the-doors
- evidence: DOOR-18 / backend/tests/test_web_ingestion.py:394 (backend/tests)
- last seen: 2026-09-06T23:47:27Z

### L-026 - When a spec enumerates edge cases explicitly, pin each one with a direct test — a sectionless source under a position bound (empty evidence + warning) was left to subsumption reasoning instead of an assertion.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `backend/db-gated retrieval tests` · harmful: 0
- features: v5-spoiler-safe-retrieval
- evidence: SPOILER Edge Cases / backend/tests/test_retrieval.py (backend/db-gated retrieval tests)
- last seen: 2026-09-08T17:32:10Z

### L-027 - Pin spec edge fixtures with their literal boundary values: no test saved percent=0.00 to prove the anchor (not the percent) defines the reading-position bound, even though the SQL never reads percent.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `backend/db-gated retrieval tests` · harmful: 0
- features: v5-spoiler-safe-retrieval
- evidence: SPOILER Edge Cases / backend/tests/test_retrieval.py (backend/db-gated retrieval tests)
- last seen: 2026-09-08T17:32:10Z

## Quarantined (failed when applied - ignore)

A confirmed lesson that recurred alongside failure. Kept for the maintainer to review.

_none_
