# ADR-028: Declined Answers Are Excluded from Judge Aggregate Means

- **Date**: 2026-07-31
- **Status**: Accepted (2026-07-31, rides the implementing cycle's merge gate; direction set by RFC-005 Cycle B)
- **Deciders**: Augusto, Claude
- **Tags**: eval, judge, gating, faithfulness, relevancy

## Context and Problem Statement

The nightly judge gate and the A/B study aggregate disagree with each other —
and with their own baselines — about what a declined answer ("not found in
source", empty text) contributes to an aggregate score.

- The gate (`_assert_aggregates`, `backend/app/eval/judge.py`) averages
  faithfulness and relevancy over **all** lines, while the pinned thresholds
  (`FAITHFULNESS_MIN`, `RELEVANCY_MIN`) were derived over the **answered**
  cases only (9 of the 12 replay snapshots — see the derivation comment above
  the constants). The clash stayed latent because the nightly judged tier was a
  single answered synthetic case.
- The A/B study aggregate (`_tier_aggregate`, `backend/app/eval/ab.py`)
  excludes declines from `mean_relevancy` but keeps them in
  `mean_faithfulness`, where they contribute a vacuous `1.0` via
  `FaithfulnessResult.supported_ratio` (no claims extracted → ratio 1.0).
- The 2026-07-21 judge A/B (`docs/research/2026-07-21/eval-deepening-ab.md`)
  showed the vacuous-`1.0` convention is **judge-model-dependent**:
  `claude-opus-4-8` scores a declined answer's faithfulness `0.0` (treating
  the decline as an unsupported assertion) where `claude-haiku-4-5` yields
  `1.0`. Any aggregate that lets decline scores in therefore changes meaning
  when the judge model changes — which blocked the judge switch that A/B
  otherwise recommended.

A declined answer is not a low-quality answer; it is a different **outcome
class**, already measured on its own axis (not-found discipline: did the case
that *should* decline actually decline?). Folding its judge scores into quality
means conflates the two axes and makes the aggregate judge-dependent.

## Decision

**Aggregate means are computed over answered lines only, in both the nightly
gate and the A/B study.**

1. **Nightly gate** (`_assert_aggregates`): the faithfulness and relevancy
   means include only lines whose `found` flag is true. The `citation_valid`
   invariant continues to run over **all** lines (a decline must still cite
   nothing invalid). When a gated run contains **no** answered lines, the
   threshold asserts are skipped — no mean exists — and the citation invariant
   still runs.
2. **A/B study** (`_tier_aggregate`): `mean_faithfulness` moves to
   answered-only, matching the existing `mean_relevancy` semantics.
   `citation_valid_rate` stays over all scored lines.
3. **Declined cases are not judge-scored.** `run_eval` skips both judge calls
   for an input marked `found=False` and records `faithfulness: null`,
   `relevancy: null`, `found: false` on the line. Scoring an empty answer buys
   a value the aggregate discards by construction — and, per the A/B evidence,
   a value whose meaning depends on which judge model is asked.
4. **The per-case vacuous-`1.0` convention is retained** at
   `FaithfulnessResult.supported_ratio` for any caller that does score an
   answer with no extractable claims. It is a per-case convention, not an
   aggregate one; ADR-028 removes it from every aggregate path.
5. **Not-found discipline carries declines.** The decline axis is measured by
   `not_found_discipline` (share of expected-not-found cases that correctly
   declined), today a study-level metric in `ab.py`. It is **not** added to the
   nightly gate yet: the nightly tier replays frozen snapshots, on which
   discipline is definitionally constant — a tautological gate. Adopting it as
   a gate assert is deferred until the nightly tier includes live generation,
   and that adoption should re-use this ADR's outcome-class framing.

## Consequences

- Aggregate means are judge-model-independent in their treatment of declines,
  unblocking judge-model comparison and the RFC-005 Cycle B flip-or-stay.
- Gate semantics now match how the pinned thresholds were actually derived;
  the "answered-only" filter is enforced in code rather than assumed in a
  comment.
- JSONL result lines gain a `found` field (`true` for all pre-existing lines
  by default — `line.get("found", True)` — so archived results remain
  readable).
- Decline-heavy runs lose judge-score observability for those declines by
  design; the study archive (2026-07-21) preserves the evidence of how each
  judge model scores declines, should the convention ever be revisited.
- A run composed entirely of declines passes the threshold gate vacuously
  (citation invariant only). Acceptable today — the replay tier always
  contains answered cases; revisit alongside the not-found-discipline gate
  adoption when the nightly tier includes live generation.
