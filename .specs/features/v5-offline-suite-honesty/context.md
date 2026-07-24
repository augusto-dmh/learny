# Context — v5-offline-suite-honesty (decisions)

No user-facing gray areas: this is a test-harness cycle with clear-cut mechanics. Decisions auto-selected (options with why/why-not recorded for audit).

## D-1 (AD-168) — Provider pin mechanism

**Decision:** A **function-scoped autouse** fixture in `backend/tests/conftest.py` that sets `LEARNY_GENERATION_PROVIDER` and `LEARNY_EMBEDDING_PROVIDER` to `local` **only if the var is absent from `os.environ`**, then clears the `get_settings` LRU cache (setup + teardown).

**Why this works:** the `backend/.env` leak is *file-based* — pydantic reads the `.env` file, but those values are **not** in `os.environ`. Setting `os.environ[...]=local` therefore wins over `.env` (env > env_file in pydantic-settings) and defeats the leak. It is **inert in CI** (no `.env` present; the vars are simply set to their existing `local` default) and **inert in nightly eval** (providers set explicitly there). The "only if absent" guard means an explicit choice always wins — a shell prefix (`LEARNY_EMBEDDING_PROVIDER=openai pytest`), a per-test `monkeypatch.setenv`, or the class-scoped `openai_source` fixture in `test_eval_retrieval_metrics.py` (which sets `openai` before the function-scoped pin runs) all survive.

**Options considered:**
- *Function-scoped autouse, only-if-absent (chosen).* Why: defeats the leak, yields to every explicit override, matches the existing per-fixture `get_settings.cache_clear()` convention. Why-not: runs on every test (negligible cost).
- *Session-scoped autouse.* Why: pins once before any adapter is built/cached. Why-not: risks clobbering the class-scoped live `openai` embedding fixture and complicates per-test override semantics — rejected.
- *Unconditional pin (always force local).* Why: simplest. Why-not: breaks the live `openai` eval embedding test and any deliberate shell override (violates FR-2) — rejected.
- *Construct `Settings(_env_file=None)` everywhere / change the loader.* Why: removes the leak at the source. Why-not: broad product-code change, out of a test-harness cycle's scope — rejected.

## D-2 (AD-169) — Frontend deflake

**Decision:** In the `TeachPanel resume` test, **await** the async-loaded resume-list content before asserting/interacting: convert the sync `getByText(/2 turns/)` and `getByRole("button", {name:"Resume"})` to awaited `findBy*` before the click. Assertions unchanged in strength.

**Why:** the click fired synchronously after only the "Previous sessions" heading was awaited, so the `Resume` button could be unmounted. Await-gating the interaction target is the genuine synchronization fix — the same pattern used by sibling deflake `c0aa7c4` ("await the confirm-dialog buttons"). **Not** a timeout bump, retry config, or weakened assertion (rejected — they mask the race without fixing it, violating invariant 3).
