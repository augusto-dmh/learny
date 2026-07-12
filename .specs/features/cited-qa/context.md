# cited-qa — Discuss Decisions (auto-decided per ship-cycle contract)

Gray areas resolved via the learny-ship-cycle auto-decision rule: each decision
lists the options with why-recommend AND why-not, the chosen (recommended)
option, and the rationale — auditable without the conversation. Mirrored as
AD-024..AD-029 in `.specs/project/STATE.md`.

## D-1 — Answer generation provider (→ AD-024)

**Question:** TDD Phase 7 says "answer-generation port, provider adapter". Which
adapter ships as the default?

- **Option A (chosen, recommended): Learny `AnswerGenerationPort` + a
  deterministic, evidence-grounded local adapter; cloud provider adapter is a
  follow-up ADR.**
  - Why recommend: exact precedent AD-019 (embedding provider, previous cycle);
    CLAUDE.md forbids assuming a concrete provider/model default without an
    accepted ADR; testable with zero network/secrets/billing; the port contract,
    endpoint, grounding guard, citations, and "not found" behavior — the durable
    product surface — all ship for real and are unchanged when a provider
    adapter lands.
  - Why not: users get extractive/composed answers from evidence snippets, not
    LLM prose, until the provider ADR lands; the "first real LLM call" is
    deferred a second time.
- **Option B: pick a cloud provider (OpenAI or Anthropic) now, ADR in-cycle.**
  - Why recommend: real generative answers immediately; Phase 7's spirit.
  - Why not: locks an external provider — exactly what CLAUDE.md/ADR-0007 say
    needs its own decision; requires API keys/billing the user must provision
    (can't be auto-decided); would trip the ship-cycle escalation rule.

**Rationale for auto-deciding rather than escalating:** the escalation rule
fires when a provider lock-in has *no clear recommendation*. Option A does not
lock a provider and has direct precedent, so a clear recommendation exists.
Flag at the merge gate: the provider ADR is now the blocking follow-up for
LLM-generated prose.

## D-2 — Answer persistence (→ AD-025)

- **Option A (chosen, recommended): stateless Q&A — no `qa_answers` /
  `answer_citations` tables this cycle.**
  - Why recommend: TDD-001 marks answer persistence "Optional"; no MVP consumer
    exists (no history UI in scope; Phase 8 sessions have their own tables;
    Phase 9 fixtures can invoke the service directly); keeps the slice free of
    a migration + repo + lifecycle/retention questions.
  - Why not: no answer history/audit trail; re-asking re-runs retrieval and
    generation.
- **Option B: persist answers + citations now.**
  - Why recommend: audit trail, future history UI ready, evaluation replay.
  - Why not: schema + lifecycle (retention, deletion, ownership) decisions with
    no consumer; scope creep versus the phase outcome.

## D-3 — Endpoint contract & "not found" representation (→ AD-026)

- **Chosen (recommended): `POST /api/sources/{source_id}/questions` (TDD API
  outline), body `{question}`. 200 for every well-formed ask against a ready
  owned source, with `answer_status: "answered" | "not_found_in_source"` in the
  body. 404 missing/non-owned (no existence disclosure, matches
  retrieve/structure). 409 when the source exists but `status != "ready"`.
  422 empty/whitespace/over-long question. No `top_k` in the request — evidence
  depth is a server-side setting.**
  - Why recommend: "not found in source" is a successful, first-class product
    outcome (ADR-0003 / TDD security list: "explicit not-found response"), not
    an HTTP error; keeps the browser client trivial; mirrors Cycle-5's empty
    list = 200 hook. Hiding `top_k` keeps prompt-shaping knobs out of the
    public API.
  - Why not (alternatives): 404/204 for not-found conflates transport errors
    with a product answer and breaks the citation-inspection UI; exposing
    `top_k` invites clients to tune retrieval, which is a server concern.

## D-4 — Grounding guard placement (→ AD-027)

- **Chosen (recommended): the application service (`AskQuestion`) enforces
  grounding: every citation the adapter returns must reference a chunk id in
  the retrieved evidence set; non-member citations are discarded; if none
  remain (or answer text is empty) the result is `not_found_in_source`. Empty
  evidence short-circuits — the generation port is never invoked.**
  - Why recommend: grounding is a Learny product invariant (ADR-0003), so it
    lives in Learny-owned application code, not per-adapter goodwill; it holds
    for every future provider adapter automatically; skipping generation on
    empty evidence saves provider cost and is deterministic.
  - Why not: trusting adapters keeps the service smaller but lets a future
    provider hallucinate citations; validating in the web layer would duplicate
    per-transport.

## D-5 — Vertical slice: frontend ask panel (→ AD-028)

- **Chosen (recommended): full slice per AD-010 — an Ask panel for ready
  sources (question form → answer text, citations with section path + snippet,
  explicit not-found message, readable 401/404/409/429/502 errors) through the
  existing same-origin proxy. AD-023 deferred Cycle 5's frontend precisely
  because Phase 7 is the intended user surface.**
  - Why recommend: restores the full-slice cadence; Phase 7 outcome is
    explicitly user-facing ("users can ask ... and inspect citations").
  - Why not: more scope than backend-only; but backend-only would repeat the
    AD-023 departure with its justification now gone.

## D-6 — Rate limiting & question bounds (→ AD-029)

- **Chosen (recommended): reuse the existing swappable in-process fixed-window
  limiter with a `rate_limit_questions` dependency on the questions endpoint
  (conservative default, same known proxy-IP limitation); bound the question at
  `LEARNY_QA_QUESTION_MAX_CHARS` (default 2000) → 422 above; evidence depth
  from `LEARNY_QA_EVIDENCE_TOP_K` (default 8).**
  - Why recommend: TDD-001 explicitly lists Q&A among endpoints needing
    rate-limit hooks "even if initial thresholds are conservative"; reuse means
    no new infrastructure; bounds keep provider payloads finite.
  - Why not: in-process limiter shares the documented proxy-IP weakness
    (accepted since Cycle 1); a Redis limiter is a later swap.

## Deviations (Execute)

- SPEC_DEVIATION (additive, accepted): QA-04 requires `model` on every 200
  response, but QA-13 forbids invoking the port on empty evidence — so the
  service reads a stable `model` attribute off the injected port instead of a
  `generate()` result. `AnswerGenerationPort` therefore declares `model: str`
  (orchestrator commit after Phase B), and `DeterministicAnswerAdapter` exposes
  it publicly. Design §AnswerGenerationPort updated to match.

## Process note

Per the ship-cycle autonomy contract, the spec below was not paused for user
confirmation; the closure gate ran with these auto-decisions recorded as
assumptions. Escalation was evaluated for D-1 and not triggered (see D-1
rationale).
