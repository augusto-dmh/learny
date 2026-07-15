# Learny v2 research — followup-eval-embedding-model

Generated 2026-07-12 by a web-research agent (v2 planning research fleet). Sources/dates inline; verify load-bearing claims before implementation.

---

## GAP RESOLUTION: Which embedding model do the retrieval eval snapshots and recall@k thresholds run against?

### Decisive answer

**Neither, today — and going forward they must run against `text-embedding-3-large` @ `dimensions=1536`, the locked production model.** The apparent conflict between the two reports is a real inconsistency in the *reports*, not in the code: the evaluation report's `text-embedding-3-small` ($0.02/M) figures should be treated as cost illustrations only and re-baselined. Recall@k measured under one embedding model says nothing about recall under another; an eval gate is only valid against the exact model+dimensions that production retrieval uses.

### What the codebase actually does (verified 2026-07-12)

- The retrieval eval harness (`/home/augusto/projects/learny/backend/tests/eval_runner.py`) is explicitly deterministic and offline: it composes the real ingestion/retrieval pipeline with `DeterministicEmbeddingAdapter` — no OpenAI model at all.
- `/home/augusto/projects/learny/backend/app/infrastructure/embeddings/local.py` is a hash-based (blake2b bag-of-tokens) adapter, L2-normalized, `LEARNY_EMBEDDING_DIM`-length (1536 default). Its own docstring says swapping in a cloud model is "an adapter + re-index change."
- `/home/augusto/projects/learny/backend/tests/test_golden_retrieval.py` asserts rank-1 recall ("recall_target_is_top_ranked") for golden queries whose content tokens appear only in the target chunk — i.e., the current "recall@k thresholds" are **structural pipeline checks under the hash adapter**, not model-quality measurements. There are no stored eval snapshots tied to any OpenAI model yet.

So nothing currently baselines on `text-embedding-3-small`; that model appears only in the earlier research report's cost math. The gap is resolved by declaring one eval baseline for v2.

### The v2 eval baseline (recommendation)

**Two-tier eval, one production model:**

1. **Tier 1 — CI golden fixtures (keep as-is).** Deterministic adapter, network-free, gates every PR. These test pipeline correctness (chunking, RRF fusion, citation anchors, SQL), which is model-independent. Do **not** point CI at OpenAI — that would make CI flaky, non-hermetic, and cost-bearing for zero signal about pipeline regressions.
2. **Tier 2 — model-quality eval (new, opt-in).** A separate runner (env-gated, e.g. `LEARNY_EVAL_LIVE=1`) that embeds the golden corpus with **`text-embedding-3-large`, `dimensions=1536`**, indexes into the test pgvector DB, and records recall@k / MRR snapshots. All recorded thresholds, snapshots, and cost projections must name the model + dimensions in the snapshot metadata (e.g. `{"model": "text-embedding-3-large", "dimensions": 1536}`) so a future model swap invalidates them loudly instead of silently.

**Rule to write down (ADR/eval doc):** *eval snapshots are only valid for the (model, dimensions) pair they were generated with; changing either requires re-embedding the eval corpus and re-baselining thresholds.* This is the same reason production requires full re-index on model change — vectors from different models are not comparable, and even the same model at different `dimensions` values produces non-interchangeable vectors.

### Why 3-large@1536 and not 3-small (the report conflict, adjudicated)

- Both v3 models support Matryoshka-style shortening via the `dimensions` parameter; OpenAI's guide states shortened embeddings keep their "concept-representing properties," and `text-embedding-3-large` cut all the way to **256** dims still outperforms full ada-002@1536 on MTEB ([OpenAI embeddings guide](https://developers.openai.com/api/docs/guides/embeddings), fetched 2026-07-12). `3-large@1536` sits well above `3-small@1536` (full-dim MTEB: **64.6% vs 62.3%**, same source) — the embeddings report's lock is sound: large-model quality at small-model storage (1536 dims fits the existing pgvector column and HNSW index with zero schema change).
- Cost delta is real but immaterial at Learny's scale: **$0.13/M vs $0.02/M standard; $0.065/M vs $0.01/M via Batch API** ([developers.openai.com model page](https://developers.openai.com/api/docs/models/text-embedding-3-small); corroborated [TokenMix pricing summary, 2026](https://tokenmix.ai/blog/openai-embedding-pricing)). A full book ≈ 150k tokens ≈ **$0.02 to embed with 3-large** (vs $0.003 with small). The eval corpus is a fraction of that. A 6.5× multiplier on ~pennies is not a reason to run eval on a different model than production — that would be the one genuinely wrong option.
- Therefore: **update the evaluation report's cost table to 3-large@1536 pricing** and delete/annotate the 3-small baseline. If 3-small figures are kept at all, label them "rejected alternative."

### Concrete actions

1. Record in the v2 embedding ADR: production **and** model-quality eval both pin `text-embedding-3-large`, `dimensions=1536`; snapshot metadata must embed the pair.
2. Keep `DeterministicEmbeddingAdapter` as the CI-tier eval model; never gate CI on live embeddings.
3. When the OpenAI adapter lands, generate the first Tier-2 recall@k snapshot with 3-large@1536 and set thresholds from that run (not from any 3-small or hash-adapter numbers).
4. Use the **Batch API ($0.065/M)** for bulk eval-corpus and book re-embedding jobs — they're already async Celery work, a natural fit.

**Uncertainty flags:** MTEB figures are OpenAI's self-reported numbers from the model launch (Jan 2024) and the current docs; no official published recall figure exists for 3-large specifically at 1536 dims (only at 256 and 3072) — expected quality at 1536 is interpolated but directionally safe. Pricing verified via the model docs page and third-party trackers dated July 2026; the pricing page itself no longer lists embeddings inline.

Sources: [OpenAI embeddings guide](https://developers.openai.com/api/docs/guides/embeddings) · [text-embedding-3-small model page](https://developers.openai.com/api/docs/models/text-embedding-3-small) · [OpenAI launch post](https://openai.com/index/new-embedding-models-and-api-updates/) (403 on fetch; scores corroborated via guide) · [TokenMix pricing 2026](https://tokenmix.ai/blog/openai-embedding-pricing)
