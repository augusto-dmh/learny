# v5-generation-denoise — Design

Binding constraints: ADR-0019/0020 (providers), ADR-028 (decline semantics), AD-166 (silver drives the verdict), AD-231..237 (this cycle's decisions, context.md). No new SDKs; the study reuses the existing Anthropic adapter and Judge.

## Architecture

Three layers, mirroring the shipped eval stack's split:

```
app/eval/ab.py                 pure: MetricSpread + denoised verdict (no I/O)
tests/eval/study.py            runner: units, checkpoint/resume, budget stop (fake-testable)
tests/eval/test_generation_study.py   live entrypoint (opt-in flag, wires real adapters)
```

## 1. Pure layer (`backend/app/eval/ab.py` additions)

- `MetricSpread` frozen dataclass: `values: tuple[float, ...]` (one per run that had the metric; `None`-runs excluded) with `mean/min/max/range` (`None`/empty-safe: no values → mean etc. `None`, mirroring the module's never-0.0 convention). (DENOISE-01)
- `metric_spread(runs: Sequence[ModelAggregate], *, tier: str, metric: str) -> MetricSpread` — collects `getattr(run.<tier>, metric)` skipping `None`.
- `denoised_generation_verdict(sonnet_runs: Sequence[ModelAggregate], opus_runs: Sequence[ModelAggregate]) -> str` — per metric in `_GENERATION_METRICS` over **silver** (AD-236): both spreads non-empty else incomparable; better iff `opus.min > sonnet.max`; worse iff `opus.max < sonnet.min`; else tie (AD-231). `"move"` iff better ≥ 2 and worse == 0; everything else (including either arm empty) `"stay"`. (DENOISE-02/03) Existing `generation_verdict` stays (historical single-run rule; docstring cross-links).

## 2. Silver ADR-028 alignment (`backend/tests/eval/silver.py`)

`run_silver_case` currently judges unconditionally and omits `found` from its line — a latent ADR-028 violation that becomes live once an arm declines a silver case. Change: when `answer.found` is falsy, skip the judge call; line carries `found: false`, `faithfulness/relevancy: null`, `generation_model`, and `citation_valid` (decline must cite nothing — `_citation_valid` already handles it); answered lines gain `found: true`. `judge_model`/`prompt_hash` on decline lines come from nowhere (no judge ran) — omit them; `ab.py` never reads them. Backward compatible: `ab.py` defaults `found→True` for legacy lines. Update `test_silver_run.py` for the new decline path.

## 3. Study runner (`backend/tests/eval/study.py`, new)

**Unit** = `(tier, case_id, arm, run_index)`; arms `("claude-sonnet-5", "claude-opus-4-8")`, run_index `0..2` (AD-235). Deterministic unit order: tier (golden first) → run_index → case order → arm, so a budget stop truncates cleanly.

**Golden scoring path** (DB-free): `harness.load_snapshots()` supplies frozen evidence per case (AD-233). Per unit: rebuild `Evidence` domain objects from `SnapshotEvidence` (`chunk_id=UUID(...)`, `section_path=()`, `source_id=UUID(int=0)`, `page_span=None` — the adapter reads only `section_path|anchor|chunk_id|snippet`, and with an empty path the document title falls back to the anchor; identical across arms, recorded as a limitation in the research doc) → `adapter.generate(message=..., mode=MODE_ANSWER, evidence=...)` → `harness.build_snapshot` (in memory) → `harness.snapshot_eval_inputs` → judge faithfulness+relevancy iff `found` (ADR-028) → line. `expected_not_found` from the case's `expected_status`.

**Silver scoring path**: `load_silver_cases()` + `resolve_case` once per study; retrieval memoized per case (AD-233) via a caching wrapper over `tests.eval_runner.retrieve`; per unit `run_silver_case(resolved, retrieve=memoized, generate=<arm adapter>, judge=<Judge wrapper>)` + study fields added. Skipped/broken cases write their existing line shapes once per (arm, run) so resume sees them complete.

**Line schema** (DENOISE-04): tier-native fields ∪ `{run_index, git_sha, ts, tier, status, generation_model, judge_model, prompt_hash, faithfulness, relevancy, citation_valid, found, expected_not_found}` — a superset of the `ab.py` input contract.

**Artifacts** (DENOISE-08): golden → tracked `evals/results/<date>-<sha>-generation-denoise.jsonl`; silver → git-ignored `evals/silver/results/<date>-<sha>-generation-denoise.jsonl`. Stable names (no time/uuid component) make resume find them; lines append one-by-one immediately after scoring (DENOISE-04) — `write_silver_results`' exclusive-create is deliberately not reused.

**Resume** (DENOISE-05/06): on start, read both artifacts; key recorded lines by `(tier, case_id, generation_model, run_index)`. Status `ok|skipped|broken` → skip (zero provider calls); `error` → re-attempt. Any recorded line whose `prompt_hash` ≠ current `prompt_hash()` or `judge_model` ≠ configured judge → raise `StudyMismatchError` before any spend.

**Budget stop** (DENOISE-14, AD-234): `CostModel(generation_usd_per_unit: dict[str, float], judge_usd_per_unit: float)` — modeled, pinned in the live entrypoint with a derivation comment (Cycle A/B observed token counts × current prices). Modeled spend = Σ unit_cost over recorded lines (any status, counted once) + units scored this invocation; before each unit, `spend + unit_cost > settings.eval_budget_usd` → clean stop with a report line (modeled spend, ceiling, remaining units). Config: `eval_budget_usd: float = 10.0` in `Settings` (`LEARNY_EVAL_BUDGET_USD`) + pin in `test_config.py` + `.env.example` row.

**Progress** (DENOISE-09): one printed line per unit (`tier/case/arm/run status`).

**Failure**: per-unit exceptions → `error` line, continue (mirrors `run_silver_case`); the runner never buffers the study in memory.

## 4. Live entrypoint (`backend/tests/eval/test_generation_study.py`, new)

- **Carries `live` but never `eval`** (as shipped; corrected post-review) — it exercises a real provider, and the nightly `-m "live and eval"` needs both markers so it cannot collect it (AD-226 lesson; DENOISE-09). Opt-in via a `--generation-study` conftest flag (mirrors `--record-generation`), with a fixture skip (`study_skip_reason`) when the flag or `LEARNY_ANTHROPIC_API_KEY` is absent. Silver additionally needs the local DB; when `silver_run_skip_reason()` fires, the study runs golden-only and says so (spec edge case: silver-driving metrics absent → verdict `stay` by incomparability).
- Wires: two `AnthropicGenerationAdapter`s (one per arm, `settings.generation_max_tokens`), one `Judge(model=settings.judge_model)`, memoized retrieval, the pinned `CostModel`; calls `study.run_study(...)`.
- Offline guard tests (in `test_study_runner.py`): the module is skipped without the flag, and it carries no `live`/`eval` marks (mirror the marker-enrollment guards in `test_eval_judge.py`).

## 5. Live execution + evidence (phase 3)

Pre-flight per the runbook: verify `prompt_hash()` matches Cycle B's, record the modeled estimate (expected ≈ 144 generations + ≤288 judge calls; well under $10), then run to completion (resume on interruption). Research doc `docs/research/<run-date>/generation-denoise-ab.md` in the Cycle B shape: header (Date · Decision · Evidence) → Context → Pre-registered rule (AD-231/235/236, fixed before the runs) → Method (exact command, arms, unit counts) → Per-metric variance tables (per tier × arm: per-run values, mean, min, max, range) → Verdict as the literal `denoised_generation_verdict` output → Spend report (ceiling/estimate/actual/ratio) → Consequences → Limitations (incl. the empty-`section_path` prompt note and snapshot staleness carry-over from AD-228). Consequence: stay → no config change (DENOISE-13); move → flip `generation_model` default + pins + `.env.example` **and** re-derive `FAITHFULNESS_MIN`/`RELEVANCY_MIN` from the opus-arm golden runs, committed together (AD-237).

## Test coverage matrix

| Requirement | Test home |
|---|---|
| DENOISE-01..03 | `tests/eval/test_ab.py` (pure, boundary-named) |
| silver decline alignment | `tests/eval/test_silver_run.py` |
| DENOISE-04..09, 14 | `tests/eval/test_study_runner.py` (new; fakes, tmp dirs, no network/DB) |
| DENOISE-10..13 | live run + research doc (procedural evidence; config state asserted by existing pins) |
