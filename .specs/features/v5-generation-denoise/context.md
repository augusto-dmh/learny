# v5-generation-denoise — Decision Context

Auto-decided per the ship-cycle autonomy contract (recommended option chosen, full option set recorded for audit). None met the escalation rule: no product-direction change beyond the cycle, no new provider lock-in, and each had a clearly defensible recommendation. The budget ceiling was already settled as an operator call at Cycle B start (RFC-005 OQ3, $10) and is carried, not re-decided.

## D-1 (AD-231) — What "strictly better/worse" means under noise

- **(a) Non-overlapping per-run ranges** — better iff min(opus) > max(sonnet) on that metric; worse symmetric; any overlap = tie. ✅ **chosen**
  - Why-recommend: honest at n=3; pre-registerable; no distributional assumptions; makes a sub-noise gap (the 0.005 case that motivated the cycle) read as tie → stay, exactly the RFC's "leave unchanged on ambiguity".
  - Why-not: very conservative — a real but small improvement inside overlapping ranges won't move the default.
- (b) Mean gap > pooled stdev — why-not: stdev from 3 samples is fragile pseudo-rigor dressed as statistics.
- (c) Welch t-test — why-not: n=3 violates its assumptions; false precision; spec lists it out of scope.
- (d) Grand-mean comparison (existing single-run rule over pooled means) — why-not: reproduces the exact single-observation failure the RFC targets.

## D-2 (AD-232) — What varies across the ≥3 runs

- **(a) Full generate+judge pass per arm per run** ✅ **chosen**
  - Why-recommend: the verdict's noise includes generation sampling — the un-measured source; judge-only variance was already characterized by Cycle B (relevancy range 0.22 over 3 runs).
  - Why-not: 3× the generation spend vs judge-only re-scoring (bounded by the cap; modeled well under $10).
- (b) Generate once per arm, judge 3× — why-not: cheaper but measures only judge noise, which is already known; leaves the actual question (generation variance) open.

## D-3 (AD-233) — Evidence handling

- **(a) Evidence fixed per case across arms and runs** (golden: committed snapshot evidence; silver: resolved once per study, retrieval memoized) ✅ **chosen**
  - Why-recommend: isolates generation quality — identical inputs across arms is the point of an A/B; retrieval is deterministic against a frozen DB anyway.
  - Why-not: measures no retrieval variance — accepted, retrieval is not the question.
- (b) Fresh retrieval per run — why-not: conflates variance sources and adds embedding spend for nothing.

## D-4 (AD-234) — Budget enforcement

- **(a) Modeled-cost enforcement in code**: `eval_budget_usd` settings field (`LEARNY_EVAL_BUDGET_USD`, default 10.0); the runner stops before any unit whose modeled cost would exceed the ceiling — a clean resumable checkpoint. Estimate + spend report stay in the research doc per the runbook. ✅ **chosen**
  - Why-recommend: AD-230 explicitly deferred this env var's code enforcement to Cycle C; stop-before-unit composes with checkpoint/resume.
  - Why-not: modeled ≠ billed — drift is possible; mitigated by the runbook's estimate-vs-actual reconciliation in the spend report.
- (b) Keep it procedural (runbook only) — why-not: contradicts recorded decision AD-230.
- (c) Live billed-usage metering — why-not: new API surface and complexity for a ~$5 study; out of scope in the spec.

## D-5 (AD-235) — Run count

- **(a) Exactly 3 runs per arm** ✅ **chosen** — meets the RFC's ≥3 floor at bounded spend; the range rule stays honest at 3. Why-not: more runs narrow ranges and could resolve near-ties — not worth ~2× spend now; a follow-up can widen n if this study lands overlapping-but-suggestive.
- (b) 5 runs — why-not: ~1.7× spend for marginal narrowing, and no pre-registered rule change would follow.

## D-6 (AD-236) — Which tier drives the verdict

- **(a) Silver drives, golden reported — AD-166 bar unchanged** ✅ **chosen** — the RFC says "hold the existing bar"; silver is the real-book distribution. Why-not: silver has no expected-not-found cases, so not-found discipline never participates and "better on ≥2 of 3" effectively requires both faithfulness and relevancy — accepted; golden discipline is still reported per arm.
- (b) Pool golden+silver into the driving comparison — why-not: silently changes the recorded bar (AD-166) and lets synthetic cases outvote real ones.

## D-7 (AD-237) — Consequence of a "move" verdict

- **(a) Flip + in-cycle threshold re-derivation** from the study's opus-arm golden runs (runbook mean-minus-margin rule), committed together. ✅ **chosen** — judge.py's constants block mandates re-derivation whenever the generation model changes; shipping a flip against sonnet-derived baselines would falsify the nightly gate.
  - Why-not: conditional extra scope — only paid if the verdict is move.
- (b) Flip now, re-derive in a follow-up — why-not: leaves the gate asserting stale baselines for an unbounded window.
