# ADR-020: Use Anthropic Claude For Cited Answer And Teaching Generation

- **Date**: 2026-07-16
- **Status**: Accepted
- **Deciders**: Augusto, Codex
- **Tags**: architecture, ai, generation, teaching, anthropic, citations, evaluation

## Context and Problem Statement

The MVP shipped cited Q&A and teaching sessions on deterministic, network-free
answer/teaching adapters behind the Learny-owned `AnswerGenerationPort` and
`TeachingGenerationPort` (ADR-0007). Those adapters stitch verbatim evidence
snippets together: they produce no synthesized prose, and their "not found in
source" outcome only fires on *empty* retrieval — they cannot judge whether
retrieved evidence is actually relevant to the question (QA finding F5). Choosing
the cloud generation provider has been the blocking follow-up ever since the
deterministic adapters were introduced.

RFC-002 Cycle C replaces that baseline with a real large language model for the
answer and teaching paths. The decisions to make are: which provider and model;
how to attach citations to exact passages without letting the provider's response
shape leak across the port; and how to express a relevance-aware "not found"
outcome, given that the provider's Citations API and its structured-output mode are
mutually exclusive in a single request.

Research evidence: `docs/research/2026-07-12/anthropic-generation.md`.

## Decision Drivers

- Materially better answers and teaching turns than verbatim snippet stitching,
  with citations to the exact passages relied on.
- A relevance-aware not-found outcome (fix F5): the model can decline irrelevant
  evidence, not only empty evidence.
- Keep the provider SDK, model names, and citation formats behind the existing
  generation ports (ADR-0007/0009) — no provider leak into application/domain code.
- Keep CI and local development offline and key-free by default.
- Keep operating cost negligible at hobby scale.
- Reuse a single grounding enforcement point (ADR-0003) rather than trusting each
  adapter to self-police its citations.

## Considered Options

- Anthropic Claude `claude-sonnet-4-6` for both answers and teaching.
- Anthropic Claude `claude-opus-4-8` for both (quality ceiling).
- OpenAI GPT models with an equivalent citation-annotation approach.
- Keep only the deterministic adapters.

## Decision Outcome

Chosen option: **Anthropic Claude behind the existing generation ports, with
`claude-sonnet-4-6` as the initial model for both the answer and teaching paths**,
because it pairs strong grounded-synthesis quality with a native Citations API that
maps cleanly onto Learny's per-chunk evidence, and costs about two cents per answer
— a non-factor at Learny's scale. The model is settings-swappable
(`LEARNY_GENERATION_MODEL`), so moving is a configuration change, not a rewrite: the
documented upgrade path is a re-baseline onto `claude-sonnet-5` (a drop-in that
changes the tokenizer — roughly 30% more tokens for the same text — and rejects
non-default sampling params, so answer/eval baselines are re-measured before the
flip), and the documented quality escalation is `claude-opus-4-8` if Sonnet answers
disappoint.

The implementation model is:

1. Add `AnthropicAnswerAdapter` and `AnthropicTeachingAdapter` implementing the
   existing ports; the `anthropic` SDK is imported only inside that adapter module,
   lazily, so the module stays import-light and tests inject a fake client.
2. Send **one plain-text, citations-enabled `document` block per retrieved chunk**,
   in evidence order, with citations enabled on every document (the API's
   all-or-none rule). Map each response citation back to its chunk strictly by
   `document_index` (the 0-based order of document blocks in the request) — never by
   `document_title`, which the API does not return in citation objects.
3. Express the not-found outcome with a **frozen system prompt plus an exact
   sentinel** (`NOT_FOUND_IN_SOURCE`): because enabling citations forbids structured
   outputs in the same request, a whole-reply sentinel is the deterministic
   relevance signal. The adapter maps a whole-reply sentinel to `found=False`; an
   embedded occurrence stays as prose (leak guard).
4. Keep grounding (ADR-0003) as the single post-generation enforcement point: cited
   chunk ids are intersected with the retrieved evidence, so a malformed or
   out-of-set citation is discarded and, if none survive, the outcome is
   `not_found_in_source`. The provider is never trusted to self-police.
5. Cache the teaching prompt prefix: the frozen teaching system prompt carries a
   `ttl: "1h"` `cache_control` breakpoint and the latest history turn carries a
   second, with per-turn volatile content (evidence, the new message) strictly after
   the cached prefix. (The teaching adapter and its caching land in this cycle's
   later phases; this ADR records the direction.)
6. Select the adapter at the composition root from `LEARNY_GENERATION_PROVIDER`
   (`local` → deterministic, `anthropic` → the Claude adapters built from the
   key/model/max-tokens settings). An empty key with the `anthropic` provider fails
   fast at composition; an unrecognized value is a loud configuration error, never a
   silent default.
7. Retain the deterministic adapters as the CI/local default
   (`LEARNY_GENERATION_PROVIDER=local`), so the suite stays network-free and no key
   is required to run or test Learny.

Provider keys stay environment-only; no key is committed. This closes the cloud
generation-provider follow-up left open by the deterministic answer/teaching
adapters (the embedding half was closed by ADR-0019).

### Positive Consequences

- Real synthesized, cited answers and coherent multi-turn teaching, replacing
  verbatim snippet stitching.
- Relevance-aware not-found (F5 fixed): the model can decline off-topic evidence.
- The provider stays behind the ports; swapping models or providers later is a
  settings change plus re-baselining, not a code rewrite.
- CI/local stays offline and key-free; grounding remains a single enforcement point
  shared by both paths.
- Negligible cost (~$0.02/answer; ~$0.01/turn with prompt caching).

### Negative Consequences

- A real provider dependency, key management, and rate/latency considerations enter
  the request path (bounded by the SDK's default transport retries; no extra retry
  layer).
- The Citations API and structured outputs cannot coexist in one request, so the
  not-found signal rides on a prompt-instructed sentinel rather than a schema — a
  prompt-adherence dependency the evaluation harness watches.
- Teaching's cache prefix can fall below the model's minimum cacheable size on early
  turns, silently missing the cache (a cost effect, not a correctness one); logged
  via `cache_read_input_tokens` and improving as history grows.

## Pros and Cons of the Options

### Anthropic Claude `claude-sonnet-4-6` ✅ Chosen

- ✅ Native Citations API maps directly onto per-chunk evidence with stable
  `document_index` identity and free sub-chunk anchors.
- ✅ Strong grounded-synthesis and multi-turn pedagogy quality at ~$0.02/answer.
- ✅ Prompt caching composes with citation documents for cheap teaching turns.
- ❌ Citations forbid structured outputs in the same request, so not-found relies on
  a sentinel convention rather than a schema.

### Anthropic Claude `claude-opus-4-8`

- ✅ Highest synthesis/faithfulness quality — the quality ceiling.
- ❌ Roughly double the per-answer cost for a margin the flagship answer path does
  not yet need; recorded as the escalation path if Sonnet answers disappoint.

### OpenAI GPT with equivalent citation annotation

- ✅ Already a Learny provider for embeddings (ADR-0019); one fewer vendor.
- ❌ No first-class citations-with-exact-passage API of the same shape; grounding
  fidelity would rely more on prompt-level conventions and post-hoc matching. The
  port abstraction keeps this a later config option if ever justified.

### Keep only the deterministic adapters

- ✅ Zero dependency, zero cost, fully offline.
- ❌ No synthesis and no relevance judgement — verbatim stitching with not-found only
  on empty retrieval (F5 unfixed); unacceptable as the product generation path.
  Retained only as the CI/local default.

## References

- [ADR-003: Citations And Evaluation Are Core Requirements](0003-citations-and-evaluation-are-core-requirements.md)
- [ADR-007: Use Learny-Owned Ports For AI Provider Integration](0007-use-learny-owned-ports-for-ai-provider-integration.md)
- [ADR-009: Use Learny-Owned Orchestration With Specialized Edge Libraries](0009-use-learny-owned-orchestration-with-specialized-edge-libraries.md)
- [ADR-016: Use Golden Fixtures For MVP Evaluation](0016-use-golden-fixtures-for-mvp-evaluation.md)
- [ADR-019: Use OpenAI Embeddings With Per-Chunk Model Versioning](0019-use-openai-embeddings-with-per-chunk-model-versioning.md)
- [RFC-002: Learny v2 Roadmap](../rfc/0002-learny-v2-roadmap.md)
- Anthropic generation research (2026-07-12): `../research/2026-07-12/anthropic-generation.md`
- Anthropic Citations guide: https://platform.claude.com/docs/en/build-with-claude/citations
- Anthropic Prompt Caching guide: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- Anthropic Structured Outputs guide: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
