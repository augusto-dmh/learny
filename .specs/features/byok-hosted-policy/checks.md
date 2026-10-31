# BYOK hosted policy checks

Profile: standard
Plan: `.specs/features/byok-hosted-policy/plan.md`

Mutations: 3
Build: `uv run ruff check .` / `uv run ruff format --check .` / `python scripts/check_boundaries.py` (backend, from `backend/`); `npx tsc --noEmit` / `npm run build` (frontend, from `frontend/`)

31 checks in 7 slices · 7 one-way doors · 0 open, of which 0 block

Check numbers match the plan's AC numbers (C*n* proves AC *n*). C31 is the authentication
row the new route owes. Backend proofs run from `backend/` with
`LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5436/learny_test`
and `LEARNY_REDIS_URL=redis://localhost:6382/0` exported (DB-gated tests skip without
them, and a skip is not green). Frontend proofs run from `frontend/`.

## Checks

### S1 - The hosted gate and the allow-list · batch A

**C1** - With `LEARNY_HOSTED_INSTANCE=true` and `LEARNY_HOSTED_BYOK_ENABLED=false`, a KEK set and profiles bound: `GET /api/me/provider-keys` answers `200 {"enabled": false, "providers": [], "hosted": true}`, `PUT`, `POST …/test` and `DELETE` answer `404`, and no credential row is read - the repository is never constructed (AC 1)
Proof: `uv run pytest tests/test_web_provider_keys.py -k "hosted_without_optin_reads_nothing"`

**C2** - With both hosted flags true, a KEK and a bound profile, the keys surface serves exactly as a self-host's: list/put/test/delete behave identically, and `GET` reports `hosted: true` (AC 2)
Proof: `uv run pytest tests/test_web_provider_keys.py -k "hosted_optin_serves_like_selfhost"`

**C3** - With `LEARNY_HOSTED_INSTANCE=false` and `LEARNY_HOSTED_BYOK_ENABLED=true`, availability stays KEK + bound profile (the keys surface serves, exactly as with the second flag unset) - the second flag is ignored without the declaration (AC 3)
Proof: `uv run pytest tests/test_web_provider_keys.py -k "byok_flag_needs_hosted_declaration"`

**C4** - Every offered provider is `anthropic`, `openai` or `gemini`, and every profile binding a user-key provider sends its keys to that provider's canonical HTTPS host - a registry binding one anywhere else fails startup naming the problem; the same rules hold with the hosted flags on (AC 4)
Proof: `uv run pytest tests/infrastructure/test_provider_profiles.py -k "canonical"`
Proof: `uv run pytest tests/infrastructure/test_provider_profiles.py -k "hosted_flags_offer_only_the_canonical"`

**C5** - A key `PUT` body carrying extra fields (for example `base_url`) stores exactly what a clean PUT stores, and the adapter a later turn builds is constructed from the bound profile's declared host - the submitted endpoint never reaches adapter construction (AC 5)
Proof: `uv run pytest tests/test_web_provider_keys.py -k "extra_body_fields_ignored"`
Proof: `uv run pytest tests/infrastructure/test_provider_profiles.py -k "host_from_profile_only"`

**C6** - Across the whole account surface (list, save with malformed and valid bodies, test, delete, budget put, profile choice, account read), no response contains a distinctive canary KEK value (AC 6)
Proof: `uv run pytest tests/test_byok_leak_canary.py -k "kek"`

### S2 - The house spend-cap exemption keeps the rate rails · batch A

**C7** - With the caller's day at the daily USD cap and their key covering the mode, an ask turn is served on their key, the house ledger's `usd_micros` stays 0, and the day's `ask_count` increments (AC 7)
Proof: `uv run pytest tests/test_web_byok_generation.py -k "usd_cap_exhausted_served_on_key"`

**C8** - While the USD cap is exempted, the kill switch still refuses with `503`, an exhausted ask counter still refuses with `429`, and a tripped route rate limit still answers `429` (AC 8)
Proof: `uv run pytest tests/test_web_byok_generation.py -k "exemption_keeps_rails"`

**C9** - When the caller's key does not cover the requested mode and the day is at the USD cap, the turn is refused with the ordinary budget `429` - the full assertion applies (AC 9)
Proof: `uv run pytest tests/test_web_byok_generation.py -k "uncovered_mode_keeps_usd_cap"`

**C10** - Deck submit with the day at the USD cap: an owner with a stored anthropic key gets `202` (the deck runs on their key); a learner without keys at the same ledger is refused `429` (AC 10)
Proof: `uv run pytest tests/test_web_quiz.py -k "deck_at_usd_cap_owner_key"`

**C11** - When a BYOK policy refusal (budget or corpus ceiling) trips for a turn the caller's key would serve, the turn is refused with the typed `429` and the house chain is never called (AC 11)
Proof: `uv run pytest tests/test_web_byok_generation.py -k "policy_refusal_never_falls_over"`

### S3 - The per-corpus prompt-token ceiling · batch A

**C12** - When a user-keyed ask turn finds the conversation's source at the month's prompt-token ceiling, the turn is refused `429` with code `byok_corpus_limit` before any provider call - nothing is generated and nothing is recorded (AC 12)
Proof: `uv run pytest tests/test_web_byok_generation.py -k "corpus_ceiling_refuses_turn"`

**C13** - The ceiling counts user-keyed input tokens per (learner, source, calendar month): a house-served turn on the same source adds nothing, another learner's calls add nothing, and a turn on a different source of the same learner is unaffected (AC 13)
Proof: `uv run pytest tests/test_application_byok_policy.py -k "corpus_ledger_scope"`

**C14** - `LEARNY_BYOK_CORPUS_PROMPT_TOKEN_CAP` defaults to 4000000, `0` disables the ceiling, and a value below 0 fails `Settings()` naming the variable (AC 14)
Proof: `uv run pytest tests/test_config.py -k "corpus_prompt_cap"`
Proof: `uv run pytest tests/test_application_byok_policy.py -k "cap_zero_disables"`

**C15** - Card suggestions and a deck submit on a learner's key, targeting a source at the ceiling, refuse with the same typed `429` before generating (AC 15)
Proof: `uv run pytest tests/test_web_byok_cards.py -k "ceiling_refuses_cards"`
Proof: `uv run pytest tests/test_web_quiz.py -k "deck_at_corpus_ceiling"`

### S4 - Per-answer token and cost display · batch A (backend) + batch B (render)

**C16** - An adapter-reported usage reaches all three surfaces: the buffered turn response, the stream's terminal `data-answer-usage` part, and the restored history view carry `usage_input_tokens`/`usage_output_tokens`/`user_keyed`; `cost_usd_micros` is set for a user-keyed turn and `null` for a house turn (AC 16)
Proof: `uv run pytest tests/test_web_byok_generation.py -k "usage_reaches_turn_and_stream"`
Proof: `uv run pytest tests/test_web_conversations.py -k "restored_history_carries_usage"`

**C17** - A turn whose adapter reports no usage carries `usage_input_tokens: null` and `usage_output_tokens: null` on every surface, and no usage line renders (AC 17)
Proof: `uv run pytest tests/test_web_byok_generation.py -k "no_reported_usage_is_null"`

**C18** - The displayed cost equals the same usage priced by the house rule: `estimate_micros` resolves the serving profile's catalog exactly as `usage_micros` does for a house call, and never returns 0 for reported usage whatever the payer (AC 18)
Proof: `uv run pytest tests/test_application_budget_pricing.py -k "estimate_matches_house_rule"`

**C19** - An answer with reported usage renders one usage line with the token counts and, on a learner-keyed answer, the estimated cost labeled as on the learner's own key - from the en and pt-BR catalogs (AC 19)
Proof: `npx vitest run tests/answer-usage.test.tsx -t "usage line"`

### S5 - The soft monthly budget · batch A (backend) + batch B (render)

**C20** - `PUT /api/me/provider-keys/budget` stores a USD budget (> 0 and ≤ 10000) and clears it with `null`; invalid input answers `422` with fixed copy echoing no submitted value; feature-off `404`, session `401`, CSRF `403` and write rate-limit `429` match the sibling key routes (AC 20, C31 auth)
Proof: `uv run pytest tests/test_web_provider_keys.py -k "budget_route"`
Proof: `uv run pytest tests/test_web_provider_keys.py -k "budget_requires_session_401"`

**C31** - The budget route answers `401` without a session
Proof: `uv run pytest tests/test_web_provider_keys.py -k "budget_requires_session_401"`

**C21** - The monthly ledger accumulates the input tokens, output tokens and estimated cost of the learner's user-keyed calls - turns and card suggestions at record time, deck passes at the worker's settle beside the house 0-USD debit - and `GET /api/me/provider-keys` exposes the month-to-date row and the stored budget (AC 21)
Proof: `uv run pytest tests/test_application_byok_policy.py -k "monthly_ledger_accumulates"`
Proof: `uv run pytest tests/worker/test_quiz_deck_spend.py -k "settle_records_byok_ledgers"`
Proof: `uv run pytest tests/test_web_provider_keys.py -k "list_reports_usage_and_budget"`

**C22** - When the month's estimated cost reaches the learner's budget, user-keyed generation refuses `429` with code `byok_budget` on the turn, card-suggestion and deck-submit surfaces, the house chain is never called, and a mode the learner's key does not cover is unaffected (governed by the house rails as ever) (AC 22)
Proof: `uv run pytest tests/test_web_byok_generation.py -k "monthly_budget_trips"`
Proof: `uv run pytest tests/test_web_byok_cards.py -k "budget_trips_cards"`
Proof: `uv run pytest tests/test_web_quiz.py -k "deck_at_monthly_budget"`

**C23** - After the learner raises or clears the budget, their key serves the next request with no operator action (AC 23)
Proof: `uv run pytest tests/test_application_byok_policy.py -k "raised_budget_serves_next"`

**C24** - The budget refusal carries code `byok_budget`, and the rendered copy says it is the learner's own monthly budget and that they can change it in Account - from the en and pt-BR catalogs (AC 24)
Proof: `npx vitest run tests/answer-usage.test.tsx -t "budget refusal"`

**C25** - The keys section shows the month-to-date usage line (estimated cost and tokens, and the budget when set) beside the budget control, updating after every change - from the en and pt-BR catalogs (AC 25)
Proof: `npx vitest run tests/provider-keys-section.test.tsx -t "usage"`

### S6 - Privacy badges and hosted disclosure · batch B

**C26** - Each offered provider row shows its privacy badge: Gemini's warns unpaid-tier content may improve Google products; Anthropic's and OpenAI's state API content is not used for training - from the en and pt-BR catalogs (AC 26)
Proof: `npx vitest run tests/provider-keys-section.test.tsx -t "badge"`

**C27** - With `hosted: true` the keys section shows the hosted disclosure (encrypted storage on this server, the learner's own provider agreement, no custom endpoints); a self-host keeps today's disclosure only (AC 27)
Proof: `npx vitest run tests/provider-keys-section.test.tsx -t "disclosure"`

### S7 - The policy record and the operator's checklist · batch B

**C28** - `docs/ops/hosted-byok-security-review.md` exists and covers: generating and backing up the KEK, declaring the hosted flags, the provider-terms review (including the unresolved OpenAI key-transfer question), the rate/ceiling defaults worth reviewing, and the explicit go/no-go line for the opt-in (AC 28)
Proof: `python -c "from pathlib import Path; t = Path('docs/ops/hosted-byok-security-review.md').read_text(encoding='utf-8'); assert all(s in t for s in ('KEK', 'LEARNY_HOSTED_INSTANCE', 'LEARNY_HOSTED_BYOK_ENABLED', 'key-transfer', 'LEARNY_BYOK_CORPUS_PROMPT_TOKEN_CAP', 'go/no-go')), 'checklist missing a required section'  # docs content proof"`

**C29** - `docs/adr/0035-learner-keys-on-a-hosted-instance.md` exists with status Accepted, records the declaration flags, the three-provider allow-list, the no-learner-endpoint rule, the exemption boundary, the ceiling and budget, badges and disclosure, and names the prior decision's point 11 as superseded (AC 29)
Proof: `python -c "from pathlib import Path; t = Path('docs/adr/0035-learner-keys-on-a-hosted-instance.md').read_text(encoding='utf-8'); assert 'Accepted' in t and 'supersede' in t.lower() and all(s in t for s in ('LEARNY_HOSTED_INSTANCE', 'LEARNY_HOSTED_BYOK_ENABLED', 'anthropic', 'openai', 'gemini'))  # docs content proof"`

**C30** - Both environment example files document the two hosted flags and the ceiling, and the production example replaces "leave the KEK unset on a hosted instance" with the checklist-gated opt-in (AC 30)
Proof: `python -c "from pathlib import Path; a = Path('.env.example').read_text(encoding='utf-8'); p = Path('.env.production.example').read_text(encoding='utf-8'); assert all(s in a for s in ('LEARNY_HOSTED_INSTANCE', 'LEARNY_HOSTED_BYOK_ENABLED', 'LEARNY_BYOK_CORPUS_PROMPT_TOKEN_CAP')); assert all(s in p for s in ('LEARNY_HOSTED_INSTANCE', 'LEARNY_HOSTED_BYOK_ENABLED', 'LEARNY_BYOK_CORPUS_PROMPT_TOKEN_CAP', 'security-review'))  # docs content proof"`

## Coverage

| Set (size) | Member -> proof | Unproven |
| --- | --- | --- |
| hosted gate states (3) | hosted + opt-in off C1 · hosted + opt-in on C2 · self-host ignores the opt-in C3 | - |
| offered providers (3) | anthropic C4 · openai C4 · gemini C4 | - |
| key PUT body fields (2) | clean `api_key` C5 · extra fields ignored C5 | - |
| account-surface leak channels (7) | list C6 · malformed save C6 · valid save C6 · test C6 · delete C6 · budget put C6 · profile choice + account read C6 | - |
| rails under the exemption (3) | kill switch C8 · integer counters C8 · route rate limit C8 | - |
| coverage determines the assertion (2) | key covers -> exempt C7 · key does not cover -> full cap C9 | - |
| BYOK refusals (2) | `byok_budget` C11, C22 · `byok_corpus_limit` C12 | - |
| corpus-ceiling surfaces (4) | ask/teach turn C12 · selection-explain turn C12 · card suggestions C15 · deck submit C15 | - |
| corpus-ceiling scope (4) | per learner C13 · per source C13 · per month C13 · user-keyed input only C13 | - |
| cap settings values (3) | default 4000000 C14 · `0` disables C14 · negative rejected C14 | - |
| usage surfaces (3) | buffered response C16 · stream terminal part C16 · restored history C16 | - |
| usage absence (2) | null tokens C17 · no rendered line C17 | - |
| cost pricing rule (2) | user-keyed estimate C18 · house view of the same catalog C18 | - |
| budget route statuses (6) | 200 C20 · 401 C31 · 403 C20 · 404 C20 · 422 C20 · 429 C20 | - |
| monthly-ledger call kinds (3) | turns C21 · card suggestions C21 · deck passes C21 | - |
| budget-trip surfaces (3) | turn C22 · cards C22 · deck C22 | - |
| budget lifecycle (3) | set/clear C20 · refusal at the cap C22 · raised/cleared serves C23 | - |
| keys-section states (5) | usage line C25 · budget control C25 · badges C26 · hosted disclosure C27 · self-host disclosure C27 | - |
| docs artifacts (3) | ops checklist C28 · the ADR C29 · env examples C30 | - |
| `POST /api/conversations/{id}/turns/stream` additions (2) | typed 429 refusals C11, C12, C22 · terminal `data-answer-usage` part C16 (pre-existing statuses covered by the existing conversation sensors) | - |
| `POST /api/conversations/{id}/turns` additions (2) | typed 429 refusals C11, C12, C22 · usage fields on the response C16 (pre-existing statuses covered by the existing conversation sensors) | - |
| `PUT /api/me/provider-keys/budget` statuses (6) | 200 C20 · 401 C31 · 403 C20 · 404 C20 · 422 C20 · 429 C20 | - |
| `POST /api/sources/{source_id}/quiz/deck` refusals (3) | usd-cap-exempt submit C10 · ceiling C15 · budget C22 | - |
| `POST /api/sources/{source_id}/cards/suggestions` refusals (2) | ceiling C15 · budget C22 | - |

- Claims naming a status code, route or response shape: C1, C2, C7-C12, C15, C16, C20-C23, C31. Each has a proof through the HTTP client
- C11, C22 refuse pre-flight at the web boundary; C13's scope rows and C14's settings values are proven at the policy/config layer

## Test policy

| Code | Required proofs | Coverage expectation |
| --- | --- | --- |
| Decides, reached across a boundary (hosted gate, budget route, turn/deck/cards refusals, usage fields) | one at the boundary and one at its own layer where the rule lives | the route's status set through the HTTP client; one case per decision row at the module |
| Decides, not reached across a boundary (estimate pricing, ledger scope, settings validation) | one at its own layer | one asserted case per row of its table |
| Docs artifacts (checklist, ADR, env examples) | one exit-code content proof each | every plan-named section asserted present |
| Instrumentation (migration body, entities, repositories) | none of its own | covered by the consumer proofs and the existing `test_migrations.py` upgrade/downgrade walk |

Evidence:

- `web/provider_keys.py` routes: four sibling routes with 401/403/404/422/429 branches -> decides at the boundary; analogue `tests/test_web_provider_keys.py`
- `application/byok.py` (new): budget and ceiling assert over three ledgers -> decides; analogue `tests/test_application_budget.py`
- `application/budget.py` `estimate_micros`: catalog resolution branch -> decides, not directly reachable through a route; analogue `tests/test_application_budget_pricing.py`
- closest analogue for the worker ledger recording: `tests/worker/test_quiz_deck_spend.py` (the settle debit), same shape, proven at the task layer
- closest analogue for the frontend sections: `tests/provider-keys-section.test.tsx` and `tests/answer-usage.test.tsx` (new), following the existing component tests

Cost: 8 new or extended backend test files, 3 new frontend test files. Without the policy-layer rows the ceiling's per-source scope would be proven only by a web test that traverses one source through it.

## Swept

- validation: C5 (extra body fields), C14 (cap values), C20 (budget bounds)
- failure modes: C11 (no house fall-over), C17 (absent usage), C8 (rails under exemption)
- idempotency: ledger upsert-increments (C21) stay single-debit through the existing one-time spend marker; budget PUT twice stores the same row
- authorization: C31, C20; the policy reads only the caller's own ledgers (C13's per-learner scope)
- concurrency: ledger upserts are single-statement `ON CONFLICT DO UPDATE` increments (C21); the deck settle keeps its one-transaction claim
- data lifecycle: account deletion cascades the three new tables (migration FK cascade, exercised by the existing account-delete sensor extended to the new rows in C21's file)
- dependency failure: C12/C22 refuse before any provider call; a ledger read failure propagates like every sibling repository's
- state transitions: budget set -> tripped -> raised (C20, C22, C23); hosted flags off -> on (C1 -> C2)
- observability: n/a - no metrics stack exists; the typed refusal codes and the persisted per-answer usage are the observability this feature adds, and both have sensors (C11, C12, C16)

## Handoff

Size, from `wc -c` on the files each slice reads or writes, divided by four (new files estimated):

- S1 = config 40k + learner_keys 3k + provider_keys route 10k + dependencies 68k + profiles 11k + leak canary 12k + tests ~20k ≈ 164 KB ≈ **41k**
- S2/S3 = budget 10k + errors 15k + conversations 62k + quiz 28k + cards 36k + byok policy ~12k + repositories 90k + config 40k + tests ~45k ≈ 338 KB ≈ **85k**
- S4/S5 backend = entities 55k + ports 65k + migration ~8k + ui_message_stream 12k + web conversations 32k + provider_keys 10k + dependencies 68k + worker tasks 35k + tests ~40k ≈ 325 KB ≈ **81k**
- S4/S5/S6 frontend = provider-keys lib 5k + section 14k + streaming 10k + ask-panel 30k + teach-panel 30k + AccountPanel 20k + messages 2×30k + tests ~25k ≈ 194 KB ≈ **49k**
- S7 docs = ADR ~6k + checklist ~5k + env examples ~20k ≈ **8k**
- Total ≈ **264k**, over the 150k budget. Per owner decision D2, the mechanism is pre-answered **handoff**: sequential batches cut at slice boundaries, one PR each, the next batch starting only after the previous one merges
- **Batch A = S1 + S2 + S3 + the backend half of S4/S5 (207k)** - the engine: hosted gate, exemption, ceiling, ledgers, budget route, usage columns and stream part. Everything stays unreachable for existing installs: the hosted flags default off, and on a self-host the ceiling and budget ledgers stay empty because no call is user-keyed that was not before. Batch A ships the backend contract the frontend consumes
- **Batch B = S4/S5 frontend + S6 + S7 (57k)** - the controls and copy: usage line, badges, disclosure, budget control, ops checklist, ADR, env examples. The Verifier runs scoped to batch A's checks (C1-C18, C20-C23, C31) before PR A, and over every check before PR B
- Mechanism: handoff (D2 pre-answer, recorded 2026-10-02)

**Dispatched:**

- Batch A (this PR): S1, S2, S3 and the backend half of S4/S5 built — C1-C18, C20-C23, C31. Proof commands above were corrected to the built tests' names (C4's hosted-canonical sensor, C5's adapter-host sensor moved to the builder's own test file); C12's claim now says what the web test asserts (no provider call, nothing recorded). Batch B (S4/S5 render, S6, S7) is not built.
