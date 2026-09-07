# Cheaper Intelligence Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user — do not proceed without it.**

---

**Design**: `.specs/features/cheaper-intelligence/design.md`
**Context / ADs**: `.specs/features/cheaper-intelligence/context.md`, STATE.md AD-334..AD-345
**Status**: In Progress

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec — confirm before Execute. Guidelines found: `Makefile` (canonical verification vocabulary), `backend/scripts/check_boundaries.py` (fitness/architecture gate), repo test conventions (`backend/tests/`, `frontend/app/**/*.test.{ts,tsx}`).

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
|---|---|---|---|---|
| Infrastructure adapters (taxonomy, router, compat) | unit (stubbed transport) | All branches; 1:1 to spec ACs; every error class + streaming rule path | `backend/tests/infrastructure/` | `cd backend && uv run pytest tests/infrastructure -q` |
| Settings / registry parsing | unit | Validation branches: dup ids, unknown kind, missing key env, legacy seed equivalence | `backend/tests/` (config/settings modules) | `cd backend && uv run pytest tests/ -q -k "config or settings or profiles"` |
| Application budget / pricing / debit sites | unit + integration | All branches; 1:1 to PRICE-* ACs; cache pricing + fallback-warning + suggest debit | `backend/tests/application/` | `cd backend && uv run pytest tests/application -q` |
| Worker deck tasks (provider pinning) | unit | Poll uses handle provider; undeclared provider → terminal; redelivery idempotency intact | `backend/tests/worker/` | `cd backend && uv run pytest tests/worker -q` |
| Eval judge JSONL | unit | Profile fields recorded; gate predicate unchanged | `backend/tests/eval/` or per repo layout | `cd backend && uv run pytest -q -k judge` |
| Web schema / ask origin | integration | Origin accepted/absent/rejected; explain chain selection per origin | `backend/tests/infrastructure/web/` | `cd backend && uv run pytest -q -k "ask or origin"` |
| Frontend origin marker | unit (vitest) | Popover Explain path sends origin; other paths do not | `frontend/app/**/*.test.*` | `cd frontend && npm test` |
| Entities / config shape | none | Build gate only (defaults verified via the unit suites above) | — | build gate only |

**Baselines (must grow, never shrink):** backend 2660 passed / 12 skipped; frontend 897 passed.

## Parallelism Assessment

> Generated from codebase — confirm before Execute.

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
|---|---|---|---|
| Backend unit (stubbed transport, no DB) | Yes | In-memory fakes; no shared state | existing adapter/service tests run under plain `pytest` |
| Backend integration (DB touch) | Mixed | Per-test transactions/fixtures; shared engine — keep DB-touching tasks sequential within a phase | repo fixtures pattern |
| Frontend vitest | Yes | jsdom per test file | existing `npm test` |

Phase workers run sequentially anyway (one worker per phase); within a phase, DB-touching tasks run in listed order.

## Gate Check Commands

> Generated from codebase — confirm before Execute.

| Gate Level | When to Use | Command |
|---|---|---|
| Quick (module) | After each task commit | `cd backend && uv run pytest <affected test paths> -q` (+ `uv run ruff check app tests && uv run ruff format --check app tests`) |
| Full suite | Phase boundary | `make lint` and `make test` from repo root (backend + frontend + fitness) |
| Build/fitness | Config/entity-only tasks | `make fitness` (+ `make lint-backend`) |

---

## Execution Plan

### Phase 0: ADR amendment (doc chore, own unit)

```
T1
```

### Phase 1: Error taxonomy + quiz provider pinning

```
T2 → T3 → T4 → T5
```

### Phase 2: Per-profile pricing + honest metering

```
T6 → T7 → T8 → T9
```

### Phase 3: Registry + routing adapter + explain origin

```
T10 → T11 → T12 → T13 → T14
```

### Phase 4: Cost moves + eval mechanics

```
T15 → T16 → T17
```

### Phase 5: OpenAI-compatible adapter + economy profile

```
T18 → T19 → T20
```

---

## Task Breakdown

### T1: ADR-0020 amendment (doc)

**What**: Add the accepted amendment section to `docs/adr/0020-*.md` answering the twelve decision inputs from `docs/research/2026-09-07/provider-adapter-architecture.md` §4; status line notes the amendment date; no code changes.
**Where**: `docs/adr/0020-anthropic-claude-generation.md` (exact name per `docs/adr/`)
**Depends on**: None
**Reuses**: ADR house style (other files in `docs/adr/`)
**Requirement**: AMD-01

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] All twelve answers present and consistent with AD-334..AD-345
- [ ] Status shows amendment accepted 2026-09-07
- [ ] `make fitness` green (docs-only, but run it)

**Tests**: none (doc) · **Gate**: `make fitness`

---

### T2: Provider error taxonomy types

**What**: New `backend/app/infrastructure/providers/` package with `errors.py` defining `ProviderError`, `Timeout`, `RateLimited`, `ProviderUnavailable`, `RequestRejected` (stdlib-only).
**Where**: `backend/app/infrastructure/providers/errors.py` (+ package `__init__.py`)
**Depends on**: T1 (amendment precedes routing work; taxonomy itself is prerequisite infrastructure)
**Reuses**: exception style of `backend/app/application/errors.py`
**Requirement**: TAX-01..04 (types only; translation lands in T3/T4)

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Types exported from the package; docstrings state the retryability contract (AD-337)
- [ ] No imports outside stdlib (fitness gate stays green)

**Tests**: unit — type hierarchy + `str` payloads · **Gate**: quick (`tests/infrastructure`)

---

### T3: Anthropic adapter taxonomy translation

**What**: Translate SDK/HTTP failures in `answering/anthropic.py` (both call paths) into the taxonomy per AD-337; keep caller-visible behavior unchanged (`AnswerGenerationFailed` envelopes); keep `_log_call` redaction.
**Where**: `backend/app/infrastructure/answering/anthropic.py` (buffered + stream error paths, the 4xx side-channel at :299-328)
**Depends on**: T2
**Reuses**: existing classification knowledge in the logging side-channel
**Requirement**: TAX-01, TAX-02, TAX-03

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Timeout (120s bound), 429, 5xx/overloaded, other-4xx each raise the mapped Learny type
- [ ] Existing error-envelope tests still green (caller surface unchanged)

**Tests**: unit — stubbed client raising each SDK error class · **Gate**: quick (`tests/infrastructure -k anthropic`)

---

### T4: Quiz adapter taxonomy translation + suggest timeout class

**What**: Same translation in `infrastructure/quiz/anthropic.py` (suggest 30s bound + batch paths), preserving retryable-vs-terminal task classification semantics.
**Where**: `backend/app/infrastructure/quiz/anthropic.py`
**Depends on**: T2
**Reuses**: T2 types; existing `_retry_or_fail_deck` classification
**Requirement**: TAX-02, TAX-03 (quiz plane)

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Suggest/batch failures raise mapped types; worker retry semantics demonstrably unchanged (tests)

**Tests**: unit — stubbed quiz client · **Gate**: quick (`tests/ -k quiz`)

---

### T5: Quiz poll provider pinning

**What**: `build_quiz_adapter(settings, provider=None)` override; poll tasks (and the inline collect) pass `handle.provider`; undeclared/unknown provider → terminal failure with operator-actionable log; never poll a foreign vendor.
**Where**: `backend/app/infrastructure/quiz/__init__.py`, `backend/app/worker/tasks.py` (deck task + both poll bodies)
**Depends on**: T4
**Reuses**: `QuizDeckHandle.provider` (`entities.py:868`), factory switch, `_retry_or_fail_deck`
**Requirement**: PIN-01..03

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Poll builds the adapter named by the handle (test with settings declaring a different provider)
- [ ] Undeclared provider → terminal (no retry loop), clear log, job marked failed
- [ ] Deck idempotency/redelivery tests still green

**Tests**: unit — worker task tests with fake adapters · **Gate**: quick (`tests/worker`, `tests/ -k quiz`)

**Commit boundary Phase 1**: run `make lint` + `make test` before dispatching Phase 2.

---

### T6: Profile registry settings + legacy seed

**What**: `GenerationProfileSettings` model + `settings.generation_profiles` (JSON env) + composition-time validation (unique ids, known kinds, non-empty, key envs present) + legacy seed synthesizing one profile from `generation_provider`/`generation_model`/`generation_effort`/`price_*` when the list is empty + `generation_explain_profile` setting. Lives in `providers/profiles.py`; `config.py` declares fields.
**Where**: `backend/app/core/config.py`, `backend/app/infrastructure/providers/profiles.py`
**Depends on**: T2 (package exists)
**Reuses**: settings comment style; factory fail-fast discipline
**Requirement**: ROUTE-01 (config half), ROUTE-05, ROUTE-06 (equivalence)

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Malformed registry fails fast with an actionable message (each validation branch tested)
- [ ] Empty registry == today's behavior byte-for-byte (equivalence tests)

**Tests**: unit — settings/registry validation matrix · **Gate**: quick (`-k "profiles or settings or config"`)

---

### T7: TokenUsage/TokenPrices cache fields + profile-priced budget

**What**: `TokenUsage` grows cache read/creation fields; `TokenPrices` grows cache micros (defaults 0.1×/1.25× input); `usage_micros` prices from a profile catalog; debit-site resolution: profile stamp → primary + warning (PRICE-04).
**Where**: `backend/app/domain/entities.py`, `backend/app/application/budget.py`, price-resolution helper in `providers/profiles.py`
**Depends on**: T6
**Reuses**: micros integer math; existing budget tests
**Requirement**: PRICE-01, PRICE-02, PRICE-04, PRICE-05

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Same usage through two catalogs → different micros (test)
- [ ] Cache fields priced; absent cache fields → input+output only (test)
- [ ] Unknown stamp → primary + warning (test, caplog assert)

**Tests**: unit — budget · **Gate**: quick (`tests/application -k budget`)

---

### T8: Anthropic adapter emits cache usage + profile-priced debit on turn paths

**What**: Anthropic adapter populates cache token fields on buffered **and** stream paths (`message_delta` usage); turn-path debit sites consume the catalog via T7 resolution.
**Where**: `backend/app/infrastructure/answering/anthropic.py` (usage extraction :218-233 + stream), debit site in `application/conversations.py`
**Depends on**: T7
**Reuses**: `_log_call`'s existing cache-read logging (:285-296)
**Requirement**: PRICE-02 (adapter half), COST-03

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Buffer and stream usage tests assert cache fields
- [ ] Turn-path debit test asserts profile-catalog micros (fixture prices differ from defaults)

**Tests**: unit — anthropic usage + conversations debit · **Gate**: quick (`-k "anthropic or conversations or budget"`)

---

### T9: Suggest/accept metering (SuggestResult + debit sites)

**What**: `SuggestResult(candidates, usage)` frozen carrier; `suggest_cards`/`suggest_note_cards` return it; all quiz adapters + call sites updated; capture + tutor-card call sites debit USD via the ledger (no caps; advisory counter column only if the repository API requires it → migration `0029`).
**Where**: `backend/app/domain/ports.py` (quiz port), `entities.py`, all `infrastructure/quiz/*` adapters, call sites in application services, optional `backend/migrations/.../0029_*.py`
**Depends on**: T7 (pricing), T4 (quiz adapters translated)
**Reuses**: ledger `record` path; migration house style (0025-0028)
**Requirement**: PRICE-03, AD-341

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Port widened with default-preserving semantics; every implementer compiles
- [ ] Suggest success → ledger row debited (test per call site); failure → no debit
- [ ] If migration added: up/down tested by the repo's migration test convention

**Tests**: unit — suggest debit sites + one adapter usage extraction · **Gate**: full (`make test` — port surface changed)

**Commit boundary Phase 2**: `make lint` + `make test` green before Phase 3.

---

### T10: RoutingGenerationAdapter — buffered policy + attribution

**What**: Router implementing `GenerationPort` over an ordered `ChainEntry` chain; buffered fallback policy per AD-337/AD-338 (timeout/unavailable → next; rate-limited → one same-provider backoff then next; rejected → only different-kind next); last error re-raised; `profile_id` stamped on returned answers.
**Where**: `backend/app/infrastructure/answering/routing.py` (new)
**Depends on**: T6 (profiles), T3 (taxonomy)
**Reuses**: `GenerationPort` contract; deterministic local adapter for chain tails in tests
**Requirement**: ROUTE-01, ROUTE-02, ROUTE-08, AD-344

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Each error class drives the policy branch (fake adapters, no network)
- [ ] Exhausted chain re-raises the translated error (envelope tests green)
- [ ] Stamp present on results from every chain position

**Tests**: unit — router policy matrix · **Gate**: quick (`tests/infrastructure -k routing`)

---

### T11: Router streaming rule + honest grounded failure

**What**: Stream fail-over only before the first delta (commit after); post-delta errors surface unchanged; mode-scoped eligibility (ask/teach enabled flags) — empty eligible chain fails honest before any provider touch.
**Where**: `backend/app/infrastructure/answering/routing.py`
**Depends on**: T10
**Reuses**: streaming contract (`ports.py:720-729`, `application/streaming.py`)
**Requirement**: ROUTE-03, ROUTE-04

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Pre-delta failure fails over (test); post-delta failure propagates exactly once, no second `AnswerCompleted` (test)
- [ ] Ask on ask-disabled-only chain → honest failure with zero adapter calls (test)
- [ ] Sentinel never streamed to the client across fail-over (test)

**Tests**: unit — streaming + eligibility · **Gate**: quick (`-k routing or streaming`)

---

### T12: Composition root — chains, accessors, registry wiring

**What**: `build_generation_chain(settings)` builds sub-adapters per profile and wraps the router; `get_generation()` returns the ask/teach chain router; explain-origin accessor (`generation_explain_profile` first, then primary) with per-origin cached accessors; fail-fast on registry/key errors at startup.
**Where**: `backend/app/infrastructure/answering/__init__.py`, `backend/app/infrastructure/web/dependencies.py`
**Depends on**: T10, T11
**Reuses**: existing factory + `lru_cache` pattern (`dependencies.py:619-622`)
**Requirement**: ROUTE-01, ROUTE-05, ROUTE-07, AD-345

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Default settings → behavior equivalent to today (existing dependency tests green, unmodified)
- [ ] Declared two-profile chain → router with both entries; missing key env → startup failure (tests)
- [ ] Rails order asserted: budget assert + rate limit fire before any adapter call regardless of profile

**Tests**: integration — web dependencies · **Gate**: quick (`tests/ -k "dependencies or generation"`)

---

### T13: Ask origin field + explain chain selection (backend)

**What**: Ask request schema grows optional `origin: Literal["explain_selection"]`; ask service entry resolves the chain accessor by origin (AD-345); unknown origin values rejected by validation; nothing else about the ask flow changes.
**Where**: request schema module (web layer), `application/conversations.py` ask entry
**Depends on**: T12
**Reuses**: `origin=tutor` precedent
**Requirement**: COST-04 (backend half), ROUTE-08

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Origin-marked request → explain chain serves (fake-chain test); plain request → primary chain
- [ ] Invalid origin literal → 422; absent → unchanged behavior (tests)

**Tests**: integration — web ask route · **Gate**: quick (`-k "ask or origin"`)

---

### T14: Frontend origin marker

**What**: Capture-popover Explain path marks its ask turn `origin: "explain_selection"`; all other ask paths send nothing.
**Where**: `frontend/app/components/` (capture-popover → ask panel plumbing), ask payload type in `frontend/app/lib/`
**Depends on**: T13 (backend accepts it)
**Reuses**: the popover's existing `onExplain(quote)` wiring
**Requirement**: COST-04 (frontend half)

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Vitest: popover-initiated turn sends the marker; panel-initiated and tutor turns do not
- [ ] `npx tsc --noEmit` green

**Tests**: unit (vitest) · **Gate**: quick (`cd frontend && npm test` + tsc)

**Commit boundary Phase 3**: `make lint` + `make test` green before Phase 4.

---

### T15: Per-mode effort (profile values, judge-gated defaults)

**What**: Anthropic adapter constructor takes per-mode effort (`effort_ask`/`effort_teach`) with legacy single-value compat; call paths select by mode; profiles feed their values; shipped defaults keep `medium` both modes.
**Where**: `backend/app/infrastructure/answering/anthropic.py` (`_THINKING`/`output_config` at :62, :462-463, :587-588), chain builder
**Depends on**: T12
**Reuses**: existing effort Literal validation
**Requirement**: COST-01, AD-339

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Prompt-capture tests: ask turn requests profile's ask effort; teach turn its teach effort
- [ ] Legacy seed still yields `medium`/`medium`; a profile with `low` ask produces a `low` request
- [ ] Compat-kind profile with unrepresentable effort builds fine and ignores it (ECON-05 sensor early)

**Tests**: unit — anthropic request shape · **Gate**: quick (`-k anthropic`)

---

### T16: Teach cache reorder (measured, not assumed)

**What**: Teach prompt assembly places stable per-section documents before the 1h cache breakpoint; playbook text and grounding behavior unchanged; cache-token measurement (T8) proves reachability.
**Where**: `backend/app/infrastructure/answering/anthropic.py` (system breakpoint :544-550, document assembly)
**Depends on**: T8 (measurement), T15 (same file — ordered)
**Reuses**: `_CACHE_CONTROL` plumbing
**Requirement**: COST-02, COST-03

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Prompt-assembly test pins: stable documents precede the breakpoint; breakpoint on the intended block
- [ ] Playbook text byte-unchanged (frozen-string test); grounding suite green
- [ ] Simulated two-turn teach shows cache-read fields populated on turn 2's usage extraction (stubbed)

**Tests**: unit — prompt assembly · **Gate**: quick (`-k anthropic`)

---

### T17: Eval profile recording + candidate-run workflow input

**What**: JSONL cases record `generation_profile` beside `generation_model`; `eval.yml` gains a `workflow_dispatch` input that overrides the profile registry env for candidate runs; threshold assert code untouched.
**Where**: `backend/app/eval/judge.py` (:321 region), `.github/workflows/eval.yml`
**Depends on**: T12 (profiles exist)
**Reuses**: eval.yml env-driven secret-skip pattern
**Requirement**: EVAL-01, EVAL-02, EVAL-03

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Judge test asserts profile fields in the JSONL case
- [ ] Gate predicate test still flips on below-threshold aggregates (unchanged behavior)
- [ ] Workflow input plumbs to the env var the settings read (yaml + a dry-run note in the PR description)

**Tests**: unit — judge · **Gate**: quick (`-k judge`) + `make fitness`

**Commit boundary Phase 4**: `make lint` + `make test` green before Phase 5.

---

### T18: OpenAI-compatible adapter — buffered generate + taxonomy + usage

**What**: `OpenAICompatibleGenerationAdapter` implementing `GenerationPort` (buffered): openai SDK with `base_url`, sentinel + `[^n]`-into-evidence prompt convention, marker parse to chunk-level spans (no fabricated offsets), usage mapping (incl. cached-token detail when present; absent → None → debit 0), HTTP/SDK error translation per AD-337, effort ignored.
**Where**: `backend/app/infrastructure/answering/openai_compat.py` (new)
**Depends on**: T2, T6 (profile kinds), T7 (usage fields)
**Reuses**: sentinel/CITE_MARK from `domain/entities.py`; embeddings adapter's SDK/base_url pattern
**Requirement**: ECON-01, ECON-02, ECON-03, ECON-05, TAX-02 (second adapter)

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Stubbed-transport contract tests: grounded answer with markers → chunk-level spans; sentinel → `found=False`
- [ ] Each error class mapped (408/timeout, 429, 5xx, other 4xx)
- [ ] Usage absent → `usage=None`; present → mapped incl. cache detail when reported
- [ ] No network in tests (ECON-06); `make fitness` green

**Tests**: unit — contract suite · **Gate**: quick (`tests/infrastructure -k openai_compat`)

---

### T19: OpenAI-compatible adapter — streaming

**What**: `generate_stream` honoring the port contract: zero+ text deltas (raw text, markers included, exactly as the Anthropic adapter streams today) then exactly one authoritative `AnswerCompleted`; usage via `stream_options.include_usage` when the host honors it (absent → None).
**Where**: `backend/app/infrastructure/answering/openai_compat.py`
**Depends on**: T18
**Reuses**: streaming semantics from the Anthropic adapter's stream path
**Requirement**: ECON-01, ROUTE-04 (compat is a fail-over candidate), ECON-03

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Contract tests: delta ordering, single `AnswerCompleted`, sentinel buffering never leaks `NOT_FOUND_IN_SOURCE` as a delta
- [ ] Pre-first-delta failure raises the translated error (router fail-over candidate behavior)

**Tests**: unit — stream contract · **Gate**: quick (`-k openai_compat`)

---

### T20: Economy profile declaration + env example + factory wiring

**What**: `openai-compatible` kind wired into `build_generation_chain`; Fireworks-US GLM-5.3-Flash profile shipped **inactive** (`ask_enabled=false`, `teach_enabled=false`, non-default) with price pair + key env name; `.env.example` documents `LEARNY_GENERATION_PROFILES` (with the inactive economy example) and `generation_explain_profile` (Haiku example disabled-by-default? no — explain profile ships **active** per COST-04; example shows the Haiku profile enabled for explain only); compose/docs untouched beyond env example.
**Where**: `backend/app/infrastructure/answering/__init__.py`, `backend/app/infrastructure/providers/profiles.py`, `.env.example` (+ production env example if separate)
**Depends on**: T18, T19, T12
**Reuses**: factory switch validation
**Requirement**: ECON-04, ROUTE-06, COST-04 (profile value)

**Tools**: MCP: NONE · Skill: NONE

**Done when**:
- [ ] Declared economy chain builds; ask turn on ask-disabled economy-only chain fails honest with zero calls (test)
- [ ] Default (undeclared) env → byte-identical legacy behavior (equivalence test green)
- [ ] `.env.example` shows both shapes; keys never carry real secrets

**Tests**: integration — chain building · **Gate**: full (`make lint` + `make test` — final phase boundary)

---

## Parallel Execution Map

```
Phase 0 (own unit):   T1
Phase 1 (sequential): T2 → T3 → T4 → T5
Phase 2 (sequential): T6 → T7 → T8 → T9
Phase 3 (sequential): T10 → T11 → T12 → T13 → T14
Phase 4 (sequential): T15 → T16 → T17
Phase 5 (sequential): T18 → T19 → T20
```

All phases sequential (each builds on the previous plane's contracts; DB-touching tasks are not parallel-safe). One worker per phase; T1 is a standalone doc chore.

---

## Task Granularity Check

| Task | Scope | Status |
|---|---|---|
| T1 | one doc | ✅ |
| T2 | one module | ✅ |
| T3 / T4 | one adapter each | ✅ |
| T5 | one factory + two task bodies | ✅ cohesive |
| T6 | settings + parser modules | ✅ |
| T7 | entities fields + budget math | ✅ |
| T8 | one adapter's usage extraction + one debit site | ✅ |
| T9 | port widening + call sites (cohesive port surface) | ✅ |
| T10–T12 | router policy / streaming / wiring split | ✅ |
| T13 / T14 | backend schema vs frontend marker | ✅ |
| T15 / T16 | effort vs prompt assembly (same file, ordered) | ✅ |
| T17 | judge + workflow | ✅ |
| T18 / T19 / T20 | buffered / streaming / declaration | ✅ |

## Diagram-Definition Cross-Check

| Task | Depends On (body) | Diagram Shows | Status |
|---|---|---|---|
| T1 | None | Phase 0 root | ✅ |
| T2 | T1 | T1→T2 | ✅ |
| T3 / T4 | T2 | T2→T3, T2→T4 (drawn linear T3→T4) | ✅ (linear order chosen deliberately — shared file family) |
| T5 | T4 | T4→T5 | ✅ |
| T6 | T2 | T5→T6 (phase boundary) | ✅ |
| T7 | T6 | T6→T7 | ✅ |
| T8 | T7 | T7→T8 | ✅ |
| T9 | T7, T4 | phase-linear | ✅ (T4 satisfied by phase boundary) |
| T10 | T6, T3 | phase-linear | ✅ |
| T11 | T10 | T10→T11 | ✅ |
| T12 | T10, T11 | T11→T12 | ✅ |
| T13 | T12 | T12→T13 | ✅ |
| T14 | T13 | T13→T14 | ✅ |
| T15 | T12 | phase-linear | ✅ |
| T16 | T8, T15 | T15→T16 | ✅ |
| T17 | T12 | phase-linear | ✅ |
| T18 | T2, T6, T7 | phase-linear | ✅ |
| T19 | T18 | T18→T19 | ✅ |
| T20 | T12, T18, T19 | T19→T20 | ✅ |

## Test Co-location Validation

Every task above modifies a code layer whose matrix row requires tests, and carries its `Tests` field accordingly (T1 is the sole doc-only task; matrix marks entities/config "none" with defaults verified through the unit suites in T6/T7). No `Tests: none` on any code task. ✅
