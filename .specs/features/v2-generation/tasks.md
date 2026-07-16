# v2-generation Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: activate it by name and follow its Execute flow and Critical Rules. If the skill cannot be activated, STOP.

**Design**: `.specs/features/v2-generation/design.md`
**Status**: Approved (auto-approved per ship-cycle rule)

---

## Test Coverage Matrix

> Guidelines found: `CLAUDE.md` (golden fixtures + citations as core requirements), `backend/pyproject.toml` (`live` marker, ruff config), `.github/workflows/ci.yml` (offline PR suite + DB services). Existing tests sampled: `test_answering_local.py`, `test_embeddings_openai.py`, `test_application_qa.py`, `test_web_questions.py`, `test_golden_citations.py`.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| --- | --- | --- | --- | --- |
| Adapters (`infrastructure/answering/*`) | unit (fake client, no network) | All branches; 1:1 to spec ACs; every listed edge case (sentinel, dedup, max_tokens partial, lazy import) | `backend/tests/test_answering_*.py` | `uv run pytest tests/test_answering_anthropic.py -q` |
| Factories / settings / DI | unit | Switch branches + fail-fast + defaults | `backend/tests/test_answering_factory.py`, `test_config*.py` | `uv run pytest tests/test_answering_factory.py -q` |
| Domain stream contract + fakes | unit | Event ordering contract; deterministic stream | `backend/tests/test_answering_local.py` | quick |
| Application services (`qa.py`, `teaching.py`) | unit (fakes) | All branches incl. hold-back, grounding, persist-on-completion, error wrap | `backend/tests/test_application_*.py` | `uv run pytest tests/test_application_qa.py tests/test_application_teaching.py -q` |
| Web endpoints (JSON unchanged + `/stream`) | integration (live test DB) | Happy + every edge + error path (404/409/422/429, mid-stream error, frame sequence) | `backend/tests/test_web_*.py` | `uv run pytest tests/test_web_questions.py tests/test_web_teaching.py -q` (needs `LEARNY_TEST_DATABASE_URL`) |
| Eval harness (invariants, replay, judge) | unit + integration | Invariants exact vs golden book; judge branches with fake client; skip paths | `backend/tests/test_generation_invariants.py`, `backend/tests/eval/`, `test_eval_judge.py` | `uv run pytest tests/test_generation_invariants.py tests/test_eval_judge.py -q` |
| Live provider | live (marker) | 1 smoke per adapter + F5 sentinel case | same files, `@pytest.mark.live` | skipped offline by design |
| ADR / workflow / prompt files | none | — (build/lint gate only) | — | build gate |

## Parallelism Assessment

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
| --- | --- | --- | --- |
| Unit (fakes) | Yes | No shared state; pure objects | `test_answering_local.py`, `fakes.py` |
| Integration (DB) | No | Shared `db_engine` session fixture + table cleanup | `backend/tests/conftest.py:28` |
| Live | No | Real provider + shared budget | marker definition |

Execution is sequential per phase worker (one worker per phase, phases sequential) — `[P]` marks order-freedom only.

## Gate Check Commands

All from `backend/` with `uv` at `/home/augusto/myenv/bin/uv`.

| Gate Level | When to Use | Command |
| --- | --- | --- |
| Quick | Per task (scoped) | `uv run pytest tests/<touched modules> -q` |
| Full | Phase boundary + before push | `uv run pytest -q` (expect ≥554 passed baseline + new; `live` skipped) |
| Build | Phase boundary | `uv run ruff check .` |

DB-dependent tests require `LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test` and `docker.exe compose up -d db` (WSL: `docker.exe`, not `docker`).

---

## Execution Plan

```
Phase A (answer adapter):    A1 → A2 → A3 → A4
Phase B (teaching adapter):  B1 → B2
Phase C (streaming):         C1 → C2 → C3 → C4
Phase D (eval):              D1 → D2 → D3 → D4 → D5
Phases strictly sequential; one sub-agent worker per phase (context.md D-8).
```

## Task Breakdown

### A1: Settings + Anthropic SDK dependency

**What**: Add `generation_provider`, `anthropic_api_key`, `generation_model`, `generation_max_tokens`, `judge_model`, `eval_max_cases` to `Settings`; add `anthropic>=0.60,<1` (or current major — verify installed floor) to `backend/pyproject.toml` and lock.
**Where**: `backend/app/core/config.py`, `backend/pyproject.toml`
**Depends on**: None. **Requirement**: GEN-01, GEN-03
**Done when**: defaults test asserts new fields + offline defaults; `uv sync` clean; quick gate passes.
**Tests**: unit | **Gate**: quick
**Commit**: `feat(config): add generation provider settings and anthropic dependency`

### A2: AnthropicAnswerAdapter + prompts + parser

**What**: `prompts.py` (SENTINEL, frozen answer+teaching system prompts) and `anthropic.py` with `AnthropicAnswerAdapter` (`generate` via `messages.create`), shared `_build_documents`/response parser per design §3; content-free log line.
**Where**: `backend/app/infrastructure/answering/{prompts.py,anthropic.py}`, tests `backend/tests/test_answering_anthropic.py`
**Depends on**: A1. **Requirement**: GEN-04..GEN-08 (buffered half)
**Done when**: fake-client tests assert: per-chunk citations-enabled docs in evidence order; `document_index` mapping (never title); dedup first-occurrence order; whole-reply sentinel → `found=False` (embedded sentinel stays prose); `max_tokens` partial returned; `model` property; SDK imported lazily (import module without `anthropic` installed-check pattern from `test_answering_local.py:no-SDK-import`); service-level test: adapter-shaped out-of-set citation → not_found via grounding (GEN-08). Quick gate.
**Tests**: unit | **Gate**: quick
**Commit**: `feat(answering): add Anthropic cited-answer adapter with relevance-aware not-found`

### A3: Answer factory + DI wiring

**What**: `build_answer_adapter(settings)` in `infrastructure/answering/__init__.py` (local/anthropic/unknown→ValueError; empty-key fail-fast); `dependencies.py` `get_answer_generation` uses lazy cached factory.
**Where**: `backend/app/infrastructure/answering/__init__.py`, `backend/app/infrastructure/web/dependencies.py`, `backend/tests/test_answering_factory.py`
**Depends on**: A2. **Requirement**: GEN-02, GEN-23 (partial)
**Done when**: factory tests mirror `test_embeddings_factory.py` (local default, anthropic constructs with settings, unknown raises, empty key raises); full existing suite green (default path byte-identical). Full gate.
**Tests**: unit | **Gate**: full
**Commit**: `feat(answering): select the answer generation provider from settings`

### A4: ADR-0020

**What**: `docs/adr/0020-use-anthropic-claude-for-generation.md` (Accepted) per design §9, following ADR-0019's structure.
**Where**: `docs/adr/` **Depends on**: A3. **Requirement**: GEN-09
**Done when**: ADR present, links RFC-002 + research; build gate (ruff) clean.
**Tests**: none | **Gate**: build
**Commit**: `docs(adr): accept Anthropic Claude as the generation provider`

### B1: AnthropicTeachingAdapter with prompt caching

**What**: `AnthropicTeachingAdapter` per design §3: alternating history messages, `ttl:"1h"` cache_control on frozen system prompt + last history assistant block, per-turn evidence+message after prefix, target section in final user text, sentinel + shared parser.
**Where**: `backend/app/infrastructure/answering/anthropic.py`, tests in `test_answering_anthropic.py`
**Depends on**: A2. **Requirement**: GEN-10, GEN-11
**Done when**: fake-client tests assert message layout, breakpoint placement (system + last history block; none when history empty), no interpolation in system prompt (byte-stable across calls/sessions), sentinel → not-found, citations mapping shared. Quick gate.
**Tests**: unit | **Gate**: quick
**Commit**: `feat(answering): add Anthropic teaching adapter with prompt caching`

### B2: Teaching factory + DI wiring

**What**: `build_teaching_adapter(settings)` + `dependencies.py` teaching wiring (lazy cached factory).
**Where**: `backend/app/infrastructure/answering/__init__.py`, `dependencies.py`, `test_answering_factory.py`
**Depends on**: B1. **Requirement**: GEN-02
**Done when**: factory branch tests (as A3); full suite green. Full gate.
**Tests**: unit | **Gate**: full
**Commit**: `feat(answering): select the teaching generation provider from settings`

### C1: Domain stream contract + deterministic/fake streams

**What**: `AnswerTextDelta`/`AnswerCompleted` entities; `generate_stream` on both ports; deterministic adapters implement (one delta + completed); update `tests/fakes.py` + `test_application_teaching.py` local fake.
**Where**: `backend/app/domain/{entities.py,ports.py}`, `infrastructure/answering/local.py`, `backend/tests/fakes.py`, tests `test_answering_local.py`
**Depends on**: B2. **Requirement**: GEN-12
**Done when**: contract tests (deltas then exactly one completed, completed authoritative); protocol conformance (isinstance) for deterministic + fakes; full suite green (fake updates). Full gate.
**Tests**: unit | **Gate**: full
**Commit**: `feat(domain): add a streaming contract to the generation ports`

### C2: Anthropic streaming implementation

**What**: `generate_stream` on both Anthropic adapters via `client.messages.stream` (text deltas → events, final message → completed; try/finally closes stream on cancellation).
**Where**: `backend/app/infrastructure/answering/anthropic.py`, tests with fake streaming client
**Depends on**: C1. **Requirement**: GEN-12
**Done when**: fake streaming-client tests: delta mapping, completed parsing equals buffered parsing, generator close → client stream closed. Quick gate.
**Tests**: unit | **Gate**: quick
**Commit**: `feat(answering): stream Anthropic generation events`

### C3: Application streaming paths

**What**: `AskQuestion.stream` + `PostTeachingTurn.stream` per design §6: pre-yield guards, sentinel hold-back, grounding on completion, teaching persist-only-on-completion, cancellation cleanup, error wrap.
**Where**: `backend/app/application/{qa.py,teaching.py}` (+ small shared helper if needed), tests `test_application_qa.py`, `test_application_teaching.py`
**Depends on**: C1 (fakes with streams). **Requirement**: GEN-13, GEN-17 (app half)
**Done when**: tests: guards raise before first yield; hold-back suppresses sentinel deltas + flushes divergent prefix; not-found via sentinel and via grounding; turn persisted only after completion; generator close → no persist + port stream closed; port error → `AnswerGenerationFailed`. Quick gate.
**Tests**: unit | **Gate**: quick
**Commit**: `feat(qa,teaching): add streaming answer and turn flows`

### C4: SSE presenter + endpoints

**What**: `ui_message_stream.py` presenter (protocol v1 frames + header), `/questions/stream` + `/turns/stream` endpoints with sibling dependency lists, mid-stream error part, fastapi floor `>=0.135`.
**Where**: `backend/app/infrastructure/web/{ui_message_stream.py,questions.py,teaching.py}`, `backend/pyproject.toml`, tests `test_web_questions.py`, `test_web_teaching.py`
**Depends on**: C3. **Requirement**: GEN-14..GEN-17
**Done when**: integration tests (deterministic provider, offline): full frame sequence incl. `data-citations`/`data-answer-status`/`finish`/`[DONE]` + header; pre-stream 404/409/422/429 as plain HTTP; mid-stream failure → error part (fake adapter raising after first delta via dependency override); not-found stream case; turn persisted on success / absent on mid-stream failure; JSON endpoints byte-identical. Full gate + build.
**Tests**: integration | **Gate**: full
**Commit**: `feat(web): stream answers and teaching turns over SSE`

### D1: Eval cases + replay harness

**What**: `backend/tests/eval/` package: `cases.yaml` (~10–15 golden-book Q&A cases incl. not-found cases), snapshot loader (schema per design §8), `--record-generation` conftest option (live rewrite, sorted keys, no volatile fields), skip-when-absent behavior.
**Where**: `backend/tests/eval/`, `backend/tests/conftest.py`
**Depends on**: C4 (adapters final). **Requirement**: GEN-18
**Done when**: loader unit tests (roundtrip, schema); absent-snapshot skip visible in `-rs` output; `--record-generation` path unit-tested with fake adapter (writes reviewable JSON). Quick gate.
**Tests**: unit | **Gate**: quick
**Commit**: `test(eval): add generation replay snapshots with a record flag`

### D2: Citation-validity invariants (every PR)

**What**: `test_generation_invariants.py`: run eval cases through real retrieval + deterministic adapter on the golden book asserting the three exact invariants; parametrize over committed snapshots too.
**Where**: `backend/tests/test_generation_invariants.py`
**Depends on**: D1. **Requirement**: GEN-19
**Done when**: invariants pass offline against golden book; snapshot param skips when none committed; a seeded violation (test-local mutant fixture) is caught by each invariant. Full gate.
**Tests**: integration | **Gate**: full
**Commit**: `test(eval): enforce exact citation validity invariants`

### D3: Judge harness

**What**: `backend/app/eval/judge.py` + versioned prompts + JSONL writer + `eval` marker; structured-outputs calls on `judge_model`; `LEARNY_EVAL_GATE` calibration switch.
**Where**: `backend/app/eval/`, `backend/pyproject.toml`, tests `backend/tests/test_eval_judge.py`
**Depends on**: D1. **Requirement**: GEN-21
**Done when**: fake-client unit tests: faithfulness ratio math, relevancy parse, JSONL line schema (prompt hash, model ids, sha), max_cases cap, gate-off = report-only; lazy SDK import. Quick gate.
**Tests**: unit | **Gate**: quick
**Commit**: `feat(eval): add an LLM judge harness for faithfulness and relevancy`

### D4: Live smoke tests

**What**: `@pytest.mark.live` (+`eval` where judge-driven): one answer, one teaching turn, one F5 irrelevant-evidence sentinel case; key-gated skips.
**Where**: `backend/tests/test_answering_anthropic.py`
**Depends on**: D3. **Requirement**: GEN-20
**Done when**: tests skip offline with clear reason; structure passes ruff; (live execution deferred to user key / nightly). Quick gate (skips counted).
**Tests**: live | **Gate**: quick
**Commit**: `test(answering): add live Anthropic smoke checks`

### D5: Nightly eval workflow

**What**: `.github/workflows/eval.yml` per design §8 (cron + dispatch, secret guard, Postgres service, `pytest -m "live and eval"`, `LEARNY_EVAL_MAX_CASES`, artifact upload); `evals/results/.gitkeep`.
**Where**: `.github/workflows/eval.yml`, `evals/results/`
**Depends on**: D4. **Requirement**: GEN-22, GEN-23
**Done when**: workflow YAML valid (actionlint-style review by worker); secret-absent path exits 0 with notice; full suite + ruff green (final full gate for the cycle).
**Tests**: none | **Gate**: build + full
**Commit**: `ci(eval): run the generation judge harness nightly`

---

## Diagram-Definition Cross-Check

| Task | Depends On (body) | Diagram | Status |
| --- | --- | --- | --- |
| A1 | none | phase start | ✅ |
| A2 | A1 | A1→A2 | ✅ |
| A3 | A2 | A2→A3 | ✅ |
| A4 | A3 | A3→A4 | ✅ |
| B1 | A2 (via phase order) | phase B after A | ✅ |
| B2 | B1 | B1→B2 | ✅ |
| C1 | B2 (phase order) | phase C after B | ✅ |
| C2 | C1 | C1→C2 | ✅ |
| C3 | C1 | C2→C3 sequential ordering retained (C3 also after C2 in worker order) | ✅ |
| C4 | C3 | C3→C4 | ✅ |
| D1 | C4 (phase order) | phase D after C | ✅ |
| D2 | D1 | D1→D2 | ✅ |
| D3 | D1 | D2→D3 (worker order; no code dep on D2) | ✅ |
| D4 | D3 | D3→D4 | ✅ |
| D5 | D4 | D4→D5 | ✅ |

## Test Co-location Validation

| Task | Layer | Matrix Requires | Task Says | Status |
| --- | --- | --- | --- | --- |
| A1 | settings | unit | unit | ✅ |
| A2 | adapter | unit | unit | ✅ |
| A3 | factory/DI | unit | unit | ✅ |
| A4 | ADR | none | none | ✅ |
| B1 | adapter | unit | unit | ✅ |
| B2 | factory/DI | unit | unit | ✅ |
| C1 | domain+adapter+fakes | unit | unit | ✅ |
| C2 | adapter | unit | unit | ✅ |
| C3 | application | unit | unit | ✅ |
| C4 | web | integration | integration | ✅ |
| D1 | eval harness | unit | unit | ✅ |
| D2 | eval invariants | integration | integration | ✅ |
| D3 | judge | unit | unit | ✅ |
| D4 | live | live | live | ✅ |
| D5 | workflow | none | none | ✅ |

Tools: MCPs none; skills none inside workers (API shapes embedded in worker payloads).
