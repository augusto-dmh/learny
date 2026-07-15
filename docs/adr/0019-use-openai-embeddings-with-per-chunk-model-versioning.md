# ADR-019: Use OpenAI Embeddings With Per-Chunk Model Versioning

- **Date**: 2026-07-15
- **Status**: Accepted
- **Deciders**: Augusto, Codex
- **Tags**: architecture, ai, embeddings, retrieval, openai, voyage, versioning

## Context and Problem Statement

The MVP shipped with a deterministic, network-free embedding adapter behind the
Learny-owned `EmbeddingPort` (ADR-0007). Its hashed bag-of-tokens vectors carry no
semantics in any language, which caps retrieval quality — most visibly for the
Portuguese-primary content the product targets, where hash collisions treat
inflected forms as unrelated. RFC-002 Cycle B replaces that baseline with a real
cloud embedding model.

The decisions to make are: which provider and model, at what vector dimensionality
(the corpus column is `vector(1536)`), and how to keep retrieval correct while
embeddings are regenerated — a query embedding must be compared only against chunk
vectors produced by the same model and dimensionality, and re-embedding a library
proceeds document by document, so mixed model states are unavoidable in flight.

Research evidence: `docs/research/2026-07-12/embeddings.md`.

## Decision Drivers

- Fit the existing `vector(1536)` column with no vector-column migration.
- Materially improve retrieval quality over the deterministic baseline, especially
  multilingual (Portuguese) retrieval.
- Keep the provider SDK and model name behind the `EmbeddingPort` adapter
  (ADR-0007/0009) — no provider leak into query/repository/domain code.
- Keep CI and local development offline and key-free by default.
- Make re-embedding idempotent and resumable, and make stale vectors detectable so
  a query never fuses vectors from a different model.
- Keep operating cost negligible at hobby scale.

## Considered Options

- OpenAI `text-embedding-3-large` with `dimensions=1536`.
- OpenAI `text-embedding-3-small` at its native 1536 dims.
- Voyage AI `voyage-4` (1024 default / 2048 dims).
- Keep the deterministic adapter as the only embedding path.

## Decision Outcome

Chosen option: **OpenAI `text-embedding-3-large` with request parameter
`dimensions=1536`**, because it fits the existing `vector(1536)` column with no
vector-column migration, is the strongest multilingual option among the 1536-dim
choices (MIRACL: `-large` 54.9 vs `-small` 44.0), and costs about four cents per
book — a non-factor at Learny's scale.

The implementation model is:

1. Add an `OpenAIEmbeddingAdapter` implementing `EmbeddingPort` behind the existing
   seam; the `openai` SDK is imported only inside that adapter module.
2. Select the adapter at the composition root from `LEARNY_EMBEDDING_PROVIDER`
   (`local` → deterministic, `openai` → the OpenAI adapter built from key/model/dims).
   An unrecognized value is a loud configuration error, never a silent default.
3. **Version embeddings per chunk.** Each chunk stores an `embedding_model` string
   that encodes model **and** dimensionality (`text-embedding-3-large@1536`), since
   `large@1536` and `large@3072` are different vector spaces. Retrieval treats a
   chunk as embedded only when its model matches the active adapter's identity, so a
   mixed state during re-embedding degrades gracefully to lexical-only rather than
   fusing incompatible vectors.
4. Re-embed document by document through an idempotent, resumable Celery task that
   selects only chunks whose vector is null or whose `embedding_model` differs from
   the target, commits per batch, and drops/recreates the HNSW index around the bulk
   write. (These land across Cycle B's later phases; this ADR records the direction.)
5. Retain the deterministic adapter as the CI/local default (`LEARNY_EMBEDDING_PROVIDER=local`),
   so the suite stays network-free and no key is required to run or test Learny.

Provider keys stay environment-only; no key is committed.

### Positive Consequences

- Real semantic retrieval, with the largest gain on multilingual content.
- No vector-column migration — the `dimensions=1536` request fits `vector(1536)`,
  and 1536 stays under pgvector's 2000-dim HNSW limit (3072 would need `halfvec`).
- Per-chunk model versioning makes stale vectors detectable and re-embedding safe to
  interrupt and resume.
- CI/local stays offline and key-free; swapping providers later is a settings +
  re-embed exercise, not a code rewrite.
- Negligible cost (~$0.04/book; ~$2 for a 50-book library).

### Negative Consequences

- A real provider dependency, key management, and rate/latency considerations enter
  the ingestion path (mitigated by keeping retries in Celery, not the adapter).
- Re-embedding an existing library is an operational step with a transient mixed
  state (bounded by the model-match filter).
- `text-embedding-3-large@1536` is a truncated (Matryoshka) representation; the API
  returns renormalized vectors, so this is acceptable, but full-size `-large` would
  be marginally stronger at the cost of a column change.

## Pros and Cons of the Options

### OpenAI `text-embedding-3-large` @ 1536 ✅ Chosen

- ✅ Fits `vector(1536)` — no vector-column migration.
- ✅ Best multilingual quality among the 1536-dim options (MIRACL 54.9).
- ✅ Symmetric model — queries and documents embed identically, no `input_type`.
- ❌ Truncated representation; slightly below full-size `-large` (3072).

### OpenAI `text-embedding-3-small` @ 1536

- ✅ Native 1536 dims (no `dimensions` parameter needed); cheapest OpenAI option.
- ✅ Fits the column with no migration.
- ❌ Materially weaker multilingual retrieval (MIRACL 44.0 vs 54.9) — the wrong
  trade for Portuguese-primary content when cost is already trivial.

### Voyage AI `voyage-4` (1024 / 2048 dims)

- ✅ Vendor benchmarks claim stronger multilingual retrieval; effectively free at
  Learny's scale (200M free tokens); Anthropic's recommended embeddings provider.
- ❌ Offers no 1536-dim option — 1024 or 2048 would force a `vector` column
  migration and HNSW rebuild.
- ❌ Asymmetric — requires `input_type` for queries vs documents, more adapter care.
- Recorded as the named alternative: the `EmbeddingPort` abstraction makes a later
  switch a config + re-embed exercise if the column change is ever justified.

### Keep only the deterministic adapter

- ✅ Zero dependency, zero cost, fully offline.
- ❌ No semantics in any language — retrieval quality is capped; unacceptable as the
  product retrieval path. Retained only as the CI/local default.

## References

- [ADR-006: Use PostgreSQL Hybrid Search With pgvector And Full-Text Search](0006-use-postgresql-hybrid-search-with-pgvector-and-full-text.md)
- [ADR-007: Use Learny-Owned Ports For AI Provider Integration](0007-use-learny-owned-ports-for-ai-provider-integration.md)
- [ADR-009: Use Learny-Owned Orchestration With Specialized Edge Libraries](0009-use-learny-owned-orchestration-with-specialized-edge-libraries.md)
- [RFC-002: Learny v2 Roadmap](../rfc/0002-learny-v2-roadmap.md)
- Embeddings research (2026-07-12): `../research/2026-07-12/embeddings.md`
- OpenAI embeddings guide: https://developers.openai.com/api/docs/guides/embeddings
- OpenAI create-embeddings API reference: https://developers.openai.com/api/reference/resources/embeddings/methods/create
- OpenAI new embedding models announcement: https://openai.com/index/new-embedding-models-and-api-updates/
- Voyage-4 announcement (2026-01-15): https://blog.voyageai.com/2026/01/15/voyage-4/
- Anthropic embeddings guide (Voyage): https://platform.claude.com/docs/en/build-with-claude/embeddings
