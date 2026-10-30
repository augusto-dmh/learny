# Running Learny on local models (self-host)

This runbook is for an operator running Learny on their own host who wants
answers (and optionally embeddings) served by a local OpenAI-compatible runtime
instead of paid cloud APIs. It works fully offline: no provider key is required
to run Learny at all (the deterministic adapters are the default), and this page
is about swapping the deterministic answer path for a real local model.

**Boundary: self-host only.** Everything on this page assumes you own the host.
A hosted deployment must not point profiles or embeddings at operator-chosen
hosts, and the local embedding model below is additionally guarded by the
per-corpus identity rule described further down (ADR-0019, amended for
self-host).

## The generation profile (answers, teach)

Learny's generation serving is a registry of profiles declared in
`LEARNY_GENERATION_PROFILES` (a JSON list). The `openai-compatible` kind speaks
any OpenAI-compatible chat API — which is what Ollama and LM Studio expose:

| Runtime | Endpoint |
| --- | --- |
| Ollama | `http://localhost:11434/v1` |
| LM Studio | `http://localhost:1234/v1` |

One profile serving both ask and teach for Ollama (inside `LEARNY_GENERATION_PROFILES`):

```json
[
  {
    "id": "local-ollama",
    "kind": "openai-compatible",
    "model": "qwen3:8b",
    "base_url": "http://localhost:11434/v1",
    "api_key_env": "LEARNY_LOCAL_RUNTIME_KEY",
    "max_tokens": 2048,
    "price_input_usd_per_million_tokens": 0,
    "price_output_usd_per_million_tokens": 0,
    "price_cache_read_usd_per_million_tokens": 0,
    "price_cache_creation_usd_per_million_tokens": 0,
    "grounding": "prompt-cited",
    "ask_enabled": true,
    "teach_enabled": true
  }
]
```

Field notes, and the two rules that are not negotiable:

- **Keyless runtimes keep `api_key_env`.** Ollama and LM Studio ignore the key,
  but the registry requires the named environment variable to exist and the SDK
  requires a non-empty string — so export the variable with any placeholder
  value (the example uses `LEARNY_LOCAL_RUNTIME_KEY=ollama`). Do not leave the
  field empty.
- **`grounding` stays `"prompt-cited"`.** This kind has no provider-side
  citation API: the system prompt instructs the model to mark each claim with
  the cited document's `[^n]`, and Learny's grounding intersection verifies the
  markers against retrieved evidence. Declaring anything else would misstate
  what this adapter can prove.
- **Price fields are `0`** — a local model has no token bill, and the spend
  ledger should say so.
- `ask_enabled`/`teach_enabled` are your call; both modes work through this
  kind. `max_tokens` must fit the model you pulled (2048 is a safe start).
- Effort/thinking knobs are accepted in the profile and deliberately never sent
  to this kind — declared degradation, not a bug.
- Restart the api (and worker) after changing the registry: resolution happens
  at composition and fails fast on a malformed profile.

## Local embeddings (optional, self-host only)

By default Learny embeds with the deterministic local adapter, which is
network-free but has no semantics. A self-hoster who wants real semantic
retrieval without an OpenAI key can point embeddings at the same local runtime
(an embedding model such as `nomic-embed-text` on Ollama):

```bash
LEARNY_EMBEDDING_PROVIDER=openai-compatible
LEARNY_EMBEDDING_BASE_URL=http://localhost:11434/v1
LEARNY_EMBEDDING_MODEL=nomic-embed-text
LEARNY_EMBEDDING_DIM=768
```

**This is self-host only.** Never enable it on a hosted instance: a shared
corpus must keep one embedding identity. In the amendment's words: swapping the
model or dimension makes every affected corpus go stale (lexical-only answers)
until an explicit re-embed — the retrieval gate plus the re-embed procedure are
the guard, recorded on the per-chunk `embedding_model` stamps.

How the guard works, in operator terms:

- Every stored vector is stamped with the identity that produced it
  (`model@dimension`). Retrieval serves a vector only when its stamp matches
  the active identity — a corpus embedded by another model or dimension
  answers **lexical-only** (no error, no fused nonsense) until re-embedded.
- The runtime's native dimension is validated against `LEARNY_EMBEDDING_DIM` on
  every response: a mismatch is a loud error naming the model and both widths,
  never a silent wrong-shaped write. The OpenAI-only `dimensions` request
  parameter is never sent to a local runtime.
- The API key is your `LEARNY_OPENAI_API_KEY` if set, else a fixed placeholder
  — local runtimes ignore it either way.
- An unreachable runtime is a `ProviderUnavailable` error naming the host you
  configured, so you can see which runtime is down.

### Changing the embedding model or dimension

Check state first, then follow what it prints:

```bash
python -m app.cli.embedding_status
```

It reports, per source: total chunks, chunks current for the active identity,
stale chunks, and every distinct stamp present — plus the same counts for notes
and the vector columns' actual widths against the configured dimension. Exit
`0` when the columns match; exit `1` with the exact resize + re-embed procedure
(drop index, clear vectors, resize `corpus_chunks.embedding`, `notes.embedding`,
`quiz_items.embedding`, recreate index, per-source `reembed.document` calls)
when they do not. The command never resizes anything itself — a dimension
change is a one-way data operation you run explicitly, and you should back up
first (see `backups.md`).

Re-embedding an existing source (model swap, no dimension change — no SQL
needed):

```bash
celery -A app.worker.celery_app call reembed.document --args '["<source-id>"]'
```

The pass is idempotent and resumable: it re-embeds only chunks whose stamp
differs from the active identity, commits per batch, and drops/recreates the
HNSW index around the bulk write. Until a source's re-embed finishes, that
source answers lexical-only.

Order of operations for a dimension change: set the new `LEARNY_EMBEDDING_DIM`,
**restart** the api and worker (the write path validates against the configured
dimension), then run the procedure `embedding_status` prints, then re-embed
every source and each note.

## Golden results for a local model (ask quality)

Local models are **unproven for cited pt-BR answers**: no local model has
recorded golden results yet, so no quality claim is made here — none exists
until a capture records one. The capture runner ships with the repo so an
operator with a local model can produce that record honestly:

```bash
# From backend/, against your local runtime, with your database configured:
uv run python -m app.cli.capture_local_golden \
    --base-url http://localhost:11434/v1 \
    --model qwen3:8b
```

The runner ingests the two golden books (English and Portuguese), retrieves and
answers every golden case through your runtime, and writes one JSONL line per
case to `evals/local/<date>-<git-sha>-<model>.jsonl` — found/not-found, cited
chunk ids, and whether the citations resolve, plus the raw answer text. Commit
the file (or attach it to an issue) so the claim and its evidence travel
together. It refuses to run without `--base-url` and `--model`; it never fakes
or scores anything — judging faithfulness is a separate, judge-owned study.

Status: **operator-gated** — the reference pt-BR capture has not been recorded
(no local runtime on the development machine and a multi-GB model download
against the owner's no-install policy). The runner itself is proven offline
against a scripted in-process runtime; the recorded-results slot stays empty
until a real capture fills it.
