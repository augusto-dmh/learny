# House Profiles — Validation (Verifier report)

- **Verdict: PASS** — 14/14 ACs matched (8 local-executed evidence, 6 static + CI-pending), 0 spec-precision gaps, 0 deviations.
- **Diff range:** `5abafcf6..HEAD` (main tip → `feat/house-profiles` @ `cce41be3`); 10 commits, +3424/−33.
- **Date:** 2026-09-13. Verifier did not author the code; all assertions re-derived from `spec.md` (HP-01..HP-14), `context.md` D-1..D-7 (AD-350..AD-356), `design.md`, and ADR-0020's "Amendment (2026-09): End-User Choice Among House Profiles" — all present and consistent with what shipped.

## Gate results (run by the verifier on this tree)

| Gate | Result |
|---|---|
| `backend: uv run pytest` | **2030 passed, 940 skipped** (all db-gated: no Docker/Postgres in session), 0 failed — re-run clean after every mutation revert |
| `backend: ruff check . && ruff format --check .` | clean (319 files formatted) |
| `python3 backend/scripts/check_boundaries.py` | clean |
| `frontend: npm test` (vitest) | **922 passed / 77 files** (runs 2 and 3 of 3; run 1 had 1 transient `waitFor` timeout in a pre-existing non-cycle file, not reproducible in 2 full re-runs; cycle files stable across 4 focused runs) |
| `frontend: npx tsc --noEmit` | clean |

Per the pre-declared environment fact, db-gated tests (`requires_db`) skip locally; **CI's `backend-test` job is the execution authority** for HP-01, HP-02, and the db-gated API/wiring tests. Nothing was weakened, skipped, or xfailed.

## Per-AC evidence

Legend: LOCAL = executed in this session; CI = db-gated, assertion statically verified here, execution authority is CI.

| AC | Test file::name | What is asserted | Matches spec |
|---|---|---|---|
| HP-01 | `backend/tests/test_migrations.py::test_migration_0029_creates_user_ai_preferences` (CI) | absent at 0028 → present at 0029; columns exactly {user_id, profile_id, created_at, updated_at}; profile_id NOT NULL (IntegrityError without it); PK == [user_id]; FK → users ON DELETE CASCADE; server-defaulted timestamps populate; deleting the user cascades the row; downgrade to 0028 drops (users survives); re-upgrade restores | **y** (CI; note 1) |
| HP-02 | `backend/tests/test_repositories.py::test_ai_preference_upsert_stores_and_replaces_the_single_row`, `::test_ai_preference_delete_is_idempotent_and_owner_scoped`, `::test_ai_preference_row_cascades_with_its_user`, `::test_ai_preference_upsert_leaves_the_user_untouched` (CI) | get missing → None; put stores; re-put replaces the id on the ONE remaining row; delete True then False; another user's row unreachable; cascade with user delete | **y** (CI) |
| HP-03 | `backend/tests/test_generation_chain.py::test_a_stored_choice_leads_and_the_registry_follows_deduped`, `::test_an_unset_choice_builds_the_operator_default_chain`, `::test_an_unknown_stored_choice_falls_back_to_the_default_chain_with_a_warning`, `::test_a_mode_ineligible_choice_is_not_prefiltered_the_router_walk_decides`, `::test_a_chosen_lead_that_fails_serves_the_rest_in_todays_fail_over_shape`, `::test_two_users_with_different_choices_resolve_different_leads_in_one_process`, cache-clear test (LOCAL); `test_web_user_generation.py::test_a_stored_choice_leads_the_users_turn_chain`, `::test_a_stale_stored_choice_serves_the_default_chain`, `::test_the_chain_cache_is_keyed_on_the_choice_never_the_user` (CI) | chosen leads + registry remainder in order deduped; unset/unknown → exactly the default chain (+ one warning, never an error); ineligible lead stays in the chain and the router walk serves the next eligible entry; fail-over answer shaped like today's with the serving stamp; two choices → two leads in one process | **y** (note 2) |
| HP-04 | `test_generation_chain.py::test_the_explain_and_card_adapters_never_gain_a_preference_parameter` (LOCAL, signature-pin); `test_web_user_generation.py::test_the_explain_chain_stays_house_routed_despite_a_stored_choice` (CI, behavioral: explain-origin turn served by the house spy, spy.calls == 1, ordinary turn served by the user chain) | explain/quiz/card seams accept no preference input; a stored choice moves nothing about an explain-origin turn | **y** |
| HP-05 | `test_generation_chain.py::test_a_chosen_lead_that_fails_serves_the_rest_in_todays_fail_over_shape` (LOCAL: stamp = the profile that actually served), `::test_build_budget_resolves_the_registry_once_across_two_builds` (LOCAL: cheap stamp prices cheap); `::test_the_request_budget_prices_a_stamp_from_the_declared_profiles_catalog` + `test_web_user_generation.py::test_a_turn_served_from_the_user_chain_debits_the_callers_day` (CI) | per-answer profile_id stamp; debit resolves the serving profile's catalog; fail-over debits at the servER | **y** |
| HP-06 | `backend/tests/infrastructure/test_answering_routing.py` ROUTE-04 stream-bound suite (LOCAL, pre-existing); `routing.py` untouched in the diff range; the user chain is the same `RoutingGenerationAdapter` | fail-over only before the first emitted delta — unchanged mechanism over the reordered chain | **y** (static + pre-existing local tests) |
| HP-07 | `test_generation_chain.py::test_the_rate_limit_fires_before_any_chain_entry` (CI); `test_web_user_generation.py::test_the_daily_rails_refuse_before_the_user_chain_serves` (CI — chooser with a stored choice, 429 before retrieval/generation, conversation intact); `assert_generation` path untouched (service file unchanged in range) | rails precede any port touch regardless of resolved profile | **y** (CI) |
| HP-08 | `test_web_ai_profile.py::test_the_catalog_lists_declared_profiles_with_honest_copy` (registry order, copy + fallbacks, grounding, eligibility, **exact field-set assertion** — no kind/api_key_env/base_url/price/max_tokens leak), `::test_an_undeclared_registry_is_an_empty_catalog`, `::test_the_catalog_tracks_a_redeclared_registry_in_the_same_process`, `::test_unauthenticated_callers_are_rejected_on_every_endpoint` (all CI); unit mirrors in `test_provider_profiles.py` incl. `::test_a_declared_profile_named_default_still_appears` (seed excluded by construction, LOCAL) | catalog = declared registry, honest copy, legacy seed never appears, 401 unauth | **y** |
| HP-09 | `test_web_ai_profile.py::test_put_stores_replaces_and_me_carries_the_choice`, `::test_a_put_with_an_unknown_id_is_a_422_naming_the_problem_and_persists_nothing` (422 + detail names the id + prior choice survives), `::test_delete_unsets_and_is_idempotent` (204 twice), `::test_an_unset_choice_reads_null_and_me_reports_null`, `::test_the_writes_refuse_a_missing_csrf_token` (all CI) | GET `{profile_id: str\|null}`; PUT stores/replaces; unknown → 422 naming the problem; DELETE idempotent 204 | **y** (CI) |
| HP-10 | `test_web_ai_profile.py` (same tests, asserting `me.json()["ai_profile_id"]` null / set / **stale-as-stored** in `::test_a_stale_stored_id_is_returned_as_stored`) (CI); `MeResponse` field additively optional | `ai_profile_id: str\|null` reflecting the stored row, stale never rewritten | **y** (CI) |
| HP-11 | `test_provider_profiles.py::test_env_json_without_copy_fields_parses_exactly_as_before` (absent == explicitly empty), `::test_declared_copy_fields_parse_through` (LOCAL) | optional `display_name`/`description`, default empty, existing env JSON parses unchanged | **y** |
| HP-12 | `frontend/tests/account-ai-profile.test.tsx::does not exist in the DOM at all when the catalog is empty (absent, not disabled)`, `::lists the operator default plus one honest row per catalog profile` (LOCAL) | section absent (not disabled) on empty catalog; "Operator default (recommended)" + per-profile rows with copy, grounding/eligibility hints; empty description hides the line | **y** |
| HP-13 | same file: `::reflects the stored choice read from the choice endpoint`, `::choosing a profile persists via PUT with the CSRF token...`, `::choosing the default entry persists via DELETE...`, `::a failed PUT changes nothing visible and surfaces the backend's honest copy`, `::a failed reset...` (LOCAL) | PUT on choose (body + CSRF + same-origin asserted), DELETE on default, selection read from `/api/me/ai-profile`, backend `detail` surfaced verbatim on `role=alert`, non-optimistic selection | **y** |
| HP-14 | same file: `::renders a stale stored id as the operator default, never a phantom selection` (default checked; stale id nowhere in the DOM; exactly 3 radios) | stale id renders as default, never a phantom | **y** |

Notes: (1) HP-01's test asserts column presence/not-null/defaults but not the timestamptz type itself; the migration source (`DateTime(timezone=True)`, `server_default=func.now()`) is the type evidence — minor, non-blocking. (2) HP-03's turn-level test posts `mode=answer`; teach-mode serving is covered at chain level (mode-agnostic wiring + the router's shared eligibility walk) — minor, non-blocking.

## Discrimination sensor (13 behavior-level mutations, each run against its target tests, then reverted; `git status --porcelain` verified clean after every revert)

| # | Mutation (fault class) | Killed by | Result |
|---|---|---|---|
| M1 | `build_user_generation_chain` ignores the stored choice (serves default order) — *resolution reorder* | `test_a_stored_choice_leads_and_the_registry_follows_deduped` + 2 more (LOCAL) | **killed** |
| M2 | unknown stored id prepends the legacy-seed entry instead of exact default fallback — *stale fallback* | `test_an_unknown_stored_choice_falls_back_to_the_default_chain_with_a_warning` (LOCAL) | **killed** |
| M3 | `get_post_conversation_turn` passes the user chain as the explain chain — *explain isolation* | killer is db-gated (`test_the_explain_chain_stays_house_routed_despite_a_stored_choice`: spy.calls==1 + model assert) — **CI-pending**; local run all-skip. Signature-pin does NOT catch this wiring mutation | killed-by-CI (static verify) |
| M4 | `DailyBudget.usage_micros` ignores the serving profile's catalog — *budget stamp* | `test_build_budget_resolves_the_registry_once_across_two_builds` (LOCAL); db pricing test in CI | **killed** |
| M5 | `_user_generation_chains` collapses to one shared slot (one user's chain served to everyone) — *cache keying* | `test_two_users_with_different_choices_resolve_different_leads_in_one_process` (LOCAL) | **killed** |
| M6 | `learner_catalog` returns the synthetic legacy seed when nothing is declared — *catalog* | `test_an_undeclared_registry_yields_an_empty_catalog` (LOCAL) | **killed** |
| M7 | PUT accepts an unknown profile id (422 check disabled) — *PUT validation* | killer db-gated (`test_a_put_with_an_unknown_id_is_a_422...`) — **CI-pending** (local all-skip) | killed-by-CI (static verify) |
| M8 | `me()` hardcodes `ai_profile_id=None` (stale id rewritten to null / omitted) — *MeResponse* | killers db-gated (put-stores/test_a_stale_stored_id_is_returned_as_stored) — **CI-pending** | killed-by-CI (static verify) |
| M9a | AccountPanel renders the section whenever the catalog loaded, even when empty — *selector visibility* | `...does not exist in the DOM at all when the catalog is empty` (LOCAL) | **killed** |
| M9b | `effectiveChoice = storedChoice` unconditionally (phantom selection for stale id) | `...renders a stale stored id as the operator default, never a phantom selection` (LOCAL) | **killed** |
| M10 | DELETE returns 404 when nothing was set — *DELETE idempotency* | killer db-gated (`test_delete_unsets_and_is_idempotent` asserts second DELETE 204) — **CI-pending** | killed-by-CI (static verify) |
| M11 | user chain pre-filtered to ask-eligible at build time (design.md trap) — *mode-ineligible fallback* | `test_a_mode_ineligible_choice_is_not_prefiltered_the_router_walk_decides` (LOCAL) | **killed** |
| M12 | `get_card_generation` gains a `preference` parameter — *quiz/card signature-pin* | `test_the_explain_and_card_adapters_never_gain_a_preference_parameter` (LOCAL) | **killed** |

**Tally: 9 killed locally, 4 killed-by-CI (db-gated killers statically verified; local execution impossible in this session). 0 true survivors → 0 sensor-driven fix tasks.**

## Deviations

None. No `SPEC_DEVIATION` markers exist for this cycle; implementation matches every decided default (D-1..D-7 / AD-350..AD-356), including reorder-not-pin, stale-hint fallback, hidden-selector honesty, two-resource API shape, and the AD-147 device-local scoping (device-local hooks untouched in the diff).

## Fix tasks

None.

## CI-pending items (Stage 2 / publish must know)

1. **CI green run is the completion authority** for the db-gated evidence: HP-01, HP-02, the `/api/ai/profiles` + `/api/me/ai-profile` endpoint suite, `MeResponse.ai_profile_id`, the ask/teach turn wiring tests, the rails-on-user-path tests, and sensors M3/M7/M8/M10. A red `backend-test` job invalidates this PASS for those rows.
2. Migration `0029_user_ai_preferences` executes on CI's Postgres only (and in deployment); it has never run against a live DB in this session.
3. Non-blocking observations recorded above (HP-01 timestamptz type asserted only in source; HP-03 turn-level teach-mode not separately posted; AD-355's "≥1 selectable **non-default** profile" wording vs HP-12's "at least one selectable profile" — implementation follows the AC: visible iff catalog non-empty).
4. One transient frontend `waitFor` timeout occurred in 1 of 3 full vitest runs (pre-existing, non-cycle test; not reproducible; cycle files stable ×4). Not a cycle finding, but the flake exists somewhere in the pre-existing suite.

## Lessons

Clean PASS — no surviving mutant, no failed AC, no spec-precision gap, no deviation → nothing recorded in `.specs/lessons.json` (verified untouched: `git diff` empty).
