# Review Triage — retrieval-indexes (PR #12)

Independent `pr-review` run posted 3 inline findings (0 blocking), 0 security, 0 regression;
requirements review confirmed all 22 ACs + 5 stories + 5 edge cases implemented. Each finding
below was checked against the code as it exists. Comments are deleted in Stage 6, so this file
is the surviving record of the review reasoning.

| # | Source comment | file:line | Verdict | Action | Rationale |
|---|---|---|---|---|---|
| F1 | ⚡ performance | `backend/app/infrastructure/db/repositories.py:467` | **real** | **fix** | `set_embeddings` issues one `UPDATE` per chunk → O(N) round trips per source; a large book is thousands of statements. A single `executemany` UPDATE keyed on a `bindparam` id (values from a param list) collapses it to one round trip and still serializes each `list[float]` through the `VECTOR` type. Low risk, covered by the existing embed round-trip + worker tests. |
| F2 | 💡 suggestion (architecture) | `backend/app/infrastructure/db/engine.py:39` | **real** | **fix** | `except Exception: pass` around `register_vector` is intentionally broad (the pre-migration "vector type absent" case is a plain error subclass, brittle to narrow across pgvector versions), but swallowing it silently hides a genuine registration failure. Keep the broad catch (correct for the documented case) and add a `logger.debug` diagnostic so a real failure is observable. Behavior unchanged; diagnosability improved. |
| F3 | 💡 suggestion (tests) | `backend/tests/test_migrations.py:429` | **real** | **fix** | Line 427 already downgrades to `base` (cleanup); line 429 repeats it — a copy-paste no-op (base→base does nothing). Remove the duplicate line. Trivial, no behavior change. |

**Rejected / won't-fix:** none — all three are correct, low-risk, and worth applying.

**Fix grouping (Stage 5):** F1 → `perf` commit; F2 → `refactor` commit; F3 → `test` commit. Re-run the full gate + ruff before pushing.
