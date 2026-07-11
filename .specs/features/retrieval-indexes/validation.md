# Validation — retrieval-indexes (Cycle 5, TDD Phase 6)

**Verdict: PASS ✅**

- **Diff/commit range:** `bb9aac7..0fc2d03` (10 commits `1bb8e24..0fc2d03`) on `feat/retrieval-indexes`.
- **Gate:** `314 passed, 0 failed` (full suite with `LEARNY_TEST_DATABASE_URL`); `ruff check .` clean.
- **Spec-anchored check:** 22/22 ACs matched their spec-defined outcome; 0 spec-precision gaps.
- **Edge cases:** all covered (see below).
- **Discrimination sensor:** 6 behavior-level mutations injected in scratch state, **6/6 killed**, all reverted (tree clean, suite green afterward).
- **Verifier note:** the always-on Verifier sub-agent was terminated early by an account session-limit (infrastructure, not code); per the tlc standalone fallback this validation was run inline by the orchestrator (not the author of the implementation code — the five phase workers wrote it), applying `validate.md` evidence-or-zero.

## Per-AC coverage (spec-anchored, evidence-or-zero)

| AC | Test evidence (`file:line`) + assertion | Spec outcome | ✅ |
|---|---|---|---|
| RET-01 extension + nullable embedding + generated search_vector | `test_migrations.py:354` `pg_extension where extname='vector' → 1`; `:359` `"embedding" in columns`; `:360` `columns["embedding"]["nullable"] is True`; `:361` `"search_vector" in columns` | columns/extension exist | ✅ |
| RET-02 HNSW + GIN indexes | `test_migrations.py:378` `"hnsw" in hnsw_def and "vector_cosine_ops" in hnsw_def`; `:379` `m=16`; `:380` `"ef_construction"`; `:381` `"gin" in gin_def and "search_vector"` | both indexes with params | ✅ |
| RET-03 generated search_vector auto-populated (incl. title 'A' + body 'D') | `test_migrations.py:390-392` `sv non-empty; "brown" in sv (body); "intro" in sv (title)` | populated from title+body | ✅ |
| RET-04 downgrade clean | `test_migration_0005_downgrade_removes_retrieval_columns_indexes` (`:400`) asserts columns/indexes/extension gone, corpus_chunks intact | reversible | ✅ |
| RET-05 depends only on EmbeddingPort (no SDK) | `test_embeddings_local.py:72` AST scan asserts no provider SDK import; ports/entities have no SDK imports (build gate) | no SDK leak | ✅ |
| RET-06 deterministic | `test_embeddings_local.py:24` `embed(x)==embed(x)` | identical vector | ✅ |
| RET-07 batch order/count | `test_embeddings_local.py:39` N in → N out, positional equality to `embed_query` | order preserved | ✅ |
| RET-08 dim + no client arg (model id in config) | `test_embeddings_local.py:32` len==1536; `:86` no-arg constructor | dim 1536, config-sourced | ✅ |
| RET-09 every chunk embedded post-run | `test_worker_tasks.py:505` after run every chunk `embedding IS NOT NULL`, job succeeded | all non-NULL | ✅ |
| RET-10 embed in own txn after corpus | `test_worker_tasks.py` embed tests + `test_ingestion_step.py:121` embed step delegates; task wiring runs embed in a second `begin()` | own committed txn | ✅ |
| RET-11 re-embed on re-ingest | `test_worker_tasks.py:523` re-ingest re-embeds exactly the rebuilt chunk set | no stale vectors | ✅ |
| RET-12 retry/terminal, no partial | `test_ingestion_step.py:131` transient→Retryable; `:136` plain→terminal; `test_worker_tasks.py:543` retryable→record_retry; `:572` terminal→failed, no partial vectors | classified + rolled back | ✅ |
| RET-13 top-k, anchors, ordering | `test_retrieval.py:180` returns known chunk with `anchor/source_id/section_path/page_span/snippet` | citation-ready top-k | ✅ |
| RET-14 RRF fusion formula | `test_retrieval.py:217-218` `score == 1/(k+1)+1/(k+1)`; `:221` others strictly lower | exact fused sum | ✅ |
| RET-15 NULL-embedding degrade | `test_retrieval.py:234-237` lexical-only returns target, `score==1/(k+1)`, no error | lexical-only, no error | ✅ |
| RET-16 empty result | `test_retrieval.py:249` `results == []` | empty list | ✅ |
| RET-17 source scoping | `test_retrieval.py:280` `result_ids.isdisjoint(b_ids)` (B seeded with a matching chunk) | no cross-source leak | ✅ |
| RET-18 200 evidence | `test_web_retrieval.py:175` 200 + asserts chunk_id/anchor/section_path/snippet/page_span/score AND exact field set (no object_key/checksum) | 200 fused evidence | ✅ |
| RET-19 422 validation | `test_web_retrieval.py:215/223/234/241` empty, whitespace, top_k=0, top_k>max → 422 | 422 before retrieval | ✅ |
| RET-20 404 ownership | `test_web_retrieval.py:252` non-owner → 404; `:265` missing → 404 | 404, no disclosure | ✅ |
| RET-21 auth/CSRF | `test_web_retrieval.py:276` 401; `:284` missing CSRF 403; `:291` invalid CSRF 403; `:300` untrusted Origin 403 | rejected pre-retrieval | ✅ |
| RET-22 empty 200 | `test_web_retrieval.py:318` nonsense query → 200 `results == []` | 200 empty | ✅ |

## Edge cases

| Edge case (spec) | Evidence | ✅ |
|---|---|---|
| Chunks not yet embedded → lexical-only, no error | `test_retrieval.py:224` | ✅ |
| No match → empty list | `test_retrieval.py:240`, `test_web_retrieval.py:318` | ✅ |
| Zero chunks → embed no-op + event count 0 | `test_application_retrieval.py:126` | ✅ |
| Deterministic query embedding (stable ordering) | `test_embeddings_local.py:24` + reproducible retrieval seeds | ✅ |
| Empty/whitespace text → zero vector, no divide-by-zero | `test_embeddings_local.py:52` | ✅ |

## Discrimination sensor (scratch-state mutations, all reverted)

| # | Mutation (`file`) | Expected killer test | Result |
|---|---|---|---|
| M1 | drop lexical RRF term (`retrieval.py`) | `test_retrieval.py::test_both_arm_hit_scores_fused_sum_and_outranks_single_arm` | **killed** (1 failed) |
| M2 | break source scoping `OR TRUE` (`retrieval.py`) | `test_retrieval.py::test_search_is_source_scoped` | **killed** (1 failed) |
| M3 | flip final `ORDER BY` DESC→ASC (`retrieval.py`) | `test_retrieval.py::test_both_arm_hit_scores_fused_sum...` | **killed** (1 failed) |
| M4 | remove L2 normalization (`embeddings/local.py`) | `test_embeddings_local.py::test_non_empty_vector_is_l2_normalized` | **killed** (1 failed) |
| M5 | weaken blank-query validator (`web/retrieval.py`) | `test_web_retrieval.py::test_retrieve_whitespace_query_returns_422` | **killed** (1 failed) |
| M6 | skip `set_embeddings` (`application/retrieval.py`) | `test_worker_tasks.py::test_run_ingestion_embeds_every_chunk_of_the_source` | **killed** (1 failed) |

**Sensor: 6 injected, 6 killed, 0 survived.** Working tree confirmed clean after reverts; full suite re-run green (314 passed).

## Necessary check

Reverse-map: every feature test maps to an AC, a listed edge case, or a Done-when criterion (RET-01..22 + edge cases). No speculative/scope-creep tests found. Two pre-existing `test_worker_tasks.py` event-sequence assertions were correctly updated to include the new `embeddings_built` event (documented in the Phase C summary) — these reflect new correct behavior, not weakened assertions.

## Conclusion

All 22 acceptance criteria are covered with concrete, spec-matching assertions; all edge cases covered; the gate is green and lint-clean; the discrimination sensor confirms the suite kills regressions in every load-bearing component. **PASS — ready to publish.**
