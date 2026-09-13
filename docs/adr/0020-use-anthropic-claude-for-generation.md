# ADR-020: Use Anthropic Claude For Cited Answer And Teaching Generation

- **Date**: 2026-07-16
- **Status**: Accepted; amended 2026-09-07 — see Amendment below
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

## Amendment (2026-09-07): Multi-Profile Generation Routing

**Trigger.** RFC-0007 Cycle G — "Cheaper intelligence, same trust" (Bet 7) — layers
effort, caching, and fallback levers on top of this ADR's provider choice, and its
fallback-adapter work is gated on an accepted amendment to this ADR. The decisions
below answer the twelve decision inputs recorded in the research evidence:
`docs/research/2026-09-07/` (`provider-adapter-architecture.md` §4, backed by
`provider-landscape-update.md` and `subscription-as-api.md`). The original decision
above stands unchanged — Anthropic Claude is the generation primary behind the
Learny-owned ports — and this amendment governs how additional provider profiles
join, are routed, priced, promoted, and constrained.

1. **Claude remains the Ask/Teach primary.** The Citations API is still the only
   provider-computed, offset-verified citation source, and citations are the product
   promise (ADR-0003); the amendment adds tiers beside the primary, it does not
   dethrone it.
2. **The second adapter lands with the first concrete profile, not speculatively.**
   A generic OpenAI-compatible adapter is built when the first concrete economy
   profile is actually selected; the factory pattern makes waiting cheap.
3. **Degradation is declared per profile via capability flags in the settings
   registry** ("grounded-primary" vs "economy"), consumed by the router — never a
   port method, never a runtime probe. Ask/Teach fall back only to profiles that
   preserve acceptable grounding; otherwise they fail honest (`found=False` /
   `AnswerGenerationFailed`).
4. **Effort stays an adapter constructor parameter fed per profile.** The port never
   grows an effort argument; effort diets land as profile values after the judge
   gate.
5. **Fallback scope is split by path, and the streaming rule bounds the turn path.**
   Turn-path auto-fallback may fail over only before the first emitted delta; once
   answer deltas are on the wire the router has committed. The deck path pins its
   provider at `begin_deck` — the provider recorded on the deck handle — and
   retries within that provider, with no cross-provider batch retry, because a
   half-submitted batch has no portable second home.
6. **A Learny-owned error taxonomy defines retryability**: `Timeout`,
   `RateLimited`, `ProviderUnavailable`, `RequestRejected`, translated inside each
   adapter. Only timeout and provider-unavailable failures cross providers; rate
   limits retry on the same provider after backoff; request rejections never
   cross, because request shapes differ per profile.
7. **Spend accounting uses per-profile price catalogs**, resolved from the serving
   (routed) profile at the debit site; the ledger, daily caps, kill switch, and the
   deck spend marker's idempotency are unchanged.
8. **Promotion of a model to default is eval-gated process**: a candidate profile
   must run green on the nightly judge gate before an operator reorders the profile
   registry. A flip without a green nightly is a documented exception, not a habit.
9. **The spend rails apply to every profile**: the pre-flight budget assertion runs
   before any port touch regardless of which adapter serves the call, and rate
   limits stay user-keyed.
10. **Embeddings do not diversify; ADR-0019 stands.** The `dimensions` parameter is
    not portable across providers, the stored vector width is coupled to it, and a
    switch is a full re-embed.
11. **End-user provider choice is explicitly deferred.** Operator-curated house
    profiles per learner are recorded as the future one-cycle path; BYO API keys
    are a pricing-gated roadmap of their own. Nothing decided here forecloses
    either.
12. **The ADR-0009 line is restated for the new surface**: no LiteLLM, OpenRouter,
    or Portkey in the composition root; routing logic lives in a Learny-owned
    adapter; user-supplied endpoints are never a configuration input.

Throughout, the generation port stays frozen: profile metadata — capabilities,
prices, effort — lives beside the port, in the settings-declared profile registry,
never inside it.

### Amendment references

- [RFC-0007: Public-Launch Roadmap](../rfc/0007-public-launch-roadmap.md) (Cycle G, Bet 7)
- Provider adapter architecture research (2026-09-07): `../research/2026-09-07/provider-adapter-architecture.md`
- Provider landscape update (2026-09-07): `../research/2026-09-07/provider-landscape-update.md`
- Subscription-as-API research (2026-09-07): `../research/2026-09-07/subscription-as-api.md`

## Amendment (2026-09): End-User Choice Among House Profiles

**Trigger.** The `house-profiles` cycle implements the slice the previous amendment
deferred: point 11 recorded "operator-curated house profiles per learner" as the
future one-cycle path once the router and per-profile pricing existed. Both now
ship (2026-09-07 amendment, implemented in RFC-0007 Cycle G), so the deferral is
resolved. The original decision and the 2026-09-07 amendment above stand
unchanged; this amendment governs only what the learner may choose and what they
may not.

1. **Flavor A is accepted: the learner picks among operator-curated house
   profiles.** One stored preference per user names a declared profile; unsetting
   it restores the operator default. The catalog is exactly the declared registry
   minus the synthetic legacy seed — the operator's configuration is the curation;
   there is no separate user-facing catalog to keep in sync.
2. **Resolution reorders the chain; it never hard-pins it.** The user's chosen
   profile leads their Ask/Teach generation chain when it is declared and
   eligible for the mode; the remaining registry entries follow in order. All
   routing policy stays in `RoutingGenerationAdapter` — transport fail-over, the
   rate-limit backoff, the before-first-delta streaming bound, and the
   mode-eligibility walk behave exactly as for the operator default. A failing
   chosen profile degrades to the next chain entry, never to an error the house
   infrastructure could have absorbed.
3. **The choice covers Ask/Teach turn generation only.** The selection-Explain
   chain, quiz decks, and card suggestions stay house-routed: the quiz port sits
   outside the profile registry and decks pin their provider at `begin_deck`, and
   the explain chain is a house cost lever. Per-user quiz routing is a coherent
   follow-up if demand appears, not part of this acceptance.
4. **Effort stays a profile value.** The learner chooses between profiles; per-user
   effort dials would reopen what amendment point 4 closed.
5. **Honest degradation copy travels with the profile.** The registry gains
   optional learner-facing fields (`display_name`, `description`) so an operator
   can state what a profile trades away ("answers may cite less precisely"); the
   account surface shows this copy and hides itself entirely when the deployment
   declares no selectable non-default profile. Budget and rails are unchanged:
   answers stamp the serving profile, the debit resolves that profile's catalog,
   the pre-flight assertion precedes any port touch, and limits stay user-keyed
   (points 7 and 9 apply to the learner-chosen surface verbatim).
6. **A stale preference is a hint, not a contract.** If the operator renames or
   removes a profile a user had chosen, turns resolve to the operator default
   with a logged warning; the stored choice must never break asking. (Contrast
   the spoiler-safety fail-closed rule, AD-349: that one guards a correctness
   invariant; a stale profile hint does not.)
7. **BYO API keys remain deferred**, unchanged from point 11: a pricing-gated
   roadmap of their own (RQ10), with the research's abuse analysis (a
   user-supplied endpoint is never a configuration input) standing as written.
8. **The device-local precedent (AD-147) is scoped, not overturned.** Account-level
   AI serving choice is account state and lives in its own table; the
   device-local hooks for reading, home, note filters, and active conversation
   remain device-local — this amendment does not create a general per-user
   preferences mechanism.
9. **The port stays frozen.** Profile metadata — now including learner-facing copy
   — lives beside the port in the settings-declared registry, never inside it
   (ADR-0007; point 12's no-gateway line is restated for the new surface).

### Follow-up amendment references

- Provider adapter architecture research (2026-09-07), §3.2 Flavor A and §4 Q11:
  `../research/2026-09-07/provider-adapter-architecture.md`
- `house-profiles` cycle spec: `.specs/features/house-profiles/spec.md`
