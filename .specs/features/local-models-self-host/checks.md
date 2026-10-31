# local-models-self-host checks

Mutations: 3
Build: `cd backend && uv run ruff check app tests`; `cd backend && uv run ruff format --check app tests`; `python backend/scripts/check_boundaries.py`
Plan: `.specs/features/local-models-self-host/plan.md`

22 checks in 4 slices · 5 one-way doors · 0 open, of which 0 block

Check numbers match the plan's AC numbers (C*n* proves AC *n*). Backend proofs run from
`backend/` with `LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5437/learny_test`
exported (DB-gated tests skip without it, and a skip is not green). No frontend work is in
this cycle.

## Checks

### S1 - The local generation profile is documented and tested

**C1** - A declared `openai-compatible` generation profile serves an ask turn through the real registry → `build_generation_chain` composition: the request carries the profile's `base_url`, and the answer is grounded with `[^n]` citations resolved to evidence chunk ids — against a deterministic fake transport, no network (AC 1)
Proof: `cd backend && uv run pytest tests/test_local_generation_profile.py -k "serves_ask_turn_through_declared_base_url"`

**C2** - When the local runtime is unreachable, the same composition raises the taxonomy `ProviderUnavailable` (retryable), never a raw SDK exception (AC 2)
Proof: `cd backend && uv run pytest tests/test_local_generation_profile.py -k "unreachable_runtime_raises_provider_unavailable"`

**C3** - `docs/ops/local-models.md` carries every operator-profile anchor: Ollama `http://localhost:11434/v1`, LM Studio `http://localhost:1234/v1`, the placeholder API-key convention, price fields `0`, the `prompt-cited` grounding declaration, ask/teach eligibility, and the self-host-only embedding boundary (AC 3)
Proof: `cd backend && uv run pytest tests/test_ops_docs_local_models.py -k "operator_profile_anchors"`

**C4** - The ops doc states the pt-BR evidence position with no quality claim: local models are unproven for cited pt-BR answers until a golden capture records otherwise (AC 4)
Proof: `cd backend && uv run pytest tests/test_ops_docs_local_models.py -k "pt_br_evidence_position"`

### S2 - Local embeddings behind the port, self-host only

**C5** - `LEARNY_EMBEDDING_PROVIDER=openai-compatible` with a base URL builds an `OpenAIEmbeddingAdapter` whose identity is `{model}@{dim}` and which is constructed with that base URL (AC 5)
Proof: `cd backend && uv run pytest tests/test_embeddings_factory.py -k "compat_provider_builds_openai_adapter"`

**C6** - `openai-compatible` without `LEARNY_EMBEDDING_BASE_URL` raises `ValueError` naming both `LEARNY_EMBEDDING_PROVIDER` and `LEARNY_EMBEDDING_BASE_URL` at composition, before any SDK import (AC 6)
Proof: `cd backend && uv run pytest tests/test_embeddings_factory.py -k "compat_provider_without_base_url"`

**C7** - A compat-kind adapter sends no `dimensions` request parameter, and validates every response: one vector per input, each numeric, each exactly the configured dim long (AC 7)
Proof: `cd backend && uv run pytest tests/test_embeddings_openai.py -k "compat_omits_dimensions_parameter"`
Proof: `cd backend && uv run pytest tests/test_embeddings_openai.py -k "compat_validates_response_shape"`

**C8** - Each unexpected runtime shape — a wrong vector count, a non-numeric entry, a wrong dimension — raises before returning, one message naming the model, the expected dim and what was received (AC 8)
Proof: `cd backend && uv run pytest tests/test_embeddings_openai.py -k "unexpected_shape_raises_naming_model_and_dim"`

**C9** - An unreachable local embedding runtime raises `ProviderUnavailable` whose message names the configured host (AC 9)
Proof: `cd backend && uv run pytest tests/test_embeddings_openai.py -k "transport_failure_names_host"`

**C10** - The untouched providers are unchanged — `local` builds the deterministic adapter and `openai` still builds from key/model/dims — and the offline provider pin holds, so the suite gains no network seam (AC 10)
Proof: `cd backend && uv run pytest tests/test_embeddings_factory.py -k "local_provider_builds_deterministic_adapter"`
Proof: `cd backend && uv run pytest tests/test_embeddings_factory.py -k "test_openai_provider_builds_openai_adapter_from_settings"`
Proof: `cd backend && uv run pytest tests/test_offline_provider_pin.py::test_default_factories_are_deterministic`

**C11** - `backend/.env.example` and `backend/.env.production.example` both document the `openai-compatible` embedding wiring with the self-host-only boundary in the amendment's words (AC 11)
Proof: `cd backend && uv run pytest tests/test_ops_docs_local_models.py -k "env_examples_document_compat_wiring"`

### S3 - A model/dimension change forces a re-embed before retrieval answers from stale vectors

**C12** - A chunk stamped with a foreign identity returns no semantic evidence — the lexical arm still finds it (AC 12)
Proof: `cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5437/learny_test uv run pytest tests/test_retrieval_stamp_guard.py -k "foreign_stamp_skips_semantic_keeps_lexical"`

**C13** - A mid-re-embed corpus (some stamps current, some stale) fuses only current-stamped chunks in the semantic arm (AC 13)
Proof: `cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5437/learny_test uv run pytest tests/test_retrieval_stamp_guard.py -k "mixed_corpus_fuses_only_current"`

**C14** - The notes semantic arm applies the same stamp rule against `notes.embedding_model` (AC 14)
Proof: `cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5437/learny_test uv run pytest tests/test_retrieval_stamp_guard.py -k "notes_semantic_arm_respects_stamp"`

**C15** - A corpus never mixes vector lengths: a wrong-length insert into the `vector(1536)` column raises at the database, and every embed write stamps one identity per write (AC 15)
Proof: `cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5437/learny_test uv run pytest tests/test_retrieval_stamp_guard.py -k "wrong_length_insert_raises"`

**C16** - With a settings dim the columns do not match, `embedding_status` exits `1` printing the exact resize + reembed procedure (drop index, clear vectors, resize the three embedding columns, recreate index, per-source reembed commands); no automatic resize exists (AC 16)
Proof: `cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5437/learny_test uv run pytest tests/test_cli_embedding_status.py -k "misaligned_prints_procedure_and_exits_one"`

**C17** - `embedding_status` reports per source: total chunks, current, stale, distinct stamps, plus the active identity and dimension; exit `0` when the columns match the active dim (AC 17)
Proof: `cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5437/learny_test uv run pytest tests/test_cli_embedding_status.py -k "reports_per_source_state_and_exits_zero"`

**C18** - End-to-end offline: embed at identity A, flip to a different-dimension deterministic adapter, the corpus answers lexical-only; after the operator procedure (clear + resize) and the re-embed body, the semantic arm is restored with matching stamps (AC 18, running AC 16's procedure as its middle step)
Proof: `cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5437/learny_test uv run pytest tests/test_reembed.py -k "dimension_change_forces_reembed_and_restores_semantic_arm"`

### S4 - Golden results for a pt-BR-capable local model

**C19** - `capture_local_golden --base-url URL --model ID` runs every golden case (12 English `cases.yaml` cases + the 4 Portuguese book cases) through the real ingestion/embedding/retrieval composition, records one JSONL line per case under `evals/local/` with the door-4 fields, and every line's `generation_model` is the `--model` argument (AC 19)
Proof: `cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5437/learny_test uv run pytest tests/test_cli_capture_local_golden.py -k "records_one_line_per_case"`

**C20** - Invoked without `--base-url` or `--model`, the capture exits `2` with a usage error before any network attempt or DB write (AC 20)
Proof: `cd backend && uv run pytest tests/test_cli_capture_local_golden.py -k "missing_args_exit_two_before_network_or_db"`

**C21** - The capture runner is proven offline end-to-end against an in-process OpenAI-compatible fake server on a loopback ephemeral port with deterministic scripted responses — the same runner an operator points at Ollama, no test-only branches (AC 21)
Proof: `cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5437/learny_test uv run pytest tests/test_cli_capture_local_golden.py -k "records_one_line_per_case"`

**C22** - The pt-BR golden capture stands recorded as operator-gated with the reason stated plainly, and the ops doc carries the exact capture procedure for the operator (AC 22)
Proof: `cd backend && uv run pytest tests/test_ops_docs_local_models.py -k "capture_procedure_and_operator_gate"`

## Coverage

| Set (size) | Member -> proof | Unproven |
| --- | --- | --- |
| `LEARNY_EMBEDDING_PROVIDER` values (3) | `local` C10 · `openai` C10 · `openai-compatible` C5 | - |
| unexpected embedding shapes (3) | wrong count C8 · non-numeric entry C8 · wrong dimension C8 (one table-driven test over all 3) | - |
| `embedding_status` exits (2) | `0` aligned C17 · `1` misaligned C16 | - |
| `capture_local_golden` exits (2) | `0` recorded C19 · `2` usage refusal C20 | - |
| retrieval arms under the stamp guard (4) | book semantic C12 · book lexical C12 · notes semantic C14 · notes lexical C12 (lexical arms unfiltered, same proof) | - |
| golden capture cases (16) | C19, table-driven over all 16 — 12 `cases.yaml` + 3 `PORTUGUESE_CASES` + `PORTUGUESE_UNSUPPORTED_QUESTION` | - |
| door 1 provider contract (3) | requires base URL C6 · never sends `dimensions` C7 · response validated per request C7 | - |
| door 2 retrieval-port contract (3) | book arm stamp filter C12 · notes arm stamp filter C14 · mixed state fuses current only C13 | - |
| door 3 adapter construction (3) | `dimensions=None` omits the param C7 · `expected_dim` validates C8 · transport failure names host C9 | - |
| door 4 capture artifact (3) | one line per case, door-4 fields C19 · usage refusal before any write C20 · same runner against a loopback fake C21 | - |
| door 5 ADR amendment (2) | ops doc anchors quote the boundary C3 · env examples carry the amendment's words C11 | - |

## Swept

- validation: C6 (missing base URL), C7/C8 (response shape), C20 (missing CLI args)
- failure modes: C2 (generation unreachable), C9 (embedding transport), C16 (misaligned columns fail loud, exit 1)
- idempotency: existing - `reembed.document` re-runs clean and a current source rewrites nothing (`test_reembed.py::test_reembed_is_idempotent_second_run_writes_nothing`); C18 re-proves the pass end-to-end across the dim change
- authorization: n/a - both surfaces are host-side operator CLIs; no HTTP route changes, and retrieval ownership is unchanged (existing `authorized_source` guard)
- concurrency: existing - the re-embed pass commits per batch and re-queries the stale set (`test_reembed.py::test_reembed_resumes_after_a_partial_completion`); the stamp guard makes a concurrent mixed state answer lexical-only, never fused (C13)
- data lifecycle: C15 (vector length is refused at the column), C16/C18 (the clear+resize+reembed lifecycle for a dim change); stamps are written with every vector and never backfilled
- dependency failure: C2, C9 (local runtime down degrades to a typed error, never a raw SDK exception); C12 (stale vectors degrade to lexical-only, never error)
- state transitions: C18 (current -> stale -> re-embedded -> current), C13 (mixed in-flight state)
- observability: existing - `reembed.document` logs start/complete with model and counts; `embedding_status` output is itself the operator view (C17); the capture prints a per-run summary (C19)

## Handoff

- **Settled mid-build:** none yet
- **Dispatched:** Verifier dispatched 2026-10-30 against PR #84 (fresh context, LEARNY_REQUIRE_DB=1, owner services postgres 5437 / redis 6383)
- **Abandoned:** golden capture judged quality scores — recorded in plan `## Assumptions`, out of scope
- **Operator gate (AC 22):** `ollama --version` returned command-not-found on this machine (2026-10-30), the owner's no-install policy applies, and a pt-BR-capable model is a multi-GB download — so the capture itself is NOT attempted; C19–C21 prove the runner offline, C22 proves the doc carries the procedure. Recorded here and to be restated in the STATE handoff at wrap.
