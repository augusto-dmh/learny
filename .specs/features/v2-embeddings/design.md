# Design — v2-embeddings (RFC-002 Cycle B)

Extends the Cycle-5 retrieval substrate. Component-by-component; ADR decisions in
`context.md` (AD-051..057). No domain type changes beyond adding `model: str` to
`EmbeddingPort`.

## 1. OpenAI embedding adapter (Phase A)

`app/infrastructure/embeddings/openai.py` — `OpenAIEmbeddingAdapter` implementing
`EmbeddingPort`:

- Constructor takes `api_key`, `model` (`text-embedding-3-large`), `dimensions`
  (1536), and an optional injected client (tests pass a fake). Lazily builds
  `openai.OpenAI(api_key=...)` — the SDK import lives only in this module.
- `model` property → `f"{model}@{dimensions}"` = `text-embedding-3-large@1536`.
- `embed_query(text)` → single-input request → one vector.
- `embed_documents(texts)` → greedy sub-batching: accumulate inputs until the next
  would exceed **2048 inputs** or **250_000 tokens** (token estimate via a cheap
  local heuristic — `len(text)//4 + 1`, no `tiktoken` dependency; the cap has 50k
  headroom under OpenAI's 300k), one request per sub-batch, concatenate in order.
- Empty input list → `[]`. Passes `dimensions=self._dimensions` on every request.
- No retry/backoff here (Celery owns retries, research §3).

`app/infrastructure/embeddings/__init__.py` gains a factory:
`build_embedding_adapter(settings) -> EmbeddingPort` selecting on
`settings.embedding_provider` (`local` → `DeterministicEmbeddingAdapter`, `openai`
→ `OpenAIEmbeddingAdapter(...)`, else `ValueError`). `DeterministicEmbeddingAdapter`
gains `model` → `f"local-deterministic@{dim}"`.

Wiring: `app/worker/tasks.py::_build_embed_step` and `eval_runner`/`RetrieveEvidence`
composition roots call the factory instead of hardcoding the deterministic adapter.
The web retrieval composition root (`app/infrastructure/web/retrieval.py`) likewise
uses the factory so query embedding matches document embedding.

**Settings** (`app/core/config.py`): `embedding_provider: str = "local"`,
`openai_api_key: str = ""`, `embedding_model: str = "text-embedding-3-large"`
(the *provider* model name; the deterministic adapter ignores it and reports its
own identity), `embedding_dimensions: int = 1536`. `.env.example` documents each.
Note: `embedding_model`'s prior value `local-deterministic` becomes the OpenAI
model name; the deterministic adapter no longer reads it (reports
`local-deterministic@{dim}` from `embedding_dim`), so the default provider is
unaffected.

## 2. Schema migration 0007 (Phase B)

`migrations/versions/0007_language_aware_fts.py` (revises `0006_teaching_schema`):

```
upgrade:
  ADD COLUMN embedding_model text            -- nullable, populated on embed
  ADD COLUMN search_config text NOT NULL DEFAULT 'simple'
  DROP INDEX ix_corpus_chunks_search_vector
  ALTER TABLE corpus_chunks DROP COLUMN search_vector          -- the generated one
  ALTER TABLE corpus_chunks ADD COLUMN search_vector tsvector  -- plain, trigger-fed
  CREATE FUNCTION corpus_chunks_search_vector_update() RETURNS trigger ...
      NEW.search_vector :=
        setweight(to_tsvector(NEW.search_config::regconfig,
                              coalesce(NEW.section_path ->> -1, '')), 'A')
        || setweight(to_tsvector(NEW.search_config::regconfig,
                                 coalesce(NEW.text, '')), 'D');
  CREATE TRIGGER trg_corpus_chunks_search_vector
      BEFORE INSERT OR UPDATE OF text, section_path, search_config
      ON corpus_chunks FOR EACH ROW EXECUTE FUNCTION corpus_chunks_search_vector_update();
  UPDATE corpus_chunks SET search_config = 'simple';   -- backfill: fires trigger
  CREATE INDEX ix_corpus_chunks_search_vector ON corpus_chunks USING GIN (search_vector);

downgrade:  reverse — drop GIN, trigger, function, plain search_vector; restore the
  generated english search_vector + its GIN; drop search_config, embedding_model.
```

`metadata.py` `corpus_chunks` Table: add `embedding_model` (Text, nullable),
`search_config` (Text, nullable=False — the DB default fills it), `search_vector`
kept (now plain, still read-only from the app's perspective — never written
directly; the trigger owns it).

**Mapping** `app/application/text_search.py`:
`resolve_text_search_config(language: str | None) -> str` — lowercase, split on
`-`/`_`, take the primary subtag, look up an allowlist
`{en:english, pt:portuguese, es:spanish, fr:french, de:german, it:italian,
nl:dutch, ru:russian, sv:swedish, da:danish, no:norwegian, fi:finnish,
hu:hungarian, ro:romanian, tr:turkish}`; accept a full config name passed through;
else `simple`. Pure, unit-tested.

**Corpus write** (`SqlAlchemyCorpusRepository.replace`): resolve the regconfig once
from the document `language` and set `search_config` on every `chunk_row`. The
trigger computes `search_vector`; the app never sets it.

## 3. Language-aware retrieval query (Phase B)

`app/infrastructure/db/retrieval.py`: add `cc.search_config AS search_config` to the
`scoped` CTE; replace both `websearch_to_tsquery('english', :q)` occurrences with
`websearch_to_tsquery(search_config::regconfig, :q)`. Both template variants
(whole-source, anchored) inherit it via the shared template. No signature change to
`RetrievalPort.search`; no new interpolation (the regconfig is a trusted column).
`ts_rank_cd(search_vector, websearch_to_tsquery(search_config::regconfig, :q), 32)`
for ranking. Semantic arm and RRF fusion unchanged.

## 4. Model write + reembed (Phase C)

- `EmbeddingPort.model: str` added (Protocol). Both adapters implement it.
- `EmbeddingIndexRepository.set_embeddings(items, *, model: str)` — writes
  `embedding` **and** `embedding_model = :model` per chunk in the one executemany.
- `EmbedCorpus.__call__` passes `self._embeddings.model` to `set_embeddings`.
- New index method `stale_chunks_for_source(source_id, model) -> list[ChunkToEmbed]`
  — chunks where `embedding IS NULL OR embedding_model IS DISTINCT FROM :model`,
  ordered by section position then chunk_index (stable).
- `app/worker/tasks.py::reembed_document(source_id)` task:
  1. own txn: `DROP INDEX IF EXISTS ix_corpus_chunks_embedding_hnsw`;
  2. loop batches of `embedding_batch_size` from `stale_chunks_for_source`; per
     batch own txn: embed via the factory-selected adapter, `set_embeddings(items,
     model=adapter.model)`, commit;
  3. own txn: recreate the HNSW index (same params as 0005) `IF NOT EXISTS`.
  Idempotent: re-run selects only remaining stale chunks; a current source loops
  zero batches (index still dropped/rebuilt — cheap and keeps the invariant).
  Reuses the `RetryableIngestionError`/backoff classification is **not** needed;
  reembed is ops-invoked, `max_retries` with Celery `autoretry`-style is out of
  scope — a raise fails the task and it is re-invoked by ops.
  Trace-scope bound like `run_ingestion` (`source_id`).

Reembed is exercised by integration tests directly calling the task body against
the test DB (no Celery broker), mirroring `test_worker_tasks` patterns.

## 5. Tier-2 eval harness (Phase D)

- `tests/eval_labeled.py`: `LABELED_PAIRS: tuple[LabeledPair, ...]` — 30–60
  `(query, expected_anchor)` over `golden_book()`, discriminating tokens per
  target section. `LabeledPair` frozen dataclass.
- `tests/test_eval_retrieval_metrics.py` (integration, `requires_db`): build+embed
  the golden book once (module/class fixture), run real `retrieve()` per query,
  compute `recall@1`, `recall@5`, `MRR` over the labeled set; assert against fixed
  thresholds; assemble a snapshot dict `{model, dimensions, recall@1, recall@5,
  mrr, n}` and assert the recorded `model`/`dimensions` equal the deterministic
  adapter's identity. A `@pytest.mark.live` test recomputes under the OpenAI
  adapter when `LEARNY_OPENAI_API_KEY` is set (else skipped).
- Register the `live` marker in `pyproject.toml` `[tool.pytest.ini_options]`
  `markers` to avoid unknown-marker warnings.

## 6. Non-regression & gates

- The unfiltered/ anchored retrieval SQL stays behaviourally identical for
  English/`simple` corpora (existing golden retrieval + `test_retrieval` +
  teaching integration tests must stay green — they build English/None-language
  corpora that now resolve to `simple`/`english`). **Risk:** existing tests build
  corpora with `language=None` → `simple` regconfig, whereas the old query used
  `english`. `simple` does no stemming, so exact-token queries still match; verify
  the golden retrieval + teaching suites pass under `simple`. If a test depended on
  English stemming, set that fixture's book language to `en` (fixture-only change).
- Gate per phase: `uv run pytest -q` (full suite, DB up) + `uv run ruff check .`.
  Provider default stays `local`, so no key is needed.

## 7. Files touched (summary)

New: `app/infrastructure/embeddings/openai.py`, `app/application/text_search.py`,
`migrations/versions/0007_language_aware_fts.py`, `docs/adr/0019-*.md`,
`tests/eval_labeled.py`, `tests/test_eval_retrieval_metrics.py`,
`tests/test_embeddings_openai.py`, `tests/test_text_search.py`,
`tests/test_reembed.py`, `tests/test_migrations_0007.py` (or extend existing).
Modified: `app/domain/ports.py` (`EmbeddingPort.model`, `set_embeddings` sig),
`app/infrastructure/embeddings/__init__.py`, `app/infrastructure/embeddings/local.py`,
`app/infrastructure/db/repositories.py`, `app/infrastructure/db/retrieval.py`,
`app/infrastructure/db/metadata.py`, `app/application/retrieval.py`,
`app/worker/tasks.py`, `app/infrastructure/web/retrieval.py`, `app/core/config.py`,
`backend/.env.example`, `backend/pyproject.toml`, `tests/eval_runner.py`.
