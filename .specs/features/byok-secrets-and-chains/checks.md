# BYOK secrets and chains checks

Profile: standard
Plan: `.specs/features/byok-secrets-and-chains/plan.md`

44 checks in 6 slices · 8 one-way doors · 0 open, of which 0 block

Check numbers match the plan's AC numbers (C*n* proves AC *n*). C43 is the authentication
row that every new route owes. Backend proofs run from `backend/` with
`LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test_byok`
exported (DB-gated tests skip without it, and a skip is not green). Frontend proofs run from
`frontend/`.

## Checks

### S1 - Sealed key storage · batch A

**C1** - A stored key leaves only ciphertext, nonce, wrapped DEK, DEK nonce, `kek_id`, fingerprint and last four in the row. Neither the plaintext nor the plaintext DEK appears in any column (AC 1) ✅
Proof: `uv run pytest tests/test_provider_credentials_repository.py -k "row_holds_no_plaintext"`

**C2** - Sealing the same key twice yields different DEKs, nonces and ciphertexts, and both open to the same plaintext (AC 2) ✅
Proof: `uv run pytest tests/infrastructure/test_secrets_envelope.py -k "fresh_dek_and_nonce_per_seal"`

**C3** - Opening a sealed secret with a different user id or a different provider in the associated data raises, and a flipped ciphertext byte raises (AC 3) ✅
Proof: `uv run pytest tests/infrastructure/test_secrets_envelope.py -k "associated_data_binds_owner"`
Proof: `uv run pytest tests/infrastructure/test_secrets_envelope.py -k "tampered_ciphertext_rejected"`

**C4** - Rotation with a new current KEK and the old one in `LEARNY_SECRETS_KEK_PREVIOUS` re-wraps every row, leaves `ciphertext` byte-identical, sets `kek_id` to the new KEK's id, keeps every key decryptable, and a second run reports 0 rewrapped (AC 4) ✅
Proof: `uv run pytest tests/test_cli_rotate_secrets_kek.py -k "rewraps_without_touching_ciphertext"`

**C5** - A row under an unknown KEK makes the rotation print it in the unknown count and exit `1`. The credential resolver returns "no credential" for that user instead of raising (AC 5)
Proof: `uv run pytest tests/test_cli_rotate_secrets_kek.py -k "unknown_kek_exits_one"`
Proof: `uv run pytest tests/test_web_byok_generation.py -k "unknown_kek_serves_house_chain"`

**C6** - `LEARNY_SECRETS_KEK` set to non-base64, or to base64 of 16 or 33 bytes, fails `Settings()` with a message naming `LEARNY_SECRETS_KEK` that does not contain the value. A valid KEK or an unset one loads (AC 6) ✅
Proof: `uv run pytest tests/test_config.py -k "secrets_kek"`

**C7** - Deleting a user through `DELETE /api/auth/account` removes every `user_provider_credentials` row of that user and leaves another user's row in place (AC 7) ✅
Proof: `uv run pytest tests/test_provider_credentials_repository.py -k "cascades_with_its_user"`
Proof: `uv run pytest tests/test_web_auth.py -k "delete_account_erases_provider_keys"`

### S2 - Key management API · batch B

**C8** - With no KEK, or with a KEK but no profile setting `user_key_provider`, `GET /api/me/provider-keys` answers `200 {"enabled": false, "providers": []}`, and `PUT`, `POST …/test` and `DELETE` answer `404` (AC 8)
Proof: `uv run pytest tests/test_web_provider_keys.py -k "disabled_feature"`

**C9** - With profiles binding `anthropic` and `openai`, `GET` lists exactly those two providers in registry order of first binding. Each carries `configured`, `last4`, `added_at`, `powers[]` (`profile_id`, `display_name`, `ask`, `teach`) and `powers_cards`, which is true for `anthropic` only (AC 9)
Proof: `uv run pytest tests/test_web_provider_keys.py -k "lists_offered_providers_with_powers"`

**C10** - `PUT` of a well-formed key answers `200` with `configured: true` and `last4` equal to the key's last four characters. A second `PUT` replaces it: one row remains, its id differs from the first, and it opens to the new key (AC 10)
Proof: `uv run pytest tests/test_web_provider_keys.py -k "put_stores_and_replace_mints_new_row"`

**C11** - `PUT` with a missing key, a key containing whitespace, a 19-character key, a 257-character key, or an anthropic key without `sk-ant-` answers `422`, and the response body contains no part of the submitted value (AC 11)
Proof: `uv run pytest tests/test_web_provider_keys.py -k "malformed_key_422_never_echoes"`

**C12** - `PUT`, `POST …/test` and `DELETE` on a provider value that no profile binds (for example `gemini` when only `anthropic` is bound, and `mistral`) answer `404` (AC 12)
Proof: `uv run pytest tests/test_web_provider_keys.py -k "unoffered_provider_404"`

**C13** - The test route answers `200 {"ok": true, "reason": null}` when the probe succeeds and `200 {"ok": false, "reason": r}` for each of `rejected`, `rate_limited` and `unavailable`, which are mapped from the provider error taxonomy. The probe is built with the stored key and the bound profile's `base_url` (AC 13)
Proof: `uv run pytest tests/test_web_provider_keys.py -k "test_route_maps_probe_outcomes"`
Proof: `uv run pytest tests/infrastructure/test_credential_probe.py -k "lists_models_with_profile_host"`

**C14** - The test route for an offered provider with no stored key answers `404` (AC 14)
Proof: `uv run pytest tests/test_web_provider_keys.py -k "test_without_key_404"`

**C15** - `DELETE` answers `204` and removes the row; a second `DELETE` also answers `204` (AC 15)
Proof: `uv run pytest tests/test_web_provider_keys.py -k "delete_is_idempotent_204"`

**C16** - `PUT`, `POST …/test` and `DELETE` without the CSRF header answer `403` and leave the stored row unchanged (AC 16)
Proof: `uv run pytest tests/test_web_provider_keys.py -k "writes_require_csrf"`

**C17** - Once the user-keyed limit is exhausted, `PUT` and `POST …/test` answer `429` (AC 17)
Proof: `uv run pytest tests/test_web_provider_keys.py -k "writes_rate_limited_429"`

**C18** - Across list, put, replace, test and delete, no response body contains the stored key or any 8-character substring of it other than the reported `last4` (AC 18)
Proof: `uv run pytest tests/test_web_provider_keys.py -k "responses_never_carry_key_material"`

**C43** - All four routes answer `401` without a session
Proof: `uv run pytest tests/test_web_provider_keys.py -k "routes_require_session_401"`

### S3 - Learner chains for Ask, Tutor and Explain · batch A

**C19** - A learner with a stored key for a bound provider is served an ask turn and a teach turn by the bound profile, through an adapter constructed with that learner's key, ahead of the house primary (AC 19)
Proof: `uv run pytest tests/test_web_byok_generation.py -k "turn_served_by_learner_key"`

**C20** - A learner's selection-Explain is served by a profile bound to their provider with their key. When `generation_explain_profile` names a bound profile, that profile serves first (AC 20)
Proof: `uv run pytest tests/test_web_byok_generation.py -k "explain_served_by_learner_key"`

**C21** - When every eligible user-keyed entry raises `RequestRejected`, `ProviderUnavailable` or `Timeout`, the router raises the generation failure and the house entries in the same chain are never called (AC 21)
Proof: `uv run pytest tests/infrastructure/test_answering_routing.py -k "never_falls_from_user_key_to_house"`

**C22** - When no user-keyed entry is eligible for the requested mode (for example, the bound profile has `ask_enabled=false`), the call is served by the house chain's first eligible entry (AC 22)
Proof: `uv run pytest tests/infrastructure/test_answering_routing.py -k "uncovered_mode_served_by_house"`
Proof: `uv run pytest tests/test_web_byok_generation.py -k "uncovered_mode_served_by_house"`

**C23** - Two learners with different keys for the same provider, asking in the same process, each reach an adapter built with their own key, and the cache holds two distinct entries (AC 23)
Proof: `uv run pytest tests/test_web_byok_generation.py -k "two_learners_two_keys"`
Proof: `uv run pytest tests/infrastructure/test_user_adapter_cache.py -k "keys_on_fingerprint"`

**C24** - After a replace, the learner's next turn is served by an adapter built with the new key. After a delete, it is served by the house chain. The old key's adapter is never called again (AC 24)
Proof: `uv run pytest tests/test_web_byok_generation.py -k "replace_and_delete_take_effect_next_request"`

**C25** - A turn served by a user-keyed entry that reports token usage leaves the ledger's `usd_micros` for that day at 0 and increments `ask_count` by 1. The same turn served by a house entry debits more than 0 (AC 25)
Proof: `uv run pytest tests/test_web_byok_generation.py -k "learner_key_debits_zero_usd_counts_call"`

**C26** - With `ai_kill_switch` on, a learner with a stored key gets the pause refusal (`503`) and no adapter is called (AC 26)
Proof: `uv run pytest tests/test_web_byok_generation.py -k "kill_switch_refuses_learner_key"`

**C27** - A profile with `user_key_provider` and no `api_key_env` never appears in `build_generation_chain`, in the explain chain or in `learner_catalog`. A registry whose only non-local profiles are user-key-only and that has no house-servable profile fails resolution with an error naming the problem. A non-local profile with neither field still fails as today (AC 27) ✅
Proof: `uv run pytest tests/infrastructure/test_provider_profiles.py -k "user_key_only"`

**C44** - The adapter cache holds at most its bound (256) entries, evicting least-recently-used, and an entry older than its TTL is rebuilt on the next lookup (Landing door 4)
Proof: `uv run pytest tests/infrastructure/test_user_adapter_cache.py -k "lru_bound_and_ttl"`

### S4 - Cards and decks under the learner's key · batch B

**C28** - A learner with a stored anthropic key requesting card suggestions (source and note paths) is served by a quiz adapter built with their key and `quiz_model`. The day's `usd_micros` stays 0 (AC 28)
Proof: `uv run pytest tests/test_web_byok_cards.py -k "suggestions_use_learner_key"`

**C29** - `quiz.generate_deck` and `notes.refresh_cards` for an owner with a stored anthropic key build their quiz adapter with that key, resolved from the database inside the task (AC 29)
Proof: `uv run pytest tests/worker/test_byok_decks.py -k "deck_task_resolves_owner_key"`
Proof: `uv run pytest tests/worker/test_byok_decks.py -k "refresh_cards_resolves_owner_key"`

**C30** - A deck begun under a learner's key yields a handle payload whose `credential_id` is that row's id. The scheduled `poll_quiz_deck` collects with an adapter built from the same credential. A handle without `credential_id` still polls with the house adapter (AC 30)
Proof: `uv run pytest tests/worker/test_byok_decks.py -k "poll_pins_credential"`

**C31** - When the pinned credential was deleted, or replaced with a new row id, before the poll, the job ends `failed` with the fixed copy and no adapter `collect_deck` is called (AC 31)
Proof: `uv run pytest tests/worker/test_byok_decks.py -k "poll_fails_when_pinned_key_gone"`

**C32** - Across deck generate, deck poll scheduling and note refresh enqueueing for a learner with a canary key, every captured Celery `args`/`kwargs` value, serialized to JSON, lacks the canary. The payload keys are limited to ids, the handle and the deadline (AC 32)
Proof: `uv run pytest tests/worker/test_byok_decks.py -k "task_payloads_carry_ids_only"`

### S5 - Keys never leak · batch B

**C33** - A log record whose message, `%s` args, `extra` values or exception text contains `sk-ant-<20+ chars>`, `sk-<20+ chars>` or `AIza<20+ chars>` is emitted with that substring replaced by a redaction marker. This holds under both the API and the worker logging configuration (AC 33)
Proof: `uv run pytest tests/test_logging_redaction.py -k "masks_provider_key_shapes"`

**C34** - With a canary key, an end-to-end run of add → test → ask turn → explain → card suggest → deck → rotate → replace → delete produces no captured log record (all loggers, DEBUG), API response body, raised exception string, Celery argument, or `repr()` of a credential entity or built adapter that contains the canary (AC 34)
Proof: `uv run pytest tests/test_byok_leak_canary.py -k "canary_never_surfaces"`

**C35** - The canary sensor's negative control writes the canary through an unmasked handler path and asserts that the same scanner reports it (AC 35)
Proof: `uv run pytest tests/test_byok_leak_canary.py -k "scanner_catches_deliberate_leak"`

### S6 - Account keys section · batch B

**C36** - With `enabled: false`, `AccountPanel` renders no element with the keys section heading (AC 36)
Proof: `npx vitest run tests/account-provider-keys.test.tsx -t "hidden when disabled"`

**C37** - With an enabled catalog of one configured anthropic row and one unconfigured openai row, the anthropic row shows `•••• ` plus last4, the added date, each powering profile's display name with Ask/Teach marks, and "flashcards & decks". The openai row shows a password-type input and a Save button (AC 37)
Proof: `npx vitest run tests/account-provider-keys.test.tsx -t "renders configured and unconfigured rows"`

**C38** - After Save succeeds the input is empty, the row shows the configured state, and no DOM text or input value contains the submitted key (AC 38)
Proof: `npx vitest run tests/account-provider-keys.test.tsx -t "save clears and never re-renders the key"`

**C39** - Test shows the literal text "Key works" for `ok: true` and a distinct message for each of `rejected`, `rate_limited` and `unavailable` (AC 39)
Proof: `npx vitest run tests/account-provider-keys.test.tsx -t "test outcome messages"`

**C40** - Delete opens a confirmation, and the delete request is sent only after confirming. Cancel sends nothing (AC 40)
Proof: `npx vitest run tests/account-provider-keys.test.tsx -t "delete confirms first"`

**C41** - A failed save, test or delete shows an inline error and keeps the previous row state (AC 41)
Proof: `npx vitest run tests/account-provider-keys.test.tsx -t "failure keeps state and shows error"`

**C42** - The section renders the disclosure copy: billed by the provider to the learner under their own agreement, stored encrypted, cannot be shown again (AC 42)
Proof: `npx vitest run tests/account-provider-keys.test.tsx -t "disclosure copy"`

## Coverage

| Set (size) | Member -> proof | Unproven |
| --- | --- | --- |
| `GET /api/me/provider-keys` statuses (2) | 200 C9 · 401 C43 | - |
| `PUT /api/me/provider-keys/{provider}` statuses (6) | 200 C10 · 401 C43 · 403 C16 · 404 C12 · 422 C11 · 429 C17 | - |
| `POST /api/me/provider-keys/{provider}/test` statuses (5) | 200 C13 · 401 C43 · 403 C16 · 404 C14 · 429 C17 | - |
| `DELETE /api/me/provider-keys/{provider}` statuses (4) | 204 C15 · 401 C43 · 403 C16 · 404 C12 | - |
| test outcomes (4) | ok C13 · rejected C13 · rate_limited C13 · unavailable C13 | - |
| key-format rejections (5) | missing C11 · whitespace C11 · too short C11 · too long C11 · missing prefix C11 | - |
| provider literals (3) | anthropic C9 · openai C9 · gemini C12 | - |
| feature-off conditions (2) | no KEK C8 · KEK without a binding profile C8 | - |
| generation surfaces on the learner key (6) | ask turn C19 · teach turn C19 · explain C20 · card suggest C28 · deck C29 · note card refresh C29 | - |
| fall-over cases (3) | user-key failure stays in user entries C21 · uncovered mode goes to house C22 · no key goes to house C24 | - |
| key lifecycle effect on serving (3) | replace C24 · delete C24 · account delete C7 | - |
| rotation outcomes (3) | rewrapped C4 · already current C4 · unknown KEK C5 | - |
| KEK config values (4) | unset C6 · valid C6 · non-base64 C6 · wrong length C6 | - |
| envelope tamper cases (3) | other user C3 · other provider C3 · flipped byte C3 | - |
| adapter cache eviction (3) | LRU bound C44 · TTL C44 · fingerprint change C24 | - |
| deck pin cases (3) | pinned present C30 · pinned gone C31 · legacy handle without pin C30 | - |
| leak channels (7) | logs C33,C34 · API responses C18,C34 · exception strings C34 · Celery args C32,C34 · credential repr C34 · adapter repr C34 · 422 echo C11 | - |
| ledger effects of a user-keyed call (3) | usd 0 C25 · ask counter C25 · kill switch C26 | - |
| Account section states (6) | hidden C36 · configured C37 · unconfigured C37 · saved C38 · error C41 · confirm C40 | - |
| startup config: KEK validation (2 assemblies) | API `get_settings()` C6 · worker `get_settings()` C6 (one shared `Settings` class) | - |
| startup config: key masking filter (2 assemblies) | API `main.py` C33 · worker `celery_app.py` C33 (shared `configure_logging`; C33 asserts both call sites install it) | - |

- Claims naming a status code, route or response shape: C8-C18, C26, C43. Each has a proof through the HTTP client
- The router claims C21 and C22 are proven at the router's own layer and again at the boundary (C22) through the web dependency

## Test policy

| Code | Required proofs | Coverage expectation |
| --- | --- | --- |
| Decides, reached across a boundary (key routes, chain resolution, deck pin) | one at the boundary **and** one at its own layer | the route's status set through the HTTP client; one case per decision row at the module |
| Decides, not reached across a boundary (envelope, adapter cache, log masking, rotation) | one at its own layer | one asserted case per row of its table (tamper cases, eviction causes, key shapes, rotation outcomes) |
| Instrumentation (entity dataclasses, the migration body, client lib fetch wrappers) | none of its own | covered by the consumer proofs (C1, C7, C37-C41) and the existing `test_migrations.py` upgrade/downgrade walk |

Evidence:

- `answering/routing.py`: `_next_index` dispatches over four error classes plus the stream bound. The new owner rule adds one branch point → decides; analogue `tests/infrastructure/test_answering_routing.py`, proven at its own layer today
- `web/ai.py`: four routes with 401/403/422/204 branches → decides at the boundary; analogue `tests/test_web_ai_profile.py`
- secrets envelope: three tamper outcomes plus KEK lookup by id → decides, not reached directly across a boundary
- closest analogue for the worker pin: `tests/worker/test_quiz_deck_pinning.py`, same shape (handle provider pin), already proven at the task layer

Cost: 13 new or extended test files. Without these rows the router's owner rule would be proven only by a web test that traverses one path through it.

## Swept

- validation: C6, C11, C12
- failure modes: C5, C21, C31
- idempotency: C4 (rotation re-run reports 0), C15 (DELETE twice); the deck spend marker stays the existing one-time claim
- authorization: C16, C43, C7; the credential resolver filters by the caller's `user_id`, and C23 proves no cross-user serving
- concurrency: C10 (`UNIQUE (user_id, provider)` makes a racing double-PUT end with one row, and the loser gets the constraint error mapped to a retry of the replace); C23 for two learners in one process
- data lifecycle: C7 (account delete), C15 (key delete), C4 (KEK rotation), C44 (cache TTL)
- dependency failure: C13 (probe taxonomy), C21 (no house fall-over), C31 (pinned key gone)
- state transitions: C10 (unset → set → replaced), C15 (set → unset), C24 (serving follows the transition)
- observability: C33-C35. The rotation CLI prints counts (C4, C5). No new metric, because no metrics stack exists (no OTel or Sentry)

## Handoff

Size, from `wc -c` on the files each slice reads or writes, divided by four (new files estimated):

- S1 = metadata 43k + repositories 118k + entities 56k + ports 63k + config 26k + new envelope/CLI/migration ~15k + tests ~25k ≈ 346 KB ≈ **86k**
- S3 = answering/__init__ 9k + routing 12k + profiles 11k + dependencies 52k + budget 10k + conversations 53k + conftest 15k + new cache ~6k + tests ~40k ≈ 208 KB ≈ **52k** → S1+S3 = **138k**, under the 150k budget
- S2 = new router ~10k + dependencies 52k + rate_limit ~9k + profiles 11k + error handlers ~8k + tests ~30k ≈ 120 KB ≈ **30k**
- S4 = tasks 33k + quiz factory 3k + quiz anthropic 19k + cards 35k + application quiz 24k + entities 56k + dependencies 52k + tests ~30k ≈ 252 KB ≈ **63k**
- S5 = logging 7k + tests ~35k ≈ **11k**
- S6 = AccountPanel 9k + new client lib ~6k + tests ~21k ≈ **9k**
- Total ≈ **251k**, over the 150k budget. Per owner decision D2, the mechanism is pre-answered **handoff**: sequential batches cut at slice boundaries, one PR each, the next batch starting only after the previous one merges
- **Batch A = S1 + S3 (138k)**, the engine: sealed storage, rotation, learner chains, ledger rule, and ADR-0032. The feature stays unreachable (no route stores a key) and off by default
- **Batch B = S2 + S4 + S5 + S6 (113k)**, the controls: key routes, cards and decks, leak sensors, Account UI. The Verifier runs scoped to batch A's checks (C1-C7, C19-C27, C44) before PR A, and over every check before PR B
- Mechanism: handoff (D2 pre-answer, recorded 2026-10-02)
