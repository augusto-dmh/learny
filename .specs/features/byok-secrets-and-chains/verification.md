# BYOK secrets and chains verification

**Verdict**: PASS
**Profile**: standard
**Diff range**: `origin/main..HEAD` = `origin/main..9a52918` (branch `feat/byok-key-routes-and-decks`, batch B). This round is scoped by the post-round-5 diff `a9f9267..9a52918`: `63b0979`, `f020b3f`, `cfd7b6d`, plus the docs commits `ebaa21a` and `9a52918`
**Round**: 6 - scoped (re-verifies C38, the only non-PASS verdict of round 5, and every check whose files `a9f9267..9a52918` touched; everything else is carried from `a9f9267` and marked as carried)
**Verifier**: independent sub-agent (author != verifier)

The fault that survived round 5 (F5, `setDraft("")` dropped after a successful save) is now killed. The C38 proof fails under it at `frontend/tests/account-provider-keys.test.tsx:183` (`expected 'sk-proj-typed-into-the-input-01234567…' to be ''`). The four new sensors are green and discriminating: each new surface was made to fail once (F6-F9, all killed). All 44 proofs re-ran green at `9a52918`: one backend invocation (111 passed, 0 skipped, 0 failed) and one frontend invocation (8 of 8).

**Ranked gaps**: none blocking. One observation follows under Observations: `uvicorn.access` and the bare `uvicorn` logger get the filter but no test logs on them.

## History

- Rounds 1-3 (batch A, PR #76, `ccfb37d..e73640b`, checks C1-C7, C19-C27, C44): rounds 1 and 2 each found one missing sensor, and both were closed. Round 3 ended PASS at `e73640b`.
- Round 4 (batch A review-fix diff `549c3da..eff1765`): 2 missing sensors were found and closed by `52f1df8`. PASS at `52f1df8`.
- Round 5 (batch B, full, every check at `a9f9267`): all 44 proofs were green with located evidence. Faults F1-F4 were killed. F5 (`provider-keys-section.tsx:133`, the save does not clear the draft) left every proof green, so the verdict was FAIL on C38 (a missing sensor, not a behaviour defect). Round 5 also logged 4 non-blocking observations (uvicorn loggers unmasked; Gemini keys outside `AIza…`; no acceptance test at 20/256; C30's selector missed the legacy-handle test).

## Scope of this round

`git diff --stat a9f9267..9a52918` touches these code and test files:

- `backend/app/core/logging.py` (`_SERVER_LOGGERS` at :149; the logger-level filter loop at :254-255)
- `backend/tests/test_logging_redaction.py` (new `test_uvicorn_records_are_masked_on_their_own_handlers`, :206-231)
- `backend/tests/test_web_provider_keys.py` (new `test_keys_at_the_length_bounds_are_accepted[20,256]`, :278-290; later lines shift by +15)
- `backend/tests/infrastructure/test_user_adapter_cache.py` (new `test_evicting_a_fingerprint_drops_only_its_entries`, :142-154)
- `backend/tests/worker/test_byok_decks.py` (rename only: the legacy-handle test is now `test_poll_pins_credential_only_when_the_handle_names_one`, :331)
- `frontend/tests/account-provider-keys.test.tsx` (C38 reopen assertion, :178-183; later lines shift by +6)
- docs: `plan.md` (2 Assumptions rows), `checks.md` (ticks), `verification.md`

Re-verified, with citations refreshed at `9a52918`: C38 (the round-5 non-PASS); C33, C34 and C35 (`core/logging.py` changed); C11-C18 and C43 (`test_web_provider_keys.py` changed); C23 and C44 (`test_user_adapter_cache.py`, the cache eviction row); C28-C32 (`test_byok_decks.py` changed; C30's selector now matches 2 tests); C36-C42 (`account-provider-keys.test.tsx` changed). Carried from `a9f9267` because no file they cite or exercise was touched: C1-C10, C19-C22, C24-C27. Their proofs still re-ran green at `9a52918` in the same invocation.

## Checks (proofs re-run at 9a52918)

Backend, one invocation from `backend/`: `LEARNY_REQUIRE_DB=1 LEARNY_TEST_DATABASE_URL=…/learny_test_byok uv run pytest -v <the 15 proof files> -k "<all 43 checks.md selectors, or-joined, plus keys_at_the_length_bounds_are_accepted, evicting_a_fingerprint_drops_only_its_entries, uvicorn_records_are_masked_on_their_own_handlers, both_process_assemblies_install_the_masking_filter>"`. Result: **111 passed, 200 deselected, 0 skipped, 0 failed**, exit 0. That is round 5's 105, plus 2 bound cases, the eviction test, the uvicorn test, the assemblies test, and the renamed legacy test that C30's selector now picks up. Each named test appears individually as PASSED.

Frontend: `npx vitest run --maxWorkers=2 --minWorkers=1 --reporter=verbose tests/account-provider-keys.test.tsx`. Result: **8 passed (8)**, exit 0, and each `-t` name shows ✓.

| Check | Claim | Proof run | Evidence | Result |
| --- | --- | --- | --- | --- |
| C1 | only sealed columns; no plaintext key or DEK | `row_holds_no_plaintext` PASSED | `backend/tests/test_provider_credentials_repository.py:74` `assert key_bytes not in raw`; `:75` `assert dek not in raw` | PASS - citation carried from a9f9267 |
| C2 | fresh DEK, nonces and ciphertext per seal; both open | `fresh_dek_and_nonce_per_seal` PASSED | `backend/tests/infrastructure/test_secrets_envelope.py:50` `first_dek != second_dek`; `:55`; `:57-58` | PASS - citation carried from a9f9267 |
| C3 | other user, other provider, flipped byte raise | `associated_data_binds_owner`, `tampered_ciphertext_rejected[x4]` PASSED | `backend/tests/infrastructure/test_secrets_envelope.py:70-73`, `:103` `pytest.raises(SealedSecretError)` | PASS - citation carried from a9f9267 |
| C4 | rotation rewraps, ciphertext identical, `kek_id` updated, re-run 0 | `rewraps_without_touching_ciphertext` PASSED | `backend/tests/test_cli_rotate_secrets_kek.py:104`, `:107` `row.kek_id == new_kek_id`, `:117` `"rewrapped=0"` | PASS - citation carried from a9f9267 |
| C5 | unknown KEK counted, exit 1; resolver serves house | `unknown_kek_exits_one`, `unknown_kek_serves_house_chain` PASSED | `backend/tests/test_cli_rotate_secrets_kek.py:143-144`; `backend/tests/test_web_byok_generation.py:512-514` | PASS - citation carried from a9f9267 |
| C6 | malformed KEK names the variable not the value; valid and unset load | `secrets_kek` (9) PASSED | `backend/tests/test_config.py:615-616`, `:640`, `:655` | PASS - citation carried from a9f9267 |
| C7 | account delete cascades that user's rows only | `cascades_with_its_user`, `delete_account_erases_provider_keys` PASSED | `backend/tests/test_provider_credentials_repository.py:107`; `backend/tests/test_web_auth.py:548` `owner_rows == 0`, `:554` | PASS - citation carried from a9f9267 |
| C8 | feature off: GET `{enabled:false,providers:[]}`, writes 404 | `disabled_feature[no_kek,no_binding]` PASSED | `backend/tests/test_web_provider_keys.py:139` `== {"enabled": False, "providers": []}`; `:140` `== (404, 404, 404)` (above the inserted test, lines unmoved) | PASS - citation carried from a9f9267 |
| C9 | bound providers in registry order, full shape, `powers_cards` anthropic only | `lists_offered_providers_with_powers` PASSED | `backend/tests/test_web_provider_keys.py:157`, `:159-169`, `:174-183` (unmoved) | PASS - citation carried from a9f9267 |
| C10 | PUT 200 with last4; replace keeps one row with a new id | `put_stores_and_replace_mints_new_row` PASSED | `backend/tests/test_web_provider_keys.py:202`, `:206-207`, `:211` (unmoved) | PASS - citation carried from a9f9267 |
| C11 | missing / whitespace / 19 / 257 / no prefix give 422, no echo | `malformed_key_422_never_echoes[x7]` PASSED; plus `keys_at_the_length_bounds_are_accepted[20,256]` PASSED | `backend/tests/test_web_provider_keys.py:249-250` the 19 and 257 lengths; `:267` `assert resp.status_code == 422`; `:273` `assert value[start : start + 8] not in resp.text`. The acceptance side of the bounds: `:288` `== 200`, `:289` `resp.json()["last4"] == "KKKK"`, `:290` one row | PASS - verified at 9a52918 |
| C12 | unoffered `gemini` / `mistral` writes give 404 | `unoffered_provider_404[x2]` PASSED | `backend/tests/test_web_provider_keys.py:307` `== (404, 404, 404)`; `:308` `probe.calls == []` | PASS - verified at 9a52918 |
| C13 | test route maps 4 outcomes; stored key plus profile host | `test_route_maps_probe_outcomes[x4]`, `lists_models_with_profile_host` PASSED | `backend/tests/test_web_provider_keys.py:337` `resp.json() == {"ok": outcome.ok, "reason": outcome.reason}`; `:339` `probe.calls == [("byok-gpt", "https://api.openai.com/v1", _OPENAI_KEY)]`; `backend/tests/infrastructure/test_credential_probe.py:88` | PASS - verified at 9a52918 |
| C14 | test with no stored key gives 404 | `test_without_key_404` PASSED | `backend/tests/test_web_provider_keys.py:350` `assert resp.status_code == 404` | PASS - verified at 9a52918 |
| C15 | DELETE 204, row gone, second DELETE 204 | `delete_is_idempotent_204` PASSED | `backend/tests/test_web_provider_keys.py:368` `first.status_code == 204`; `:370` `second.status_code == 204` | PASS - verified at 9a52918 |
| C16 | writes without CSRF give 403, row unchanged | `writes_require_csrf` PASSED | `backend/tests/test_web_provider_keys.py:424` `== (403, 403, 403)`; `:425` `_rows(db_conn, user_id) == before` | PASS - verified at 9a52918 |
| C17 | PUT and test give 429 once spent | `writes_rate_limited_429` PASSED | `backend/tests/test_web_provider_keys.py:446` `puts == [200, 200, 429]`; `:447` `tests == [200, 200, 429]` | PASS - verified at 9a52918 |
| C18 | no 8-char substring of either key in any body | `responses_never_carry_key_material` PASSED | `backend/tests/test_web_provider_keys.py:476` `assert fragment not in body` over both keys and every body (`:472-476`) | PASS - verified at 9a52918 |
| C19 | ask and teach on the learner key | `turn_served_by_learner_key` PASSED | `backend/tests/test_web_byok_generation.py:199-200`, `:202`, `:205` | PASS - citation carried from a9f9267 |
| C20 | explain on the learner key | `explain_served_by_learner_key*` PASSED | `backend/tests/test_web_byok_generation.py:319`, `:327` | PASS - citation carried from a9f9267 |
| C21 | user-key failure never falls to house | `never_falls_from_user_key_to_house*` PASSED | `backend/tests/infrastructure/test_answering_routing.py:700`, `:704` `house_entry.calls == 0` | PASS - citation carried from a9f9267 |
| C22 | uncovered mode served by house | `uncovered_mode_served_by_house*` PASSED | `backend/tests/infrastructure/test_answering_routing.py:769-772`; `backend/tests/test_web_byok_generation.py:369-371` | PASS - citation carried from a9f9267 |
| C23 | two learners, two keys, two cache entries | `two_learners_two_keys`, `keys_on_fingerprint` PASSED | `backend/tests/test_web_byok_generation.py:398-401`; `backend/tests/infrastructure/test_user_adapter_cache.py:60` `learner_a is not learner_b`, `:62` `len(cache) == 2` (above the inserted test, unmoved) | PASS - verified at 9a52918 |
| C24 | replace then delete take effect next request | `replace_and_delete_take_effect_next_request` PASSED | `backend/tests/test_web_byok_generation.py:432-438` | PASS - citation carried from a9f9267 |
| C25 | learner turn 0 USD, `ask_count` +1 | `learner_key_debits_zero_usd_counts_call` PASSED | `backend/tests/test_web_byok_generation.py:467-469` | PASS - citation carried from a9f9267 |
| C26 | kill switch 503, no adapter call | `kill_switch_refuses_learner_key` PASSED | `backend/tests/test_web_byok_generation.py:491-492` | PASS - citation carried from a9f9267 |
| C27 | user-key-only profile never in a house chain or catalog | `user_key_only*` (8) PASSED | `backend/tests/infrastructure/test_provider_profiles.py:329-339`, `:357-362`, `:369` | PASS - citation carried from a9f9267 |
| C28 | card suggestions on the learner key, `quiz_model`, 0 USD | `suggestions_use_learner_key` PASSED | `backend/tests/test_web_byok_cards.py:154` `== [_KEY]`; `:155`; `:158` `_usd_today(...) == 0` | PASS - verified at 9a52918 |
| C29 | deck and note refresh resolve the owner's key in the task | `deck_task_resolves_owner_key`, `refresh_cards_resolves_owner_key` PASSED | `backend/tests/worker/test_byok_decks.py:250` `== [_KEY]`; `:254`; `:296` (rename only, lines unmoved) | PASS - verified at 9a52918 |
| C30 | handle carries `credential_id`; poll uses the same credential; legacy handle polls house | `poll_pins_credential` selector now runs both `test_poll_pins_credential` and `test_poll_pins_credential_only_when_the_handle_names_one`, both PASSED | `backend/tests/worker/test_byok_decks.py:314` `round_tripped["credential_id"] == str(credential_id)`; `:323` `[fake.api_key for fake in poll_adapters] == [_KEY]`; `:345` `house.requested == ["anthropic"]`; `:346` `fakes == []` | PASS - verified at 9a52918 |
| C31 | pinned key gone: job `failed`, no collect | `poll_fails_when_pinned_key_gone[deleted,replaced]` PASSED | `backend/tests/worker/test_byok_decks.py:371-373` | PASS - verified at 9a52918 |
| C32 | Celery payloads lack the canary; ids, handle, deadline only | `task_payloads_carry_ids_only` PASSED | `backend/tests/worker/test_byok_decks.py:408` `_KEY not in serialized`; `:412` handle keys | PASS - verified at 9a52918 |
| C33 | 4 key shapes masked in message, args, extras, exception; both assemblies | `masks_provider_key_shapes[x8]`, `both_process_assemblies_install_the_masking_filter`, `uvicorn_records_are_masked_on_their_own_handlers` PASSED | `backend/tests/test_logging_redaction.py:169` `output.count("carries") == 6`; `:170` `key not in output`; `:172` marker present. Assemblies read directly: `backend/app/main.py:98` and `backend/app/worker/celery_app.py:57` call `configure_logging()`. The server loggers: `backend/app/core/logging.py:149` and `:254-255`; asserted at `backend/tests/test_logging_redaction.py:230` `key not in output`, `:231` marker present | PASS - verified at 9a52918 |
| C34 | canary absent across the whole lifecycle | `canary_never_surfaces` PASSED | `backend/tests/test_byok_leak_canary.py:408` `scan(channels, …) == []`; `:411` (test file untouched; re-run against the changed `logging.py`) | PASS - verified at 9a52918 |
| C35 | negative control reports the unmasked path | `scanner_catches_deliberate_leak` PASSED | `backend/tests/test_byok_leak_canary.py:448`, `:451` (test file untouched; re-run against the changed `logging.py`) | PASS - verified at 9a52918 |
| C36 | disabled: no keys heading | ✓ `is hidden when disabled` | `frontend/tests/account-provider-keys.test.tsx:133` heading `toBeNull()` (above the insertion, unmoved) | PASS - verified at 9a52918 |
| C37 | configured and unconfigured rows | ✓ `renders configured and unconfigured rows` | `frontend/tests/account-provider-keys.test.tsx:143-147`; `:152` `type === "password"`; `:153` (unmoved) | PASS - verified at 9a52918 |
| C38 | after save: input empty, configured shown, key never rendered | ✓ `save clears and never re-renders the key` | `frontend/tests/account-provider-keys.test.tsx:172` the input is gone; `:173-177` key absent from text, HTML and every input value; `:181-183` Replace reopens the input and `expect(reopened.value).toBe("")`. F5 is now killed at `:183` | PASS - verified at 9a52918 |
| C39 | "Key works" plus 3 distinct reasons | ✓ `test outcome messages` | `frontend/tests/account-provider-keys.test.tsx:209` `toBe("Key works")`; `:210-215` 3 messages, `new Set(seen).size` 4 | PASS - verified at 9a52918 |
| C40 | delete confirms first; cancel sends nothing | ✓ `delete confirms first` | `frontend/tests/account-provider-keys.test.tsx:231` 0 DELETE after cancel; `:235` 0 before confirm; `:239` 1 after | PASS - verified at 9a52918 |
| C41 | failed save, test, delete: inline error, state kept | ✓ `failure keeps state and shows error` | `frontend/tests/account-provider-keys.test.tsx:258-260`, `:264-267`, `:272-273` | PASS - verified at 9a52918 |
| C42 | disclosure copy | ✓ `disclosure copy` | `frontend/tests/account-provider-keys.test.tsx:279` exact string | PASS - verified at 9a52918 |
| C43 | four routes 401 without a session | `routes_require_session_401` PASSED | `backend/tests/test_web_provider_keys.py:495` `== [401, 401, 401, 401]` | PASS - verified at 9a52918 |
| C44 | cache bound 256 LRU; TTL entry rebuilt | `lru_bound_and_ttl*` (3) PASSED | `backend/tests/infrastructure/test_user_adapter_cache.py:92` `len(cache) == DEFAULT_MAX_ENTRIES`; `:94` least recently used gone; `:112` expired entry rebuilt (unmoved). Round 5's table had no C44 row; this row restores it | PASS - verified at 9a52918 |

## Coverage

Rows whose authority `a9f9267..9a52918` touched were recomputed at `9a52918`. The others are carried from `a9f9267` (round 5's recompute), and each says so.

| Set (size) | Recomputed from | Member -> proof | Unproven |
| --- | --- | --- | --- |
| GET statuses (2) | carried from a9f9267 (`provider_keys.py` untouched) | 200 C9 · 401 C43 | - |
| PUT statuses (6) | carried from a9f9267; citations refreshed at 9a52918 | 200 C10 · 401 C43 · 403 C16 · 404 C12 · 422 C11 · 429 C17 | - |
| POST test statuses (5) | carried from a9f9267; citations refreshed | 200 C13 · 401 C43 · 403 C16 · 404 C14 · 429 C17 | - |
| DELETE statuses (4) | carried from a9f9267; citations refreshed | 204 C15 · 401 C43 · 403 C16 · 404 C12 | - |
| test outcomes (4) | carried from a9f9267 | C13 x4; own layer `test_credential_probe.py` | - |
| key-format rejections (5) + accepted bounds (2) | verified at 9a52918: `_key_from_body` `provider_keys.py:149-159`, bounds `MIN_KEY_CHARS`/`MAX_KEY_CHARS` `:63-64` | missing, whitespace, 19, 257, no prefix C11; accepted 20 and 256 `test_web_provider_keys.py:288-290` (F7 killed) | - |
| provider literals (3) | carried from a9f9267 | anthropic, openai C9 · gemini C12 | - |
| feature-off conditions (2) | carried from a9f9267 | C8 | - |
| generation surfaces on the learner key (6) | carried from a9f9267 | C19 x2 · C20 · C28 · C29 x2 | - |
| fall-over cases (3) | carried from a9f9267 | C21 · C22 · C24 | - |
| key lifecycle effect (3) | carried from a9f9267 | C24 x2 · C7 | - |
| rotation outcomes (3) | carried from a9f9267 | C4 x2 · C5 | - |
| KEK config values (4) | carried from a9f9267 | C6 | - |
| envelope tamper (3) | carried from a9f9267 | C3 | - |
| adapter cache eviction (4) | verified at 9a52918: `user_adapters.py` (LRU, TTL, fingerprint key, `evict_fingerprint` :117-129) | LRU, TTL C44 · fingerprint change C23/C24 · eviction on write at its own layer `test_user_adapter_cache.py:149-154` (F8 killed) and at the route `test_web_provider_keys.py:400-403` | - |
| deck pin cases (3) | verified at 9a52918: `_poll_quiz_deck_body` `tasks.py:739-764` | pinned present C30 · gone C31 · legacy C30, now inside C30's own selector (F9 killed by it) | - |
| leak channels (7) | verified at 9a52918 for logs: `configure_logging` now installs the filter on the Learny root handler and on `uvicorn`, `uvicorn.error`, `uvicorn.access` (`logging.py:149`, `:254-255`) | logs C33/C34 (root handler, both assemblies; `uvicorn.error` at `test_logging_redaction.py:230-231`, F6 killed) · responses C18/C34 · exceptions C34 · Celery C32/C34 · credential and adapter repr C34 · 422 echo C11 | - |
| ledger effects (3) | carried from a9f9267 | C25 · C26 · C28 | - |
| Account section states (6) | verified at 9a52918: `provider-keys-section.tsx` | hidden C36 · configured, unconfigured C37 · error C41 · confirm C40 · saved C38 (F5 killed) | - |
| startup config: KEK (2 assemblies) | carried from a9f9267 | C6 | - |
| startup config: masking (2 assemblies) | read directly at 9a52918: `app/main.py:98`, `app/worker/celery_app.py:57` | C33 plus `test_logging_redaction.py:195-203` | - |

## Test policy rows

| Row | Files it classifies | Required proof | Expectation met |
| --- | --- | --- | --- |
| Decides, reached across a boundary | `web/provider_keys.py`, `answering/probe.py`, chain resolution in `dependencies.py`, deck pin in `worker/tasks.py` | boundary: HTTP client `test_web_provider_keys.py` (now with both bound acceptances) and the task functions `test_byok_decks.py` (legacy handle under C30's selector); own layer: `test_credential_probe.py`, `test_answering_routing.py` | yes - re-judged at 9a52918 |
| Decides, not reached across a boundary | `core/logging.py` (changed), `user_adapters.py`, envelope, rotation | own layer: `test_logging_redaction.py` (8 shape cases, assemblies, and the server-logger case), `test_user_adapter_cache.py` (LRU, TTL, and now `evict_fingerprint` directly at :142-154), envelope and CLI tests | yes - re-judged at 9a52918; round 5's caveat (eviction proven only via the route) is closed |
| Instrumentation | entities, `lib/provider-keys.ts` | consumer proofs C29-C32, C37-C41 | yes - carried from a9f9267 (files untouched) |

## Faults injected

Scratch worktree: `git worktree add --detach <scratchpad>/wt HEAD` at `9a52918`. Backend runs used `UV_PROJECT_ENVIRONMENT=<real>/backend/.venv uv run --no-sync` from the scratch `backend/`. `app.core.logging`, `app.infrastructure.web.provider_keys`, `app.worker.tasks` and `app.infrastructure.answering.user_adapters` all printed scratch `__file__` paths. The frontend ran in the scratch `frontend/` with `node_modules` symlinked from the real tree. The failure at the scratch-only mutation confirms vitest resolved the scratch component. Each fault was reverted with `git checkout -- <file>` before the next, and the scratch `git status` was clean between faults. The real tree's `git status --porcelain` was empty before and after. The scratch worktree is removed.

| Mutation | Location | Killed |
| --- | --- | --- |
| F5 (round-5 survivor, re-injected): the draft is not cleared after a successful PUT | `frontend/app/components/provider-keys-section.tsx:133` | yes: `save clears and never re-renders the key` fails at `account-provider-keys.test.tsx:183` (`expected 'sk-proj-typed-into-the-input-01234567…' to be ''`); 7 others green |
| F6: `uvicorn.error` dropped from `_SERVER_LOGGERS` | `backend/app/core/logging.py:149` | yes: `test_uvicorn_records_are_masked_on_their_own_handlers` (`assert key not in output`); 15 others green |
| F7: upper key bound off by one (`<= MAX_KEY_CHARS` to `< MAX_KEY_CHARS`) | `backend/app/infrastructure/web/provider_keys.py:154` | yes: `test_keys_at_the_length_bounds_are_accepted[256]`; 26 others green |
| F8: `evict_fingerprint` counts the stale entries but deletes none | `backend/app/infrastructure/answering/user_adapters.py:127` | yes: `test_evicting_a_fingerprint_drops_only_its_entries` (`assert 2 == 0`) |
| F9: a handle without `credential_id` resolves the owner's current key (`if handle.credential_id is not None` to `if True`) | `backend/app/worker/tasks.py:742` | yes: under C30's own selector `-k poll_pins_credential`, `test_poll_pins_credential_only_when_the_handle_names_one` (`[] == ['anthropic']`) |
| F1-F4 (round 5): pin ignored; feature on without a binding; Gemini shape unmasked; cards not stamped `user_keyed` | `tasks.py:531`, `dependencies.py:829`, `logging.py:42`, `quiz/learner.py:65,68` | yes - carried from a9f9267 (those code lines are unchanged in `a9f9267..9a52918`) |

The cap of 5 new injections was reached. Every surface the post-round diff created or touched was made to fail once.

## Observations (non-blocking, outside any check's wording)

- `_SERVER_LOGGERS` names 3 loggers, but only `uvicorn.error` is exercised. No test logs on `uvicorn.access` or on the bare `uvicorn` logger. By inspection, a mutation that drops `uvicorn.access` would survive. It was not injected because of the cap. Impact is low: access lines carry the client address, method, path and status, and no route takes a key in its URL. The decision is a plan Assumptions row, not a check. Closing it is one line: parametrize `test_uvicorn_records_are_masked_on_their_own_handlers` over the three names.
- Round-5 observations: uvicorn masking is closed (code `logging.py:254-255`, sensor above). Gemini keys outside `AIza…` are now an accepted plan Assumptions row (`plan.md`). The 20/256 acceptance is closed (C11 row). C30's selector is closed (rename).
- `uvicorn app.main:app` (the `Dockerfile` and both compose files) imports the module after uvicorn's own `dictConfig`, and `create_app()` calls `configure_logging()` at `main.py:98`. So the logger-level filter is attached after uvicorn configures its handlers, and `dictConfig` does not clear existing logger filters.

## Gate

- Targeted proofs at `9a52918`: backend **111 passed, 0 failed, 0 skipped** (`LEARNY_REQUIRE_DB=1`); frontend **8 passed**.
- `ruff check` and `ruff format --check` on the 5 touched backend files: exit 0.
- Not re-run this round (scoped; memory budget): the full backend and frontend suites and `tsc --noEmit`. Round 5 ran them at `a9f9267`. The post-round diff adds tests and 9 lines in `logging.py` only.
- `validate_verification.py byok-secrets-and-chains`: exit 0 (0 errors, 0 warnings).
