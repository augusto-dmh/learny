# App Instrumentation — Validation

**Verdict: PASS.**

Independent verification by a fresh Verifier (author ≠ verifier, evidence-or-zero).
Coverage was re-derived from `spec.md` rather than inherited from the authors: every
acceptance criterion was traced to the test that covers it, the asserted value was
compared against the *spec-defined* outcome, and the sensors were then attacked with
behaviour-level mutations.

| | |
| --- | --- |
| Diff range | `cbc296d8..df628ba2` (branch `feat/app-instrumentation`, 13 commits) |
| Acceptance criteria | **26 of 26 covered** (OBS-01..26), all against the amended spec text |
| Mutation sensor | **42 injected, 38 killed, 4 survived** — no survivor breaks a spec-defined outcome |
| Backend suite | 1736 passed / 1 failed / 11 skipped — the single failure is `test_eval_retrieval_metrics.py::TestDeterministicRetrievalMetrics::test_metrics_meet_thresholds`, pre-existing on `main`, local-only, green in CI, out of scope for this cycle |
| Frontend suite | 564 passed / 59 files |
| Working tree | Byte-identical to `HEAD` after every mutation was reverted; `git diff` empty |

The mid-cycle amendment under "Server timing on the wire" was read first and every
server-timing criterion was checked against the **amended** text: the header carries
time-to-response-start, the access log and the recorder keep whole-request duration,
and a truly-unhandled exception's response carries neither correlation header.

---

## Per-AC evidence

Test paths are relative to `backend/` unless marked otherwise. "Sensor" names the
mutation from the next section that this criterion's tests killed.

### P1: One timing recorder

| AC | Test | What it asserts | Sensor |
| --- | --- | --- | --- |
| OBS-01 | `tests/test_instrumentation.py::test_request_sample_carries_route_method_status_and_duration` | A stored sample carries exactly method (upper-cased), route template, status, duration | M3 |
| | `::test_recording_a_request_accepts_no_path_query_header_or_body` | The record API's keyword set *is* `{method, route, status_code, duration_ms}` — structural, so no path/header/body parameter can be added silently | — |
| | `::test_a_query_string_never_reaches_the_stored_label` | A route arriving with `?token=…` stores `/api/sources`; the secret is absent from the whole snapshot | M3 |
| | `tests/test_web_request_instrumentation.py::test_completed_request_is_recorded_with_template_method_status_and_duration` | A real request through the middleware records `/items/{item_id}`, not the path | M1 |
| | `::test_recorded_route_carries_no_parameter_value_or_query_string` | The resource id and query value are absent from the recorded route | M1 |
| | `::test_handled_error_is_recorded_with_its_final_status` | A 404 from an exception handler is recorded with status 404 | — |
| OBS-02 | `tests/test_instrumentation.py::test_an_unmatched_request_buckets_under_one_constant_label` | `None` and blank both bucket under `UNMATCHED_ROUTE`, count 2 in one row | M2 |
| | `tests/test_web_request_instrumentation.py::test_unmatched_request_is_recorded_under_the_constant_placeholder` | A real unmatched request records the placeholder; the id in the path is absent | M1, M2 |
| | `tests/test_web_instrument.py::test_surface_exposes_no_path_parameter_query_string_or_raw_path` | Read end-to-end off the response body: no id, no query value, but `/api/sources/{source_id}` present | M1, M2 |
| OBS-03 | `tests/test_instrumentation.py::test_the_newest_samples_up_to_capacity_are_retained_exactly` | Capacity 3 over 5 samples retains `[5, 4, 3]` — *exactly* the newest, oldest discarded | M8 |
| | `::test_slow_query_entries_are_bounded_by_the_same_capacity` | The query buffer is bounded independently by the same number | M8 |
| OBS-04 | `::test_ranking_reports_count_mean_max_and_p95_per_method_and_route` | One row per `(method, route)`; count 3, mean 20.0, max 30.0, p95 30.0 — all four fields | M4, M5 |
| | `::test_ranking_is_ordered_by_descending_p95` | Three groups rank slow → middling → fast | M7 |
| | `::test_equal_p95_falls_back_to_descending_maximum` | Equal p95 (100.0 both); the group with max 900.0 ranks first, recorded *second* so ordering cannot come from arrival | M6, M7 |
| | `::test_an_empty_recorder_ranks_to_nothing_without_raising` | Edge case: empty recorder → `()`, no raise | — |
| OBS-05 | `::test_p95_of_a_single_sample_is_that_sample` | n=1 → the sample itself (spec edge case) | M4 |
| | `::test_p95_is_the_ascending_sorted_value_at_the_nearest_rank` | n=20, inserted descending → 19.0 (index 18), max 20.0 — pins both the index and order-independence | M4 |
| | `::test_p95_rounds_the_rank_up_for_a_sample_count_that_does_not_divide` | n=3 → 9.0 (`ceil(2.85) - 1 = 2`), which is what separates ceil from floor | M4, M5 |
| OBS-06 | `::test_concurrent_recording_loses_no_sample` | 8 threads × 200 samples → count 1600, no loss | — (see gap 2) |
| | `::test_concurrent_recording_stays_within_capacity` | Mixed request/query load stays at capacity 100 and every retained sample is one a producer actually wrote | — |
| | `::test_reading_a_snapshot_while_recording_never_tears` | Overlapping readers and writers; no exception, no over-capacity read | — |
| OBS-07 | `tests/test_web_request_instrumentation.py::test_a_failing_recorder_leaves_the_response_untouched` | With a recorder that raises: 200, correct body, `X-Request-ID` present, access record still status 200 | M26 |
| | `tests/test_instrumentation.py::test_a_failing_recorder_cannot_escalate_into_its_producer` | The producer entry points swallow a raising recorder | M26 |
| | `::test_recording_an_unusable_duration_is_dropped_rather_than_raised` | A string, a NaN and a `None` duration are dropped, not stored, and the read path still answers | M27, M28 |

### P1: Server timing on the wire (verified against the amendment)

| AC | Test | What it asserts | Sensor |
| --- | --- | --- | --- |
| OBS-08 | `tests/test_web_request_instrumentation.py::test_response_carries_a_server_timing_app_metric` | Exactly one `app` metric in the header, parsed out of the list header | M14 |
| | `::test_server_timing_reports_the_time_to_response_start_the_access_log_reports` | `dur` **equals** `response_start_ms` on the access record — one measurement, two consumers | M14, M15 |
| | `::test_server_timing_leaves_the_request_id_header_intact` | Appending the metric does not disturb `X-Request-ID` | — |
| OBS-09 | `frontend/tests/proxy-forwarding.test.ts` — "relays Server-Timing so the browser keeps the backend's timing split" | `relayResponse` preserves `server-timing: app;dur=12.345` verbatim | M34 |
| OBS-10 | `::test_handled_error_response_carries_server_timing` | A 404 produced by an exception handler carries the header, equal to the log's `response_start_ms`, and is recorded | M14, M15 |
| | `::test_unhandled_exception_response_shares_the_documented_header_gap` | A truly-unhandled 500 carries **neither** `Server-Timing` nor `X-Request-ID`, pinned together so they can only be fixed together | — |
| | `::test_unhandled_exception_is_still_recorded_with_its_final_status` | The request is still recorded, status 500 | — |
| OBS-25 | `::test_streamed_response_logs_and_ranks_on_the_whole_request` | Header `dur` = `response_start_ms`; the access record's `duration_ms` exceeds it by at least 0.8 × the 50 ms body delay; the recorded sample equals `duration_ms`, not the header | **M13** |

M13 is the exact regression the brief named — whole-request duration silently reverting
to time-to-response-start. It was re-injected and killed. The sensor still holds.

### P1: Slow query capture

Every case in `tests/test_db_slow_query.py` drives a real statement through
`get_engine()` against the live test database, so it exercises the shipped wiring
rather than a hand-called listener.

| AC | Test | What it asserts | Sensor |
| --- | --- | --- | --- |
| OBS-11 | `::test_a_slow_statement_is_logged_and_recorded_with_its_text_and_duration` | One `pg_sleep(0.35)` at a 200 ms threshold → exactly one recorder sample and exactly one log record, each with the text and a duration ≥ 200 | M19 |
| OBS-12 | `::test_a_statement_below_the_threshold_is_neither_logged_nor_recorded` | At a 10 s threshold, `SELECT 1` produces neither | — |
| | `::test_a_threshold_of_zero_captures_every_statement` | At threshold 0 the captured list is exactly `["SELECT 1"]` (spec edge case: no implicit floor) | M11, M19 |
| | `::test_the_threshold_is_met_at_its_boundary_and_has_no_implicit_floor` | `is_slow(200, 200)` true, `is_slow(199.999, 200)` false, `is_slow(0, 0)` true, `is_slow(0, -1)` true | **M10, M11** |
| OBS-13 | `::test_a_bound_parameter_value_never_reaches_the_captured_statement` | The bound value is absent from every captured statement **and** from every field of every log record; the statement itself was captured | **M12, M12b** |
| | `::test_an_executemany_parameter_value_never_reaches_the_captured_statement` | Same for the separate `executemany` driver path, with two distinct secrets | **M12, M12b** |
| OBS-14 | `::test_a_long_statement_is_stored_truncated_to_the_configured_cap` | A 3000-char statement is stored at exactly 40 chars, prefix preserved | M9 |
| OBS-15 | `::test_a_failing_capture_leaves_the_statement_result_untouched` | With `record_query` raising, `SELECT 42` still returns 42 | M25 |
| | `::test_a_failing_capture_leaves_a_database_error_raised_as_before` | `ProgrammingError` still propagates (but see gap 6 — this one cannot fail) | — |
| — | `::test_an_engine_not_built_by_the_application_captures_nothing` | The fixtures' own engine captures nothing, so capture is a property of the application engine, not an import side effect | — |

### P1: Uniform Celery task durations

The tasks in `tests/test_worker_task_duration.py` are declared in the test and contain
no timing code, and are registered on the application's own `celery_app`.

| AC | Test | What it asserts | Sensor |
| --- | --- | --- | --- |
| OBS-16 | `::test_a_task_with_no_instrumentation_code_reports_its_duration` | An uninstrumented task yields one `task.duration` record with state `SUCCESS` and a float duration | M36, M22 |
| OBS-17 | `::test_a_failing_task_reports_a_duration_under_a_distinct_state` | A raising task still reports, state `FAILURE`, and that state differs from the success one | **M20, M37** |
| | `::test_a_retried_task_reports_one_duration_per_attempt` | A task that retries once produces **two** records (spec edge case) | M22 |
| OBS-18 | `::test_a_task_that_logs_its_own_duration_still_does_so_alongside_the_uniform_record` | The hand-rolled record survives with its domain fields (`duration_ms`, `job_id`) alongside exactly one uniform record | M35 |
| | `tests/test_worker_tasks.py` (pre-existing, lines 359, 712, 730) | The real ingestion tasks' own `duration_ms` records still assert as before | **M35** |
| — | `::test_overlapping_tasks_each_report_their_own_duration` | Two tasks overlapping in one process: the slow one reports ≥ 300 ms, the fast one < 200 ms — no start reading crosses between them | **M22** |
| — | `::test_finished_tasks_leave_no_timing_state_behind` | `pending_attempts()` returns to its prior value after success, failure and retry | **M23** |

### P1: The dev-only surface

| AC | Test | What it asserts | Sensor |
| --- | --- | --- | --- |
| OBS-19 | `tests/test_web_instrument.py::test_surface_is_absent_when_the_flag_is_off` | Flag off, *authenticated* caller → 404 | **M16** |
| | `::test_surface_is_absent_from_the_schema_when_the_flag_is_off` | Absent from `/openapi.json` with the flag off, present with it on | M16 |
| OBS-20 | `::test_enabled_surface_still_requires_a_session` | Flag on, no cookie → 401. Exercised independently of the flag case, so each gate is its own sensor | **M17** |
| OBS-21 | `::test_authenticated_read_returns_ranked_endpoints_and_slow_queries` | 200; `("POST", "/api/auth/register")` present among ranked rows with count/mean/max/p95; the slow-query list matches exactly | M16, M17 |
| | `::test_response_states_that_it_covers_one_process_only` | The payload's `scope` names process, worker and restart | M38 |
| OBS-22 | `::test_idle_process_returns_empty_collections` | Recorder reset → 200 with both collections `[]`, not an error | — |
| OBS-23 | `tests/test_config.py::test_env_example_documents_the_instrument_contract` | All four variables appear as real (uncommented) assignments in `.env.example` | **M31** |
| | `::test_instrument_settings_defaults` | `false / 500 / 200 / 2000`, with the environment neutralised first | **M32** |
| | `::test_instrument_settings_env_override` | All four override from env; `0` survives as a legitimate threshold | — |
| | `::test_instrument_defaults_match_the_recorder_process_defaults` | The recorder's process defaults cannot drift from the settings defaults | **M33** |
| OBS-24 | `tests/test_compose_prod.py::test_prod_never_enables_the_dev_instrument_surface` | No production service carries `LEARNY_DEV_INSTRUMENT_ENABLED` — checked across both prod files | **M29, M39** |
| | `::test_local_override_enables_the_dev_instrument_surface` | The dev override does set it | M30 |
| OBS-26 | `tests/test_web_instrument.py::test_configured_capacity_bounds_what_the_surface_returns` | Capacity 2 over 5 entries returns exactly the newest two, read off the response | **M18, M8** |
| | `::test_configured_statement_cap_truncates_what_the_surface_returns` | A cap of 10 truncates the rendered statement | **M18, M9** |
| | `::test_reported_capacity_is_the_configured_one` | The payload's `capacity` is the configured 7 | M18 |

---

## Discrimination sensor

Each mutation was applied to the working tree, the targeted test file was run, and the
file was reverted immediately. `git status` was checked after every one; the tree is
byte-identical to `HEAD` and the only untracked path is `docs/research/2026-07-24/`,
which was untracked before and remains so.

### Killed (38)

| # | Mutation | Killed by |
| --- | --- | --- |
| M1 | `_route_template` returns the raw `scope["path"]` | 4 tests across the middleware and surface files |
| M2 | Only *unmatched* requests fall back to the raw path | 2 tests |
| M3 | The recorder stops stripping query strings from a route label | `test_a_query_string_never_reaches_the_stored_label` |
| M4 | p95 index off by one (`- 2`) | 3 tests |
| M5 | p95 uses `floor` instead of `ceil` for the rank | 2 tests |
| M6 | Ranking tie-break on max dropped | `test_equal_p95_falls_back_to_descending_maximum` |
| M7 | Ranking order reversed (ascending p95) | 2 tests |
| M8 | Recorder buffers become unbounded (`deque()`) | 4 tests, incl. the surface's capacity test |
| M9 | Statement cap becomes inert (no slice) | 3 tests across all three layers |
| M10 | Slow-query threshold drifts to `>` | `test_the_threshold_is_met_at_its_boundary_and_has_no_implicit_floor` |
| M11 | Implicit 1 ms floor added to the threshold | 3 tests |
| M12 | Bound parameters appended to the captured statement | 3 tests |
| M12b | Bound parameters added to the slow-query **log record** only | 2 tests |
| M13 | Whole-request duration reverts to time-to-response-start | `test_streamed_response_logs_and_ranks_on_the_whole_request` |
| M14 | `Server-Timing` header dropped | 5 tests |
| M15 | Header and log become two independently-taken measurements | 3 tests |
| M16 | Flag gate dropped — the route is always mounted | 3 tests |
| M17 | Auth gate dropped from the route | `test_enabled_surface_still_requires_a_session` |
| M18 | `create_app` installs a default recorder, ignoring configured bounds | 3 tests |
| M19 | The slow-query listener is never attached to the application engine | 5 tests |
| M20 | A failing task attempt loses its duration record | `test_a_failing_task_reports_a_duration_under_a_distinct_state` |
| M22 | Timing state keyed globally instead of per task | 6 tests |
| M23 | The start reading is never removed (state leaks) | `test_finished_tasks_leave_no_timing_state_behind` |
| M25 | The database listener loses its containment `try`/`except` | `test_a_failing_capture_leaves_the_statement_result_untouched` |
| M26 | The request producer entry point loses its containment | 2 tests |
| M27 | The recorder's own validation containment is stripped | `test_recording_an_unusable_duration_is_dropped_rather_than_raised` |
| M28 | NaN and negative durations accepted instead of rejected | same |
| M29 | The base production compose enables the flag | `test_prod_never_enables_the_dev_instrument_surface` |
| M30 | The dev override stops enabling the flag | `test_local_override_enables_the_dev_instrument_surface` |
| M31 | `.env.example` comments out the statement cap | `test_env_example_documents_the_instrument_contract` |
| M32 | The threshold default drifts to 500 | `test_instrument_settings_defaults` |
| M33 | The recorder's process default drifts from the settings default | `test_instrument_defaults_match_the_recorder_process_defaults` |
| M34 | The proxy denylist adds `server-timing` (frontend) | the proxy relay test |
| M35 | The pre-existing hand-rolled per-task timing returns `None` | 3 tests in `test_worker_tasks.py` |
| M36 | The Celery duration signals are never connected | 5 tests |
| M37 | The terminal state is hard-coded to `SUCCESS` | `test_a_failing_task_reports_a_duration_under_a_distinct_state` |
| M38 | The scope notice is dropped from the payload | `test_response_states_that_it_covers_one_process_only` |
| M39 | The production *overlay* enables the flag | `test_prod_never_enables_the_dev_instrument_surface` |

### Survived (4)

None of these breaks an outcome the spec defines. All four are recorded rather than
waved away.

| # | Mutation | Why it survives | Severity |
| --- | --- | --- | --- |
| M24 | Both Celery receivers lose their `try`/`except` entirely | Confirms the authors' disclosure. Celery's `Signal.send` already swallows a receiver's exception, so the task's result, exception and retry behaviour are unchanged either way. The suite cannot tell the two containments apart | None — disclosed, and honestly documented (see below) |
| M13b | A constant `+1.0` ms offset applied to the single shared measurement | Every assertion is *relative*: header `dur` still equals the log's `response_start_ms`, and the streaming test's floor is comfortably clear. Nothing pins the reported number to real elapsed time | Low — a spec-precision gap, not an implementation defect (gap 1) |
| M21 | Retry attempts of one task id share a single slot instead of a LIFO stack | Attempts are **sequential**, not nested, on both the eager test path and a real worker: `postrun` removes the reading before the next `prerun` records one. The stack is defence against a nesting that does not occur | Low — mechanism beyond any AC (gap 4) |
| M40 | The recorder's lock replaced with a null context | A bounded `deque` append is atomic under CPython's GIL, which is exactly what the module docstring says. The lock's stated purpose — free-threaded builds, and future read-modify-writes — is out of reach of this interpreter | Low — real property, untestable sensor here (gap 2) |

---

## Known limitations — confirmed, not rediscovered

All three disclosures were checked and all three are true.

1. **The Celery containment is unsensored.** Confirmed by M24: stripping both
   `try`/`except` blocks kills no test. It is documented rather than implied to be
   tested — `backend/app/worker/instrumentation.py:26-31` states that Celery already
   contains a receiver's exception and gives three non-correctness reasons for keeping
   the guard, and `backend/tests/test_worker_task_duration.py:206-212` says outright
   that the pair "does not discriminate the instrument's containment from Celery's".
   That is the honest framing.
2. **A slow statement ending in a database error is not captured.** Verified
   independently: a `SELECT pg_sleep(0.3) FROM no_such_table` at threshold 0 captured
   nothing, because `after_cursor_execute` does not fire. Documented at
   `backend/app/infrastructure/db/instrumentation.py:30-34` and in
   `docs/ops/instrumentation.md:134-137`, and the runbook wording is pinned by
   `test_ops_docs.py::test_instrumentation_documents_that_failed_statements_are_not_captured`.
3. **A truly-unhandled exception's response carries neither `Server-Timing` nor
   `X-Request-ID`.** Confirmed by reading and by the committed test; it is the
   pre-existing boundary of a pure-ASGI middleware sitting inside Starlette's
   `ServerErrorMiddleware`, shared with the already-shipped `X-Request-ID`. Documented
   at `backend/app/infrastructure/web/middleware.py:36-42` and
   `docs/ops/instrumentation.md:138-143`.

---

## Ranked gaps

Nothing here blocks the cycle. Ordered by how much it would cost to be wrong.

1. **The `Server-Timing` criterion is relative, not absolute (OBS-08).** The AC pins the
   header's `dur` to the access record's `response_start_ms` and nothing else, so a
   uniform offset applied to the shared measurement satisfies every assertion (M13b).
   The intent — "one measurement, two consumers" — is fully sensored (M15 kills a split
   into two independent readings); what is unpinned is that the shared number is a real
   elapsed time. Cheap fix if wanted: bound the header from below by a deliberate
   in-handler sleep.
2. **The recorder's lock is not discriminable on CPython (OBS-06).** The AC itself is
   demonstrated — 1600 concurrent samples, none lost, capacity respected — but the lock
   can be removed with no test failing (M40), because `deque.append` is atomic under the
   GIL. The design docstring is already explicit that the lock exists for free-threaded
   builds and future read-modify-writes, so this is a limit of the runtime, not a
   missing test.
3. **The Celery containment cannot be sensored here (invariant 3).** Disclosed,
   confirmed, documented honestly. No action.
4. **The per-attempt LIFO stack is unsensored (M21).** The spec-level outcome — one
   record per attempt — is covered and killed by M22. The stack guards against nested
   attempts, which neither the eager path nor a real worker produces. Harmless; worth
   knowing it is untested if anyone simplifies it later.
5. **Record inconsistency in `test_ops_docs.py`.** Its runbook block is headed
   `(OBS-24)`, but OBS-24 in `spec.md` is the production-compose criterion, covered by
   `test_compose_prod.py`. The runbook is task D2's deliverable and has no AC of its
   own. Comment-level only; the spec's own mapping is internally consistent.
6. **`test_a_failing_capture_leaves_a_database_error_raised_as_before` cannot fail.**
   Because `after_cursor_execute` never fires for a failing statement, the monkeypatched
   exploding `record_query` is never reached — the test restates limitation 2 rather than
   sensing containment. Its sibling
   (`..._leaves_the_statement_result_untouched`) does the real work and is what killed
   M25. No behaviour is unverified; one test is just weaker than it reads.
7. **Two ACs are verified through a stand-in rather than the real population.**
   OBS-16's "for every registered task" is shown on tasks declared inside the test (the
   mechanism is registry-wide signals, and M36 kills the wiring), and OBS-10's
   "application's own exception handlers" is asserted on a synthetic FastAPI app rather
   than on `create_app`. The latter was checked independently during verification: on
   the assembled application, a 401 from `get_authenticated_user` and a 422 from the
   validation handler both carry `Server-Timing`. Behaviour holds; no committed test
   pins it at that level.

## Reproduction

```bash
# backend, from backend/
LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test \
LEARNY_REDIS_URL=redis://localhost:6379/0 .venv/bin/python -m pytest -q

# frontend, from frontend/
npx vitest run
```
