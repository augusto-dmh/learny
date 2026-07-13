# v2-foundation — Decision Context

Auto-decided per the learny-ship-cycle autonomy contract (recommended option chosen, both sides recorded). Mirrored as AD-045..AD-050 in `.specs/project/STATE.md`.

## D-1 (AD-045) — Roadmap driver for v2

- **Options**: (a) RFC-002 becomes the roadmap source, ROADMAP.md maps its cycles *(recommended)*; (b) write a new TDD first and derive cycles from it; (c) keep planning ad hoc per cycle.
- **Why (a)**: RFC-002 is Accepted, research-backed, and already cycle-sequenced; a TDD now would duplicate it (the per-cycle designs belong in each cycle). Why not: an RFC is coarser than a TDD — accepted risk: cycle-level design happens inside each tlc cycle, where it did for the MVP too. (b) delays foundation work behind a document that adds no new decisions today. (c) loses the traceability that made the MVP manageable.

## D-2 (AD-046) — Land pre-authored artifacts unmodified

- **Options**: (a) commit README/QA/research/RFC exactly as authored and user-approved *(recommended)*; (b) re-review/edit them inside the cycle.
- **Why (a)**: the user approved RFC-002 and saw the QA docs; editing them now re-litigates approved content and inflates the diff. Why not: they bypass task-level test derivation — accepted because they are documentation, guarded by presence/content checks only where regressions matter (compose fix). (b) burns cycle budget on already-reviewed prose.

## D-3 (AD-047) — CI per research sketch, adapted

- **Options**: (a) 4-job workflow from `docs/research/2026-07-12/oss-maturity-ci.md`, adapted to `LEARNY_*` env names and `/healthz` *(recommended)*; (b) minimal single-job CI (pytest only) now, grow later; (c) add coverage/e2e jobs too.
- **Why (a)**: the sketch was verified against official actions docs on 2026-07-12 and covers exactly the local gates; adapting env names is mandatory (the sketch's `DATABASE_URL` would silently skip every DB test since conftest reads `LEARNY_TEST_DATABASE_URL`). Why not: compose-smoke is the slowest job (~3–5 min) — accepted, it guards the deploy artifact v2 depends on. (b) leaves frontend/compose regressions ungated — the QA run proved those break. (c) scope creep; coverage gates punish a solo repo.

## D-4 (AD-048) — Apache-2.0

- **Options**: (a) Apache-2.0 *(recommended)*; (b) MIT; (c) AGPL-3.0.
- **Why (a)**: explicit patent grant, enterprise-readable, §5 gives implicit contribution licensing, sole-author can relicense later. Why not: marginally longer/less familiar than MIT — cosmetic. (b) loses the patent grant for zero benefit at app (not library) granularity. (c) buys SaaS-competitor protection Learny's locked decisions say it doesn't need, at the cost of reflexive enterprise distrust.

## D-5 (AD-049) — F4 root cause and fix

- **Diagnosis (Execute, task B3 — confirmed empirically)**: `migrations/env.py` unconditionally overwrote the Alembic Config's `sqlalchemy.url` with `get_settings().database_url`. The session bootstrap in `tests/conftest.py::db_engine` configures the test-database URL **only** via `Config.set_main_option`, so its upgrade silently migrated the settings-resolved **dev** database and left `learny_test` schemaless. On a fresh test DB, exactly the DB-bound tests collected **before** `test_migrations.py` (the 8 golden retrieval/citation tests) failed — first with `UndefinedTable: relation "users"`, cascading to psycopg `InFailedSqlTransaction` (SQLAlchemy f405) inside the per-test transaction. `test_migrations.py`'s own tests monkeypatch `LEARNY_DATABASE_URL`, so once that module ran (and its restore-to-head teardown), the test DB gained its schema — masking the bug for every later test and every subsequent run. Verified: post-failure, `learny_test` had zero relations while the dev DB had the full schema.
- **Fix**: `env.py` injects the settings URL only when the caller has not already set one (`if not config.get_main_option("sqlalchemy.url")`). Caller-configured URLs (test bootstrap, migration tests) now win; the CLI/container path (`alembic upgrade head`, no programmatic URL) still resolves from settings.
- **Options**: (a) env.py honors caller-provided URL *(recommended, chosen)*; (b) conftest sets `LEARNY_DATABASE_URL` + clears the settings cache around the bootstrap; (c) reorder tests so migrations run first.
- **Why (a)**: fixes the mechanism at its source and makes every in-process Alembic caller behave the same; regression test proves it (`test_upgrade_honors_caller_provided_url`). Why not: env.py behavior change affects all callers — mitigated by the empty-URL guard preserving the CLI path. (b) spreads the settings-cache trick to every future caller (this exact trap already produced candidate lesson L-007 in cycle 9). (c) masks the bug and breaks on any collection-order change.

## D-6 (AD-050) — Slice shape departure from AD-010

- This cycle ships docs, fixes, CI, and hygiene — no frontend product feature. Deliberate departure from AD-010 (full vertical slices), precedent AD-023/AD-039/AD-044. Why not: none of the deliverables have a user-facing surface; padding one in would be artificial. Flagged for the merge gate.
