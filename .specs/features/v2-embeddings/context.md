# Context & Decisions — v2-embeddings (RFC-002 Cycle B)

Auto-decided under the ship-cycle rule: each decision states options (why-recommend
+ why-not), the chosen option, and rationale. None met a ship-cycle escalation
condition — RFC-002 (Accepted) already sets the provider direction, so a clear
recommendation exists for every choice. The one provider lock-in is ratified by
ADR-0019 (what CLAUDE.md requires) and surfaced at the merge gate.

## D-1 (AD-051) — Cycle framing & slice

- **Options:** (a) full RFC-002 Cycle B backend slice, extend Cycle-5 substrate;
  (b) also add a frontend surface (reembed button, language badge).
- **Chosen: (a).** Why: retrieval quality is infrastructure with no user-facing
  behaviour to change this cycle; extending the existing ports keeps the diff
  reviewable. Why-not (a): a fourth consecutive backend-only slice — flag at the
  merge gate (precedent AD-023/AD-039/AD-044/AD-050). Why-not (b): invents UI
  ahead of the Cycle-D frontend rebuild; premature.

## D-2 (AD-052) — OpenAI adapter + provider selection

- **Options:** (a) `OpenAIEmbeddingAdapter` behind `EmbeddingPort`, selected by
  `LEARNY_EMBEDDING_PROVIDER` (default `local`); (b) make OpenAI the default now;
  (c) Voyage-4 instead.
- **Chosen: (a).** `text-embedding-3-large` + request `dimensions=1536` (fits the
  existing `vector(1536)` column; HNSW's 2000-dim limit rules out native 3072).
  Adapter sub-batches to ≤2048 inputs / ≤250k tokens (headroom under the 300k cap),
  base64 via the SDK, no client-side retry (Celery owns retries). Why: honors the
  Accepted RFC-002 decision; keeps CI/local offline and key-free (default `local`).
  Why-not (a): introduces the first paid provider SDK + an API-key requirement for
  production use. Why-not (b): would force every CI run and every dev to hold an
  OpenAI key and spend — RFC explicitly keeps the deterministic adapter the CI
  default. Why-not (c): Voyage-4 offers only 1024/2048 dims → forces a
  `vector` column migration; RFC locked OpenAI. Voyage recorded as the ADR
  alternative.
- **This is the cycle CLAUDE.md gates the OpenAI SDK to** ("becomes binding through
  its cycle's ADR"). Ratified by ADR-0019.

## D-3 (AD-053) — Per-chunk model versioning

- **Options:** (a) nullable `embedding_model text` per chunk, value `"<model>@<dims>"`;
  (b) model on `corpus_documents` only; (c) no versioning.
- **Chosen: (a).** `EmbeddingPort` gains a stable `model: str` (mirrors
  `AnswerGenerationPort.model`); `EmbedCorpus` + reembed write it. Why: reembed and
  eval-snapshot pinning are inherently per-chunk (mixed-model states exist mid
  reembed); the model string is the retrieval-consistency key. Why-not (a): a
  column that's NULL until embedded (same shape as `embedding`). Why-not (b): can't
  express a partially-reembedded document. Why-not (c): can't detect stale vectors
  or pin snapshots — blocks EMB-17/21.

## D-4 (AD-054) — Language-aware FTS (fixes F8)

- **Problem:** the generated `search_vector` hardcodes `'english'`; Portuguese
  content is mis-stemmed, degrading the lexical RRF arm (F8).
- **Mechanism options:** (a) drop the generated column, add a plain `tsvector`
  maintained by a `BEFORE INSERT/UPDATE` **trigger** keyed on a per-row
  `search_config` regconfig; (b) keep a generated column referencing
  `search_config`; (c) compute the tsvector in the app INSERT.
- **Chosen: (a).** A STORED generated column requires an **IMMUTABLE** expression;
  `to_tsvector(<row-regconfig>::regconfig, …)` is not immutable (config resolution
  + the `regconfig` cast), so (b) is invalid. (c) collides with the existing bulk
  `executemany` chunk insert (per-row SQL expressions don't fit a values-list
  insert) and misses the reembed UPDATE path. A trigger has no immutability
  constraint, works transparently with the bulk insert, and covers reembed
  updates. Why-not (a): adds a trigger function + trigger (extra migration
  surface); acceptable and standard.
- **Query side:** the lexical arm reads each chunk's own `search_config` column —
  `websearch_to_tsquery(search_config::regconfig, :q)` — so no new `RetrievalPort`
  parameter, no app-level language lookup at query time, and no interpolation of
  untrusted input (the regconfig comes from a trusted allowlisted column, written
  by `resolve_text_search_config`). Correct per-row even for a mixed-language
  source. Semantic arm untouched (embeddings are language-agnostic).
- **Mapping:** pure `resolve_text_search_config(dc:language) -> regconfig` over an
  allowlist of built-in Postgres configs; unknown/None → `simple`. Denormalized
  onto chunks (like `section_path`/`anchor`) so the trigger and query read one row.

## D-5 (AD-055) — reembed_document task

- **Options:** (a) idempotent per-document task, selects NULL-or-stale-model
  chunks, per-batch commits, HNSW drop-before/rebuild-after, provider from
  settings, no HTTP endpoint; (b) full re-embed every run; (c) add an HTTP trigger.
- **Chosen: (a).** Selection `embedding IS NULL OR embedding_model IS DISTINCT FROM
  :target` makes re-runs resumable and a current source a no-op. Per-batch commits
  bound transaction size and make partial progress durable. HNSW drop→bulk
  update→recreate yields a better graph and a faster bulk run than incremental
  index maintenance (research §3). Reuses `embedding_batch_size` for the loop; the
  OpenAI adapter sub-batches to API limits internally. Why-not (a): brief mixed
  model state mid-run — guarded by the per-chunk model column. Why-not (b): rewrites
  unchanged rows, not resumable. Why-not (c): out of the backend-only slice; ops
  invokes the task directly this cycle.

## D-6 (AD-056) — Tier-2 retrieval eval

- **Options:** (a) recall@k + MRR over 30–60 labeled pairs, computed under the
  deterministic adapter in CI with a `@pytest.mark.live` OpenAI variant; snapshot
  records model+dims; (b) require the real-model snapshot in CI; (c) skip until a
  key exists.
- **Chosen: (a).** CI is offline, so the committed snapshot is
  `local-deterministic@1536`; the harness, labeled pairs, and metric code land now
  and gate regressions deterministically, while the live variant produces the real
  numbers when keyed. Why-not (a): the deterministic recall isn't the production
  model's recall — a representative regression gate, not the real quality number
  (flag at merge gate). Why-not (b): impossible without a key in CI. Why-not (c):
  loses the labeled dataset + harness that are the durable deliverable
  (consistent with AD-036: evaluation as a deterministic test harness).

## D-7 (AD-057) — ADR-0019

- Records OpenAI `text-embedding-3-large@1536` **Accepted**, per-chunk model
  versioning, deterministic adapter retained as default, Voyage-4 recorded
  alternative. Makes the provider binding per CLAUDE.md ("becomes binding through
  its cycle's ADR"). No other open decision is closed.

## Merge-gate flags

1. Fourth consecutive backend-only slice (AD-051).
2. First paid provider SDK + API-key requirement for production embeddings
   (AD-052) — CI/local remain offline on the deterministic default.
3. Committed tier-2 snapshot is deterministic-model, not the real OpenAI model
   (AD-056) — real-model snapshot is a keyed follow-up.
