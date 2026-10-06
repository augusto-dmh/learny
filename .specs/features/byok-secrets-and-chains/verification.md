# BYOK secrets and chains verification

**Verdict**: PASS
**Profile**: standard
**Diff range**: ccfb37d..e73640b (`origin/main..HEAD`, branch `feat/byok-secrets-and-chains`); round-3 fix diff `fb2d0a9..e73640b` (one test-only commit, `e73640b`; no file under `backend/app/` changed)
**Round**: 3 - scoped (batch A scope: C1-C7, C19-C27, C44)
**Verifier**: independent sub-agent (author != verifier)

All 17 batch-A checks are proven at HEAD `e73640b`, and the full backend suite passes in a clean scratch worktree (3144 passed, 0 failed). Round 2 left one gap: the plan's Assumptions row (`plan.md:225`, confirmed `y`) says a stored choice that is not bound to the learner's provider "is otherwise ignored", and the mutant M4 (`return () if lead else bound`) survived the full suite. That gap is closed. The fix adds three tests:

- two boundary tests through the HTTP client, one for the Ask chain (stored choice `house`) and one for the Explain chain (`generation_explain_profile="house"`);
- one parametrized own-layer test of `order_learner_profiles` with five decision rows: no lead, bound lead, unbound lead, lead bound to another provider, unknown lead.

M4 is now killed by 5 tests. Four further wrong readings of the lead rule were also killed: the lead looked up outside the bound set, an unbound lead that reorders the bound set, an Explain-only drop, and an Explain lead that is dropped. Test policy row 1 is now met. The round-1 and round-2 gaps are closed, and no new gap was found.

Batch B checks (C8-C18, C28-C43) are not built in this PR. They stay deferred, not Unproven.

## Binding sources

Carried from 42ec428 (re-confirmed at fb2d0a9). Fix `e73640b` touches no interface: it changes two test files and no ADR or plan text, so step 1 was not re-run. The Assumptions row `plan.md:225` was re-read at e73640b to judge the new tests.

| Source | Opened | Contradiction | Uncovered |
| --- | --- | --- | --- |
| `docs/adr/0033-learner-provider-keys-bound-to-house-profiles.md` (rules 1, 2, 4, 6, 7, 9, 11 for batch A) | yes - read in full at 42ec428 (carried) | - | - |
| `docs/adr/0020-use-anthropic-claude-for-generation.md` amendment point 7 (superseded marker) and point 3 (widened by ADR-0033 rule 5) | yes - `git diff ccfb37d..42ec428` of the file (carried) | - | - |
| `.specs/features/byok-secrets-and-chains/plan.md` (Landing doors 1-5, 8, 9; S1 and S3 criteria; Assumptions) | yes - re-read the Assumptions row "learner's house-profile preference when they have a key" (`plan.md:225`) at e73640b | - | - |

Notes (carried from 42ec428):
- Each batch-A ADR rule has a check or a located test:
  - rule 1 (envelope): C1-C3;
  - rule 2 (rotation): C4, C5 and the `unreadable` outcome;
  - rule 4: C27;
  - rule 6: C21 and C22, plus fail-over among keyed entries at `test_answering_routing.py:703-722` (line refreshed);
  - rule 7: C23, C44 and `test_user_adapter_cache.py:75-76`;
  - rule 9: C25 and C26;
  - rule 11: `backend/tests/test_config.py:665`.
- Deferred to batch B (not built, out of scope): ADR-0033 rule 3 (C8), rule 5 cards and decks (C28, C29), rule 8 (C30-C32) and rule 10 (C33-C35).
- Observation, carried: AC 27 says "reject at startup", but registry resolution is lazy and runs at the first chain build. C27 is worded "fails resolution". This does not contradict a binding source.

## Checks

Verified at e73640b. All proofs ran in one invocation from `backend/`:

```
LEARNY_REQUIRE_DB=1 LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test_byok uv run pytest -p no:cacheprovider -v <10 files> -k "<30-name alternation>"
```

The run covered:

- the 21 round-1 names;
- the 2 round-2 tests;
- the 3 round-3 tests: `test_a_stored_choice_not_bound_to_the_key_is_ignored`, `test_an_explain_profile_not_bound_to_the_key_is_ignored`, and `test_learner_profiles_follow_registry_order_with_only_a_bound_lead_moved` (5 parametrized ids);
- 4 supporting tests: `test_without_a_kek_the_command_refuses_with_exit_two`, `test_without_a_kek_a_learner_with_a_row_gets_the_house_chain_object`, `test_without_a_bound_profile_the_feature_stays_off` and `test_migration_0030_creates_user_provider_credentials`.

Result: exit 0, **74 passed, 0 skipped, 176 deselected**. That is round 2's 67, plus the 2 new web tests, plus the 5 new parametrized ids. Every named test appears individually as PASSED in the `-v` output, including all five ids `[no-lead-registry-order]`, `[bound-lead-moves-first]`, `[unbound-lead-ignored]`, `[other-provider-lead-ignored]` and `[unknown-lead-ignored]`.

Citations were refreshed in the two files that `e73640b` touched:

- `test_web_byok_generation.py`: 43 lines were inserted after line 243, so citations past that line moved by +43.
- `test_answering_routing.py`: one import was added at line 34 (citations moved by +1), and the new test was appended at `:807-837`.

Citations in the other files are carried from fb2d0a9, because those files did not change.

| Check | Claim | Proof run | Evidence | Result |
| --- | --- | --- | --- | --- |
| C1 | row holds only sealed columns; no plaintext key or DEK in any column | `test_row_holds_no_plaintext` PASSED | `backend/tests/test_provider_credentials_repository.py:55` - `assert set(row._mapping) == {"id", ..., "ciphertext","nonce","wrapped_dek","dek_nonce","kek_id","fingerprint","last4", ...}`; `:74-75` - `assert key_bytes not in raw` / `assert dek not in raw` | PASS |
| C2 | same key sealed twice: different DEKs, nonces, ciphertexts; both open | `test_fresh_dek_and_nonce_per_seal` PASSED | `backend/tests/infrastructure/test_secrets_envelope.py:50` `first_dek != second_dek`; `:52` `first.nonce != second.nonce`; `:55` `first.ciphertext != second.ciphertext`; `:57-58` both `open(...) == _KEY` | PASS |
| C3 | other user id / other provider in AAD raises; flipped byte raises | `test_associated_data_binds_owner` (+ `_on_the_wrapped_dek_too`), `test_tampered_ciphertext_rejected[4]` PASSED | `backend/tests/infrastructure/test_secrets_envelope.py:70-73` - `pytest.raises(SealedSecretError)` on other `user_id` / `provider="openai"`; `:102-103` - `pytest.raises(SealedSecretError)` on each byte-flipped field | PASS |
| C4 | rotation re-wraps all, ciphertext byte-identical, `kek_id` new, decryptable, re-run 0 | `test_rewraps_without_touching_ciphertext` PASSED | `backend/tests/test_cli_rotate_secrets_kek.py:98` `"rewrapped=2" in first_output`; `:104` ciphertext bytes equal; `:107` `row.kek_id == new_kek_id`; `:112` `new_only.reveal(...) == key`; `:117` `"rewrapped=0" in second_output` | PASS |
| C5 | unknown-KEK row: counted, exit 1; resolver returns no credential | `test_unknown_kek_exits_one`, `test_unknown_kek_serves_house_chain` PASSED | `backend/tests/test_cli_rotate_secrets_kek.py:143-144` - `exit_code == 1`, `"unknown_kek=1" in captured.out`; `backend/tests/test_web_byok_generation.py:511-514` (refreshed) - `status_code == 201`, `model == "claude-house"`, `_by_key(fakes, _KEY_A) == []` | PASS |
| C6 | bad KEK (non-base64, 16, 33 bytes) fails `Settings()` naming the var, not the value; valid/unset load | `test_secrets_kek_*` (11 cases) PASSED | `backend/tests/test_config.py:615` `"LEARNY_SECRETS_KEK" in str(excinfo.value)`; `:616` `value not in shown`; `:640` `settings.secrets_keks() == (current, (previous,))`; `:655` `settings.secrets_keks() is None` | PASS |
| C7 | `DELETE /api/auth/account` removes the user's credential rows, keeps another user's | `test_cascades_with_its_user`, `test_delete_account_erases_provider_keys` PASSED | `backend/tests/test_web_auth.py:542` `resp.status_code == 204`; `:548` `owner_rows == 0`; `:554` `[row.id for row in remaining] == [survivor.id]`; `backend/tests/test_provider_credentials_repository.py:107` | PASS |
| C19 | ask and teach turns served by bound profile with learner's key, ahead of house; a stored choice reorders only when bound (plan Assumptions) | `test_turn_served_by_learner_key`, `test_stored_choice_leads_the_learner_keyed_profiles`, `test_a_stored_choice_not_bound_to_the_key_is_ignored`, `test_learner_profiles_follow_registry_order_with_only_a_bound_lead_moved[5]` PASSED | `backend/tests/test_web_byok_generation.py:199-200` both `json()["model"] == "claude-byok"`; `:202` `_calls(fakes, _KEY_A) == 2`; `:205` `_calls(fakes, _HOUSE_KEY) == 0`; bound choice `:236` `== "claude-dual"`; unbound choice `:261` `turn.json()["model"] == "claude-byok"`, `:262` `_calls(fakes, _KEY_A) == 1`, `:263` `_calls(fakes, _HOUSE_KEY) == 0`; own layer `backend/tests/infrastructure/test_answering_routing.py:837` `[p.id for p in ordered] == expected` over the params at `:823-829` | PASS |
| C20 | selection-Explain on learner's key; bound `generation_explain_profile` leads; an unbound one is ignored | `test_explain_served_by_learner_key` (+ `_without_a_named_explain_profile`), `test_an_explain_profile_not_bound_to_the_key_is_ignored` PASSED | `backend/tests/test_web_byok_generation.py:319` (refreshed) `explained.json()["model"] == "claude-byok-explain"`; `:321-324` models of the keyed fakes; `:344-346` (no named profile: `claude-byok`, key 1 call, house 0); unbound explain profile `:282` `explained.json()["model"] == "claude-byok"`, `:283-284` key A 1 call, house 0 | PASS |
| C21 | every eligible user-keyed entry fails: router raises; house never called | `test_never_falls_from_user_key_to_house_*` (13 cases) PASSED | `backend/tests/infrastructure/test_answering_routing.py:678` (refreshed) `pytest.raises(type(error))`; `:682-683` `house_local.calls == 0`, `house_compat.calls == 0`; `:700` `house_entry.calls == 0`; `:739` `house.stream_calls == 0` | PASS |
| C22 | no eligible user-keyed entry for the mode: served by house's first eligible | routing `test_uncovered_mode_served_by_house_*` (3) + web `test_uncovered_mode_served_by_house` PASSED | `backend/tests/infrastructure/test_answering_routing.py:752-754` (refreshed) `profile_id == "house"`, `user_keyed is False`, `keyed.calls == 0`; `:766-768`; `backend/tests/test_web_byok_generation.py:369-371` (refreshed) `model == "claude-house"`, house 1 call, key 0 | PASS |
| C23 | two learners, two keys, one process: each own adapter; cache holds two | `test_two_learners_two_keys`, `test_keys_on_fingerprint` PASSED | `backend/tests/test_web_byok_generation.py:398-399` (refreshed) `_calls(_KEY_A) == 1`, `_calls(_KEY_B) == 1`; `:401` `len(dependencies._user_adapters) == 2`; `backend/tests/infrastructure/test_user_adapter_cache.py:58,60` | PASS |
| C24 | after replace: new key; after delete: house; old adapter never called again | `test_replace_and_delete_take_effect_next_request` PASSED | `backend/tests/test_web_byok_generation.py:433-434` (refreshed) `second ... "claude-byok"`, `third ... "claude-house"`; `:436-438` `_calls(_KEY_A) == 1`, `_KEY_B == 1`, `_HOUSE_KEY == 1` | PASS |
| C25 | user-keyed turn: `usd_micros` 0, `ask_count` +1; house-served debits > 0 | `test_learner_key_debits_zero_usd_counts_call` PASSED | `backend/tests/test_web_byok_generation.py:467` (refreshed) `keyed_day.usd_micros == 0`; `:468` `keyed_day.ask_count == 1`; `:469` `house_day.usd_micros > 0` | PASS |
| C26 | kill switch on: learner with key gets 503, no adapter called | `test_kill_switch_refuses_learner_key` PASSED | `backend/tests/test_web_byok_generation.py:491` (refreshed) `resp.status_code == 503`; `:492` `sum(fake.calls for fake in fakes) == 0` | PASS |
| C27 | user-key-only profile never in house / explain chain / catalog; all-user-key registry fails naming the problem; neither field fails as today | `test_user_key_only_*` (8) PASSED | `backend/tests/infrastructure/test_provider_profiles.py:329,330,335` `_chain_ids(...) == ["house-claude","house-local"]`; `:339` catalog; `:351-352` `"house" in message`, `"user_key_provider" in message`; `:359` `pytest.raises(ValueError, match="api_key_env")` | PASS |
| C44 | cache bounded at 256 with LRU eviction; entry past TTL rebuilt | `test_lru_bound_and_ttl_*` (3) PASSED | `backend/tests/infrastructure/test_user_adapter_cache.py:80` `DEFAULT_MAX_ENTRIES == 256`; `:90-93` `len(cache) == 256`, `fp-1` evicted, `fp-0` kept; `:99` `DEFAULT_TTL_SECONDS == 15 * 60`; `:110` `rebuilt is not original` | PASS |

### The round-3 tests, judged against the plan (verified at e73640b)

The plan-approved behaviour is in `plan.md:225`: the learner's stored choice "reorders the user-keyed entries when the chosen profile is bound to their provider, and is otherwise ignored for those modes". The ADR-0033 Explain wording at `dependencies.py:877-878` says `generation_explain_profile` leads "when it is one of them". The code that decides both is `order_learner_profiles` at `backend/app/infrastructure/answering/__init__.py:207-225`. The `head is None -> return bound` branch is at `:223-224`. It is reached by `dependencies.py:862` (Ask/Teach) and `:880-881` (Explain).

- **`test_a_stored_choice_not_bound_to_the_key_is_ignored`** (`backend/tests/test_web_byok_generation.py:244-263`).
  - Setup: registry `[house, byok-claude]`, stored choice `house` (bound to no provider), anthropic key A.
  - It asserts `201`, `model == "claude-byok"`, one call on key A and none on the house key (`:260-263`).
  - These are the round-2 probe's exact assertions, now in the real tree and run through the HTTP client.
  - Under M4 it fails with `'claude-house' == 'claude-byok'`.
- **`test_an_explain_profile_not_bound_to_the_key_is_ignored`** (`:266-284`).
  - This is the same case on the second entry point: `generation_explain_profile="house"` and an Explain-origin turn.
  - It asserts `claude-byok` on key A and 0 house calls (`:281-284`).
  - It is the only test killed by M7 (an Explain-only wrong reading), so it pins the Explain entry point on its own.
- **`test_learner_profiles_follow_registry_order_with_only_a_bound_lead_moved[5]`** (`backend/tests/infrastructure/test_answering_routing.py:807-837`).
  - Registry: `house(None)`, `byok-a(anthropic)`, `byok-o(openai)`, `byok-a2(anthropic)`; the learner holds anthropic.
  - Expected orders (`:823-829`):

    | Lead | Expected order |
    | --- | --- |
    | none | `[byok-a, byok-a2]` |
    | `byok-a2` (bound) | `[byok-a2, byok-a]` |
    | `house` (unbound) | `[byok-a, byok-a2]` |
    | `byok-o` (other provider) | `[byok-a, byok-a2]` |
    | `missing` (unknown) | `[byok-a, byok-a2]` |

  - The registry has two bound profiles, so "ignored" is pinned as "registry order kept", not merely "keyed entries still present". That is what kills M6, which no web test can see because each web registry has only one bound profile.
  - This test is the own-layer "one case per decision row at the module" that Test policy row 1 requires.

All three assert the plan-approved values directly at the assertion; no expected value is built elsewhere. **They close round-2 gap 1.**

Round-2 judgments carried from fb2d0a9: `test_stored_choice_leads_the_learner_keyed_profiles` (`:208-241`, unchanged) closes the bound-lead half; `test_unreadable_row_exits_one_and_is_left_untouched` (`test_cli_rotate_secrets_kek.py:154-186`) closes round-1 gap 2.

Notes:
- Diff check: every proof file is new or extended in `ccfb37d..e73640b`. All three round-3 tests are in the fix diff, and `git diff --stat fb2d0a9..HEAD` shows only the two test files.
- Observation, carried from 42ec428 and unranked: C21 is proven at the router's own layer only. The "fixed generation-failure copy" half of AC 21 relies on the existing TAX-03 mapping. `checks.md` declares C21 router-only.

## Coverage

The chain-resolution row was recomputed at e73640b, because the fix touched its authority. The other rows carry from fb2d0a9 (or 42ec428), with line numbers refreshed where they point into the two touched test files.

| Set (size) | Recomputed from | Member -> proof | Unproven |
| --- | --- | --- | --- |
| generation surfaces on the learner key (batch-A members: 3 of 6) - carried from 42ec428 | AC 19, 20; ADR-0033 rule 5; `dependencies.py` wiring | ask turn `test_web_byok_generation.py:199` · teach turn `:200` · explain `:319` | - |
| fall-over cases (3) - carried from 42ec428 | ADR-0033 rule 6; `routing.py:173-186`, `:127-133`, `:264`, `:317` | user-key failure stays keyed `test_answering_routing.py:678-683,696-700,735-739` · uncovered mode -> house `:752-754,766-768`, web `test_web_byok_generation.py:369-371` · no key -> house `:434`, keyless explain `:327` | - |
| key lifecycle effect on serving (3) - carried from 42ec428 | AC 7, 24 | replace `test_web_byok_generation.py:433,436` · delete `:434,438` · account delete `test_web_auth.py:548` | - |
| rotation outcomes (code: 4 counts + no-KEK exit) - carried from fb2d0a9 | `rotate_secrets_kek.py:51-58`, `:73-107`, `:115-128` | rewrapped `test_cli_rotate_secrets_kek.py:98` · already_current `:118` · unknown_kek + exit 1 `:143-144` · unreadable + exit 1 + stderr + row untouched `:177-186` · no KEK exit 2 `:195` | - |
| KEK config values (4 + previous) - carried from 42ec428 | `config.py:447-480` | unset/empty/blank `test_config.py:655` · valid `:640` · non-base64, 16/33 bytes `:615-616` · malformed previous `:629` | - |
| envelope tamper cases (3 + code branches) - carried from 42ec428 | `secrets_envelope.py:142-159` | other user `test_secrets_envelope.py:70-71` · other provider `:72-73` · flipped byte x4 `:102-103` · DEK-layer AAD `:89-90` · unknown KEK `:112-113` | - |
| adapter cache eviction (3 + code) - carried from 42ec428 | `user_adapters.py:79-94` | LRU `test_user_adapter_cache.py:90-93` · TTL `:105,110` · fingerprint change `:66`, web `test_web_byok_generation.py:436` · failed build not cached `:126-127` | - |
| ledger effects of a user-keyed call (4) - carried from 42ec428 | AC 25; ADR-0033 rule 9; `budget.py:186`, `:210-213` | usd 0 `test_web_byok_generation.py:467` · ask counter `:468` · teach_start by composition (`:467` + `test_application_budget.py:916`) · kill switch `:491-492` | - |
| user-key-only exclusion (5 sites) - carried from 42ec428 | `profiles.py` `house_profiles`, `_validate_declared`, `learner_catalog`; two `resolve_house_profiles` calls | default chain `test_provider_profiles.py:329` · explain chain `:330` · preference chain `:335` · catalog `:339` · empty house set fails `:351-352` | - |
| chain-resolution decision rows (code: 8 rows; the lead rule has 4 outcomes and 2 entry points) - verified at e73640b | `dependencies.py:798-881` (`_learner_entries`, `get_generation_for_user`, `get_explain_generation_for_user`), `answering/__init__.py:207-247` (`order_learner_profiles`, `build_learner_keyed_chain`); plan Assumptions `plan.md:225` | no KEK -> house object `test_web_byok_generation.py:539-540` · no bound profile `:557` · unusable credential `:511-514` · keyed entries lead, house beside `:199-205` · empty entries -> house as-is `:539` · lead rule: no lead -> registry order `test_answering_routing.py:837[no-lead-registry-order]`; bound lead moves first, Ask `test_web_byok_generation.py:236-240`, Explain `:319`, own layer `[bound-lead-moves-first]`; lead not bound to the learner's provider -> ignored and registry order kept, Ask `:261-263`, Explain `:282-284`, own layer `[unbound-lead-ignored]`, `[other-provider-lead-ignored]`; unknown lead -> ignored, own layer `[unknown-lead-ignored]` | - |
| Landing one-way door literals (batch-A doors 1, 2, 3, 4, 5, 9) - carried from 42ec428 | plan Landing | UNIQUE `test_migrations.py:4015` · FK CASCADE `:4023` · column set `test_provider_credentials_repository.py:55` · DEK/nonce sizes `test_secrets_envelope.py:49,51` · AAD `:37,59` · `kek_id` `:62` · re-wrap keeps ciphertext `test_cli_rotate_secrets_kek.py:104` · 256 / 15 min `test_user_adapter_cache.py:80,99` · key includes profile `:75-76` · provider Literal `test_provider_profiles.py:385-386` · fingerprint mismatch -> absent `test_provider_credentials_repository.py:174-175` · rotation keeps fingerprint `test_cli_rotate_secrets_kek.py:108` | - |
| startup config: KEK validation (2 assemblies) - carried from 42ec428 | read directly: `backend/app/main.py:99`, `backend/app/worker/celery_app.py:17` | both construct the one `Settings` whose validator C6 proves `test_config.py:615-616` | - |

Deferred to batch B (not built, out of scope), carried from 42ec428: C8-C18, C28-C43 and the sets they own:

- the key routes' status sets, test outcomes, key-format rejections and route provider literals;
- feature-off at the routes;
- the cards, deck and note surfaces, and the deck pin;
- leak channels;
- the Account section states;
- the startup masking filter.

Swept rows that resolve to existing code, carried from 42ec428: the credential resolver filters by `user_id` at `provider_credentials.py:96`, and `UNIQUE (user_id, provider)` is at `metadata.py:982` and in migration `0030_user_provider_credentials.py:67`.

## Test policy rows

Row 1 was re-judged at e73640b: it was unmet in round 2, and the fix touched the files it classifies. Row 2 carries from fb2d0a9 and row 3 from 42ec428; the fix touched neither of their files.

| Row | Files it classifies | Required proof | Expectation met |
| --- | --- | --- | --- |
| Decides, reached across a boundary (chain resolution in batch A; key routes and deck pin deferred to batch B) - verified at e73640b | `web/dependencies.py` (`_learner_entries`, `get_generation_for_user`, `get_explain_generation_for_user`), `answering/__init__.py` (`order_learner_profiles`, `build_learner_keyed_chain`), `answering/routing.py` | at the boundary: C19, C20, C22, C23, C24, C5 (web), bound lead `test_web_byok_generation.py:236-240`, unbound lead Ask `:261-263` and Explain `:282-284` · at its own layer: C21, C22 (router), `:539-540,557`, `test_answering_routing.py:837` (5 lead rows) | yes - every lead-rule decision row now has a case at the module (the five parametrized ids: absent lead, bound, unbound, other-provider, unknown) and a case through the HTTP client on both entry points. All five faults on this surface were killed (M4-M8) |
| Decides, not reached across a boundary (envelope, adapter cache, rotation; log masking deferred to batch B) - carried from fb2d0a9 | `security/secrets_envelope.py`, `answering/user_adapters.py`, `cli/rotate_secrets_kek.py` | own layer C2, C3 (envelope) · C23, C44 (cache) · C4, C5, `unreadable` (rotation) | yes - each rotation outcome has an asserted case: rewrapped, already_current, unknown_kek, unreadable (`test_cli_rotate_secrets_kek.py:177-186`) and the KEK-absent exit 2 (`:195`). The envelope tamper cases and the cache eviction causes are covered as in round 1. All re-ran PASSED at e73640b |
| Instrumentation (entity dataclasses, the migration body) - carried from 42ec428 | `domain/entities.py`, `domain/ports.py`, `migrations/versions/0030_user_provider_credentials.py`, `db/metadata.py` | none of its own; consumers C1, C7 and the migration walk | yes - C1 `test_provider_credentials_repository.py:55`, C7 `test_web_auth.py:548`, migration `test_migrations.py:4015,4023` (re-run PASSED at e73640b) |

Observation, carried from 42ec428 and unranked: `budget.py:186` (`user_keyed` prices 0) is proven only at the boundary (C25). The Test policy names no row for it.

## Faults injected

Verified at e73640b, on the surface the fix created: the lead rule in `order_learner_profiles` and its two entry points.

Method:
- Scratch worktree: `git worktree add --detach <scratchpad>/r3-wt HEAD`, run with the real venv through `UV_PROJECT_ENVIRONMENT=... uv run --no-sync`.
- Before mutating anything, I confirmed that `dependencies.__file__` and `answering.__file__` resolved inside the scratch.
- I reverted each fault with `git checkout -- .` and checked that the scratch porcelain was empty (`porcelain:[]`) before the next one.
- I removed the scratch with `git worktree remove --force`. Afterwards the real tree's `git status --porcelain` matched the recorded baseline (`?? .specs/features/byok-secrets-and-chains/verification.md` only).

Faults from earlier rounds are carried, all killed: M1-M3 from fb2d0a9, and the round-1 faults on AAD, rotation `kek_id`, the owner rule, the cache fingerprint and `user_keyed` pricing from 42ec428. The fix did not touch any of that code or its proofs.

| Mutation | Location | Killed |
| --- | --- | --- |
| M4 (round-2 survivor): a lead that does not qualify drops the learner's keyed entries (`if head is None: return () if lead else bound`) | `answering/__init__.py:223-224` | yes - 5 failed: `test_a_stored_choice_not_bound_to_the_key_is_ignored` and `test_an_explain_profile_not_bound_to_the_key_is_ignored` (`'claude-house' == 'claude-byok'`), plus `[unbound-lead-ignored]`, `[other-provider-lead-ignored]` and `[unknown-lead-ignored]` (`[] == ['byok-a', 'byok-a2']`) |
| M5: lead looked up outside the bound set (`next((p for p in bound ...` -> `next((p for p in profiles ...`) | `answering/__init__.py:222` | yes - 4 failed: both new web tests (`KeyError: None` from `credentials[profile.user_key_provider]`), `[unbound-lead-ignored]` (`['house','byok-a','byok-a2']`), and `[other-provider-lead-ignored]` (`['byok-o', ...]`) |
| M6: a lead that does not qualify reorders the bound set instead of being ignored (`return bound[::-1] if lead else bound`) | `answering/__init__.py:223-224` | yes - 3 failed: `[unbound-lead-ignored]`, `[other-provider-lead-ignored]` and `[unknown-lead-ignored]` (`['byok-a2','byok-a'] == ['byok-a','byok-a2']`). No web test sees this, so the own-layer test carries it alone |
| M7: Explain-only wrong reading: an unbound `generation_explain_profile` empties the keyed entries in `get_explain_generation_for_user` | `dependencies.py:880-881` | yes - 1 failed: `test_an_explain_profile_not_bound_to_the_key_is_ignored` (`'claude-house' == 'claude-byok'`); the Ask test is unaffected |
| M8: Explain lead dropped (`lead = get_settings().generation_explain_profile or None` -> `lead = None`) | `dependencies.py:880` | yes - 1 failed: `test_explain_served_by_learner_key` (`'claude-byok' == 'claude-byok-explain'`) |

Five faults were injected, the cap. Each forces a different proof or assertion to fail: the shared drop (M4), the bound-set lookup (M5), registry order preservation at the module (M6), the Explain entry point on its own (M7), and the Explain bound lead (M8). Every round-3 test failed under at least one fault.

## Gate

Verified at e73640b.

- Batch-A proofs, run as one `-v` invocation from `backend/` with `LEARNY_REQUIRE_DB=1` and the `learny_test_byok` URL: 74 passed, 0 failed, 0 skipped.
- Full backend suite at `e73640b`, in a clean scratch worktree that has no local skip-worktree `docker-compose.override.yml`: `uv run --no-sync pytest -p no:cacheprovider -q` gave **3144 passed, 0 failed, 12 skipped** (156 s). The fb2d0a9 baseline was 3137 passed. The difference is the 7 new test items: 2 web tests and 5 parametrized ids. The two `test_deploy_topology.py::test_dev_merge_*` failures that occur only in the real tree come from that local override file. They are environmental, as in rounds 1 and 2.
- Frontend and lint were not re-run, because the fix diff changes only two backend test files.
