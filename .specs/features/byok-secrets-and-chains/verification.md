# BYOK secrets and chains verification

**Verdict**: FAIL
**Profile**: standard
**Diff range**: `origin/main..HEAD` = `origin/main..a9f9267` (branch `feat/byok-key-routes-and-decks`, batch B, 8 commits `a22ea59`..`a9f9267`; batch A merged earlier as PR #76)
**Round**: 5 - full (final batch; every check C1-C44, batch-A rows re-proven at this HEAD, not carried)
**Verifier**: independent sub-agent (author != verifier)

All 44 checks have a green proof at `a9f9267` with a located assertion. 4 of the 5 injected faults were killed. One fault survived: removing the input clear after a successful save (`provider-keys-section.tsx:133`) leaves every proof green. Under that fault, pressing **Replace key** after a save puts the submitted key back into the input's `value`, which AC 38 forbids ("never render the submitted value again"). I wrote a probe test and ran it in the scratch worktree: it passes at HEAD and fails under the fault. So the code at HEAD is correct, but the C38 proof cannot tell it apart from this wrong version. This is a missing sensor, not a behaviour defect.

**Ranked gaps**

1. C38: surviving mutant F5. `frontend/tests/account-provider-keys.test.tsx:158-178` checks the DOM only right after the save. It never presses Replace (or reopens the input) to show that the cleared draft stays cleared. **Closes with:** in that test, after `findByText("•••• 6789")`, click "Replace key" and assert `getByLabelText("API key for OpenAI").value === ""`. The verifier's scratch probe did exactly this: it passed at HEAD and was red under F5.

## History (batch A, PR #76)

- Rounds 1-3 (batch A over `ccfb37d..e73640b`, checks C1-C7, C19-C27, C44): round 1 and round 2 each found one missing sensor. The last was mutant M4 on the `order_learner_profiles` lead rule. Both were closed. Round 3 ended PASS at `e73640b` with 3144 backend tests passing in a clean scratch worktree.
- Round 4 (the review-fix diff `549c3da..eff1765`): the first pass at `c35b8fe` found 2 missing sensors on the fix surface (no behaviour defect). Commit `52f1df8` closed both. Final: PASS at `52f1df8`.
- The batch-B diff does not touch the batch-A files `infrastructure/security/`, `infrastructure/db/`, `cli/`, `core/config.py`, `answering/routing.py`, `providers/` or `web/auth.py` (`git diff --stat` is empty). It does change `web/dependencies.py` (`_learner_entries` now takes the per-request `LearnerCredentials`), `answering/user_adapters.py` (generic type, `evict_fingerprint`) and the call sites in `tests/test_web_byok_generation.py` / `tests/test_web_user_generation.py`. Those call sites only adapt to the new signatures and weaken no assertion. Because of these changes, C5, C19-C26 and C44 are re-proven below rather than carried. Every other batch-A proof was also re-run at this HEAD.

## Checks (verified at a9f9267)

Backend proof command, one invocation run from `backend/`: `LEARNY_REQUIRE_DB=1 LEARNY_TEST_DATABASE_URL=…/learny_test_byok uv run pytest -v <15 files> -k "<the 43 proof selectors of checks.md, or-joined>"`. Result: **105 passed, 202 deselected, 0 skipped, 0 failed**. Each named test appears individually as PASSED in the output. Frontend proof command: `npx vitest run --maxWorkers=2 --minWorkers=1 --reporter=verbose tests/account-provider-keys.test.tsx` (plus the three other touched account test files). Result: **31 passed**, and each `-t` name shows ✓.

| Check | Claim | Proof run | Evidence | Result |
| --- | --- | --- | --- | --- |
| C1 | only sealed columns; no plaintext key or DEK | `row_holds_no_plaintext` PASSED | `backend/tests/test_provider_credentials_repository.py:74` `assert key_bytes not in raw`; `:75` `assert dek not in raw` | PASS |
| C2 | fresh DEK, nonces and ciphertext per seal; both open | `fresh_dek_and_nonce_per_seal` PASSED | `backend/tests/infrastructure/test_secrets_envelope.py:50` `first_dek != second_dek`; `:55` ciphertexts differ; `:57-58` both open to `_KEY` | PASS |
| C3 | other user, other provider and a flipped byte all raise | `associated_data_binds_owner`, `tampered_ciphertext_rejected[x4]` PASSED | `backend/tests/infrastructure/test_secrets_envelope.py:70-73` `pytest.raises(SealedSecretError)` for other user and other provider; `:103` raises on the flipped field | PASS |
| C4 | rewraps every row, ciphertext byte-identical, `kek_id` updated, second run 0 | `rewraps_without_touching_ciphertext` PASSED | `backend/tests/test_cli_rotate_secrets_kek.py:104` ciphertext equal; `:107` `row.kek_id == new_kek_id`; `:117` `"rewrapped=0"` | PASS |
| C5 | unknown KEK: counted, exit 1; resolver serves house | `unknown_kek_exits_one`, `unknown_kek_serves_house_chain` PASSED | `backend/tests/test_cli_rotate_secrets_kek.py:143-144` exit 1, `unknown_kek=1`; `backend/tests/test_web_byok_generation.py:512-514` model `claude-house`, key A never built | PASS |
| C6 | malformed KEK names the variable, not the value; valid and unset load | `secrets_kek` (9 cases) PASSED | `backend/tests/test_config.py:615-616` variable named, value absent; `:640` valid loads; `:655` unset gives `None` | PASS |
| C7 | account delete cascades the user's rows only | `cascades_with_its_user`, `delete_account_erases_provider_keys` PASSED | `backend/tests/test_provider_credentials_repository.py:107`; `backend/tests/test_web_auth.py:548` `owner_rows == 0`, `:554` survivor kept | PASS |
| C8 | off (no KEK / no binding): GET 200 `{enabled:false,providers:[]}`, writes 404 | `test_disabled_feature[no_kek,no_binding]` PASSED | `backend/tests/test_web_provider_keys.py:139` `== {"enabled": False, "providers": []}`; `:140` `== (404, 404, 404)` | PASS |
| C9 | exactly the bound providers in registry order, with full row shape; `powers_cards` true for anthropic only | `lists_offered_providers_with_powers` PASSED | `backend/tests/test_web_provider_keys.py:157` `== ["openai", "anthropic"]`; `:159-169` full openai row incl. `powers_cards: False`; `:174-183` anthropic powers and `powers_cards is True` | PASS |
| C10 | PUT 200 with last4; replace leaves one row with a new id that opens to the new key | `put_stores_and_replace_mints_new_row` PASSED | `backend/tests/test_web_provider_keys.py:202` last4; `:206-207` one row, `id !=`; `:211` `reveal == _NEW_KEY` | PASS |
| C11 | missing / whitespace / 19 / 257 / no prefix give 422, no echo | `malformed_key_422_never_echoes[x7]` PASSED | `backend/tests/test_web_provider_keys.py:267` `== 422`; `:273` no 8-char window of the value in the body; `:249-251` the 19 and 257 lengths | PASS |
| C12 | unoffered `gemini` / `mistral` writes give 404 | `unoffered_provider_404[gemini,mistral]` PASSED | `backend/tests/test_web_provider_keys.py:292` `== (404, 404, 404)`; `:293` probe never called | PASS |
| C13 | test route maps ok / rejected / rate_limited / unavailable; stored key plus the profile's host | `test_route_maps_probe_outcomes[x4]`, `lists_models_with_profile_host` PASSED | `backend/tests/test_web_provider_keys.py:322` `== {"ok":…, "reason":…}`; `:324` probe called with `("byok-gpt", "https://api.openai.com/v1", _OPENAI_KEY)`; `backend/tests/infrastructure/test_credential_probe.py:88` client `base_url` equals the profile host | PASS |
| C14 | test with no stored key gives 404 | `test_without_key_404` PASSED | `backend/tests/test_web_provider_keys.py:335` `== 404` | PASS |
| C15 | DELETE 204, row gone, second DELETE 204 | `delete_is_idempotent_204` PASSED | `backend/tests/test_web_provider_keys.py:353-355` | PASS |
| C16 | writes without CSRF give 403, row unchanged | `writes_require_csrf` PASSED | `backend/tests/test_web_provider_keys.py:409` `== (403, 403, 403)`; `:410` rows `== before` | PASS |
| C17 | PUT and test give 429 once the limit is spent | `writes_rate_limited_429` PASSED | `backend/tests/test_web_provider_keys.py:431-432` `== [200, 200, 429]` for each route | PASS |
| C18 | no 8-char substring of either key in any response body | `responses_never_carry_key_material` PASSED | `backend/tests/test_web_provider_keys.py:457-461` `fragment not in body` over 8 bodies | PASS |
| C19 | ask and teach served by the bound profile on the learner key | `turn_served_by_learner_key` PASSED | `backend/tests/test_web_byok_generation.py:199-200` model `claude-byok`; `:202` 2 calls on `_KEY_A`; `:205` house 0 | PASS |
| C20 | explain served on the learner key; bound explain profile leads | `explain_served_by_learner_key*` PASSED | `backend/tests/test_web_byok_generation.py:319` `"claude-byok-explain"`; `:327` keyless learner gets house | PASS |
| C21 | user-key failure never falls to house entries | `never_falls_from_user_key_to_house*` (13) PASSED | `backend/tests/infrastructure/test_answering_routing.py:700` raises; `:704` `house_entry.calls == 0` | PASS |
| C22 | uncovered mode served by house | `uncovered_mode_served_by_house*` PASSED | `backend/tests/infrastructure/test_answering_routing.py:769-772`; `backend/tests/test_web_byok_generation.py:369-371` | PASS |
| C23 | two learners, two keys, two cache entries | `two_learners_two_keys`, `keys_on_fingerprint` PASSED | `backend/tests/test_web_byok_generation.py:398-401`; `backend/tests/infrastructure/test_user_adapter_cache.py:60-62` | PASS |
| C24 | replace then delete: new key, then house; old key never again | `replace_and_delete_take_effect_next_request` PASSED | `backend/tests/test_web_byok_generation.py:432-438` | PASS |
| C25 | learner-keyed turn: 0 USD, `ask_count` +1; house turn > 0 | `learner_key_debits_zero_usd_counts_call` PASSED | `backend/tests/test_web_byok_generation.py:467-469` | PASS |
| C26 | kill switch gives 503 and no adapter call | `kill_switch_refuses_learner_key` PASSED | `backend/tests/test_web_byok_generation.py:491-492` | PASS |
| C27 | user-key-only profile never in a house chain or the catalog; registry without a house-servable profile fails | `user_key_only*` (8) PASSED | `backend/tests/infrastructure/test_provider_profiles.py:329-339`; `:357-362`; `:369` | PASS |
| C28 | highlight and note suggestions on the learner key with `quiz_model`; 0 USD | `suggestions_use_learner_key` PASSED | `backend/tests/test_web_byok_cards.py:154` `== [_KEY]`; `:155` `quiz_model`; `:158` `_usd_today(...) == 0` | PASS |
| C29 | deck and note refresh resolve the owner's key inside the task | `deck_task_resolves_owner_key`, `refresh_cards_resolves_owner_key` PASSED | `backend/tests/worker/test_byok_decks.py:250` `== [_KEY]`; `:254` house served the keyless learner; `:296` `== [_KEY]` | PASS |
| C30 | handle carries `credential_id`; poll collects with the same credential; a legacy handle polls house | `poll_pins_credential` PASSED (+ `test_a_handle_without_a_pin_polls_with_the_house_adapter` PASSED, see Coverage) | `backend/tests/worker/test_byok_decks.py:314` `== str(credential_id)`; `:323-324` poll adapter built with `_KEY`, collected; `:345-346` legacy goes to house, learner fake untouched | PASS |
| C31 | pinned row deleted or replaced: job `failed` with fixed copy; no collect | `poll_fails_when_pinned_key_gone[deleted,replaced]` PASSED | `backend/tests/worker/test_byok_decks.py:371-373` FAILED status, `_DECK_KEY_GONE`, no adapter built | PASS |
| C32 | Celery args and kwargs lack the canary; poll payload is ids, handle and deadline only | `task_payloads_carry_ids_only` PASSED | `backend/tests/worker/test_byok_decks.py:408` `_KEY not in serialized`; `:412` handle keys `== {provider, batch_id, payload, credential_id}` | PASS |
| C33 | 4 key shapes masked in message, args, extras and exception, human and JSON | `masks_provider_key_shapes[x8]` PASSED | `backend/tests/test_logging_redaction.py:169-172` 6 records emitted, key absent, marker present. Assemblies read directly: `backend/app/main.py:100` and `backend/app/worker/celery_app.py:57` call `configure_logging()` | PASS |
| C34 | canary absent from logs, stdio, responses, exceptions, Celery args and reprs across the whole lifecycle | `canary_never_surfaces` PASSED | `backend/tests/test_byok_leak_canary.py:408` `scan(channels, …) == []`; `:411` masking actually fired at least 5 times | PASS |
| C35 | negative control: the unmasked path is reported | `scanner_catches_deliberate_leak` PASSED | `backend/tests/test_byok_leak_canary.py:448` and `:451` report the unmasked lines | PASS |
| C36 | disabled: no keys heading | ✓ `is hidden when disabled` | `frontend/tests/account-provider-keys.test.tsx:133` heading `toBeNull()` | PASS |
| C37 | configured row (mask, date, profile marks, cards) and unconfigured row (password input, Save) | ✓ `renders configured and unconfigured rows` | `frontend/tests/account-provider-keys.test.tsx:143-147`; `:152` `type === "password"`; `:153` Save | PASS |
| C38 | after save: input empty, configured shown, key never rendered | ✓ `save clears and never re-renders the key` | `frontend/tests/account-provider-keys.test.tsx:172-177`. Proof green, but **does not discriminate** (fault F5 survived) | PASS (proof green; gap 1) |
| C39 | "Key works" plus 3 distinct reason messages | ✓ `test outcome messages` | `frontend/tests/account-provider-keys.test.tsx:203-209` | PASS |
| C40 | delete asks first; cancel sends nothing | ✓ `delete confirms first` | `frontend/tests/account-provider-keys.test.tsx:225` 0 DELETE after cancel; `:229` 0 before confirm; `:233` 1 after | PASS |
| C41 | failed save, test and delete: inline error, prior state kept | ✓ `failure keeps state and shows error` | `frontend/tests/account-provider-keys.test.tsx:252-254`, `:258-261`, `:266-267` | PASS |
| C42 | disclosure copy | ✓ `disclosure copy` | `frontend/tests/account-provider-keys.test.tsx:273-277` exact string | PASS |
| C43 | four routes give 401 without a session | `routes_require_session_401` PASSED | `backend/tests/test_web_provider_keys.py:480` `== [401, 401, 401, 401]` | PASS |

The `Result` column records the proof run. The FAIL verdict comes from fault F5 (below), not from a red proof.

## Coverage (recomputed at a9f9267)

| Set (size) | Recomputed from | Member -> proof | Unproven |
| --- | --- | --- | --- |
| GET statuses (2) | FastAPI route `provider_keys.py:162-179`: no 404/422 path | 200 C9 · 401 C43 | - |
| PUT statuses (6) | `provider_keys.py:182-210` deps (`enforce_csrf`, `rate_limit_provider_keys`, auth), `_offered_repo` 404, `_key_from_body` 422. The framework's own JSON-decode 422 was also probed: body `"input":{}`, the key is not echoed (scratch probe, 3 malformed bodies) | 200 C10 · 401 C43 · 403 C16 · 404 C12 · 422 C11 · 429 C17 | - |
| POST test statuses (5) | `provider_keys.py:213-234`: probe exceptions are all caught in `probe.py:189-204`, so no 5xx | 200 C13 · 401 C43 · 403 C16 · 404 C14 · 429 C17 | - |
| DELETE statuses (4) | `provider_keys.py:237-257`: not rate limited, matching the plan | 204 C15 · 401 C43 · 403 C16 · 404 C12 | - |
| test outcomes (4) | `ProbeReason` literal `probe.py:125` plus ok | C13 parametrized x4 at the boundary; own-layer mapping in `test_credential_probe.py:126-154` (SDK 401/403/429/500 and taxonomy x5) | - |
| key-format rejections (5) | `_key_from_body` `provider_keys.py:149-159` | missing, whitespace, 19, 257, no prefix: C11, plus non-string and raw-string body | - |
| provider literals (3) | `UserKeyProvider` Literal | anthropic C9 · openai C9 · gemini C12 (unoffered); gemini host probe `test_credential_probe.py:88` | - |
| feature-off conditions (2) | `build_provider_credential_repository` `dependencies.py:824-831` | no KEK, no binding: C8 | - |
| generation surfaces on the learner key (6) | composition sites `dependencies.py` (chains, `get_card_generation_for_user`), `tasks.py` (`_generate_quiz_deck_body`, `refresh_note_cards`) | ask, teach C19 · explain C20 · card suggest C28 (highlight + note) · deck C29 · note refresh C29 | - |
| fall-over cases (3) | `routing.py` owner rule | C21 · C22 · C24 | - |
| key lifecycle effect (3) | routes plus cascade | replace, delete C24 · account delete C7 | - |
| rotation outcomes (3) | CLI | rewrapped, current C4 · unknown C5 | - |
| KEK config values (4) | `Settings` validator | unset, valid, non-base64, wrong length: C6 | - |
| envelope tamper (3) | envelope | C3 | - |
| adapter cache eviction (3) | `user_adapters.py` | LRU, TTL C44 · fingerprint C23/C24. The new eviction on write (`evict_fingerprint`) is asserted only through the route test `test_web_provider_keys.py:385-388` | - |
| deck pin cases (3) | `_poll_quiz_deck_body` `tasks.py:739-764` | pinned present C30 · gone C31 (deleted + replaced) · legacy `test_byok_decks.py:345-346` (a test outside C30's `-k` selector) | - |
| leak channels (7) | plan AC 34 | logs C33/C34 · responses C18/C34 · exceptions C34 · Celery C32/C34 · credential repr, adapter repr C34 · 422 echo C11 | - |
| ledger effects (3) | `budget.usage_micros(user_keyed=)` | C25 · C26; cards C28; deck `test_byok_decks.py:328` | - |
| Account section states (6) | `provider-keys-section.tsx` | hidden C36 · configured, unconfigured C37 · error C41 · confirm C40 · saved C38 | saved: "never re-rendered" is unproven (F5 survived, gap 1) |
| startup config: KEK (2 assemblies) | one `Settings` class used by both | C6 | - |
| startup config: masking (2 assemblies) | read `app/main.py:100`, `app/worker/celery_app.py:57` | C33 plus `test_logging_redaction.py:195-196` | - |

## Test policy rows

| Row | Files it classifies | Required proof | Expectation met |
| --- | --- | --- | --- |
| Decides, reached across a boundary | `web/provider_keys.py`, `answering/probe.py`, chain resolution in `dependencies.py`, deck pin in `worker/tasks.py` | boundary: HTTP client (`test_web_provider_keys.py`, `test_web_byok_cards.py`) and task functions with the Celery JSON round-trip (`test_byok_decks.py:312-315`); own layer: `test_credential_probe.py`, `test_answering_routing.py` | yes |
| Decides, not reached across a boundary | `core/logging.py`, `user_adapters.py`, envelope, rotation | `test_logging_redaction.py` (4 shapes x 2 formats, every record channel), `test_user_adapter_cache.py`, envelope and CLI tests | yes (the new `evict_fingerprint` is asserted via the route test; it is outside the row's listed eviction table) |
| Instrumentation | entities, `lib/provider-keys.ts` | consumer proofs C29-C32, C37-C41 | yes |

## Faults injected

Scratch worktree `git worktree add --detach <scratchpad>/wt HEAD`, using the real venv with `UV_PROJECT_ENVIRONMENT=…/backend/.venv uv run --no-sync`. Modules resolved inside the scratch tree (`app.infrastructure.web.provider_keys.__file__` and `app.worker.tasks.__file__` printed scratch paths). Each fault was reverted with `git checkout -- <file>` before the next. The real tree's porcelain was empty before and after.

| Mutation | Location | Killed |
| --- | --- | --- |
| F1: poll ignores the pin (`credential.id != pinned` dropped) | `backend/app/worker/tasks.py:531` | yes: `test_poll_fails_when_pinned_key_gone[replaced]` (`'running' == 'failed'`) |
| F2: feature on with a KEK but no binding (`or not _offered_providers()` dropped) | `backend/app/infrastructure/web/dependencies.py:829` | yes: `test_disabled_feature[no_binding]` (`enabled: True`) |
| F3: masking regex loses the Gemini shape (`(?:sk-\|AIza)` to `(?:sk-)`) | `backend/app/core/logging.py:42` | yes: `test_masks_provider_key_shapes[gemini-human,gemini-json]` |
| F4: card suggestions not stamped `user_keyed` | `backend/app/infrastructure/quiz/learner.py:65,68` | yes: `test_suggestions_use_learner_key` (`4200000 == 0`) |
| F5: save does not clear the draft (`setDraft("")` after a successful PUT dropped) | `frontend/app/components/provider-keys-section.tsx:133` | survived: all 8 tests in `account-provider-keys.test.tsx` stay green; the verifier probe (Save, then Replace, then input value `""`) passes at HEAD and fails under F5 |

The cap of 5 was reached. Surfaces not mutated: the 422 parser (`_key_from_body`), the probe mapping, the Celery payload shape and the cache `evict_fingerprint`. Their proofs are listed above.

## Observations (non-blocking, outside any check's wording)

- Logging: `SensitiveDataFilter` and the masking formatters sit on the Learny root handler. Uvicorn's own `uvicorn` / `uvicorn.access` handlers (`propagate: False` in uvicorn's default config) do not pass through them. An unhandled exception logged by `uvicorn.error` would print unmasked. I found no current path that puts a key into an unhandled exception: probe errors are swallowed and adapter errors are translated and handled. The negative control (`test_byok_leak_canary.py:451`) documents the same class of path (a handler ahead of the masking one).
- By the plan's design, Gemini keys get no prefix check. The log mask recognizes only `AIza…`, so a Gemini key in any other shape would not be masked.
- C11 proves only the rejection side (19 and 257 characters). No test pins acceptance at exactly 20 and 256 characters.
- C30's selector `-k poll_pins_credential` does not select the legacy-handle test it claims (`test_byok_decks.py:331`). That test exists and passes.

## Gate

- Targeted proofs: backend 105 passed, 0 failed, 0 skipped; frontend 31 passed.
- Full backend (`LEARNY_REQUIRE_DB=1 uv run pytest`, run once, no `-n`): **3280 passed, 12 skipped, 2 failed**. The 2 failures are the known environmental `tests/test_deploy_topology.py::test_dev_merge_publishes_the_app_ports` and `::test_dev_merge_still_publishes_todays_infra_ports` (local skip-worktree `docker-compose.override.yml`). Both pass in the clean scratch worktree, where the whole `test_deploy_topology.py` file is green.
- Full frontend (`npx vitest run --maxWorkers=2 --minWorkers=1`, run once): 1022 passed, 1 failed. The failure is `tests/chapter-reader.test.tsx` "ChapterFlow in pt-BR … renders in pt-BR" under load. The batch-B diff does not touch that file. Re-running the file alone gave 81/81 passed.
- `make lint`: exit 0 (ruff, format, `tsc --noEmit`, check_commits 8 OK, boundaries clean).
- `validate_verification.py byok-secrets-and-chains`: exit 1, as expected for a FAIL verdict.
