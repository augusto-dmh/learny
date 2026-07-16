# Claude Generation (Cited Answers + Teaching + Eval Harness) Specification

RFC-002 Cycle C. Feature slug: `v2-generation`.

## Problem Statement

Learny's cited Q&A and teaching sessions still run on the deterministic extractive adapters (AD-024/AD-032): answers are verbatim snippet stitching, and the "not found in source" outcome only triggers on empty retrieval — the adapter cannot judge relevance (QA finding F5). The cloud generation provider decision has been the blocking follow-up since AD-024. This cycle wires Anthropic Claude behind the existing `AnswerGenerationPort`/`TeachingGenerationPort`, adds the streaming surface Cycle D's frontend will consume, and ships the evaluation layer (replay snapshots, live smoke, judge harness) that keeps generation quality measurable.

## Goals

- [ ] Real LLM answers and teaching turns with API-native citations, behind existing ports, opt-in via settings; deterministic adapters remain the offline/CI default.
- [ ] Relevance-aware `not_found_in_source` (fixes F5): the model can decline irrelevant evidence, not just empty evidence.
- [ ] SSE streaming endpoints emitting the UI Message Stream protocol, ready for Cycle D's `useChat` frontend.
- [ ] Evaluation: exact citation-validity invariants on every PR, port-level replay snapshots with a `--record` flag, `@pytest.mark.live` smoke, and a nightly Haiku judge harness (faithfulness/relevancy) with committed JSONL results.

## Out of Scope

| Feature | Reason |
| --- | --- |
| Frontend changes (useChat, AI Elements, citation popovers) | Cycle D rebuilds the frontend on these endpoints |
| Quiz generation / Batch API | Cycle E flagship |
| Ragas or any eval framework | ADR-0016 + evaluation research: custom harness, no framework |
| Persisting Q&A answers or stream transcripts | AD-025 unchanged — stateless Q&A; teaching turns persist as today |
| Reranker, retrieval changes | ADR-0006 defers; retrieval layer untouched |
| Removing/altering the existing buffered JSON endpoints | Cycle D decides their fate once frontend migrates |
| Provider fallback chains / multi-provider routing | Single provider per port this cycle; revisit if needed |

## Assumptions & Open Questions

All gray areas auto-decided per the ship-cycle rule; full option analysis in `context.md` (D-1..D-8), ledger rows AD-058..AD-064.

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| Model for answers + teaching | `claude-sonnet-4-6` via `LEARNY_GENERATION_MODEL` | RFC-002 pin; research-verified cost/quality; swap is config-only | auto (D-1) |
| Provider switch granularity | one `LEARNY_GENERATION_PROVIDER` for both ports | RFC treats generation as one cycle; two flags = config surface without a consumer | auto (D-2) |
| Citations request shape | one plain-text citations-enabled document per chunk; map by `document_index` | Anthropic docs' explicit RAG guidance; `document_title` never parsed | auto (D-3) |
| F5 mechanism | frozen prompt + exact sentinel `NOT_FOUND_IN_SOURCE` → `found=False` | citations + structured outputs are API-incompatible (400); sentinel is the deterministic signal | auto (D-3) |
| Streaming citations delivery | text deltas stream live; grounded citations emitted once in a terminal `data-citations` part | keeps AD-027 grounding a single post-stream enforcement point | auto (D-4) |
| Teaching stream persistence | persist turn only on successful stream completion | mirrors buffered-path semantics; disconnect = no partial turn | auto (D-4) |
| Replay snapshots in CI | harness + `--record` ship now; snapshot-dependent tests skip cleanly when no snapshots are committed | CI stays offline/key-free (AD-052/AD-056 precedent); user records with their key | auto (D-5) |
| Judge thresholds | first runs are calibration (report-only); gate values set from observed baseline, asserted thereafter | evaluation research: literature defaults are not Learny-calibrated | auto (D-5) |
| SDK client-side retries | keep Anthropic SDK default (2 retries on 429/5xx); no extra retry layer | mirrors AD-052's "no client-side retry beyond transport" spirit; HTTP request path needs bounded latency | auto (D-6) |
| Slice shape | backend-only (5th consecutive) | SSE consumer is Cycle D; flag at merge gate (AD-051 precedent) | auto (D-7) |

**Open questions:** none — all resolved or logged above.

## User Stories

### P1: Claude-generated cited answers ⭐ MVP

**User Story**: As a reader, I want real synthesized answers to my questions about a book, with citations to the exact passages, so that answers are useful prose rather than stitched snippets.

**Why P1**: The core value of the cycle; unblocks the provider follow-up open since AD-024.

**Acceptance Criteria**:

1. WHEN `LEARNY_GENERATION_PROVIDER=anthropic` and a question is asked THEN the system SHALL call Claude with one plain-text citations-enabled document per retrieved evidence chunk (in evidence order) and a frozen system prompt, and return prose text with `cited_chunk_ids` resolved via `document_index`.
2. WHEN Claude cites documents THEN `cited_chunk_ids` SHALL contain the matching evidence `chunk_id`s in first-citation order, deduplicated, and never be derived from `document_title`.
3. WHEN Claude replies with the not-found sentinel THEN the adapter SHALL return `found=False` and the endpoint SHALL return 200 with `answer_status="not_found_in_source"` (F5).
4. WHEN the provider raises any error THEN the endpoint SHALL return 502 with the existing generic body, never leaking provider details (QA-17 preserved).
5. WHEN `LEARNY_GENERATION_PROVIDER` is unset or `local` THEN behavior SHALL be byte-identical to today (deterministic adapter, offline).
6. WHEN the adapter response cites a document index outside the evidence set (malformed) THEN grounding SHALL discard it and, if none survive, return `not_found_in_source` (AD-027 applies unchanged).

**Independent Test**: Unit tests with an injected fake Anthropic client asserting request shape and citation mapping; endpoint test with fake adapter; live smoke with a real key.

### P1: Claude teaching turns with prompt caching

**User Story**: As a learner in a teaching session, I want pedagogically coherent multi-turn responses grounded in the target section, so that teaching feels like tutoring rather than excerpt display.

**Why P1**: Closes AD-032's deferred cloud adapter; teaching is the second core surface.

**Acceptance Criteria**:

1. WHEN a teaching turn is posted with provider `anthropic` THEN the adapter SHALL send the frozen teaching system prompt, the bounded history as alternating user/assistant messages, and this turn's evidence as citations-enabled documents, returning cited, grounded prose.
2. WHEN the request is assembled THEN the system prompt SHALL contain no per-session/per-turn interpolation (no ids, timestamps) and SHALL carry a `cache_control` breakpoint with `ttl: "1h"`; the latest history turn SHALL carry the second breakpoint; per-turn volatile content (evidence, new message) SHALL sit after the cached prefix.
3. WHEN evidence is irrelevant to the learner's message THEN the sentinel path SHALL produce the existing not-found turn semantics.
4. WHEN the provider errors THEN the turn endpoint SHALL return 502 (existing mapping) and persist no turn.

**Independent Test**: Unit tests with fake client asserting message layout + cache_control placement; existing teaching service tests unchanged and green.

### P2: SSE streaming endpoints (UI Message Stream)

**User Story**: As the Cycle D frontend, I want SSE endpoints speaking the UI Message Stream protocol so `useChat` can render tokens as they generate.

**Why P2**: Not user-visible until Cycle D, but the RFC places the backend half here so Cycle D is purely frontend.

**Acceptance Criteria**:

1. WHEN `POST /api/sources/{source_id}/questions/stream` is called with a valid question THEN the response SHALL be an SSE stream with header `x-vercel-ai-ui-message-stream: v1` emitting `start` → `text-start`/`text-delta`(×N)/`text-end` → one `data-citations` part carrying the grounded citations (same projection as the JSON endpoint) → `finish` → `[DONE]`.
2. WHEN `POST /api/teaching-sessions/{session_id}/turns/stream` completes successfully THEN the turn SHALL be persisted with the same fields as the buffered endpoint, and the stream SHALL emit the same part sequence.
3. WHEN ownership/readiness/validation/rate-limit checks fail THEN the endpoint SHALL return the same non-streaming HTTP errors as the JSON siblings (404/409/422/429) before any SSE bytes are sent.
4. WHEN generation fails mid-stream THEN the stream SHALL emit a protocol `error` part with the generic message and terminate; no teaching turn SHALL be persisted.
5. WHEN the not-found outcome occurs THEN the stream SHALL emit a `data-answer-status` part with `not_found_in_source` (and the not-found text), mirroring the JSON contract.
6. WHEN the client disconnects mid-stream THEN the server SHALL cancel the provider stream (no leaked generation) and persist nothing.
7. WHEN the deterministic provider is active THEN the same endpoints SHALL stream (trivially chunked) — the protocol surface is provider-independent.

**Independent Test**: Endpoint tests with fake streaming adapter parsing the SSE frames; deterministic-provider stream test runs offline.

### P2: Evaluation harness

**User Story**: As the project owner, I want deterministic citation invariants on every PR plus recorded-response replay and a nightly judge, so that generation quality regressions are caught without paying for LLM calls in CI.

**Why P2**: Quality backbone for this and later cycles (quizzes reuse it).

**Acceptance Criteria**:

1. WHEN the PR suite runs offline THEN citation-validity invariants SHALL be asserted exactly (cited ids ⊆ retrieved evidence; every cited anchor resolves in the golden corpus; `answered` ⇒ ≥1 citation) over the deterministic adapter's answers on the golden book.
2. WHEN replay snapshots exist under the committed snapshot dir THEN the same invariants SHALL run against them; WHEN none exist THEN those tests SHALL skip with an explicit reason (CI green, key-free).
3. WHEN pytest runs with `--record` and a key THEN the harness SHALL call the live adapter for each eval case and rewrite the snapshot files (reviewable in diff).
4. WHEN `LEARNY_ANTHROPIC_API_KEY` is set THEN `@pytest.mark.live` smoke SHALL make one real call per adapter asserting answer text + ≥1 valid citation; WHEN unset THEN skip.
5. WHEN the judge harness runs THEN each case SHALL be scored for faithfulness (claims labeled SUPPORTED/UNSUPPORTED via structured outputs, aggregated to a ratio) and answer relevancy (1–5) by the judge model, with prompts stored as versioned files, and results appended as one JSONL line per case (scores, model ids, prompt hash, git sha).
6. WHEN the nightly workflow runs (cron or manual dispatch) with the secret present THEN it SHALL execute the live/judge suites under a case-count cost cap and upload the results JSONL as an artifact; WHEN the secret is absent THEN it SHALL skip gracefully.

**Independent Test**: Invariant tests run in the normal suite; judge module unit-tested with a fake client; workflow validated by dispatch dry-run structure.

## Edge Cases

- WHEN evidence is empty THEN the port SHALL NOT be invoked (existing short-circuit; applies to streaming path too).
- WHEN Claude returns text with zero citations (no sentinel) THEN grounding SHALL yield `not_found_in_source` (no ungrounded prose reaches users).
- WHEN Claude's reply contains the sentinel embedded inside a longer answer THEN the adapter SHALL treat only an exact/whole-reply sentinel as not-found (guard against sentinel leakage in prose; test it).
- WHEN a citation's `document_index` repeats across text blocks THEN dedup SHALL keep first occurrence order.
- WHEN `LEARNY_GENERATION_PROVIDER=anthropic` but `LEARNY_ANTHROPIC_API_KEY` is empty THEN adapter construction SHALL fail fast with a clear error (config error, not a 502 at request time).
- WHEN an unknown provider value is configured THEN the factory SHALL raise `ValueError` (mirrors embeddings factory).
- WHEN `stop_reason` is `max_tokens` THEN the adapter SHALL still return the partial text with its citations (grounding decides), never raise.
- WHEN the SSE client disconnects before the first token THEN no provider call SHALL leak (generator cancellation closes the SDK stream).

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| --- | --- | --- | --- |
| GEN-01 settings fields (`generation_provider`, `anthropic_api_key`, `generation_model`, `generation_max_tokens`, `judge_model`, eval caps) | P1 answers | A | Pending |
| GEN-02 generation factories mirror embeddings factory; DI composition-root switch; unknown → ValueError; empty key with anthropic → fail fast | P1 answers | A | Pending |
| GEN-03 `anthropic` SDK dep, imported lazily only in adapter/judge modules | P1 answers | A | Pending |
| GEN-04 `AnthropicAnswerAdapter`: per-chunk plain-text citations-enabled docs, evidence order, `model` property, SDK streaming internally + `get_final_message` | P1 answers | A | Pending |
| GEN-05 citation mapping by `document_index` only; first-citation order; dedup | P1 answers | A | Pending |
| GEN-06 frozen answer system prompt + exact sentinel ⇒ `found=False` (F5) | P1 answers | A | Pending |
| GEN-07 provider error propagation → existing 502 mapping; no detail leak; partial `max_tokens` output returned not raised | P1 answers | A | Pending |
| GEN-08 grounding AD-027 verified against adapter-shaped malformed outputs | P1 answers | A | Pending |
| GEN-09 ADR-0020 (Anthropic generation provider) authored, Accepted | P1 answers | A | Pending |
| GEN-10 `AnthropicTeachingAdapter`: history as alternating turns, per-turn evidence docs, sentinel, citations mapping shared with answer adapter | P1 teaching | B | Pending |
| GEN-11 prompt caching: frozen system prompt + `ttl:"1h"` breakpoints (system, latest history turn); volatile content after prefix | P1 teaching | B | Pending |
| GEN-12 domain streaming contract: Learny-owned stream events + port streaming method; deterministic adapters implement | P2 SSE | C | Pending |
| GEN-13 streaming service paths reuse all guards + grounding; teaching persists turn only on completion | P2 SSE | C | Pending |
| GEN-14 SSE endpoints `/questions/stream` + `/turns/stream`: UI Message Stream v1 frames + header; same deps (auth/CSRF/origin/rate limit); JSON endpoints untouched | P2 SSE | C | Pending |
| GEN-15 edge presenter module owns the protocol; domain/application protocol-free | P2 SSE | C | Pending |
| GEN-16 pre-stream errors are plain HTTP; mid-stream failure → protocol `error` part, generic message | P2 SSE | C | Pending |
| GEN-17 disconnect cancels provider stream; nothing persisted | P2 SSE | C | Pending |
| GEN-18 replay harness: snapshot format + loader + `--record` flag; skip-when-absent | P2 eval | D | Pending |
| GEN-19 citation-validity invariants exact, every PR, deterministic + snapshot inputs | P2 eval | D | Pending |
| GEN-20 live smoke per adapter behind `live` marker + key gate | P2 eval | D | Pending |
| GEN-21 judge harness: faithfulness + relevancy, structured outputs, versioned prompts, JSONL results, calibration-then-gate thresholds | P2 eval | D | Pending |
| GEN-22 nightly eval workflow (cron + dispatch), secret-gated, cost-capped, artifact upload | P2 eval | D | Pending |
| GEN-23 suite stays green offline; no schema changes; frontend untouched | all | A–D | Pending |

**Coverage:** 23 total, mapped to phases A–D; 0 unmapped.

## Implicit-Requirement Dimensions (sweep)

| Dimension | Resolution |
| --- | --- |
| Input validation & bounds | Existing question/message bounds unchanged (GEN-14 reuses validators); sentinel matching is whole-reply-anchored (edge case) |
| Failure / partial-failure | GEN-07 (502), GEN-16 (mid-stream error part), GEN-17 (disconnect), partial `max_tokens` edge case |
| Idempotency / retry / duplicates | SDK default transport retries only (D-6); no new write paths except teaching turn (existing conflict handling applies); `--record` rewrites snapshots idempotently |
| Auth boundaries & rate limits | GEN-14: stream endpoints reuse the exact dependency set of their JSON siblings |
| Concurrency / ordering | Stateless request paths; citation order defined (GEN-05); teaching turn ordering unchanged |
| Data lifecycle / expiry | Snapshots + JSONL results are committed repo artifacts; no PII beyond book text already in repo fixtures; cache TTL 1h is provider-side |
| Observability | Adapters log one content-free line per call (model, usage token counts, found flag) matching existing logging conventions |
| External-dependency failure | Provider outage → 502/error part; CI never depends on provider (GEN-23); nightly skips without secret (GEN-22) |
| State-transition integrity | Teaching turn persisted only on stream completion (GEN-13/17); `not_found` is a product outcome, never an HTTP error (unchanged) |

## Success Criteria

- [ ] With a real key: asking a question against the golden book returns synthesized prose with ≥1 valid citation; an off-topic question returns `not_found_in_source` (F5 demonstrably fixed).
- [ ] Full backend suite green offline with zero provider config (existing counts + new tests).
- [ ] SSE endpoint streams protocol-valid frames under the deterministic provider (verifiable offline).
- [ ] Nightly workflow present, dispatchable, secret-gated; judge module unit-tested offline.
