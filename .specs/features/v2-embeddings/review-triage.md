# Review triage — v2-embeddings (PR #20)

Independent `pr-review` posted 4 inline findings + 2 issue comments (requirements
22/22 implemented; consolidated summary). CI: 4/4 jobs green (lint, backend-test,
compose-smoke, frontend). Each finding judged against the code as it exists.

| # | Source (marker) | file:line | Verdict | Action | Rationale |
|---|---|---|---|---|---|
| F1 | architecture 💡 | `app/core/config.py:104` | **real** | **fix** | This cycle added `embedding_dimensions` (1536) alongside the pre-existing `embedding_dim` (1536): two settings for one concept (vector width), read by different paths (deterministic adapter + `model` identity read `embedding_dim`; OpenAI adapter + eval snapshot read `embedding_dimensions`) with no cross-check. Overriding one and not the other silently disagrees while the `vector(1536)` column is fixed. Collapse to a single source of truth. |
| F2 | performance ⚡ | `app/worker/tasks.py:294` (`stale_chunks_for_source`, repositories.py) | **real** | **fix** | `stale_chunks_for_source` has no SQL `LIMIT`; the reembed loop fetches ALL remaining stale chunks (id + full text) + a full `ORDER BY` every pass and slices `[:batch_size]` in Python. N/B passes each scanning O(N) rows → ~N²/2B rows transferred, quadratic in document size. Push the batch bound into the query — keeps per-pass re-query resumability, bounds each fetch to one batch. |
| F3 | tests 💡 | `tests/test_eval_retrieval_metrics.py:42` | **real (readability)** | **fix (comment)** | `recall@5 >= 1.0` on the shared 3-chunk golden fixture (AD-037) is always true for any ranking (top_k=5 ≥ 3 chunks), so it guards only total-retrieval-failure, not ranking (recall@1/MRR guard ranking). Flagged by both the Verifier (L-008) and pr-review. The golden book can't grow without disturbing the tier-1 goldens, and EMB-21 mandates k∈{1,5}, so keep recall@5 computed + as a presence guard but add the inline comment the reviewer suggests so it is not misread as a ranking metric. Not dropped: it still catches an empty/short result set. |
| F4 | tests ⚠️ | `tests/test_reembed.py:256` (`_index_exists`) | **real** | **fix** | The dedicated EMB-18 test asserts only that an index *named* `ix_corpus_chunks_embedding_hnsw` exists — a regression recreating it with wrong params or as a different type would still pass (retrieval "serves" via seqscan). `test_migrations.py` already asserts `indexdef` for the GIN index. Strengthen to assert the recreated `indexdef` contains `hnsw` + `m = '16'` + `ef_construction = '64'`, so "same params as 0005" is verified, not inferred. |
| — | requirements | issue comment | n/a | none | 22/22 EMB criteria implemented, 0 missing; ADR-0007/0009/0019 constraints honored. No action. |
| — | summary | issue comment | n/a | none | Consolidated roll-up. No action. |

## Fix plan

4 findings, all real, all fixed — grouped into atomic commits:
1. `perf` — push the batch limit into `stale_chunks_for_source` (F2).
2. `refactor` — collapse the duplicate embedding-dimension setting to one (F1).
3. `test` — verify the reembed HNSW index definition + document the recall@5 presence guard (F4, F3).

Re-run the full backend suite + ruff after fixes; push to the PR branch.
