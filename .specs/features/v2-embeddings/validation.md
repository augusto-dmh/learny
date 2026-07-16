# v2-embeddings Validation

**Date**: 2026-07-15
**Spec**: `.specs/features/v2-embeddings/spec.md`
**Diff range**: `main..HEAD` (14 implementation commits, branch `feat/v2-embeddings`)
**Verifier**: independent sub-agent (author ≠ verifier, evidence-or-zero)

---

## Summary

**Overall**: ✅ PASS (ready) — 2 spec-precision notes flagged for hardening, no blockers.

- **Spec-anchored check**: 22/22 ACs COVERED, 0 PARTIAL, 0 GAP. 2 ⚠️ spec-precision notes (EMB-17 resumability depth, EMB-22 recall@5 discrimination).
- **Sensor**: 5 mutations injected, 5 killed, 0 survived.
- **Gate**: 553 passed, 2 skipped (both live-marked, justified), ruff clean.

---

## Spec-Anchored Acceptance Criteria

| AC | Spec-defined outcome | `file:line` + assertion | Result |
| -- | -------------------- | ----------------------- | ------ |
| EMB-01 | one 1536-vector per input in order, `dimensions=1536` sent | `tests/test_embeddings_openai.py:79` `len(vector)==1536` + `:98` `[v[0]...]==[float(i)...]` + `:111` `all(c["dimensions"]==1536)` | ✅ COVERED |
| EMB-02 | sub-batch at ≤2048 inputs AND ≤250k tokens, order preserved | `:118` `==[2048]`, `:122` `==[2048,1]` (input cap); `:133` `==[5,1]` (token cap); `:98`/`:101` order+`[2048,2048,904]` across 3 sub-batches | ✅ COVERED |
| EMB-03 | factory: local→deterministic, openai→OpenAI, unknown→error | `tests/test_embeddings_factory.py:27` isinstance Deterministic, `:41` isinstance OpenAI, `:49` `raises(ValueError, "unknown embedding provider: voyage")` | ✅ COVERED |
| EMB-04 | stable `model` w/o network; det=`local-deterministic@1536`, openai=`text-embedding-3-large@1536` | `tests/test_embeddings_local.py:90` `==local-deterministic@1536`; `tests/test_embeddings_openai.py:68` `==text-embedding-3-large@1536` | ✅ COVERED |
| EMB-05 | fake-client unit tests, live smoke skipped when key unset | whole `test_embeddings_openai.py` drives `_FakeClient`; `:136-140` `@live`+`skipif`; gate shows SKIPPED | ✅ COVERED |
| EMB-06 | ADR-0019 Accepted; openai dep; env+Settings knobs; no SDK leak | ADR `Status: Accepted`; `pyproject.toml` `openai>=1.40,<2`; `.env.example` 4 knobs; `test_config.py:18-37` defaults+override; `test_embeddings_local.py:82` no `openai`/`anthropic` import | ✅ COVERED |
| EMB-07 | nullable `embedding_model`; downgrade removes | `test_migrations.py:594-595` `embedding_model` nullable; `:663` `"embedding_model" not in columns` after downgrade | ✅ COVERED |
| EMB-08 | `search_config text NOT NULL DEFAULT 'simple'` | `test_migrations.py:597-598` `search_config` nullable is False; migration `0007:50-53` | ✅ COVERED |
| EMB-09 | generated→trigger-fed plain tsvector from per-row regconfig, title 'A'>text 'D', backfill, GIN rebuilt | `test_migrations.py:609` GIN rebuilt; `:622-623` insert under 'simple'; `:641-642` `corr` in / `correndo` not in after switching to portuguese (per-row regconfig proven) | ✅ COVERED |
| EMB-10 | pure lang→regconfig, insensitive, unknown/None/blank→simple | `test_text_search.py:24` en/pt/es/fr/de; `:32` pt-BR/pt_br/PT→portuguese; `:38` passthrough; `:45` None/""/xx→simple | ✅ COVERED |
| EMB-11 | `replace` writes `search_config`=resolve(language) per chunk | `test_repositories.py:593` parametrized pt→portuguese, en→english, None→simple, xx→simple | ✅ COVERED |
| EMB-12 | lexical arm uses `websearch_to_tsquery(search_config::regconfig,:q)`, both variants, semantic unchanged, degrade lexical-only | `retrieval.py:70,74,76` both arms use `search_config::regconfig`; single template feeds `_HYBRID_SQL`+`_HYBRID_SQL_ANCHORED`; `test_retrieval.py:246-252` degrade RET-15 | ✅ COVERED |
| EMB-13 | PT inflected query matches under portuguese, misses under english | `test_retrieval.py:373` `target_id in pt_results` ('correr'→'correndo'); `:382` `en_results == []` (same text under english) | ✅ COVERED (killed by M1) |
| EMB-14 | `EmbedCorpus` writes `embedding_model`=adapter.model per chunk | `test_worker_tasks.py:544` `_count_embedded_with_model(..., "local-deterministic@1536")==5`; `retrieval.py` app diff threads `model=self._embeddings.model` | ✅ COVERED (killed by M2) |
| EMB-15 | `set_embeddings` persists vector+model in one write | `test_repositories.py:982-984` reads back `embedding` + `embedding_model=="local-deterministic@1536"` | ✅ COVERED (killed by M2) |
| EMB-16 | `reembed_document` re-embeds via settings provider writing embedding+model | `test_reembed.py:135-137` every row `embedding is not None` and `embedding_model==target` | ✅ COVERED |
| EMB-17 | idempotent AND resumable: select NULL-or-diff-model, commit per batch, no-op when current | `test_reembed.py:165` `writes==[]` (no-op); `:179/:183` stale-model rescue all→0; `test_repositories.py:1021` current→`[]`, `:1030` blank one → exactly that chunk stale (remainder logic); per-batch txn `tasks.py:291-300` | ✅ COVERED ⚠️ (resumability depth — see note) |
| EMB-18 | drop HNSW before, recreate after w/ 0005 params; index serves | `test_reembed.py:198` `_index_exists`, `:200-201` retrieval serves; `tasks.py:246-250` `m=16, ef_construction=64`; verifier empirically confirmed drop+recreate (restored index `m='16', ef_construction='64'`) | ✅ COVERED |
| EMB-19 | after reembed all chunks carry target model + vector, retrieval returns target | `test_reembed.py:135-141` all rows model+vector, `any(anchor=="chap2.xhtml")` | ✅ COVERED |
| EMB-20 | 30–60 hand-labeled pairs, discriminating tokens from target section | `test_eval_labeled.py:16` `30<=len<=60`; `:35` anchors == all golden chapters; `eval_labeled.py` 42 pairs | ✅ COVERED |
| EMB-21 | recall@{1,5}+MRR via real hybrid retrieval + deterministic; snapshot records model+dims | `test_eval_retrieval_metrics.py:105-106` snapshot model+dims pinned, `:93-111` metrics via `retrieve()` real path | ✅ COVERED |
| EMB-22 | assert snapshot meets fixed thresholds (regression gate); live OpenAI variant skipped w/o key | `test_eval_retrieval_metrics.py:109-111` recall@1>=0.9, recall@5>=1.0, mrr>=0.93; `:114-118` `@live`+skipif; gate shows SKIPPED | ✅ COVERED ⚠️ (recall@5 weak — see note) |

**Status**: ✅ All 22 ACs covered with evidence. 2 spec-precision notes flagged (non-blocking).

---

## Discrimination Sensor

| # | File:line | Mutation | Target test | Killed? |
| - | --------- | -------- | ----------- | ------- |
| 1 | `app/application/text_search.py:54` | `resolve_text_search_config` always returns `'english'` | `test_retrieval.py::test_lexical_arm_uses_document_language_regconfig` (EMB-13) | ✅ Killed (`assert UUID in set()` failed) |
| 2 | `app/infrastructure/db/repositories.py:522` | drop `embedding_model=model` from `set_embeddings` write | `test_repositories.py::...set_embeddings_persists_vectors` (EMB-15) + `test_worker_tasks.py::...embeds_every_chunk` (EMB-14) | ✅ Killed (both failed) |
| 3 | `app/infrastructure/embeddings/openai.py:119` | reverse a flushed sub-batch in `embed_documents` | `test_embeddings_openai.py::test_input_order_preserved_across_subbatches` (EMB-02) | ✅ Killed (`2047.0 != 0.0`) |
| 4 | `app/infrastructure/db/repositories.py:496` | `stale_chunks_for_source` returns all chunks always | `test_repositories.py::...stale_chunks...` (EMB-17 selection) + `test_reembed.py::...idempotent...` | ✅ Killed (repo test failed cleanly; reembed idempotency test hangs on infinite loop → never PASSes, terminated) |
| 5 | `app/infrastructure/db/retrieval.py:98` | reverse RRF fusion order (`DESC`→`ASC`) — degrades ranking | `test_eval_retrieval_metrics.py::...test_metrics_meet_thresholds` (EMB-22) | ✅ Killed (recall@1 1.0→0.0, mrr 1.0→0.33) |

**Sensor depth**: lightweight fault-injection (5 behavior-level mutations across the load-bearing new code).
**Result**: 5/5 killed — ✅ PASS. All mutations run in scratch (edit → run → `git checkout --`); working tree clean afterward.

**Sensor finding (EMB-22 discrimination):** under mutation 5 the snapshot showed `recall@5` stayed at **1.0** even with fully reversed ranking. The golden book has 3 chunks (one/chapter) and `top_k=5`, so every returned target trivially fits within top-5 — `recall@5 >= 1.0` cannot detect a ranking regression, only a target being wholly absent. The real regression discrimination is carried by `recall@1 >= 0.9` and `mrr >= 0.93` (both tripped). The gate is meaningful, but recall@5 is near-vacuous on this corpus.

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code / no scope creep | ✅ backend-only slice; deterministic default retained; adapters behind ports |
| Surgical changes / matches patterns | ✅ mirrors prior cycles (fake-client seam, per-conn repos, migration harness) |
| Provider SDK containment (ADR-0007/0009) | ✅ `openai` import isolated to `embeddings/openai.py` (local import); `test_embeddings_local.py` asserts no SDK leak |
| Spec-anchored asserted values match spec | ✅ every AC's test asserts the spec-defined value/state |
| Every test maps to a spec AC / Done-when | ✅ no unclaimed tests observed in the diff surface |
| Documented guidelines followed | pgvector-hybrid-search / celery-workers skills, ADR-0006/0007/0019 |

---

## Edge Cases

- [x] Empty input list → `embed_documents([]) == []`, no request (`test_embeddings_openai.py:83-87`).
- [x] Single oversized input still gets its own request (batch-empty flush guard, `openai.py:115`).
- [x] Not-yet-embedded corpus degrades to lexical-only (`test_retrieval.py:239-252`, RET-15).
- [x] Unknown/None/blank language → `simple`, never raises (`test_text_search.py:45`).
- [x] Fully-current source → reembed no-op, index survives write-free drop+recreate (`test_reembed.py:144-167`).
- [x] HNSW drop/recreate idempotent under redelivery (`IF EXISTS`/`IF NOT EXISTS`, `tasks.py:245-250`).

---

## Gate Check

- **Gate command**: `LEARNY_TEST_DATABASE_URL=... uv run pytest -q` + `uv run ruff check .`
- **Result**: 553 passed, 0 failed, 2 skipped. Ruff: All checks passed.
- **Skipped (justified)**: `test_embeddings_openai.py:136` live OpenAI smoke (no key); `test_eval_retrieval_metrics.py:143` live OpenAI metrics (no key). Both are `@pytest.mark.live` + `skipif` — the CI-offline contract (EMB-05/22).
- **Test integrity**: net +new tests across the feature diff (embeddings factory/openai/config, text_search, migration 0007, reembed, eval labeled/metrics, retrieval F8, repositories stale/model). No test count decrease; no assertions weakened.
- **DB state**: HNSW index confirmed present after the run (`m='16', ef_construction='64'`) — restored after mutation 4's mid-run termination via a final full-suite pass.

---

## Notes for hardening (non-blocking, ranked)

1. **EMB-22 — recall@5 is a vacuous discriminator on the golden book.** With 3 chunks and `top_k=5`, `recall@5` is always 1.0 for any query that returns its target at all; it cannot catch a ranking regression (mutation 5 confirmed). The gate still bites via `recall@1`/`mrr`. Consider (a) documenting recall@5 as an "absent-target" guard only, or (b) enlarging the golden corpus / lowering `top_k` below chunk count so recall@k measures ranking. — evidence: sensor mutation 5, `test_eval_retrieval_metrics.py:41-43,110`.
2. **EMB-17 — resumability (per-batch-committed partial progress) is inferred, not integration-tested end-to-end.** `embedding_batch_size=128` and the fixtures have ≤5 chunks, so the reembed loop always runs a single batch; the "re-run finishes the remainder after a partial completion" guarantee is proven only via the unit stale-selection remainder test (`test_repositories.py:1024-1030`) + per-batch-commit structure, never by an interrupted multi-batch run. Consider a test that seeds >batch_size chunks (or a small batch_size) and interrupts mid-pass. — evidence: `tasks.py:291-300`, `test_reembed.py:144-187`.

---

## Requirement Traceability Update

| Requirement | New Status |
| ----------- | ---------- |
| EMB-01..22  | ✅ Verified (22/22 covered; EMB-17, EMB-22 carry hardening notes) |
