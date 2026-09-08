# Cheaper Intelligence Validation

**Date**: 2026-09-07
**Spec**: `.specs/features/cheaper-intelligence/spec.md`
**Diff range**: `fc1835f3..710408b6` (branch `feat/cheaper-intelligence`, 23 commits: 1 spec, 1 ADR amendment, 18 code, 3 spec bookkeeping)
**Verifier**: independent sub-agent (author ≠ verifier)

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| T1 (planning + ADR-0020 amendment, `752204f8`, `0d7e69cb`) | ✅ Done | Amendment answers all twelve decision inputs; precedes every code commit |
| T2 (taxonomy + pinning, `644f5428`..`f9cf3cb9`) | ✅ Done | - |
| T3 (pricing + registry + router + explain, `a8666a3f`..`fddb6e03`) | ✅ Done | - |
| T4 (cost moves, `73d98a04`..`8100059e`) | ✅ Done | - |
| T5 (eval, `d4aaf021`) | ✅ Done | - |
| T6 (compat adapter + economy profile, `1e4d908e`..`027cc749`) | ✅ Done | - |

---

## Spec-Anchored Acceptance Criteria

Paths relative to repo root; `backend/tests/` abbreviated `b/tests/`.

| AC | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| AMD-01 | Accepted amendment answering the twelve inputs, **before** any routing/fallback commit | `docs/adr/0020-use-anthropic-claude-for-generation.md:166-233` — twelve numbered decisions (primary stays Claude; adapter-with-first-profile; capability-flag degradation; effort = constructor arg; streaming rule; deck pins at `begin_deck`; taxonomy retryability; per-profile catalogs; eval-gated promotion; rails on every profile; embeddings frozen; choice deferred; ADR-0009 restated). Status line `:4` "Accepted; amended 2026-09-07". History: `git log --oneline --reverse fc1835f3..HEAD` → `752204f8` (spec) → `0d7e69cb` (ADR) → `644f5428` (first code commit). **No fallback commit precedes the amendment.** | ✅ PASS |
| TAX-01 | Bound exceeded → Learny `Timeout` (generate 120s, suggest 30s anchors preserved) | `b/tests/infrastructure/test_answering_anthropic_taxonomy.py:120-130` — `pytest.raises(Timeout)`, `__cause__ is error`, both paths (sdk/httpx/builtin timeout ids). Quiz mirror `b/tests/infrastructure/test_quiz_anthropic_taxonomy.py:117,176`. Anchors unchanged: `_GENERATE_TIMEOUT_S = 120.0` and `_SUGGEST_TIMEOUT_S = 30.0` identical at merge-base (`git show fc1835f3:…:70` / `:44`); bounds asserted sent: `b/tests/test_answering_anthropic.py:292` `0 < call["timeout"] <= 180`, `b/tests/test_quiz_anthropic.py:444` `0 < timeout <= 60` | ✅ PASS (nuance: tests bound the constants inequality-style, not exact 120/30) |
| TAX-02 | 429→`RateLimited`; 5xx/overloaded/unreachable→`ProviderUnavailable`; other 4xx→`RequestRejected`, translated inside each adapter | `test_answering_anthropic_taxonomy.py:101-114,120-130` — parametrized 429/500/529/APIConnectionError/400/401 → mapped class; compat adapter `b/tests/infrastructure/test_answering_openai_compat.py:425-447`; quiz batch+suggest `b/tests/infrastructure/test_quiz_anthropic_taxonomy.py:138-159,180-199` | ✅ PASS |
| TAX-03 | Caller-visible envelopes unchanged (`AnswerGenerationFailed` mapping, error payloads exactly as today) | `b/tests/infrastructure/test_answering_routing.py:250-261` — `assert excinfo.value is last` (exhausted chain re-raises the exact last error); `:264-276` — `assert excinfo.value is error` (unrecognized propagates identity-preserved); `b/tests/test_web_conversations.py:1711-1753` — 502 with generic body, question kept (pre-cycle envelope test, green); `b/tests/worker/test_quiz_deck_tasks_taxonomy.py:67-81` — translated errors take the identical retry path (`retry_calls[0]["exc"] is error`) | ✅ PASS |
| TAX-04 | Local adapter failure behavior unchanged (no network, no taxonomy raises) | `app/infrastructure/answering/local.py` untouched by diff (empty `git diff fc1835f3..HEAD --stat`); `app/infrastructure/quiz/local.py` only wraps returns in `SuggestResult(usage=None)`; local suites green: `b/tests/test_quiz_local.py:41-256` (23 tests), `b/tests/test_answering_local.py` in the green offline suite (2002 offline tests) | ✅ PASS |
| PIN-01 | Poll builds the adapter for the provider on the handle, not current settings | `b/tests/worker/test_quiz_deck_pinning.py:93-108` — settings pinned `local`, handle says `anthropic`: `assert factory.requested == ["anthropic"]`; `:111-126` — `requested == ["local"]` (never `None`) | ✅ PASS |
| PIN-02 | Undeclared handle provider → **terminal** failure, operator-actionable, never a foreign poll | `test_quiz_deck_pinning.py:190-216` — `job.status == QuizJobStatus.FAILED`, `job.last_error == "Quiz deck generation provider is no longer configured."`, `bound.retry_calls == []`, `apply_async.assert_not_called()`, log names `"gemini"` + `"does not declare"` | ✅ PASS |
| PIN-03 | Begin carries provider identity through Celery JSON round-trips | `test_quiz_deck_pinning.py:223-247` — `QuizDeckHandle.from_payload(json.loads(json.dumps(payload)))`, `round_tripped.provider == "vendor-a"`, `batch_id == "batch-9"` | ✅ PASS |
| PRICE-01 | USD from the serving profile's catalog, not a global pair | `b/tests/test_application_budget_pricing.py:64-74` — same usage: `economy == 1380`, `premium == 6400` (exact per-catalog arithmetic); through the real request budget `b/tests/test_generation_chain.py:254-279` — `usage_micros(usage, "cheap") == 1_200_000` vs `"primary" == 18_000_000` | ✅ PASS |
| PRICE-02 | Cache fields priced at profile cache prices; absent → input+output only | `test_application_budget_pricing.py:80-89` — `with_cache - without_cache == 800` (exactly the cache terms); `:92-99` — `legacy_shaped == 3000` (pre-cache formula); adapter populates from Anthropic usage `b/tests/test_answering_anthropic.py:433-451,470-489` | ✅ PASS |
| PRICE-03 | Suggest/accept calls debit USD like turn paths, no new integer caps | `b/tests/test_application_cards.py:1945-1970` — ledger row `(580, 0, 0)` (USD only, counters zero); `:1972-1982` failed → no row; `:1984-2000` note suggest `(540, 0, 0)`; `:2012-2030` refresh debits the note's owner (700) | ✅ PASS |
| PRICE-04 | Unknown model/stamp → primary catalog **and** a warning, never silent | `test_application_budget_pricing.py:132-143` — `micros == 6400` (primary arithmetic) AND `len(warnings) == 1` with `"ghost" in message`; registry-level `:201-212` — `resolved is primary` + exactly 1 warning naming stamp and primary | ✅ PASS |
| PRICE-05 | Embedding pricing unchanged (ADR-0019 single house provider) | `app/infrastructure/web/dependencies.py:238-256` `_profile_catalogs` — profile catalogs price generation only (`embed_micros_per_million=0`); no embed call site passes a `profile_id` (all stamp-carrying `usage_micros` calls are generation: `conversations.py:1003`); global catalog wiring unchanged; pre-existing embed tests green (`b/tests/test_application_budget.py:1241`) | ✅ PASS |
| ROUTE-01 | Turn-path adapter = routing adapter over the settings-declared ordered registry with all per-profile fields | `b/tests/test_generation_chain.py:146-162` — `_chain_ids == ["primary", "scout"]` with per-kind adapters; `:561-593` compat profile builds model/base_url/max_tokens/efforts from its declaration; field surface `b/tests/infrastructure/test_provider_profiles.py:63-101` | ✅ PASS |
| ROUTE-02 | Timeout/ProviderUnavailable → next; RateLimited → one same-provider retry then next; RequestRejected → only a different request shape | `b/tests/infrastructure/test_answering_routing.py:155-166` transport fail-over (`profile_id == "fallback"`, `second.calls == 1`); `:169-209` exactly-one retry (`primary.calls == 2`, `second.calls == 0`; per-entry retry budget `:194-209`); `:212-244` rejection skips same-kind sibling **without a call** (`same_kind.calls == 0`), raises when no different kind exists | ✅ PASS |
| ROUTE-03 | Only eligible profiles serve grounded modes; none reachable → honest failure, zero adapter calls | `test_answering_routing.py:473-483` — `pytest.raises(RuntimeError, match="no generation profile is enabled")` + `disabled.calls == 0`; teach `:514-521`; skip-to-enabled `:486-497` | ✅ PASS |
| ROUTE-04 | No fail-over after first delta; errors surface exactly as today after commit | `test_answering_routing.py:369-386` — post-delta outage: seen events `== [AnswerTextDelta]` (exactly one error, **no second `AnswerCompleted`**), `second.stream_calls == 0`; pre-delta fail-over still works `:353-366`; pre-delta stream policy matches buffered `:389-401` | ✅ PASS |
| ROUTE-05 | Missing key env at composition → fail fast | `test_generation_chain.py:165-177` — `pytest.raises(ValueError, match="LEARNY_TEST_PROFILE_KEY")`; `b/tests/infrastructure/test_provider_profiles.py:173-190` (missing name / unset env, message names both) | ✅ PASS |
| ROUTE-06 | No registry → behavior equals today's single-provider config | `test_generation_chain.py:83-113` — default `_chain_ids == ["default"]`, `DeterministicGenerationAdapter`, `chain.model == "local-extractive"`; `:95-113` anthropic legacy seeds Claude adapter; `b/tests/infrastructure/test_provider_profiles.py:202-262` (seed equals today's settings, today's error messages) | ✅ PASS |
| ROUTE-07 | Budget assert, rate limits, kill switch apply before any provider touch — per user | `test_generation_chain.py:433-472` — 4th throttled turn: HTTP 429 and `first.calls + second.calls == 3` (rail fired before either entry); budget-before-provider `b/tests/test_application_budget.py:338-355` (`generation.calls == 0`); kill switch pre-existing (`:1185`) green | ✅ PASS |
| ROUTE-08 | Outcome identifies the serving profile/model | `test_answering_routing.py:123-134` + `:283-297` — `answer.profile_id` names whichever entry served (primary/middle/tail); spend maps to it: `b/tests/test_application_budget.py:426-465` — `row.usd_micros == 580` from a stamped answer | ✅ PASS |
| EVAL-01 | JSONL records serving profile id + model; thresholds unchanged (faithfulness ≥ 0.90, relevancy ≥ 3.1, citation_valid 12/12) | `b/tests/test_eval_judge.py:171-190` — schema contains `"generation_profile"`; `:193-226` — `line["generation_profile"] == "cheap-candidate"` while the declared registry names a different profile (never re-read from settings); thresholds `app/eval/judge.py:59-60` unchanged (`0.90`/`3.1`); gate flips below threshold `test_eval_judge.py:358-380`; citation validity asserted `:314-318` | ✅ PASS |
| EVAL-02 | Candidate override is env/workflow-input-driven; production defaults untouched | `b/tests/test_eval_workflow.py:49-55` — dispatch input string, optional, default `""`; `:57-65` — `env["LEARNY_GENERATION_PROFILES"] == "${{ inputs.generation_profiles || '[]' }}"` (empty → legacy default byte-for-byte); `:67-73` — no change to the secret-skip gate | ✅ PASS |
| EVAL-03 | No green nightly → Ask-ineligible in shipped config; incumbent grandfathered | `b/tests/test_generation_chain.py:486-519` — parses `backend/.env.example` example registry: economy `ask_enabled is False`, `teach_enabled is False`; named explain profile `ask_enabled is True`; `:478-483` — `Settings(_env_file=None).generation_profiles == []` (ships undeclared/non-default); `:522-558` — a chain built from exactly that declaration refuses ask and teach with zero adapter calls | ✅ PASS |
| COST-01 | Effort from the serving profile's per-mode value; no port effort argument; shipped default `medium` | `b/tests/test_answering_anthropic.py:359-367` — buffered+streamed: answer `{"effort": "low"}`, teach `{"effort": "high"}`; `:384-399` — no effort argument → `{"effort": "medium"}` both modes; `b/tests/test_generation_chain.py:116-140` — profile values reach the constructor; `backend/app/domain/ports.py` diff — GenerationPort untouched | ✅ PASS |
| COST-02 | Teach: stable section documents before the cache breakpoint; playbook contract unchanged | `b/tests/test_answering_anthropic.py:1306-1334` — system prompt breakpoint-free, documents lead, breakpoint on the LAST document, volatile input after; `:1337-1354` empty history; `:1358-1373` no-documents fallback to playbook breakpoint; `:1378-1408` prefix byte-stable turn 1→2; `:1456` playbook text byte-unchanged | ✅ PASS |
| COST-03 | Cache-read/creation counts captured (log + metering) | `test_answering_anthropic.py:433-451` buffered usage carries cache counts; `:470-489` streamed completed answer carries them; `:491-505` log line names both counts | ✅ PASS |
| COST-04 | Explain-origin ask turn → designated cheap grounded profile; transport error → falls back to Ask primary | Selection: `b/tests/test_web_conversations.py:1860-1891` — marked turn `body["model"] == "explain-chain"`, `explain.calls == 1`, `primary.calls == 0`; `:1893-1917` plain turn → primary; `:1919-1945` unknown origin → 422 with zero chain calls; `:1947-1975` stream route; frontend `frontend/tests/streaming.test.ts:150-178` (body `{message, mode, origin}` vs exactly `{message, mode}`), `frontend/tests/ask-panel.test.tsx` (Explain verb marks; panel ask sends nothing) | ✅ PASS — ⚠️ the transport-error fallback leg is covered only by composition (explain-chain ordering `test_generation_chain.py:190-199` + router transport fail-over `test_answering_routing.py:155-166`); no single test drives a failing explain head into the Ask primary |
| COST-05 | Explain served from cheap profile with citations/grounding identical to any ask turn | `app/application/grounding.py` untouched by the cycle diff (AD-027 backstop intact); grounding suites green (`test_answering_anthropic.py:950-979` span verification, `test_answering_openai_compat.py:312-325` intersection); explain turn persists as a normal ANSWERED ask turn with the full view (`test_web_conversations.py:1877-1891`) | ✅ PASS |
| ECON-01 | `openai-compatible` profile → new Learny-owned adapter implementing `GenerationPort`; port gains no members | `b/tests/infrastructure/test_answering_openai_compat.py:272-278` — adapter is a `GenerationPort`, reports model without a call; `backend/app/domain/ports.py` diff touches only the quiz suggest return type | ✅ PASS |
| ECON-02 | Requests prompt-id citations (`[^n]` into supplied documents); grounding intersection verifies; degraded grounding declared | `test_answering_openai_compat.py:226-249` (numbered docs + marker convention in the frozen system prompt); `:283-301` markers parse to chunk ids, first-occurrence order, out-of-range names no chunk; `:312-325` grounding keeps only cited chunks; declaration `b/tests/test_generation_chain.py:509-516` (`grounding == "prompt-cited"`, ask/teach disabled) | ✅ PASS |
| ECON-03 | Usage maps input/output (+cache when host reports); no usage → debit 0 | `test_answering_openai_compat.py:352-364` — prompt/completion/cached mapped; `:365-372` no cache detail → input+output; `:374-380` absent usage → `None` → debit 0; stream usage `:635-645` | ✅ PASS |
| ECON-04 | Economy profile ships **inactive** (Ask-ineligible, non-default) with price pair + key env name in config | `test_generation_chain.py:478-483` — nothing shipped declared; `:486-519` — `.env.example` example: `economy-glm` kind `openai-compatible`, `ask_enabled is False`, `teach_enabled is False`, prices 0.22/0.75, `api_key_env == "LEARNY_FIREWORKS_API_KEY"`, `base_url != ""`, commented out; `:522-558` — chain from that declaration refuses ask/teach with `adapter._client is None` | ✅ PASS |
| ECON-05 | Inexpressible effort → ignored (no error, no port change) | `test_answering_openai_compat.py:386-423` — `low`/`high` accepted; captured request body contains no effort/thinking key, buffered and streamed | ✅ PASS |
| ECON-06 | CI exercises the adapter via stubbed transport only; offline suite network-free | `test_answering_openai_compat.py:73+` — fake client, no socket; `:704` — module imports no SDK at module level (lazy-import mirror); the 2002-test offline run is green with no network | ✅ PASS |

**Status**: ✅ All 35 ACs covered with spec-matched assertions; 2 nuances flagged (TAX-01 bound asserted inequality-style, constants verified unchanged at 120.0/30.0; COST-04 fallback leg by composition).

**Searches run for absence** (all empty): `grep -rn "explain" backend/tests/infrastructure/test_answering_routing.py` (no explain-chain fail-over test), `grep -n "AnswerGenerationFailed|502|envelope" backend/tests/test_web_conversations.py` (envelope evidence found at :1711), `grep -rn "KIND_EMBED" backend/app` (embed pricing site), threshold grep in `test_eval_judge.py`.

---

## Discrimination Sensor

Expanded tier (money math + routing honesty + provider pinning). All mutants injected one at a time in a detached scratch worktree (`git worktree add --detach /tmp/verifier-mut 710408b6`); real working tree never touched; each mutant reverted immediately (`git restore`) and the worktree removed after. Baseline subsets green before injection (87 passed).

| # | Target | Fault | Test subset run | Result |
| --- | --- | --- | --- | --- |
| 1 | `answering/routing.py` `_eligible_entries` | Ignore `ask_enabled` — return the whole chain for ask | `tests/infrastructure/test_answering_routing.py` | ✅ Killed (2 failed: ask-disabled chain served instead of honest failure) |
| 2 | `answering/routing.py` `generate_stream` commit rule | Commit only on `AnswerCompleted` — fail-over legal after first delta | `tests/infrastructure/test_answering_routing.py` | ✅ Killed (`test_a_post_delta_failure_propagates_once_with_no_second_completed`) |
| 3 | `answering/routing.py` `_next_index` RateLimited | Unlimited same-entry retries (drop the `retried` budget) | `tests/infrastructure/test_answering_routing.py` | ✅ Killed (2 failed, incl. buffered retry-budget test) |
| 4 | `application/budget.py` `usage_micros` unknown-stamp fallback | Remove the PRICE-04 warning (silent primary pricing) | `tests/test_application_budget_pricing.py` | ✅ Killed (`test_an_unknown_stamp_falls_back_to_the_primary_catalog_with_a_warning`) |
| 5 | `worker/tasks.py` `_poll_quiz_deck_body` | Ignore `handle.provider`, fall back to settings | `tests/worker/test_quiz_deck_pinning.py` + `tests/infrastructure/test_quiz_factory_pinning.py` | ✅ Killed (3 failed, incl. terminal-failure test) |
| 6 | `answering/openai_compat.py` `_parse_answer` sentinel | Sentinel reply maps to `found=True` | `tests/infrastructure/test_answering_openai_compat.py` | ✅ Killed (3 failed incl. not-found outcome and stream sentinel tests) |
| 7 | `answering/anthropic.py` `_effort_for` | Swap per-mode effort (ask↔teach) | `tests/test_answering_anthropic.py -k effort` | ✅ Killed (3 failed incl. per-mode request test) |
| 8 | `application/budget.py` `usage_micros` cache terms | Drop cache read/creation from the debit (input+output only) | `tests/test_application_budget_pricing.py` + cache tests | ✅ Killed (5 failed incl. cache-priced-debit delta test) |

**Sensor depth**: expanded (8 mutants — cycle carries money math, routing honesty, provider pinning)
**Result**: 8/8 killed — PASS ✅

---

## Edge Cases (spec §Edge Cases)

- [x] Misconfigured registry (duplicate ids, empty id, unknown kind, missing key env) fails fast with actionable messages — `test_provider_profiles.py:144-190`
- [x] `local`-only chain is a pass-through — `test_generation_chain.py:83-92`, offline suite byte-identical
- [x] Post-delta stream error surfaces exactly as today, no rewind, no second `AnswerCompleted` — `test_answering_routing.py:369-386`
- [x] Mid-flight provider removal → terminal per PIN-02 — `test_quiz_deck_pinning.py:190-216`
- [x] Two profiles naming one model disambiguated by the router's stamp — `test_application_budget_pricing.py:185-192`, `test_answering_routing.py:283-297`
- [x] Profile flip between stream-open and commit — adapters built per chain at composition (cached accessors, `test_generation_chain.py:224-247`)
- [x] Non-grounded profile refused for `answer` mode despite being "cheaper" — `test_answering_routing.py:473-483`, `test_generation_chain.py:522-558`

---

## Gate Check

- **Gate command**: `make lint` (ruff check + ruff format --check + `tsc --noEmit` + boundaries fitness), then backend `uv run pytest`, frontend `npm test`
- **Lint/fitness**: green ("All checks passed!", "313 files already formatted", "architecture boundaries clean")
- **Backend**: `LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test` (services up via `make infra`): **2882 passed / 12 skipped / 1 failed** in 226s
  - The 1 failure is `tests/test_eval_retrieval_metrics.py::TestDeterministicRetrievalMetrics::test_metrics_meet_thresholds` — the flagged KNOWN PRE-EXISTING failure. Reproduced OUTSIDE the cycle at merge-base `fc1835f3` in a scratch worktree: without the owner's `backend/.env` → **1 passed**; with the owner's `backend/.env` copied in → **FAILED** identically (recall@1 0.857 < 0.9, mrr 0.917 < 0.93). Not a cycle defect. With `.env` absent the branch is at the expected clean 2883/12.
- **Frontend**: **899 passed (75 files)** — matches the expected clean baseline exactly
- **Test count before feature**: backend 2668 passed / 12 skipped (DB up), frontend 897
- **Test count after feature**: backend 2883 (2882 + 1 pre-existing env-dependent failure) / 12 skipped, frontend 899
- **Delta**: +215 backend, +2 frontend — no deletions, no weakened assertions found (spot-checked TAX-03 envelope tests retain exact-identity assertions)
- **Skipped tests**: 12, all pre-existing live-provider smokes (`LEARNY_ANTHROPIC_API_KEY`/`LEARNY_OPENAI_API_KEY` unset — CI stays offline) and one committed-snapshot invariant skip; all justified
- **Failures**: only the pre-existing, env-dependent retrieval-metrics test (see above)

---

## Code Quality

| Principle | Status |
| --- | --- |
| Minimum code / no scope creep | ✅ Out-of-scope items (BYO keys, model-picker UI, embedding swap, semantic cache, auto-promotion) all absent |
| Surgical changes | ✅ Grounding, local adapters, GenerationPort untouched; legacy settings kept as seed |
| Matches existing patterns | ✅ Adapter/factory/composition-root conventions followed; redaction culture preserved |
| Port frozen | ✅ GenerationPort gains no members (effort stays constructor arg; profile metadata in settings) |
| Spec-anchored outcome check | ✅ 35/35 asserted against spec values (2 nuances noted above) |
| Every test maps to an AC/edge case | ✅ Test module docstrings cite AC ids; spot-check of routing + pricing suites confirms non-shallow assertions (exact arithmetic, exact error identity, call-count sensors) |
| Documented guidelines | ✅ `.agents/skills/tlc-spec-driven` verification vocabulary; `CLAUDE.md` gate vocabulary |

---

## Requirement Traceability Update

| Requirement | Previous Status | New Status |
| --- | --- | --- |
| AMD-01 | Pending | ✅ Verified |
| TAX-01..04 | Pending | ✅ Verified |
| PIN-01..03 | Pending | ✅ Verified |
| PRICE-01..05 | Pending | ✅ Verified |
| ROUTE-01..08 | Pending | ✅ Verified |
| EVAL-01..03 | Pending | ✅ Verified |
| COST-01..05 | Pending | ✅ Verified (COST-04 fallback leg by composition — see gaps) |
| ECON-01..06 | Pending | ✅ Verified |

---

## Summary

**Overall**: ✅ Ready — **PASS**

**Spec-anchored check**: 35/35 ACs matched spec outcome | 2 minor nuances flagged (no fix required to pass; listed below)
**Sensor**: 8/8 mutations killed
**Gate**: lint+fitness green; backend 2882 passed / 12 skipped / 1 known pre-existing env-dependent failure (proven pre-existing at merge-base `fc1835f3`); frontend 899 passed

**What works**: the full prerequisite order (taxonomy → pinning → pricing → registry/router → eval gate → cost moves → adapter/profile); envelopes byte-compatible (TAX-03 exact-identity assertions); streaming commit rule and honest-failure zero-call guarantees under mutation; economy profile provably inert; ADR amendment precedes all routing commits.

**Issues found / ranked gaps** (none blocking):

1. **COST-04 transport-error fallback leg untested as a composition** — the explain chain's fail-over to the Ask primary on a transport-class error is only implied by composition (ordering test `test_generation_chain.py:190` + router fail-over `test_answering_routing.py:155`). Suggested fix: one test driving a `Timeout`-scripted explain head over an ask turn and asserting the primary served with the explain origin. — Priority: Minor
2. **TAX-01 bound assertions are inequality-style** (`0 < timeout <= 180`, `<= 60`) rather than exact 120/30; the constants are verified unchanged from merge-base, but an exact-pin would guard against silent bound drift. — Priority: Cosmetic

**Next steps**: none required to merge; optional follow-ups above can ride the next cycle's task list.
