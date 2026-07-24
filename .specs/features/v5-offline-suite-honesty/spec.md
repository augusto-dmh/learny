# Spec — v5-offline-suite-honesty (RFC-005 Cycle A)

## Problem

The deterministic offline test suite is only network-free by accident of invocation. `backend/app/core/config.py` loads `backend/.env`, whose real `LEARNY_GENERATION_PROVIDER=anthropic` / `LEARNY_EMBEDDING_PROVIDER=openai` values (with real keys) override the code's `local` defaults. Any test that builds an adapter via `get_settings()` therefore gets the real provider unless `pytest` is manually prefixed with `LEARNY_GENERATION_PROVIDER=local LEARNY_EMBEDDING_PROVIDER=local`. Separately, the frontend `teach-panel.test.tsx` `TeachPanel resume` test carries a pre-existing intermittent race (a `Resume`-button click fired before the required render settles).

Scope: test-harness only. **No product code, no schema, no migration, no endpoint, no frontend product change.**

## Requirements

- **FR-1** The offline backend suite selects the network-free `local` generation, embedding, and quiz/teaching adapters **by default** — a bare `pytest` (no `LEARNY_*_PROVIDER` prefix) yields deterministic adapters regardless of ambient `backend/.env` provider values.
- **FR-2** The default-local pin **must not mask** tests that deliberately assert real-provider configuration or exercise the `anthropic`/`openai` factory branches: a per-test provider override still reaches the real branch.
- **FR-3** In the default offline path, **no real network provider client is constructed** — the factories return the `Deterministic*`/`local` adapters, never the OpenAI/Anthropic client.
- **FR-4** The DB-gated tests that previously required the manual `LEARNY_*_PROVIDER=local` prefix pass with a **bare invocation** (given a test DB), with no prefix.
- **FR-5** Tests asserting the **default** provider values (e.g. `test_config.py` provider-default tests) continue to pass unchanged.
- **FR-6** The frontend `TeachPanel resume` test is deflaked by a **genuine await-gating fix** rooted in the actual race (the `Resume` interaction is gated on the awaited render it depends on) — **not** a timeout bump, retry config, `waitFor` blanket, or a weakened assertion.

## Acceptance Criteria

- **AC-1 (FR-1, FR-3)** With ambient env simulating a real `.env` (`LEARNY_GENERATION_PROVIDER=anthropic`, `LEARNY_EMBEDDING_PROVIDER=openai`), a test resolving the generation and embedding adapters in the default suite context receives the deterministic `local` adapters (asserted by adapter type/identity), and no real provider client is instantiated.
- **AC-2 (FR-2)** A test that explicitly overrides the provider to `anthropic`/`openai` (via the same mechanism real tests use) still resolves the real factory branch — the default-local pin yields to explicit overrides.
- **AC-3 (FR-4)** At least one representative previously-prefix-dependent test (e.g. an embedding leak test) resolves the deterministic embedding adapter under a bare invocation — demonstrated without `requires_db` if possible, else asserted at the factory/settings seam so it runs offline.
- **AC-4 (FR-5)** The provider-default assertion tests in `test_config.py` pass unchanged (defaults remain `local`).
- **AC-5 (FR-1)** The full offline backend suite passes with a bare `pytest` (no provider env prefix), at the same or greater pass count than today's prefixed baseline, with zero real provider calls.
- **AC-6 (FR-6)** The `TeachPanel resume` test passes deterministically; the fix awaits the render the `Resume` click depends on, and the assertion on resumed cited history is unchanged in strength. Frontend suite green.

## Out of Scope

Product/behavior code; new providers; schema/migrations/endpoints; frontend product changes; broad rework of the settings loader; any change to what the real adapters do.

## Invariants (must hold)

1. Offline suite is network-free by default and cannot make real provider calls.
2. The pin never hides a test that asserts real-provider behavior — explicit overrides win.
3. The frontend deflake is a real synchronization fix, not a tolerance/timeout change.
