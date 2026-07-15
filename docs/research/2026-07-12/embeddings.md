# Learny v2 research — embeddings

Generated 2026-07-12 by a web-research agent (v2 planning research fleet). Sources/dates inline; verify load-bearing claims before implementation.

---

# Real Embeddings for Learny's EmbeddingPort — Research Report (2026-07-12)

## Recommendation (TL;DR)

**Use OpenAI `text-embedding-3-large` with `dimensions=1536`** (fits the existing `vector(1536)` column, no schema change to the vector column), embed documents in batches of ≤2048 inputs / ≤300k tokens per request, store `embedding_model` per chunk, and re-embed via an idempotent per-document Celery task with drop-and-recreate of the HNSW index. Cost is trivial (~$0.04/book). If you're ever willing to change the column to `vector(1024)`, **Voyage `voyage-4`** is measurably better (especially multilingual) and effectively free at your scale — but it does **not** offer 1536 dims, so it forces a schema migration; the locked OpenAI decision stands comfortably.

---

## 1. OpenAI embeddings (official docs, fetched 2026-07-12)

**Pricing** ([openai.com announcement](https://openai.com/index/new-embedding-models-and-api-updates/), [developers.openai.com models pages](https://developers.openai.com/api/docs/models/text-embedding-3-small)):
- `text-embedding-3-small`: **$0.02 / 1M tokens** (Batch API: $0.01). Default **1536 dims** — drop-in for your `vector(1536)` column.
- `text-embedding-3-large`: **$0.13 / 1M tokens** (Batch API: $0.065). Default **3072 dims**.

**Dimensions parameter** ([embeddings guide](https://developers.openai.com/api/docs/guides/embeddings)): both v3 models support the `dimensions` request parameter (Matryoshka-style shortening). **Yes, `-large` can be truncated to 1536** — the API returns already-renormalized vectors at the requested size; OpenAI states `-large` shortened even to 256 dims still beats full-size ada-002. `-small` at its native 1536 fits your column with no parameter needed. Caveat: if you ever truncate *manually* (client-side slice), you must re-normalize; via the API `dimensions` param you don't.

**Request limits** ([API reference, create embeddings](https://developers.openai.com/api/reference/resources/embeddings/methods/create)):
- Max **8,192 tokens per input** (a ~800-token chunk is nowhere near this).
- Max **2,048 inputs per request**.
- Max **300,000 tokens summed across all inputs per request**.
- `encoding_format`: `float` (default) or `base64` (base64 halves payload size; the official Python SDK uses it transparently).

**Rate limits** (tier-based, verify in your dashboard — [community/aggregator sources](https://community.openai.com/t/rate-limits-for-new-embedding-v3-models/618110), approximate as of early 2026): Tier 1 ≈ **1,000,000 TPM / 3,000 RPM** for embedding models. A whole book (~320k tokens) fits in ~2 requests and well under one minute of quota. *(Flagged: exact per-tier numbers only visible in your account settings.)*

**Query vs document**: OpenAI v3 models are **symmetric** — no `input_type` distinction; embed queries and documents identically with the same model+dims. (Contrast with Voyage, below.)

## 2. Voyage AI — credible alternative? (official docs, fetched 2026-07-12)

Anthropic officially points to Voyage: "Anthropic does not offer its own embedding model… one embeddings provider… is Voyage AI" ([platform.claude.com embeddings guide](https://platform.claude.com/docs/en/build-with-claude/embeddings)).

**Current generation is voyage-4** (announced [2026-01-15](https://blog.voyageai.com/2026/01/15/voyage-4/)) — `voyage-4-large`, `voyage-4`, `voyage-4-lite`, plus open-weight `voyage-4-nano`. All: 32k context, dims **1024 (default), 256, 512, 2048** — **note: no 1536 option**. Quantization via `output_dtype` (`float`, `int8`, `binary`…) ([docs.voyageai.com/docs/embeddings](https://docs.voyageai.com/docs/embeddings)).

**Pricing** ([docs.voyageai.com/docs/pricing](https://docs.voyageai.com/docs/pricing)): `voyage-4-large` $0.12/M, `voyage-4` $0.06/M, `voyage-4-lite` $0.02/M — each with **200M free tokens** (≈600+ books free at your scale).

**Quality claims** (Voyage's own benchmarks, [voyage-4 blog](https://blog.voyageai.com/2026/01/15/voyage-4/)): `voyage-4-large` beats OpenAI-v3-large by **~14% NDCG@10** on their 29-dataset RTEB benchmark; explicitly optimized for multilingual retrieval. Vendor-reported — treat direction as credible, magnitude with salt.

**Rate limits** ([docs.voyageai.com/docs/rate-limits](https://docs.voyageai.com/docs/rate-limits)): Tier 1 `voyage-4`: 8M TPM / 2000 RPM. Batch: max **1,000 texts** per request, 320K total tokens (`voyage-4`).

**SDK**: official [`voyageai` Python package](https://github.com/voyage-ai/voyageai-python), mature, simple `vo.embed(texts, model=…, input_type="document"|"query")`. Voyage is **asymmetric**: Anthropic's guide says "Do not omit `input_type`" — it prepends retrieval prompts to queries vs documents.

**Verdict**: credible, arguably better, effectively free — but the 1024/2048-only dims break your `vector(1536)` column, and per the locked v2 decision (OpenAI embeddings), **stick with OpenAI**. Record Voyage as the named alternative in the ADR; the EmbeddingPort abstraction makes a later swap a config + re-embed exercise.

## 3. Migration mechanics

**Schema (Alembic)**
- Add `embedding_model TEXT NOT NULL` (e.g. `"text-embedding-3-large@1536"` — encode model *and* dims, since large@1536 ≠ large@3072) and optionally `embedded_at` on the chunk-embedding row. Keep `vector(1536)` unchanged.
- Retrieval invariant: query embedding **must** use the same model string as the chunks it searches. Enforce with a `WHERE embedding_model = :current_model` filter (or an assertion at startup that no stale rows exist for active corpora).

**Adapter**
- New `OpenAIEmbeddingAdapter(EmbeddingPort)` in infrastructure; settings-driven (`EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, API key). Keep the deterministic adapter as the default for tests/CI so the suite stays network-free — exactly the pattern you already have.

**Celery re-embed task** (fits existing worker conventions: Postgres is source of truth, Redis is transport)
- `reembed_document(document_id)`: loads chunks where `embedding_model != target`, batches greedily up to min(2048 inputs, ~250k tokens — leave headroom under the 300k cap), calls the port, bulk-updates rows + model string per batch, commits per batch → **idempotent and resumable** (retry re-selects only unfinished chunks).
- Retries with exponential backoff on 429/5xx (`autoretry_for`, `retry_backoff=True`), `acks_late=True`, sane `time_limit`. A dispatcher task fans out one task per document.
- Since the current deterministic vectors carry no semantics, there's **no dual-column/dual-read phase needed**: re-embed in place, per document, and accept briefly-mixed state guarded by the model filter above.

**HNSW rebuild** (pgvector)
- HNSW indexes update incrementally on UPDATE, but a full-corpus rewrite is faster and yields a better graph if you **drop the index → bulk update → `CREATE INDEX` (raise `maintenance_work_mem` for the build)**. At hobby scale (tens of thousands of rows) either path takes seconds–minutes; use `CREATE INDEX CONCURRENTLY` only if the app must stay live during migration.
- Constraint worth recording: pgvector HNSW indexes `vector` up to **2,000 dims** — full-size `-large` (3072) would need `halfvec`. Another reason 1536 is the sweet spot.

**Cost table — one typical book (~400 chunks × 800 tok = 320k tokens) and a 50-book library (16M tokens):**

| Model @ dims | $/1M tok | Per book | 50 books |
|---|---|---|---|
| OpenAI 3-small @1536 | $0.02 | $0.0064 | $0.32 |
| **OpenAI 3-large @1536** | **$0.13** | **$0.042** | **$2.08** |
| voyage-4-lite @1024 | $0.02 | $0.0064 (free ≤200M) | $0 |
| voyage-4 @1024 | $0.06 | $0.019 (free ≤200M) | $0 |
| voyage-4-large @1024/2048 | $0.12 | $0.038 (free ≤200M) | $0 |

Cost is a non-factor; choose on quality + schema fit. `-large@1536` costs ~4 cents/book and materially outperforms `-small` (see multilingual next). Batch API halves cost but adds async complexity — skip it.

## 4. Multilingual (Portuguese)

- The deterministic hash baseline has **zero semantics in any language** — any real model is a step-change, and PT is where it will show most (hash collisions treat inflected PT forms as unrelated).
- OpenAI v3 MIRACL (multilingual retrieval benchmark incl. Portuguese): **`-small` 44.0 vs `-large` 54.9** (ada-002 was 31.4) ([OpenAI announcement, Jan 2024](https://openai.com/index/new-embedding-models-and-api-updates/)). That gap is the main argument for `-large@1536` over `-small` given PT-primary content. Voyage-4 claims stronger multilingual still ([blog](https://blog.voyageai.com/2026/01/15/voyage-4/)) — vendor-reported.
- **Postgres FTS: yes, make the regconfig per-document.** The `'english'` config's Snowball stemmer mangles Portuguese (wrong stems, English stopwords ignored, PT stopwords indexed), degrading the lexical leg of your RRF fusion. Postgres ships a built-in `'portuguese'` config ([PostgreSQL FTS docs](https://www.postgresql.org/docs/current/textsearch-dictionaries.html)). Plan: add `language` to the document record (from EPUB `dc:language` metadata, fallback `'simple'`), denormalize it onto chunk rows so the tsvector generated column can reference it (generated columns can't join), regenerate tsvectors + GIN index in the same migration, and use the same regconfig in `websearch_to_tsquery(doc_language, :q)` at query time. Semantic leg needs nothing — embedding models are language-agnostic at query time.

## 5. Actionable sequence

1. ADR: `text-embedding-3-large`, `dimensions=1536`, Voyage-4 recorded as alternative; per-chunk `embedding_model` versioning.
2. Alembic: `embedding_model` column + document/chunk `language` + regconfig-aware tsvector regeneration.
3. `OpenAIEmbeddingAdapter` (batching ≤2048 inputs/≤250k tokens, base64 encoding via SDK, tenacity-free — rely on Celery retries).
4. Celery `reembed_document` fan-out; drop/recreate HNSW around the bulk run.
5. Golden-fixture retrieval eval before/after (you already have the fixture harness) — especially PT queries.

Uncertain/verify-at-implementation: exact OpenAI Tier-1 RPM/TPM for your account (dashboard-only); Voyage RTEB margins are vendor benchmarks.

Sources: [OpenAI embeddings guide](https://developers.openai.com/api/docs/guides/embeddings) · [OpenAI create-embeddings API ref](https://developers.openai.com/api/reference/resources/embeddings/methods/create) · [OpenAI new embedding models announcement](https://openai.com/index/new-embedding-models-and-api-updates/) · [text-embedding-3-small model page](https://developers.openai.com/api/docs/models/text-embedding-3-small) · [OpenAI community: v3 rate limits](https://community.openai.com/t/rate-limits-for-new-embedding-v3-models/618110) · [Anthropic embeddings guide](https://platform.claude.com/docs/en/build-with-claude/embeddings) · [Voyage embeddings docs](https://docs.voyageai.com/docs/embeddings) · [Voyage pricing](https://docs.voyageai.com/docs/pricing) · [Voyage rate limits](https://docs.voyageai.com/docs/rate-limits) · [Voyage-4 blog (2026-01-15)](https://blog.voyageai.com/2026/01/15/voyage-4/) · [voyageai-python](https://github.com/voyage-ai/voyageai-python) · [PostgreSQL FTS dictionaries](https://www.postgresql.org/docs/current/textsearch-dictionaries.html)
