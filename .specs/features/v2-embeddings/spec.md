# Spec — v2-embeddings (RFC-002 Cycle B)

Real retrieval: swap the deterministic embedding baseline for a real cloud model
(OpenAI `text-embedding-3-large@1536`) behind the existing `EmbeddingPort`, add
per-chunk model versioning, make Postgres full-text search language-aware (fixes
QA finding **F8**), add an idempotent `reembed_document` Celery task, and add a
tier-2 retrieval eval (recall@k / MRR) over hand-labeled pairs.

Extends the Cycle-5 substrate (`EmbeddingPort`, deterministic adapter, hybrid RRF
retrieval, Celery ingestion). Does not rebuild it. **Backend-only slice** — no
frontend product change (retrieval quality is infrastructure; precedent
AD-023/AD-039/AD-050). The deterministic adapter stays the CI/test default so the
suite runs offline with no API key.

Requirement source: `docs/rfc/0002-learny-v2-roadmap.md` §"Cycle B" and
`docs/research/2026-07-12/embeddings.md`.

## Acceptance Criteria

### Phase A — OpenAI adapter + provider selection + ADR (no DB)

- **EMB-01** — `OpenAIEmbeddingAdapter` implements `EmbeddingPort`
  (`embed_query`, `embed_documents`, `model`) using the official `openai` SDK,
  model `text-embedding-3-large` with request param `dimensions=1536`, returning
  one 1536-length vector per input **in input order**.
- **EMB-02** — `embed_documents` sub-batches to **≤2048 inputs and ≤250k tokens**
  per API request (token headroom under OpenAI's 300k cap), concatenating
  sub-batch results so overall input order is preserved regardless of input size.
- **EMB-03** — A composition-root factory returns the adapter named by
  `LEARNY_EMBEDDING_PROVIDER`: `local` (default) → `DeterministicEmbeddingAdapter`;
  `openai` → `OpenAIEmbeddingAdapter` built from settings (API key, model, dims).
  An unrecognized value raises a clear configuration error, not a silent default.
- **EMB-04** — `EmbeddingPort` exposes a stable `model: str` readable without a
  network call; deterministic = `local-deterministic@1536`, openai =
  `text-embedding-3-large@1536` (encodes model **and** dims, since large@1536 ≠
  large@3072).
- **EMB-05** — OpenAI adapter behaviour (batching, dims param, order) is unit
  tested against a **mocked/fake SDK client** with no network; a
  `@pytest.mark.live` smoke exercising the real API is **skipped** when
  `LEARNY_OPENAI_API_KEY` is unset (so CI stays offline).
- **EMB-06** — ADR-0019 records the provider decision **Accepted**; `openai` is
  added to backend deps; `.env.example` + `Settings` document the new knobs
  (`LEARNY_EMBEDDING_PROVIDER`, `LEARNY_OPENAI_API_KEY`, `LEARNY_EMBEDDING_MODEL`
  updated intent). No provider SDK leaks past the adapter (ADR-0007/0009).

### Phase B — schema + language-aware FTS / F8 (DB)

- **EMB-07** — Migration adds nullable `embedding_model text` to `corpus_chunks`;
  `downgrade` removes it and restores the prior shape.
- **EMB-08** — Migration adds `search_config text NOT NULL DEFAULT 'simple'` to
  `corpus_chunks` (the resolved Postgres text-search regconfig for the chunk).
- **EMB-09** — Migration replaces the hardcoded-`english` **generated**
  `search_vector` with a plain `tsvector` maintained by a `BEFORE INSERT OR UPDATE`
  trigger that builds it from the row's `search_config` regconfig — deepest TOC
  title (`section_path ->> -1`) weight `'A'` over `text` weight `'D'`; existing
  rows are backfilled (fire the trigger); the GIN index is rebuilt over the new
  column. (A STORED generated column cannot use a per-row regconfig — the
  expression must be IMMUTABLE — so a trigger is the mechanism.)
- **EMB-10** — `resolve_text_search_config(language)` (pure) maps a `dc:language`
  value's primary subtag to a built-in Postgres regconfig
  (`en`→`english`, `pt`→`portuguese`, `es`→`spanish`, …); unknown/`None`/blank →
  `simple`; case- and separator-insensitive (`pt-BR`, `pt_br`, `PORTUGUESE`).
- **EMB-11** — `CorpusRepository.replace` writes each chunk's `search_config` =
  `resolve_text_search_config(document language)` — a Portuguese book's chunks get
  `portuguese`, an English book's `english`, an unknown/absent language `simple`.
- **EMB-12** — The hybrid retrieval **lexical arm** matches and ranks with
  `websearch_to_tsquery(search_config::regconfig, :q)` sourced from each chunk's
  own trusted `search_config` column (no new port parameter, no interpolation of
  untrusted input); both the whole-source and anchored SQL variants use it; the
  semantic arm is unchanged; a not-yet-embedded corpus still degrades to
  lexical-only (RET-15).
- **EMB-13** — Integration proof of F8: a Portuguese mini-corpus returns the
  target chunk for a query using an inflected Portuguese form that the old
  `english` config stems differently and would miss/mis-rank.

### Phase C — reembed task + model write (DB)

- **EMB-14** — During ingestion, `EmbedCorpus` writes `embedding_model` (=
  the active adapter's `model`) alongside each chunk vector.
- **EMB-15** — `EmbeddingIndexRepository.set_embeddings` persists both the vector
  and the model string per chunk in one write.
- **EMB-16** — `reembed_document(source_id)` Celery task re-embeds the source's
  chunks through the settings-selected provider, writing `embedding` +
  `embedding_model`.
- **EMB-17** — reembed is **idempotent and resumable**: it selects only chunks
  whose `embedding IS NULL` or `embedding_model` differs from the target model, and
  commits **per batch**; a re-run after a partial completion finishes the
  remainder, and a fully-current source is a no-op (no rows rewritten).
- **EMB-18** — reembed **drops the HNSW index before** the bulk write and
  **recreates it after** with the same params as migration 0005; the index exists
  and serves the semantic arm afterward.
- **EMB-19** — Integration: after `reembed_document`, every chunk carries the
  target model and a non-null vector, and hybrid retrieval returns the target.

### Phase D — tier-2 retrieval eval (DB)

- **EMB-20** — 30–60 hand-labeled `(query → expected_anchor)` pairs over the
  golden book are defined as reviewable code (`tests/eval_labeled.py`), each
  query's discriminating tokens drawn from its target section.
- **EMB-21** — recall@k (k∈{1,5}) and MRR are computed over the labeled set via
  the **real hybrid retrieval** + deterministic adapter; a snapshot records the
  model+dims identity alongside the metric values.
- **EMB-22** — The eval asserts the snapshot meets fixed thresholds (a retrieval
  regression gate); a `@pytest.mark.live` variant recomputes the metrics under
  OpenAI when `LEARNY_OPENAI_API_KEY` is set and is skipped otherwise.

## Out of scope (recorded, deferred)

- No frontend/product change; no HTTP endpoint for reembed (ops-invoked task).
- The committed tier-2 snapshot is under `local-deterministic@1536` (CI is
  offline). Producing/committing the real `text-embedding-3-large@1536` snapshot
  is a **keyed follow-up** (or Cycle C's live smoke) — the harness + labeled pairs
  land now (flagged at the merge gate).
- No change to the `vector(1536)` column type; Voyage-4 (1024/2048 dims) is
  recorded in the ADR as the alternative, not adopted.

## Traceability

Requirements EMB-01..22 map to tasks in `tasks.md`; decisions in `context.md`
(AD-051..AD-057). Non-regression: the existing 506-test suite stays green.
