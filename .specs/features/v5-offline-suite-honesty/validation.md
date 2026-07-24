# Validation — v5-offline-suite-honesty (RFC-005 Cycle A)

**Verdict: PASS** (test-harness only). The one non-blocking gap the sensor found (M3) was closed post-verification — see the Orchestrator addendum at the end.

Independent verification — author ≠ verifier. Coverage re-derived from the spec, evidence-or-zero.

- Diff range: `dccff02164d04d19026858ba6968938231b39f2b` .. `b6ab43199c4ec5de23841964b2c61530638b9955` (`main` .. `feat/offline-suite-honesty`)
- Cycle diff surface (non-planning): `backend/tests/conftest.py`, `backend/tests/test_offline_provider_pin.py` (new, 82 lines), `frontend/tests/teach-panel.test.tsx`. No product/schema/endpoint change — scope respected.
- Leak precondition confirmed real: `backend/.env` sets `LEARNY_EMBEDDING_PROVIDER=openai` and `LEARNY_GENERATION_PROVIDER=anthropic` (with keys). All backend runs below were **bare** (no `LEARNY_*_PROVIDER` prefix; `env | grep LEARNY_` empty), so the leak is actually exercised.

## Environment limitations

- No local Postgres (`:5432` refused) → `requires_db` tests SKIP. Expected, not a failure. Full offline suite = **1056 passed / 610 skipped**, matching the stated baseline.
- The live OpenAI/Anthropic arms are additionally `LEARNY_OPENAI_API_KEY` / DB-gated and skip offline.

## Per-AC evidence

| AC | Spec outcome | Evidence (bare invocation) | Result |
|----|--------------|----------------------------|--------|
| AC-1 (FR-1,FR-3) | Under a real-`.env` ambient, resolving generation+embedding adapters yields deterministic `local`; no real client built | `pytest tests/test_offline_provider_pin.py` — `test_offline_suite_pins_local_providers` asserts `os.environ[...]=="local"` **and** `settings.*_provider=="local"`; `test_default_factories_are_deterministic` asserts all four factories (`build_answer/teaching/quiz/embedding_adapter`) return `Deterministic*` types | PASS |
| AC-2 (FR-2) | Explicit `anthropic`/`openai` override still reaches the real factory branch | `test_explicit_generation_override_reaches_real_branch` → `Anthropic{Answer,Teaching,Quiz}Adapter`; `test_explicit_embedding_override_reaches_real_branch` → `OpenAIEmbeddingAdapter` (both via per-test `monkeypatch.setenv`, the same mechanism real tests use) | PASS |
| AC-3 (FR-4) | A representative previously-prefix-dependent test resolves deterministic adapter under bare run, asserted at the factory/settings seam so it runs offline | `test_default_factories_are_deterministic` resolves `DeterministicEmbeddingAdapter` bare at the `build_embedding_adapter(get_settings())` seam (no `requires_db`) | PASS |
| AC-4 (FR-5) | Provider-default assertion tests in `test_config.py` pass unchanged (defaults `local`) | `pytest tests/test_config.py` green; `test_embedding_settings_defaults`/`test_generation_settings_defaults` still assert `local`; their `openai`/`anthropic` override tests (lines 26/…) unaffected — file unmodified in the cycle | PASS |
| AC-5 (FR-1) | Full offline suite passes bare, ≥ prefixed baseline, zero real provider calls | `pytest -q` (bare) → **1056 passed, 610 skipped, exit 0** in 32.7s | PASS |
| AC-6 (FR-6) | `TeachPanel resume` deterministic; fix awaits the render the `Resume` click depends on; resumed-history assertion strength unchanged; suite green | `npx vitest run tests/teach-panel.test.tsx` → 11/11 passed (3/3 repeat runs); `npx tsc --noEmit` exit 0. Await-gate verified by inspection (below) | PASS |

Aggregate green baselines (bare): `test_offline_provider_pin.py` + `test_config.py` = 18 passed; full suite 1056/610; frontend teach-panel 11/11; `tsc` clean; `ruff check tests/conftest.py tests/test_offline_provider_pin.py` = "All checks passed!".

## Discrimination sensor (mutants injected in scratch, then reverted)

| # | Behavior-level fault | Expectation | Outcome |
|---|----------------------|-------------|---------|
| M1 | Neuter the pin: replace `monkeypatch.setenv(var,"local")` with `pass` | pin tests must fail (proves the pin is load-bearing given `.env` leaks) | **KILLED** — `test_offline_suite_pins_local_providers` (`os.environ` = `None`) and `test_default_factories_are_deterministic` (factory returned real `AnthropicAnswerAdapter`) both fail. Confirms the real leak. |
| M2 | Wrong pin value `"local"` → `"anthropic"` | default-factory determinism test must fail | **KILLED** — `test_default_factories_are_deterministic` (real `AnthropicAnswerAdapter`) + `test_offline_suite_pins_local_providers` (env != `"local"`) fail. |
| M3 | Weaken guard: unconditional `setenv` (drop `if var not in os.environ`) | explicit-override tests / guard-protected tests may fail | **SURVIVED (offline)** — full suite still 1056/610. Honest gap, not a defect: the per-test override tests (`test_explicit_*_override_reaches_real_branch`) call `monkeypatch.setenv` *after* the autouse fixture, so they win regardless of the guard. The only case the guard actually protects — the class-scoped live `openai` embedding fixture in `test_eval_retrieval_metrics.py` (sets `openai` before the function-scoped pin) — is DB-gated **and** `LEARNY_OPENAI_API_KEY`-gated, so it skips offline and cannot exercise the guard here. Guard is still correct behavior for the live-eval path; it is simply uncovered by an offline-runnable discriminating test. |
| M4 | Revert frontend await-gate to sync `getByText`/`getByRole` | test may race | **SURVIVED (non-deterministic flake, as anticipated)** — 11/11 passed over 3 runs; vitest/jsdom does not reproduce the intermittent race. Verified by **inspection** instead (below). |

Tally: **2 killed / 2 survived** (M3 = offline-coverage gap, not a correctness miss; M4 = flake not reproducible in-harness, covered by inspection).

### M4 inspection — the frontend fix is a genuine await-gate (FR-6 / invariant 3)

The `Resume` button and the `/2 turns/` count are rendered from the async `GET /api/sources/s1/teaching-sessions` fetch, on a later render pass than the static "Previous sessions" heading that `findByText` already awaited. The original code queried both with synchronous `getBy*`, which throws immediately if the session row has not rendered yet — the race. The fix:

- `fireEvent.click(await screen.findByRole("button", { name: "Resume" }, …))` — the click is now **gated on the awaited existence of the exact button it depends on** (retries until present), which is precisely the render the interaction depends on. This is the substantive synchronization change, matching FR-6's "the `Resume` interaction is gated on the awaited render it depends on."
- It is **not** a timeout bump of an existing `waitFor`, **not** a retry config (`vitest.config`/setup contain no `retry`/`testTimeout`), **not** a blanket `waitFor` around unrelated assertions (targeted `findByRole`/`findByText` on the specific elements), and **not** a weakened assertion — the downstream resumed-history assertions (`"It is about early computing."`, `"What is this about?"`, `Citation: Chapter 1 › Intro`, the `not-found` callout, oldest-first DOM order) are byte-for-byte unchanged. The `{ timeout: 5000 }` is headroom on the async query, not a tolerance loosening of a prior gate.

## Invariant check

1. **Offline suite network-free by default** — HOLDS. Bare full suite green with no provider prefix; M1 proves that without the pin the default path builds the real `AnthropicAnswerAdapter` (i.e. the pin is what enforces the invariant), and `test_default_factories_are_deterministic` asserts all four factories return `Deterministic*` — no real client constructed in the default path.
2. **Pin never hides real-provider tests; explicit overrides win** — HOLDS. `test_explicit_*_override_reaches_real_branch` reach `Anthropic*`/`OpenAI*` branches under the pin; `test_config.py` `openai`/`anthropic` override assertions still pass; the guard only ever sets *unset* vars. (Coverage nuance: the guard-vs-unconditional distinction is not offline-discriminated — see M3 — but the invariant itself is satisfied and tested.)
3. **Frontend deflake is a real synchronization fix, not a tolerance/timeout change** — HOLDS. See M4 inspection.

## Ruff

`.venv/bin/ruff check backend/tests/conftest.py backend/tests/test_offline_provider_pin.py` → **All checks passed!**

## Non-blocking follow-up (optional)

- M3 gap: no offline-runnable test discriminates the `if var not in os.environ` guard from an unconditional `setenv`. Its only offline-relevant guard consumer (the class-scoped `openai` embedding fixture) is DB+key-gated. Optionally add a pure-offline test that pre-sets `os.environ["LEARNY_EMBEDDING_PROVIDER"]="openai"` before the fixture (e.g. a class-scoped monkeypatch) and asserts the pin does **not** clobber it, to lock the guard against regression. Not required for AC/FR/invariant satisfaction.

## Working tree

Clean of all scratch mutations after verification (`git status --porcelain` empty for tracked files); all four mutants reverted via `git checkout`. Only this `validation.md` is left for the orchestrator.

## Orchestrator addendum — M3 closed (post-verification)

The M3 offline-coverage gap was closed by a follow-up test committed in `b27ba08` (`test(backend): cover the provider-pin override guard`). Added `TestPinDoesNotClobberPresetProvider.test_preset_provider_survives_the_pin` to `backend/tests/test_offline_provider_pin.py`: a **class-scoped** autouse fixture presets `LEARNY_EMBEDDING_PROVIDER=openai` *before* the function-scoped pin runs (reproducing the live `openai` fixture's ordering, fully offline), and the test asserts the pin leaves it `openai`.

Empirically confirmed to kill the M3 mutant: with the guard weakened to an unconditional `setenv` (`if var not in os.environ:` → `if True:`), the new test **fails** (`openai` → `local`); reverted; with the guard restored it passes. Full offline suite re-run bare after the addition: **1057 passed / 610 skipped**, ruff clean.

Revised sensor tally: **3 killed / 1 survived** — M4 remains covered by inspection (frontend flake is not deterministically reproducible in jsdom; the fix is a genuine await-gate, unchanged assertions).
