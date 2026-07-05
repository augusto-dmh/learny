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

## Quarantined (failed when applied — ignore)

A confirmed lesson that recurred alongside failure. Kept for the maintainer to review.

_none_
