# Eval Deepening Specification

## Problem Statement

The eval harness (RFC-003 Cycle B) gates only a synthetic, lexically-disjoint golden book — both candidate generation models ace it, so it cannot discriminate between models, and the relevancy judge parks at 3 because the rubric has no per-score exemplars. Before any product-default decision (Sonnet 5 vs Opus 4.8) can be evidence-based, the harness needs a small real-book eval tier and an anchored, calibrated judge.

## Goals

- [ ] A silver eval tier: 10–20 curated question→expected-passage cases over the user's real ingested books, runnable locally, with all copyrighted data git-ignored and only the runner committed.
- [ ] The relevancy rubric anchored with per-score exemplars, followed by one recalibration pass (baselines re-derived, gate constants re-pinned).
- [ ] Judge A/B evidence: Haiku 4.5 vs Opus 4.8 scoring identical outputs.
- [ ] Generation A/B evidence: Sonnet 5 vs Opus 4.8 over golden + silver, concluded in a research doc that decides whether the product default moves.

## Out of Scope

| Feature | Reason |
| --- | --- |
| Eval dashboard / Ragas adoption | Excluded by RFC-003 exclusions; ADR-0016 keeps the custom harness |
| New judge metrics (beyond relevancy anchoring) | Candidate scope is anchoring + A/B only |
| Committing any real-book text (cases, snippets, results) | Copyrighted; silver data is git-ignored by design |
| CI execution of the silver tier | Data exists only on the user's machine; CI self-skips |
| BYOK / provider changes | RFC-003 exclusions; ADR-0019/0020 lock providers |
| FSRS/quiz eval changes | Untouched by this cycle |

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| Silver case authorship | Authored in-cycle by the agent from the local corpus DB, curated per-passage (not template-generated) | Generation A/B is uninformative without silver; user's books are ingested and readable locally; "hand-authored" = per-passage human-quality curation | auto (AD-161) |
| Silver case identity | Keyed by source checksum + chunk anchor, never source UUID | Survives re-ingestion and DB rebuilds; UUIDs are per-DB | auto (AD-162) |
| Silver data location | `evals/silver/` (cases + results), git-ignored; runner committed under `backend/tests/eval/` | Mirrors existing cases.yaml/results conventions; keeps copyrighted text out of git | auto (AD-163) |
| Recalibration corpus | The 12 committed replay snapshots (replayed outputs; no generation spend) plus the silver outputs once recorded | Matches the calibration-first procedure in docs/ops/eval-calibration.md | auto (AD-164) |
| Judge default after A/B | Stays `claude-haiku-4-5` unless the A/B shows material disagreement with Opus on the anchored rubric | Candidate scope: A/B produces evidence; changing the judge default needs that evidence | auto (AD-165) |
| Generation default flip | Applied in-cycle only if the A/B verdict is decisive; otherwise stays `claude-sonnet-5`; either way the research doc records the decision and the merge gate surfaces it | ROADMAP: "product default stays claude-sonnet-5 until that evidence exists" | auto (AD-166) |
| A/B judge for generation comparison | The anchored Haiku judge scores both models' outputs; the Opus judge run (judge A/B) doubles as a robustness check on the verdict | One judged dataset serves both studies; avoids a third scoring pass | auto (AD-167) |

**Open questions:** none — all resolved or logged above.

## User Stories

### P1: Silver eval tier ⭐ MVP

**User Story**: As the Learny maintainer, I want a local eval set over my real books so that eval verdicts reflect real usage, not a synthetic book both models ace.

**Why P1**: Every other deliverable (recalibration on real outputs, generation A/B) is uninformative without it.

**Acceptance Criteria**:

1. WHEN the silver runner is invoked with `evals/silver/cases.yaml` present and the referenced books ingested THEN it SHALL resolve each case by source checksum + anchor, run retrieval + generation over the local corpus, and append one JSONL line per case under `evals/silver/results/`.
2. WHEN a silver case references a book not present in the local DB THEN the runner SHALL skip that case with a per-case skip reason, not fail the run.
3. WHEN `evals/silver/` data is absent (e.g. CI, fresh clone) THEN the committed runner SHALL self-skip cleanly (pytest skip, exit 0-equivalent), and no provider call SHALL be attempted.
4. WHEN the cycle completes THEN `evals/silver/cases.yaml` SHALL contain 10–20 cases spanning at least 3 books and both corpus languages (portuguese, english), each with question, source checksum, expected anchor(s), and an expected-passage snippet.
5. WHEN `git status` is inspected after a silver run THEN no file under `evals/silver/` SHALL be tracked or staged (gitignore covers cases, results, and any derived data).

**Independent Test**: Run the silver runner locally → JSONL results appear under `evals/silver/results/`; run the same pytest module with `evals/silver/` moved away → clean skip.

### P1: Anchored relevancy rubric + recalibration ⭐ MVP

**User Story**: As the Learny maintainer, I want the relevancy judge anchored with per-score exemplars so that scores spread across the scale instead of parking at 3, making thresholds meaningful.

**Why P1**: Both A/B studies read relevancy scores; an uncalibrated judge invalidates them.

**Acceptance Criteria**:

1. WHEN `relevancy.md` is edited THEN it SHALL contain one exemplar per score (1–5), each a question/answer sketch with a one-line reason, and `prompt_hash()` SHALL change as a consequence.
2. WHEN the recalibration pass runs over the 12 replay snapshots with the anchored rubric THEN new relevancy baselines SHALL be recorded in `docs/ops/eval-calibration.md` with the same derivation procedure as 2026-07-18 (baseline − margin).
3. WHEN `RELEVANCY_MIN` changes THEN the pinning test (`test_gate_constants_pin_the_calibrated_baselines`) SHALL be updated to the new constant in the same commit, and the nightly gate semantics SHALL be otherwise unchanged.
4. WHEN the deterministic test suite runs THEN judge unit tests SHALL pass without any provider key (replay/deterministic paths untouched).

**Independent Test**: Diff of `relevancy.md` shows 5 exemplars; a live one-case judge smoke returns a score; calibration doc shows the new baseline row with prompt_hash.

### P2: Judge A/B (Haiku 4.5 vs Opus 4.8)

**User Story**: As the Learny maintainer, I want both judges scored on identical outputs so that I know whether the cheap judge's verdicts can be trusted.

**Acceptance Criteria**:

1. WHEN the judge A/B runs THEN both `claude-haiku-4-5` and `claude-opus-4-8` SHALL score the identical set of outputs (12 golden replayed + all silver outputs) under the anchored rubric, with per-case scores persisted (golden → `evals/results/`, silver → `evals/silver/results/`).
2. WHEN the research doc reports the A/B THEN it SHALL include per-judge score distributions, exact-agreement and within-1 agreement rates, and a keep/switch recommendation for `judge_model`.
3. WHEN the A/B does not show material disagreement THEN `judge_model` SHALL remain `claude-haiku-4-5`.

**Independent Test**: Research doc section with the two distributions and agreement rates; results files contain both judge models' lines with the anchored prompt_hash.

### P2: Generation A/B (Sonnet 5 vs Opus 4.8) + research doc

**User Story**: As the Learny maintainer, I want Sonnet 5 and Opus 4.8 compared over golden + silver so that the product-default choice is evidence, not vibes.

**Acceptance Criteria**:

1. WHEN the generation A/B runs THEN both models SHALL answer the identical case set (12 golden + all runnable silver cases) over identical retrieved evidence per case, and outputs SHALL be judged with the anchored judge.
2. WHEN the research doc is written THEN it SHALL live under `docs/research/2026-07-21/` and report per-model faithfulness, relevancy, citation validity, and not-found discipline, split by golden vs silver, plus cost-per-answer, and SHALL end with an explicit decision: default stays `claude-sonnet-5` or moves to Opus, with rationale.
3. WHEN the decision is "stay" THEN `generation_model` default SHALL be unchanged; WHEN "move" THEN the default SHALL be flipped in `config.py` in its own commit referencing the research doc (no internal IDs).
4. WHEN the research doc quotes evidence THEN it SHALL NOT reproduce book passages beyond short attributed quotes (≤25 words per passage).

**Independent Test**: Research doc exists with metric tables for both models and a decision paragraph; config default matches the decision.

## Edge Cases

- WHEN the anchored judge returns malformed/unschema'd output for a case THEN the runner SHALL fail that case visibly (recorded as an error line), never silently score it.
- WHEN a silver case's expected anchor no longer resolves (book re-ingested with different structure) THEN the runner SHALL report the case as broken (distinct from skip) so the case can be re-authored.
- WHEN retrieval returns no chunks for a silver question THEN the case SHALL still be generated and judged (retrieval quality is part of what silver measures), with retrieved-empty recorded on the result line.
- WHEN a provider call fails mid-run (rate limit/5xx) THEN completed case results SHALL survive (append-per-case), and re-running SHALL be safe (results keyed by run file; a rerun writes a new results file, never corrupts a prior one).

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| --- | --- | --- | --- |
| DEEP-01 | P1 silver: runner resolves checksum+anchor, runs, appends JSONL | Done | Verified |
| DEEP-02 | P1 silver: missing-book case → per-case skip | Done | Verified |
| DEEP-03 | P1 silver: absent data → clean self-skip, no provider call | Done | Verified |
| DEEP-04 | P1 silver: 10–20 cases, ≥3 books, both languages | Done | Verified |
| DEEP-05 | P1 silver: nothing under evals/silver/ tracked | Done | Verified |
| DEEP-06 | P1 rubric: 5 exemplars, prompt_hash changes | Done | Verified |
| DEEP-07 | P1 rubric: recalibration baselines recorded in calibration doc | Done | Verified |
| DEEP-08 | P1 rubric: RELEVANCY_MIN + pinning test updated together | Done | Verified |
| DEEP-09 | P1 rubric: deterministic suite green without keys | Done | Verified |
| DEEP-10 | P2 judge A/B: both judges over identical outputs, persisted | Done | Verified |
| DEEP-11 | P2 judge A/B: distributions + agreement + recommendation in doc | Done | Verified |
| DEEP-12 | P2 judge A/B: judge_model unchanged absent material disagreement | Done | Verified |
| DEEP-13 | P2 gen A/B: both models, identical cases + evidence, judged | Done | Verified |
| DEEP-14 | P2 gen A/B: research doc with metrics split + explicit decision | Done | Verified |
| DEEP-15 | P2 gen A/B: config default matches the decision | Done | Verified |
| DEEP-16 | P2 gen A/B: no long copyrighted quotes in the doc | Done | Verified |
| DEEP-17 | Edge: malformed judge output → visible error line | Done | Verified |
| DEEP-18 | Edge: broken anchor → broken (not skip) | Done | Verified |
| DEEP-19 | Edge: empty retrieval → still generated+judged, flagged | Done | Verified |
| DEEP-20 | Edge: mid-run failure → completed results survive, rerun safe | Done | Verified |

**Coverage:** 20 total, 20 mapped to tasks, 20 Verified (validation.md, 2026-07-22).

## Success Criteria

- [ ] Silver tier runnable locally end-to-end; CI and fresh clones unaffected (deterministic suite green, no tracked silver data).
- [ ] Anchored rubric live: scores spread beyond a single value on real outputs; gate re-pinned to recalibrated baselines.
- [ ] Research doc under `docs/research/2026-07-21/` closes both A/Bs with explicit judge and generation-default decisions.

## Implicit-Requirement Dimensions (sweep)

| Dimension | Resolution |
| --- | --- |
| Input validation & bounds | Silver cases schema-validated on load (question, checksum, ≥1 anchor, snippet required); malformed file → clear error (DEEP-01/17); 10–20 case bound (DEEP-04) |
| Failure / partial-failure | Per-case skip/broken/error states; append-per-case results survive mid-run failure (DEEP-02/18/20) |
| Idempotency / retry / duplicates | Reruns write a new dated results file; no in-place mutation (DEEP-20) |
| Auth boundaries & rate limits | N/A — offline local eval; keys via env, never committed |
| Concurrency / ordering | N/A — sequential single-process runs |
| Data lifecycle / expiry | All silver data git-ignored (DEEP-05); results retained locally only |
| Observability | Every result line carries model, judge model, prompt_hash, timestamps (existing JSONL pattern) |
| External-dependency failure | No keys → self-skip (DEEP-03); provider 5xx → error line + safe rerun (DEEP-20) |
| State-transition integrity | N/A — no domain state machines touched |
