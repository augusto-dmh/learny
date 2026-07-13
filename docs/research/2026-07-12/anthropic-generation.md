# Learny v2 research — anthropic-generation

Generated 2026-07-12 by a web-research agent (v2 planning research fleet). Sources/dates inline; verify load-bearing claims before implementation.

---

# Anthropic Integration Design Facts for Learny's Generation Ports

All facts verified 2026-07-12 against official docs (platform.claude.com); pricing from Anthropic's current model catalog (cached 2026-06-24). Sources: [Citations](https://platform.claude.com/docs/en/build-with-claude/citations), [Structured Outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), [Batch Processing](https://platform.claude.com/docs/en/build-with-claude/batch-processing), [Prompt Caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [Pricing](https://platform.claude.com/docs/en/pricing).

## Executive recommendations (per port)

| Port | Model | API features | Est. cost/op (5k in / 0.5k out) |
|---|---|---|---|
| **AnswerGenerationPort** (cited Q&A) | `claude-sonnet-4-6` ($3/$15 per MTok) | Citations API (one plain-text document per chunk), streaming SSE | ~$0.0225 |
| **TeachingGenerationPort** (multi-turn) | `claude-sonnet-4-6` | Citations + prompt caching (evidence+system cached), streaming | ~$0.026 first turn, ~$0.010/turn cached; ~$0.12 for a 10-turn session |
| **QuizGenerationPort** (new) | `claude-haiku-4-5` ($1/$5) | Structured outputs (`messages.parse`), chunk-ids-via-schema-enum (NOT Citations API), Batch API for bulk | ~$0.006/quiz batched; ~$0.012 online |

Note: Anthropic's own default guidance is "use the latest Opus (`claude-opus-4-8`, $5/$25) unless cost decides otherwise." Given Learny's portfolio/no-revenue posture, the Sonnet/Haiku split above is the pragmatic call — Opus 4.8 at ~$0.0375/answer is the quality ceiling if answers disappoint. `claude-sonnet-5` ($3/$15; intro $2/$10 through 2026-08-31) is a drop-in upgrade but uses a new tokenizer (~30% more tokens for the same text) and rejects non-default `temperature`/`top_p` — re-baseline before switching.

## 1. Citations API — exact shapes

**Request (custom content document, one per retrieved chunk):**
```json
{"type": "document",
 "source": {"type": "content", "content": [
     {"type": "text", "text": "First chunk sentence group..."},
     {"type": "text", "text": "Second..."}]},
 "title": "Ch. 3 §2 — The Method of Loci",
 "context": "{\"chunk_id\": \"...\", \"anchor\": \"epub:ch3#s2\"}",
 "citations": {"enabled": true}}
```
- `citations.enabled` must be **all-or-none across every document in the request** (mixed → error).
- `title` and `context` are passed to the model but are **never cited from and never returned in citation objects** — the docs explicitly suggest `context` for "document metadata as text or stringified JSON". Mapping back to your chunk therefore rides on **`document_index`**, not on title/context.

**Response citation (custom content):**
```json
{"type": "content_block_location",
 "cited_text": "The exact text being cited",
 "document_index": 0,
 "document_title": "Ch. 3 §2 — The Method of Loci",
 "start_block_index": 0,
 "end_block_index": 1}
```
Semantics (verbatim from docs): `document_index` is 0-indexed **across all document blocks in the request, spanning all messages**. `start_block_index` is 0-indexed into that document's `content` list; `end_block_index` is **exclusive**. Custom-content blocks are used **as-is — no further chunking** — so a block is the minimum citable unit. Response text is split into multiple `text` blocks; cited blocks carry a `citations` array.

**Per-chunk documents vs one-doc-many-blocks — recommendation: one document per chunk.**
- The docs' explicit RAG guidance: *"if you want Claude to be able to cite specific sentences from your RAG chunks, you should put each RAG chunk into a plain text document"* (source `{"type": "text", "media_type": "text/plain", "data": ...}`). Then citations come back as `char_location` (`start_char_index`/`end_char_index`, 0-indexed, exclusive end) **within that chunk** — `document_index` → your `chunk_id`, char offsets → sub-chunk highlight. This is the best fit for Learny: chunk-level identity via index, sentence-level anchors for the UI, automatic sentence chunking for free.
- Use **custom content** (`type: "content"`) only if you must control granularity exactly (bullet lists, verse, tables) — then `content_block_location` block indices are your sub-anchors.
- One document containing all chunks as blocks is worse: a citation can span consecutive blocks (`start`..`end`), which is meaningless across non-contiguous retrieved chunks, and you lose per-chunk `title`/`context`.
- **Adapter mapping rule:** build an ordered list `request_doc_index → chunk_id` when assembling the request; resolve citations by `document_index`. Never parse `document_title`.

**Token economics (significant for Learny):** `cited_text` does **not** count toward output tokens, and when passed back in later turns does **not** count toward input tokens. Enabling citations adds a small input overhead (system-prompt additions + chunking). Citations work with prompt caching, token counting, and batch processing (explicit in docs). ZDR-eligible. Supported on all active models except Haiku 3 (so Haiku 4.5 ✅).

## 2. Structured outputs incompatibility — confirmed

Verbatim: *"If you enable citations on any user-provided document (`document` blocks or `search_result` blocks) and also include the `output_config.format` parameter (or the deprecated `output_format` parameter), the API returns a 400 error."* Reason: citations require interleaving citation blocks with text output, incompatible with strict JSON schema constraints. Implication: **a single call cannot return schema-guaranteed quiz JSON with API citations.** (Strict tool use — `strict: true` on a tool — is not named in the incompatibility, but it doesn't help: citations attach only to `text` blocks, and a quiz emitted as `tool_use.input` carries no citations anyway.)

## 3. Streaming citations (SSE)

Citations arrive as a **`citations_delta`** delta type inside ordinary `content_block_delta` events, each carrying one complete citation object to append to the current `text` block's `citations` list:
```
event: content_block_delta
data: {"type":"content_block_delta","index":0,
       "delta":{"type":"citations_delta",
                "citation":{"type":"char_location","cited_text":"...","document_index":0, ...}}}
```
Pattern per cited block: `content_block_start` → `text_delta`s → `citations_delta`(s) → `content_block_stop`. For Learny: FastAPI streams SSE through the Next.js proxy untouched; the frontend accumulates per block `index` and resolves `document_index → chunk_id` client-side (ship the mapping alongside the stream, e.g., an initial metadata event). Python SDK: `client.messages.stream(...)`, handle `event.delta.type == "citations_delta"`; `stream.get_final_message()` yields fully-assembled `citations` arrays for persistence.

## 4. Model choice + costs per workload

Current pricing ($/MTok in/out): **Haiku 4.5** 1/5 (200K ctx) · **Sonnet 4.6** 3/15 (1M ctx) · **Sonnet 5** 3/15, intro 2/10 through 2026-08-31 (1M) · **Opus 4.8** 5/25 (1M). Assume ~4k evidence + ~1k system/question ≈ 5k input, 500 output.

- **Cited Q&A → Sonnet 4.6, ~$0.0225/answer** (5k×$3 + 0.5k×$15). Haiku 4.5 is ~$0.0075 and supports citations — fine as a cheap tier, but Sonnet's synthesis/faithfulness margin matters for the flagship "grounded answers" claim. Opus 4.8 ~$0.0375 — premium option.
- **Multi-turn teaching → Sonnet 4.6 + prompt caching.** Warm, coherent multi-turn pedagogy is where Haiku degrades most; Sonnet is the sweet spot.
- **Quiz generation → Haiku 4.5.** Template-shaped extraction over provided evidence is Haiku's lane; schema enforcement removes the format-reliability worry. Spot-check quality; upgrade to Sonnet 4.6 (~3× cost) only if distractor quality is weak. 10-question quiz (~5k in / ~1.5k out): Haiku online ~$0.012, **batched ~$0.006**; Sonnet 4.6 batched ~$0.019.

Thinking config differs per model — encapsulate in the adapter: Sonnet 4.6 → `thinking: {"type": "adaptive"}` (no beta); Haiku 4.5 → older style `{"type": "enabled", "budget_tokens": N}` or omit (for extractive quiz gen, omit); Sonnet 5 → adaptive is default even when omitted, and non-default `temperature` 400s.

## 5. Prompt caching for teaching sessions

Caching is a strict **prefix match**; render order `tools → system → messages`. Recipe for TeachingGenerationPort:
- Frozen system prompt (no timestamps/session IDs interpolated) + evidence documents in the **first user message**, `cache_control: {"type": "ephemeral"}` on the **last document block**. Per-turn student messages append after the breakpoint; also drop a breakpoint on the latest turn so history accrues incrementally (max 4 breakpoints).
- Economics: reads ~0.1× input price; writes 1.25× (5-min TTL) or 2× (1-hour TTL). Sonnet 4.6, 5k prefix: write ≈ $0.019, each cached turn ≈ $0.0015 read + new tokens + $0.0075 output ≈ **$0.010/turn vs ~$0.0225+ uncached** (and growing with history). ~10-turn session ≈ $0.12.
- **TTL pitfall:** teaching sessions have human think-time; gaps >5 min between turns silently re-pay the write. Use `ttl: "1h"` (2× write, break-even ≥3 turns — nearly always true for teaching) — this is the right default here.
- **Minimum cacheable prefix is model-dependent and silently enforced:** Sonnet 4.6 = 2048 tokens (fine), **Haiku 4.5 = 4096** — a lean Haiku teaching prefix may silently never cache (`cache_creation_input_tokens: 0`). Another reason teaching stays on Sonnet. Verify via `usage.cache_read_input_tokens`.
- Citations + caching compose: document blocks are cacheable content blocks.

## 6. Batch API for bulk quiz generation

`POST /v1/messages/batches` (Python: `client.messages.batches.create(requests=[Request(custom_id=..., params=MessageCreateParamsNonStreaming(...))])`). Facts: **50% off all token usage** (stacks with prompt caching, though cache hits across batch items aren't guaranteed — items run concurrently); up to 100k requests / 256 MB per batch; most complete <1 h, 24 h max; results retrievable 29 days; **results arrive in any order — key by `custom_id`** (use your quiz-job or section ID); poll `processing_status == "ended"` then stream `.results()`; per-item results are `succeeded`/`errored`/`canceled`/`expired`. All Messages API features supported, including structured outputs and citations. **Fit for Learny: excellent** — "generate a spaced-repetition deck for this book" after ingestion is asynchronous by nature; run it as a Celery task that submits one batch (one request per section/chunk-group), polls, and upserts cards keyed by `custom_id`. Haiku 4.5 batched ≈ $0.006/quiz → a 300-section book ≈ **$1.80**.

## 7. Quiz JSON strategy (since citations + `output_config.format` = 400)

Evaluated options:
1. **Recommended — structured outputs with chunk-ids-in-schema (single pass, no Citations API).** Pass chunks as plain text with explicit IDs (`[chunk:abc123] ...text...`). Schema per question: `{"question", "options": [...], "correct_index", "source_chunk_id": {"enum": [<the actual retrieved chunk ids>]}, "evidence_quote"}` with `additionalProperties: false`. The **enum guarantees a valid chunk id** (schema-enforced — this replaces the Citations API's validity guarantee). Then verify `evidence_quote` server-side with a normalized substring match against the chunk; drop/regenerate questions that fail (deterministic, cheap, testable with golden fixtures — on-brand for Learny's eval philosophy). Use `client.messages.parse(...)` with a Pydantic model → `response.parsed_output`. Caveats: no recursive schemas, no min/max numeric or length constraints, `additionalProperties: false` required, enum casing can drift (compare case-insensitively); first request per new schema pays a one-time compilation cost (24 h schema cache); `stop_reason == "max_tokens"` → incomplete JSON, so size `max_tokens` generously (~4k for 10 questions).
2. **Two-pass** (pass 1: citations-enabled fact extraction; pass 2: Haiku formats to JSON): API-grade citations but 2× calls/latency and citation indices must survive re-serialization. Not worth it as the default; reasonable for a high-assurance eval pipeline later.
3. **Strict tool use as the output channel:** no benefit over `output_config.format` — tool inputs can't carry citations, and it adds tool-loop machinery. Skip.

## Pitfalls checklist

- Never map citations via `document_title` — only `document_index` (order of document blocks in the request, across all messages).
- `end_*_index` fields are **exclusive**; PDF pages are 1-indexed; char/block indices 0-indexed.
- Citations enablement is all-or-none per request.
- `output_config.format` (and deprecated `output_format`) + any citations-enabled document → 400. Keep AnswerGeneration and QuizGeneration on different request shapes in the adapter.
- Don't count on `cited_text` for cost math — it's free on output and on replayed input.
- Cache invalidators: any interpolated timestamp/UUID in system prompt, unsorted JSON, model switch (caches are per-model — switching Sonnet→Haiku mid-session cold-starts).
- Haiku 4.5's 4096-token cache minimum and 200K context; Sonnet 5's new tokenizer (+~30% tokens) and rejected sampling params.
- Batch results are unordered and can individually error/expire — idempotent upserts keyed by `custom_id`.
- SDK: non-streaming requests with large `max_tokens` raise a `ValueError` guard in the Python SDK — stream anything long (teaching turns especially).
