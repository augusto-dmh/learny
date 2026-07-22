# Eval Deepening Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. If the skill cannot be activated, STOP.

**Design**: `.specs/features/eval-deepening/design.md`
**Status**: In Progress — Phase A done (T1 `b97add6`, T2 `dcc7921`, T3 `0ff1911`, T4 `775d348`; full gate 1620 passed/11 skipped, additive +40/+1 self-skip; ruff clean). Accepted deviations: results files are `<dateTHMS>-<sha>-<uuid8>.jsonl` (fresh-file-per-run beats the "same convention" note — DEEP-20 wins), result lines carry tier/source/language/metric fields + `expected_chunk_hit` (feeds T6; golden lines have no `tier` — aggregate treats missing tier as golden).
Phase B done (T5 `2fcd7e7`; prompt_hash `7a1437…`→`211d9d…`; baseline 3.3 answered-only, `RELEVANCY_MIN` 2.5→2.8, pin moved same commit; full 1621/11, ruff clean). Finding recorded honestly: parks-at-3 did not reproduce — anchoring stabilized 2/3/4 boundaries (volcano case stopped flapping 2↔3, tides circular-restatement locks at 2). Not-found declines score relevancy 1 by construction → relevancy means exclude not-found; not-found discipline tracked separately (binds T6).
Phase C done (T6 `aadde11`, T7 `124986f`; full 1649/11 +28 additive, ruff clean). T9 producer contract: scored lines must add `found: bool` (absent→True) and `expected_not_found: bool` (absent→False); pairing key (case_id, generation_model); `aggregate([])` → None metrics (never 0.0). Consequence: silver all-answerable → silver not-found is None (incomparable) → generation "move" requires opus strictly better on BOTH silver faithfulness and silver relevancy, worse on neither. Gate-flip detection imports the constants from judge.py.
Phase D done (T8 local data only; T9 `d7432c3` golden results; T10 `383f7be` research doc + ROADMAP, `dc30318` judge switch). Silver: 12 cases, 6 books, 5 PT/7 EN, 12 runnable. Runs: 48 generations + 240 judge calls, 0 errors in the final dataset, ~$5.8 modeled. Verdicts from ab.py: generation STAY (Opus worse on silver faithfulness 0.986 vs 0.991); judge SWITCH on gate_flips=8 (exact 0.683, within-1 0.967 — otherwise high agreement; 6/8 flips are 2↔3 boundary noise at RELEVANCY_MIN 2.8; Opus also scores declines faithfulness 0.0 vs the vacuous-1.0 convention, a point for Haiku). Switch isolated in `dc30318` for merge-gate review; if kept, gate baselines need Opus re-derivation (follow-up flagged in the research doc). Full gate at commit state: 1649/11, ruff clean.

---

## Test Coverage Matrix

> Guidelines found: `CLAUDE.md` (citations/eval are core; golden-fixture-first evaluation), `backend/pyproject.toml` (markers `live`, `eval`), `.github/workflows/ci.yml` (deterministic `pytest -q`, no keys), `.github/workflows/eval.yml` (nightly `-m "live and eval"`).

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| --- | --- | --- | --- | --- |
| Silver loader/validation (`silver.py` pure parts) | unit | All branches; 1:1 to DEEP-01/04/17 load semantics; every malformed-input shape listed | `backend/tests/eval/test_silver_*.py` | `backend/.venv/bin/pytest tests/eval -q` |
| Silver DB resolution (`resolve_case`) | integration (test DB) | checksum hit/miss, duplicate checksum, anchor hit / alias hit / broken; env-gated like existing DB tests | `backend/tests/eval/test_silver_*.py` | same (skips without `LEARNY_TEST_DATABASE_URL`) |
| Silver per-case execution (injected fakes) | unit | statuses ok/skip/broken/error, retrieved-empty flag, JSONL line schema, fresh-file-per-run | `backend/tests/eval/test_silver_*.py` | same |
| Live silver runner (`test_silver.py`) | live (self-skipping) | smoke only — real run happens in Phase D; CI-facing requirement is the *skip* path, which gets a deterministic test | `backend/tests/eval/test_silver.py` | deterministic suite proves skip; live run manual |
| A/B logic (`ab.py`) | unit | All branches of aggregate/agreement/verdicts; AD-165/AD-166 thresholds each get boundary cases | `backend/tests/eval/test_ab.py` | `backend/.venv/bin/pytest tests/eval -q` |
| Rubric + gate constants | unit (existing pinning test updated) | pinning test asserts the recalibrated constants; prompt-file exemplar presence asserted | `backend/tests/test_eval_judge.py` | `backend/.venv/bin/pytest tests/test_eval_judge.py -q` |
| gitignore hygiene | unit (subprocess `git check-ignore`) | `evals/silver/` paths ignored (DEEP-05) | `backend/tests/eval/test_silver_hygiene.py` | `backend/.venv/bin/pytest tests/eval -q` |
| Research doc / calibration doc / ROADMAP | none | — (review artifact) | — | build gate only |

## Parallelism Assessment

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
| --- | --- | --- | --- |
| Backend pytest (all) | No — run sequentially | Shared test DB (`LEARNY_TEST_DATABASE_URL`), suite runs single-process in CI | `.github/workflows/ci.yml:77` (`pytest -q`, no `-n`) |

All `[P]` flags below are order-freedom information only; execution is sequential.

## Gate Check Commands

> `uv` is not on PATH in fresh shells — use the venv binaries (STATE handoff, v4-F process notes).

| Gate Level | When to Use | Command |
| --- | --- | --- |
| Quick | After eval-scoped tasks | `cd backend && .venv/bin/pytest tests/eval -q` |
| Judge | After rubric/gate tasks | `cd backend && .venv/bin/pytest tests/test_eval_judge.py tests/eval -q` |
| Full | Phase boundary + pre-push | `cd backend && .venv/bin/pytest -q && .venv/bin/ruff check .` |

Baseline to verify at Execute start (test DB up): record the pre-cycle full-suite pass/skip counts before the first task and hold them as the floor.

---

## Execution Plan

```
Phase A (silver foundation):   T1 → T2 → T3 → T4
Phase B (rubric+recalibrate):  T5            [needs live Haiku judge calls]
Phase C (A/B logic):           T6 [P] T7 [P] (order-free, same module)
Phase D (studies+evidence):    T8 → T9 → T10 [needs live provider runs, local DB]
```

Phase B depends only on nothing in A (prompt file is independent) but runs after A to keep one live-spend window late; C depends on nothing in A/B (pure logic); D depends on A (runner), B (anchored rubric), C (verdict helpers).

## Task Breakdown

### T1: Ignore the silver data tree + hygiene test

**What**: Add `evals/silver/` to the root `.gitignore`; add `backend/tests/eval/test_silver_hygiene.py` asserting via `git check-ignore` that `evals/silver/cases.yaml` and `evals/silver/results/x.jsonl` are ignored.
**Where**: `.gitignore`, `backend/tests/eval/test_silver_hygiene.py`
**Depends on**: None
**Requirement**: DEEP-05
**Done when**: hygiene test passes; quick gate green.
**Tests**: unit · **Gate**: quick
**Commit**: `chore(eval): keep local silver eval data out of git`

### T2: Silver case schema + loader

**What**: `SilverCase` dataclass + `load_silver_cases(path)` with schema validation (`SilverCaseError` naming case id + field), bounds awareness (10–20 advisory), language field.
**Where**: `backend/tests/eval/silver.py`, `backend/tests/eval/test_silver_loader.py`
**Depends on**: T1
**Requirement**: DEEP-01, DEEP-04 (schema), DEEP-17 (load leg)
**Done when**: valid fixture loads; each malformed shape (missing question / bad checksum / empty anchors / missing snippet / dup case_id) raises with case+field; quick gate green.
**Tests**: unit · **Gate**: quick
**Commit**: `feat(eval): add the silver case format and loader`

### T3: Checksum+anchor resolution against a DB

**What**: `resolve_case(conn, case)` → `ResolvedCase | SkippedCase | BrokenCase`: checksum→source (duplicate checksum → deterministic latest, chosen id surfaced), anchors→chunks (sections' `anchor_aliases` honored), absent book → skipped, unresolvable anchor → broken.
**Where**: `backend/tests/eval/silver.py`, `backend/tests/eval/test_silver_resolution.py`
**Depends on**: T2
**Requirement**: DEEP-01, DEEP-02, DEEP-18
**Done when**: integration tests (test DB via existing corpus-building helpers) cover hit / miss / duplicate / alias / broken; env-gated skip without test DB; quick gate green.
**Tests**: integration · **Gate**: quick
**Commit**: `feat(eval): resolve silver cases by source checksum and anchor`

### T4: Per-case execution + runner module

**What**: `run_silver_case(resolved, *, retrieve, generate, judge) -> dict` (injected callables; statuses ok/error, `retrieved_empty` flag, result-line schema with model/judge/prompt_hash/ts) + fresh-file JSONL writer under `evals/silver/results/` + the committed pytest runner `test_silver.py` (markers `live`+`eval`; module-level self-skip on missing data/keys/DB with zero provider imports on the skip path).
**Where**: `backend/tests/eval/silver.py`, `backend/tests/eval/test_silver.py`, `backend/tests/eval/test_silver_run.py`
**Depends on**: T3
**Requirement**: DEEP-01, DEEP-03, DEEP-19, DEEP-20, DEEP-17
**Done when**: deterministic tests with fakes cover all statuses, empty-retrieval, malformed-judge-output error line, fresh-file-per-run; the skip path is deterministically tested (no data → skip, no SDK import); quick gate green.
**Tests**: unit + integration · **Gate**: quick
**Commit**: `feat(eval): add the local silver eval runner`

### T5: Anchor the relevancy rubric + recalibrate the gate

**What**: Add one exemplar per score (1–5) to `backend/app/eval/prompts/relevancy.md`; run the judge live over the 12 committed replay snapshots with the anchored rubric; re-derive the relevancy baseline per `docs/ops/eval-calibration.md` (baseline − margin procedure); update `RELEVANCY_MIN` (judge.py) + `test_gate_constants_pin_the_calibrated_baselines` + the calibration doc (new baseline row with new prompt_hash and date); add a deterministic assertion that the rubric file carries 5 exemplars.
**Where**: `backend/app/eval/prompts/relevancy.md`, `backend/app/eval/judge.py`, `backend/tests/test_eval_judge.py`, `docs/ops/eval-calibration.md`
**Depends on**: none (runs after Phase A by schedule, not dependency)
**Requirement**: DEEP-06, DEEP-07, DEEP-08, DEEP-09
**Done when**: prompt_hash provably changed (old ≠ new recorded in the calibration doc); constants + pin updated in the same commit; judge gate green; full deterministic suite green without keys.
**Tests**: unit (pin + exemplar presence); live calls are the calibration run, evidenced in the doc · **Gate**: Judge, then Full at phase boundary
**Commit**: `feat(eval): anchor the relevancy rubric and recalibrate the gate`

### T6: A/B aggregates [P]

**What**: `ModelAggregate` + `aggregate(lines)` — mean faithfulness, mean relevancy, citation-valid rate, not-found discipline, golden/silver split, error-line exclusion (counted separately).
**Where**: `backend/app/eval/ab.py`, `backend/tests/eval/test_ab.py`
**Depends on**: none (pure)
**Requirement**: DEEP-11, DEEP-13, DEEP-14 (metric inputs)
**Done when**: unit tests cover empty input, mixed tiers, error lines, not-found cases; quick gate green.
**Tests**: unit · **Gate**: quick
**Commit**: `feat(eval): add generation study aggregates`

### T7: Judge agreement + verdict helpers [P]

**What**: `judge_agreement(a, b)` (paired by case+generation model; exact, within-1, n, gate-flips) and `judge_verdict`/`generation_verdict` encoding the recorded thresholds (judge: keep unless exact<0.60 or within-1<0.90 or any gate flip; generation: move only if better on ≥2 of faithfulness/relevancy/not-found over silver and worse on none).
**Where**: `backend/app/eval/ab.py`, `backend/tests/eval/test_ab.py`
**Depends on**: none (pure; same module as T6 — coordinate, order-free)
**Requirement**: DEEP-10, DEEP-11, DEEP-12, DEEP-15 (decision logic)
**Done when**: boundary cases on every threshold (at, above, below), unpaired-line handling, gate-flip detection tested; quick gate green.
**Tests**: unit · **Gate**: quick
**Commit**: `feat(eval): encode the judge and generation study verdicts`

### T8: Author the silver case set (local data, no commit)

**What**: Curate 10–20 cases into `evals/silver/cases.yaml` by reading passages from the local corpus DB: ≥3 books, both languages (portuguese + english), per-case question written against a specific read passage, expected anchors verified via `resolve_case` (all runnable, zero broken), expected snippet ≤25 words.
**Where**: `evals/silver/cases.yaml` (git-ignored)
**Depends on**: T4
**Requirement**: DEEP-04
**Done when**: loader+resolver accept the full set against the app DB (a small local verification run, no providers); case count, book count, language mix recorded in the phase report; `git status` clean of `evals/` paths.
**Tests**: none (data; validated by T2–T4 code) · **Gate**: quick (regression only)
**Commit**: none (data is ignored; no repo change)

### T9: Run the studies live

**What**: Execute (a) silver run under the settings default (sonnet) — this is also the silver smoke; (b) generation A/B: both `claude-sonnet-5` and `claude-opus-4-8` over the 12 golden cases + all runnable silver cases with identical per-case evidence; (c) judge pass: Haiku (primary) and Opus 4.8 over all A/B outputs and the 12 replayed snapshots. Golden-tier results → `evals/results/`; silver-tier → `evals/silver/results/`.
**Where**: local runs; tracked outputs only under `evals/results/`
**Depends on**: T5, T6, T7, T8
**Requirement**: DEEP-10, DEEP-13, DEEP-19, DEEP-20
**Done when**: result files exist for every (case, generation model, judge model) or carry explicit error lines; run manifest (counts, models, prompt_hash, spend estimate) captured for T10; no silver text in any tracked file.
**Tests**: none (execution) · **Gate**: quick (regression only)
**Commit**: `chore(eval): record the golden-tier study results` (tracked golden results only)

### T10: Research doc + apply the decisions

**What**: Write `docs/research/2026-07-21/eval-deepening-ab.md`: judge A/B (distributions, exact/within-1 agreement, gate flips, keep/switch recommendation) and generation A/B (per-model metrics split golden/silver, cost per answer, explicit stay/move decision) — quotes from books ≤25 words, attributed. Apply the verdicts: `judge_model` and/or `generation_model` defaults changed only per the encoded thresholds, each flip (if any) in its own commit referencing the doc. Update the ROADMAP candidate row to Done.
**Where**: `docs/research/2026-07-21/eval-deepening-ab.md`, `backend/app/core/config.py` (only if a verdict says move), `.specs/project/ROADMAP.md`
**Depends on**: T9
**Requirement**: DEEP-11, DEEP-12, DEEP-14, DEEP-15, DEEP-16
**Done when**: doc complete with both decisions and their inputs; config matches the decisions; full gate green (suite + ruff).
**Tests**: none (doc) + existing suite for any config change · **Gate**: Full
**Commit**: `docs(research): decide the judge and generation defaults from the eval studies` (+ optional `feat(eval): …` flip commit(s))

## Task Granularity Check

| Task | Scope | Status |
| --- | --- | --- |
| T1 | 1 ignore rule + 1 test file | ✅ |
| T2 | 1 loader + its tests | ✅ |
| T3 | 1 resolver fn + its tests | ✅ |
| T4 | 1 exec fn + runner module + tests | ✅ (cohesive: one execution seam) |
| T5 | 1 prompt + 1 constant + pin + doc | ✅ (atomic: constant is invalid without rubric+doc) |
| T6 | 1 aggregate fn + tests | ✅ |
| T7 | 2 verdict fns + agreement fn + tests | ✅ (one decision module) |
| T8 | 1 data file | ✅ |
| T9 | study execution | ✅ (no code) |
| T10 | 1 doc + conditional config line | ✅ |

## Diagram-Definition Cross-Check

| Task | Depends On (body) | Diagram | Status |
| --- | --- | --- | --- |
| T1 | none | phase A head | ✅ |
| T2 | T1 | T1→T2 | ✅ |
| T3 | T2 | T2→T3 | ✅ |
| T4 | T3 | T3→T4 | ✅ |
| T5 | none (scheduled after A) | phase B, no arrow from A | ✅ |
| T6 | none | phase C [P] | ✅ |
| T7 | none | phase C [P] | ✅ |
| T8 | T4 | phase D head | ✅ |
| T9 | T5,T6,T7,T8 | T8→T9 (+B,C complete) | ✅ |
| T10 | T9 | T9→T10 | ✅ |

## Test Co-location Validation

| Task | Layer | Matrix Requires | Task Says | Status |
| --- | --- | --- | --- | --- |
| T1 | gitignore hygiene | unit | unit | ✅ |
| T2 | silver loader | unit | unit | ✅ |
| T3 | silver resolution | integration | integration | ✅ |
| T4 | per-case exec + runner | unit+integration | unit+integration | ✅ |
| T5 | rubric + gate constants | unit (pin) | unit | ✅ |
| T6 | ab logic | unit | unit | ✅ |
| T7 | ab logic | unit | unit | ✅ |
| T8 | data | none | none | ✅ |
| T9 | execution | none | none | ✅ |
| T10 | docs | none | none | ✅ |
