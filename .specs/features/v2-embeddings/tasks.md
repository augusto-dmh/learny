# Tasks — v2-embeddings (RFC-002 Cycle B)

One atomic commit per task; gate = full backend suite (`uv run pytest -q`, DB up) +
`uv run ruff check .` green before a task is done. Tests derive from the EMB-NN
acceptance criteria. Phases run sequentially (B depends on A's factory; C depends on
B's columns; D depends on B+C). Env: `LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test`,
`uv` at `/home/augusto/myenv/bin/uv`.

## Phase A — OpenAI adapter + provider selection + ADR (no DB)

- **A1 — settings + deps + env** (EMB-06): add `embedding_provider`,
  `openai_api_key`, `embedding_model` (→`text-embedding-3-large`),
  `embedding_dimensions` to `Settings`; document in `.env.example`; add
  `openai>=1.40,<2` to `pyproject.toml`; `uv sync`. Test: settings defaults +
  env-override.
- **A2 — EmbeddingPort.model + deterministic identity** (EMB-04): add `model: str`
  to the `EmbeddingPort` Protocol; `DeterministicEmbeddingAdapter.model` →
  `local-deterministic@{dim}`. Test: identity string.
- **A3 — OpenAIEmbeddingAdapter** (EMB-01/02/05): new `openai.py`; fake-client unit
  tests for input-order preservation, `dimensions=1536` passed, sub-batching at the
  2048-input and 250k-token boundaries, `model` identity, empty-list; a
  `@pytest.mark.live` smoke skipped without `LEARNY_OPENAI_API_KEY`.
- **A4 — provider factory + wiring** (EMB-03): `build_embedding_adapter(settings)`;
  unknown provider → `ValueError`; rewire the deterministic-adapter composition
  roots (`worker/tasks._build_embed_step`, `web/retrieval`, `eval_runner`) to the
  factory. Test: factory selection + error; existing suite stays green.
- **A5 — ADR-0019** (EMB-06): `docs/adr/0019-use-openai-embeddings-with-per-chunk-model-versioning.md`
  Accepted (3-large@1536, per-chunk versioning, Voyage-4 alternative, deterministic
  default retained). Doc-only (no gate beyond ruff/tests still green).

## Phase B — schema + language-aware FTS (DB)

- **B1 — resolve_text_search_config** (EMB-10): pure mapping module +
  `test_text_search.py` (en/pt/es/…, `pt-BR`, `PORTUGUESE`, None/blank/unknown →
  simple, passthrough of a real config name).
- **B2 — migration 0007** (EMB-07/08/09): columns + trigger + backfill + GIN
  rebuild + reversible downgrade; update `metadata.py`. Test: upgrade→head then a
  fresh insert gets a populated `search_vector`; downgrade restores the generated
  column; run within the existing migrations test harness.
- **B3 — corpus.replace writes search_config** (EMB-11): resolve regconfig from the
  document language, set on every chunk row. Test (integration): a `pt` book's
  chunks have `search_config='portuguese'`, `None`→`simple`, `en`→`english`.
- **B4 — language-aware lexical arm** (EMB-12/13): add `search_config` to the
  `scoped` CTE; both `websearch_to_tsquery` calls use `search_config::regconfig`.
  Integration F8 proof: a Portuguese mini-corpus returns the target for an
  inflected-form query; existing whole-source + anchored retrieval tests stay
  green.

## Phase C — reembed task + model write (DB)

- **C1 — set_embeddings writes model + EmbedCorpus passes it** (EMB-14/15): extend
  the port + repo signature (`*, model: str`), thread `adapter.model`. Test
  (integration): embedded chunks carry the adapter's model string.
- **C2 — stale_chunks_for_source** (EMB-17 selection): index method selecting
  NULL-or-different-model chunks, stably ordered. Test (integration): selects
  exactly the stale/unembedded chunks; empty when all current.
- **C3 — reembed_document task** (EMB-16/17/18/19): task body (HNSW drop →
  per-batch-committed embed+write → HNSW recreate), factory-selected provider,
  trace scope. Integration tests: full reembed populates model+vectors + retrieval
  works (EMB-19); idempotent re-run rewrites nothing new and current-source no-op
  (EMB-17); HNSW index present afterward (EMB-18).

## Phase D — tier-2 eval (DB)

- **D1 — labeled pairs** (EMB-20): `tests/eval_labeled.py` — 30–60 reviewable
  `(query, expected_anchor)` pairs over the golden book; a lightweight structural
  test asserts count ∈ [30,60] and every `expected_anchor` exists in the book.
- **D2 — metrics + snapshot gate** (EMB-21/22): `test_eval_retrieval_metrics.py` —
  recall@1/@5 + MRR over the labeled set via real retrieval + deterministic
  adapter; snapshot dict with model+dims; threshold assertions; `live` marker
  registered; `@pytest.mark.live` OpenAI variant skipped without a key.

## Verifier (always-on, fresh context)

After D2 commits, dispatch a fresh independent Verifier: spec-anchored outcome
check EMB-01..22, discrimination sensor (inject faults — e.g. break the regconfig
so PT stems as english, drop the model write, break sub-batch ordering — confirm
tests kill them), write `validation.md`, distill lessons. Bounded fix loop (≤3).
