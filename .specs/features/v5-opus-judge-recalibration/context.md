# Context — v5-opus-judge-recalibration auto-decisions (ship-cycle protocol)

Operator inputs (2026-07-31): run Cycle B before Cycle E (user choice at the ship-cycle gate); live-eval budget cap **$10** for this cycle's runs (RFC-005 OQ-3).

- **AD-225 — Unified answered-only aggregate semantics (gate + study); not-found
  discipline stays study-level.** Options: (a) exclude declines from both means in
  both aggregates (chosen) — matches how the pinned thresholds were actually
  derived (9 answered of 12), removes the judge-dependent vacuous-1.0 vs 0.0
  ambiguity from aggregates entirely, and keeps gate and study measuring the same
  thing; why-not: touches `test_ab.py` expectations and changes the study
  aggregate's recorded meaning between Cycle B and C runs. (b) RFC-literal
  minimum — faithfulness-only exclusion in the gate, study untouched — smaller
  diff; why-not: leaves gate relevancy counting decline-1s that its own threshold
  derivation excluded, and leaves the study's faithfulness carrying the exact
  vacuous-1.0 convention Opus contradicts, so Cycle C would hit the same clash.
  (c) Also gate not-found discipline; why-not: on a frozen replay tier discipline
  is constant — a tautological gate with no baseline; deferred until the nightly
  tier includes live generation (documented in ADR-0028).
- **AD-226 — Nightly judged tier widens from the 1 synthetic smoke case to the 12
  committed replay snapshots.** Options: (a) widen the live tier (chosen) — the
  gate finally runs on the distribution its thresholds derive from (closing the
  drift the AD-116 amendment flagged), and the runbook's "run the live tier ≥3
  times" becomes literally the calibration procedure, no ad-hoc scripting;
  why-not: nightly judge spend rises from 2 calls to ~20 (still cents on Haiku,
  ~$0.30 on Opus), and the smoke's synthetic case disappears as a distinct
  signal. (b) Keep the smoke + add a separate non-nightly calibration runner file;
  why-not: preserves the gate-vs-baseline drift permanently and adds a second
  live entrypoint to maintain. (c) Ad-hoc scripting like July's derivation;
  why-not: irreproducible — the exact failure mode this cycle exists to close.
- **AD-227 — Declined cases skip judge calls; their line scores are `null`.**
  Options: (a) skip + null (chosen) — no spend on scores the aggregate discards
  by construction; `found` on the line is the explicit semantic carrier; why-not:
  loses per-run observability of how each judge model scores declines (the very
  signal that exposed the Opus 0.0 behavior — but ADR-0028 makes that signal
  moot by contract, and the study data already archived it). (b) Keep scoring
  declines and exclude at aggregate time; why-not: pays 2 judge calls per decline
  per run forever for discarded values, and keeps emitting a judge-dependent
  score for empty answers that invites misreading.
- **AD-228 — Calibrate on the committed snapshots as-is; no re-record.** Options:
  (a) as-is (chosen) — the Haiku thresholds were derived on exactly these inputs,
  so the Opus comparison is same-inputs clean; zero generation spend; why-not:
  v6-E changed live answer shape (inline `[^n]` markers, 4096 tokens, thinking),
  so the snapshots understate current production answers — recorded as a runbook
  follow-up flag, not fixed mid-experiment. (b) Re-record first per runbook step
  1; why-not: confounds the judge comparison with new answer text and pulls a
  generation-side change into a judge-side cycle.
- **AD-229 — Flip-or-stay rule fixed in the spec before any run (RECAL-08):
  default FLIP unless instability (per-run mean spread > the safety margins),
  degeneracy (derived floors below discrimination), or nightly budget
  (> $0.50/night projected).** Options: (a) default-flip with stay-triggers
  (chosen) — the study's verdict was `switch`, deferred on two conditions this
  cycle discharges, so the burden of proof sits on staying; the triggers are the
  three defensible reasons a stronger judge could still be the wrong gate;
  why-not: a rule authored before data can bind awkwardly if runs land near a
  boundary. (b) Default-stay unless Opus strictly dominates; why-not:
  contradicts the study's recorded verdict and re-defers what this cycle exists
  to close. (c) Decide after seeing the data; why-not: unfalsifiable — the
  decision must be auditable against a pre-stated rule.
- **AD-230 — Budget compliance is procedural this cycle (runbook protocol:
  pre-flight estimate vs the $10 ceiling, per-case JSONL append as checkpoint,
  resume-never-regenerate, spend report).** Options: (a) procedural (chosen) —
  the estimate (~$1) is 10× under the ceiling and the append-only JSONL already
  checkpoints per case; why-not: nothing enforces the ceiling in code if the
  operator misestimates. (b) Build `LEARNY_EVAL_BUDGET_USD` enforcement now;
  why-not: that is RFC-005 Cycle C's named deliverable — building it here
  duplicates a queued cycle's scope in a judge cycle.
