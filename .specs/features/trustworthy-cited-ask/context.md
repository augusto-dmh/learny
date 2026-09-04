# trustworthy-cited-ask Context

**Gathered:** 2026-09-03
**Spec:** `.specs/features/trustworthy-cited-ask/spec.md`
**Status:** Ready for design

Ship-cycle auto-decisions (recommended option at every fork). No user prompt; each row is an `AD-NNN` in STATE.md.

---

## Feature Boundary

Make cited Ask trustworthy for a stranger: never delete a failed turn's conversation or message; pin and fix the real-provider Anthropic 400; surface citation spans the API already returns. No model swap, no retrieval rewrite, no streaming redesign, no activation event, no teach playbook.

---

## Implementation Decisions

### D-1 — Failed turns persist (`failed`) → AD-262

- Persist the user message on generation failure as a turn with `answer_status=failed`, empty `answer_text`, no citations.
- HTTP still signals failure (502 / stream error part) so the client can render the error.
- Supersedes AD-034's "502 persists nothing" for the unified conversation path (that rule was the teaching-era empty-502 contract; it is exactly what makes reload lose the question).
- **Why-recommend:** must-be-true says the message survives, which reload cannot do from `useChat` memory alone.
- **Why-not:** a `failed` vocabulary addition; clients that switch on three statuses need a fourth. Bound: treat unknown status as failed-looking (empty answer), and pin the new wire string in the domain test.

### D-2 — Retry is a new turn → AD-263

- The retry control resubmits the same text as a **new** turn on the same conversation.
- The failed turn stays in history.
- **Why-recommend:** diagnosis and honesty; in-place replace would hide the 400 from the thread.
- **Why-not:** a noisy transcript if the provider flaps. Accepted: one failed row plus a success is the truthful record.

### D-3 — Stop deleting provisional conversations → AD-264

- Remove `discardProvisional`'s `deleteConversation` on abort / disconnect / error.
- Announce the conversation to the dock when it is created (or on first persist), not only on success.
- **Why-recommend:** that DELETE is the observed vaporize; the backend never deleted.
- **Why-not:** the original comment feared empty dock orphans. After D-1 those conversations have a failed turn, so they are not empty.

### D-4 — Spans ship in this cycle → AD-265

- Do not split claim-level citations to a follow-up PR.
- **Why-recommend:** rq13 Cycle 1 is an adapter + view change; the 400 fix without tactile citations still fails rq01 item 1.
- **Why-not:** if 1+2 explode, Tasks would have split. They did not: spans are Phase D, after the survival/shape kernel.

### D-5 — First span per chunk for hover / highlight → AD-266

- AD-222 numbering stays first-occurrence-per-chunk. Hover and "Show in book" use the first `CitedSpan` for that chunk.
- **Why-recommend:** changing numbering to per-API-citation would split marks for the same passage and fight AD-222's stream≡persist invariant.
- **Why-not:** two claims citing different sentences in one chunk share a hover. The passage region still shows the full snippet.

### D-6 — Two request shapes, never mixed → AD-267

- Flagship generate: citations-enabled documents + sentinel + thinking/effort. No `output_config.format`.
- Quiz/judge: JSON schema `output_config.format`. No citation documents.
- CI pins both. Live 400 is reproduced in Execute with a real dump; the fix follows the dump, not the hypothesis.
- **Why-recommend:** Anthropic documents Citations ⊕ structured outputs as a 400. Shape tests catch that class offline.
- **Why-not:** the walkthrough 400 might be thinking/display/`effort` instead. That is why ASK-11 is in-phase verification, not a guessed patch.

### D-7 — 4xx log shape → AD-268

- Log `request_shape`, HTTP status, `request_id`. Never document `data`, system prompt, or user message.
- **Why-recommend:** handoff diagnostic bar; existing `_log_call` is usage-only and cannot debug a 400.
- **Why-not:** logging the request body would be the fastest debug and would violate NFR-SEC-004.

### D-8 — Span persistence → AD-269

- Migration `0018`: nullable `quoted_text`, `start_char`, `end_char` on `conversation_turn_citations`.
- Deterministic adapter and legacy rows leave them null (ASK-17).
- **Why-recommend:** additive; history snapshots already live on that table (AD-033).
- **Why-not:** a JSONB array of all spans per chunk. Rejected: hover needs one quote; extra structure is unused.

### D-9 — Draft RFC-0007 rides this PR → AD-270

- Distill `docs/research/2026-09-03/synthesis.md` into `docs/rfc/0007-public-launch-roadmap.md` (Draft). This cycle is Cycle A / Bet 1.
- **Why-recommend:** ROADMAP's next unstarted row is paused RFC-005 F; Bet 1 needs a named driver. v5-A precedent (RFC landed with the first cycle).
- **Why-not:** a full RFC-writing session before any code. Rejected: synthesis already is the evidence; a slim RFC unblocks the row without another research pass.

### Agent's Discretion

- Hover card chrome: reuse existing shadcn hover/tooltip patterns on `CitationMark`; do not adopt unused `inline-citation.tsx` if it models web sources.
- Reader highlight: reuse `findQuoteOffset` + the existing paint path with the span quote as the needle.
- Where to catch Anthropic 4xx for logging: adapter, before the generic `AnswerGenerationFailed` wrap.

### Declined / Undiscussed Gray Areas → Assumptions

All gray areas auto-decided above. Abstention copy, Haiku routing, and activation events are out of scope (spec table), not declined-and-assumed.

---

## Specific References

- Observed walkthrough: embed 200 → Anthropic messages 400 → "Answer generation failed. Please try again." → conversation gone.
- `useConversationThread` (L14–21, L98–113, L155–158): provisional delete is intentional current behavior, now reversed.
- ADR-0020: `document_index` maps inside the adapter only.
- Anthropic: Citations cannot combine with `output_config.format` (400).

---

## Deferred Ideas

- `first_cited_answer` server event (Bet 5).
- Sufficient-context autorater (rq05).
- Teach playbook / Ask+Teach dock merge (Bet 3).
- Per-claim marks (one `[^n]` per API citation) — would reopen AD-222.
