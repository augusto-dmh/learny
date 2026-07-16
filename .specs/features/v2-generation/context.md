# v2-generation — Decision Context

Gray areas auto-decided per the learny-ship-cycle auto-decision rule (no user prompt; each option lists why-recommend AND why-not; recommended option chosen). Ledger: AD-058..AD-064 in `.specs/project/STATE.md`.

## D-1 — Generation model (→ AD-058)

- **`claude-sonnet-4-6` (chosen, recommended)** — Why: RFC-002 pins it for Cycle C; 2026-07-12 research verified cost (~$0.0225/answer, ~$0.010/cached teaching turn) and citation/caching support; 1M context; adaptive thinking available but unneeded for grounded extraction-style generation. Why not: not the newest Sonnet; Sonnet 5 may eventually be better per dollar during intro pricing.
- **`claude-sonnet-5`** — Why: same sticker price with intro discount through 2026-08-31; newest Sonnet tier. Why not: new tokenizer (~30% more tokens for same text → cost/max_tokens re-baseline), rejects non-default sampling params, and the RFC itself says "re-baseline before switching"; switching later is a settings change + eval re-run, which the eval harness this cycle ships makes cheap.
- **`claude-opus-4-8`** — Why: quality ceiling; the API guidance default. Why not: ~1.7× output price; RFC-002's cost envelope for an author-scale portfolio product deliberately chose the Sonnet/Haiku split; Opus stays the documented escalation path in ADR-0020 if answer quality disappoints.

Model id lives in `LEARNY_GENERATION_MODEL` so the swap is config + eval re-baseline, not code. Judge model `claude-haiku-4-5` via `LEARNY_JUDGE_MODEL` (research: sufficient for binary claim-support; Sonnet tier is the escalation).

## D-2 — Provider switch + factory shape (→ AD-059)

- **Single `LEARNY_GENERATION_PROVIDER` (`local`|`anthropic`) covering both ports, two factory functions (chosen, recommended)** — Why: mirrors AD-052's embeddings pattern exactly (`build_embedding_adapter`); both ports ship the same provider this cycle; deterministic default keeps CI/local offline and key-free; unknown value → `ValueError` (no silent fallback). Why not: can't run answers on Anthropic while teaching stays local — no current need, and adding a second flag later is additive.
- **Per-port provider flags** — Why: independent rollout/rollback per surface. Why not: doubles config surface with no consumer; contradicts the one-cycle provider decision; YAGNI.
- **Factory returns both adapters from one call** — Why: single switch point. Why not: DI composes the two services separately today (`dependencies.py:330,400`); two functions keep each dependency's wiring a one-line change as the code comments promise.

Fail-fast: `anthropic` provider with empty `LEARNY_ANTHROPIC_API_KEY` raises at construction (config error), never a runtime 502 surprise.

## D-3 — Citations request/response mapping + F5 sentinel (→ AD-060)

- **One plain-text citations-enabled document per chunk; map by `document_index`; whole-reply sentinel for not-found (chosen, recommended)** — Why: Anthropic docs' explicit RAG guidance ("put each RAG chunk into a plain text document"); `char_location` offsets become sub-chunk anchors for a later UI; `document_index → chunk_id` is the only documented-stable mapping (title/context are never returned in citations); citations+`output_config.format` return 400, so a schema-enforced `found` flag is impossible in one call — an exact sentinel reply (`NOT_FOUND_IN_SOURCE`, whole-reply anchored) is the deterministic substitute, and AD-027 grounding remains the backstop for zero-citation prose. Why not: sentinel is prompt-enforced, not schema-enforced — a model could leak it mid-prose (mitigated: whole-reply match only + grounding backstop + judge harness watches faithfulness).
- **Custom-content documents (one block per sentence)** — Why: exact citable granularity control. Why not: we don't need sub-snippet granularity yet; plain-text gives sentence-level `char_location` for free.
- **Two-pass (citations pass + structured verdict pass)** — Why: schema-guaranteed verdict. Why not: 2× calls/latency/cost on the hot path; research recommends against as default.

## D-4 — Streaming architecture (→ AD-061)

- **Learny-owned domain stream events + port streaming method; grounded citations in one terminal `data-citations` part; separate `/stream` sibling endpoints (chosen, recommended)** — Why: RFC Cycle C explicitly ships the SSE surface so Cycle D is purely frontend; a Learny event vocabulary keeps the Vercel protocol at the edge (presenter module) per ADR-0009/AD-016 port discipline; emitting citations once post-stream keeps AD-027 grounding a single enforcement point (incremental citation events would need incremental grounding); sibling endpoints leave the JSON contract untouched for the current frontend. Why not: token-level citation highlighting mid-stream is deferred (Cycle D can still anchor from the terminal part); two endpoints per surface until Cycle D consolidates.
- **Defer all SSE to Cycle D** — Why: smaller cycle; streaming has no consumer yet. Why not: contradicts the accepted RFC's cycle contents; Cycle D would then mix backend protocol work with the UI rebuild it's scoped to avoid.
- **Fake-stream the buffered result (chunk a completed answer)** — Why: trivial. Why not: no latency benefit — defeats the purpose; misleading to Cycle D.

Transport: `fastapi.sse.EventSourceResponse` (FastAPI 0.138.1 installed ≥ 0.135 floor; raise pin to `>=0.135`). Teaching stream persists the turn only after successful completion; `CancelledError` closes the provider stream.

## D-5 — Eval harness shape (→ AD-062, AD-063)

- **Port-level replay + skip-when-absent snapshots; Learny-owned ~200-line judge; nightly workflow (chosen, recommended)** — Why: evaluation research conclusion #3 (replay at the port boundary survives SDK upgrades and provider swaps; VCR/httpx-streaming is flaky); CI stays offline (AD-052/AD-056 precedent — committed real snapshots are a keyed follow-up the `--record` flag makes one command); judge = faithfulness + relevancy with structured outputs on Haiku, prompts as versioned files, JSONL results in-repo (git is the dashboard, no Ragas per research conclusion #2 + locked v2 decision); thresholds calibrate on first runs then gate. Why not: replay snapshots only cover cases someone recorded; judge scores are themselves model-produced (mitigated: deterministic invariants stay the hard gate; judge is nightly signal, not a PR gate).
- **vcrpy HTTP cassettes** — Why: exercises real request shaping. Why not: leaks headers, breaks on SDK upgrades, documented rough edges with httpx streaming; the fake-client unit tests already pin request shape.
- **Judge as PR gate** — Why: earliest signal. Why not: paid + nondeterministic in CI; nightly with aggregate thresholds absorbs per-case flakiness (research §5).

## D-6 — Retries/timeouts (→ folded into AD-060)

- **SDK defaults (2 transport retries, default timeout); no app retry layer (chosen, recommended)** — Why: request path is interactive (user waiting); Celery-style retry ownership doesn't apply to HTTP handlers; SDK already handles 429/5xx sanely. Why not: a transient provider blip becomes a user-visible 502 — acceptable; the client can re-ask.
- **App-level retry/backoff wrapper** — Why: fewer user-visible failures. Why not: multiplies worst-case latency on an interactive path; hides provider health.

## D-7 — Slice shape (→ AD-064)

- **Backend-only slice, 5th consecutive (chosen, recommended)** — Why: the SSE consumer is Cycle D by design; wiring the current buffered frontend to Claude requires zero frontend changes (same JSON contract). Why not: departs from AD-010 full-slice cadence again — flagged at merge gate per AD-051 precedent.
- **Minimal frontend toggle/badge showing the live model** — Why: visible demo. Why not: throwaway before Cycle D's rebuild; `model` field already surfaces in JSON responses.

## D-8 — Execute delegation (process)

- **One sub-agent worker per phase (A–D), Opus for all four (chosen, recommended)** — Why: 4 phases > 3 triggers tlc's sub-agent model; every phase carries design decisions or correctness invariants (request-shape contracts, caching prefix rules, stream cancellation, eval semantics) — per the ship-cycle cost-discipline table none passes the Haiku-safe test; Verifier always Opus. Why not: more tokens than inline execution — accepted for context isolation and per-phase atomicity.
- **Inline execution** — Why: cheaper. Why not: 4 phases × large context (SDK shapes, protocol specs) would blow the orchestrator budget and mix authorship.
- MCPs: none. Skills context: workers receive the needed API shapes in their payloads (no skill invocation inside workers).
