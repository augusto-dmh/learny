# Review triage — PR #35 (v3-eval-maturity)

Reviewer: fresh-context pr-review run (6 lanes; security/architecture/
performance/regression zero-finding; requirements lane verified 13/13 ACs).
Findings below judged against the code as it exists on `feat/v3-eval-maturity`
at `51f59b0`.

| # | Source comment | File:line | Verdict | Action | Rationale |
|---|---|---|---|---|---|
| 1 | inline 3609383596 | `backend/tests/test_eval_judge.py:238` | **real** | **fix** | `_assert_aggregates` has three enforcement branches; faithfulness and relevancy got dedicated single-failure cases in `51c63cc` but citation validity did not, and no gate=True test runs with all-good aggregates — so an inverted citation comparison survives every existing test. Add a citation-only-bad case plus a gate-passes-on-baseline case (the pass case is what kills an inverted `all()`). |
| 2 | inline 3609390424 | `backend/tests/test_eval_retrieval_metrics.py:122` | **real** | **fix** | The `eval` marker is the sole wiring that enrolls the keyed retrieval arm in the nightly selection; its removal is only observable at collection time (the Verifier classified this mutant as a collection-level sensor). A marker-membership meta-test makes the wiring offline-assertable. |
| 3 | inline 3609390811 | `backend/tests/eval/snapshots/notfound-black-holes.json:3` | **real** | **fix** | The recorded not-found snapshots encode `found=false` with empty `cited_chunk_ids`, and the domain contract (not-found answers cite nothing) is asserted elsewhere for live generation, but no replay invariant enforces it over the committed artifacts — a corrupted snapshot could smuggle citations into a not-found case unnoticed. Cheap invariant over `load_snapshots()`. |
| 4 | issue 5013299526 (requirements review) | — | n/a | keep-until-cleanup | Verification artifact, not a finding; deleted in comment cleanup. |
| 5 | issue 5013312747 (summary) | — | n/a | keep-until-cleanup | Consolidated summary; deleted in comment cleanup. |

Counts: 3 findings — 3 real, 0 false; 3 fix, 0 won't-fix.
