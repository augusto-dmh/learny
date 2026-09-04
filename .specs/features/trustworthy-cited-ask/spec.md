# trustworthy-cited-ask Specification (RFC-0007 Cycle A / Bet 1)

## Problem Statement

On the live stack with real provider keys, Ask succeeds at OpenAI embeddings then fails at Anthropic `POST /v1/messages` with **400 Bad Request**. The UI shows a generic "Answer generation failed. Please try again." and the **conversation is deleted**. The aha event (`first_cited_answer`) cannot exist while the first question can vanish. Six 2026-09-03 research reports name this the public-launch blocker.

A second trust gap sits on the same path: the Citations API already returns `cited_text` and char offsets, but the adapter drops them. Marks are `[^n]` over whole chunks; hover does not show the quoted sentence, and "Show in book" flashes a section rather than the span.

## Goals

- [ ] A failed generation never deletes the conversation or the user's message; the thread shows the error and a retry control.
- [ ] Both Anthropic request shapes (citations-enabled documents vs structured-output JSON) are pinned by tests so mixing them fails CI.
- [ ] Claim-level citation spans survive the adapter: hover on `[^n]` shows the quoted sentence; "Show in book" highlights that span; offsets match the Citations document body byte-for-byte.

## Out of Scope

| Feature | Reason |
|---|---|
| Model/provider changes, Haiku routing, fallback adapters | Bet 7; needs its own RFC + ADR-0020 amendment |
| Sufficient-context autorater, retrieval `top_k`, embed headers | rq05; headers must stay out of Citations document bodies if they ever ship |
| Streaming protocol redesign | Error state + citation hover only |
| Teach playbook changes | Bet 3 |
| UI redesign beyond error-in-thread and citation hover/highlight | Handoff bound |
| Retry loops against Anthropic 5xx/529 | House rule: check status page, do not loop |
| `first_cited_answer` activation event | Bet 5; this cycle only makes that event *possible* |
| Calm "not in this book" abstention UX polish | Synthesis listed it; handoff keeps abstention as the existing sentinel path |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|
| Failed generation persistence | Persist a turn with `answer_status=failed`, empty answer text, no citations; HTTP still reports generation failure | Must-be-true requires the user's message to survive reload, not only the in-memory chat | auto (ship-cycle) |
| Retry | Retry posts a **new** turn with the same message on the same conversation | Failed turns stay as history; replacing in place would hide the failure from later diagnosis | auto |
| User abort / disconnect | Same as provider failure: keep the conversation, persist `failed` if a message was sent | Handoff: never lose the thread. An empty shell after Stop is how today's delete-on-failure was justified | auto |
| Citation spans this cycle | Ship them (do not split) | Adapter already receives `cited_text`; UI already has marks + "Show in book". Highest trust-UX per dollar (rq13 Cycle 1) | auto |
| One hover quote per `[^n]` | First `CitedSpan` for that chunk | AD-222 numbers by first-occurrence chunk, not per API citation. Multiple quotes on one chunk still share one mark | auto |
| 400 root cause | Pin both request shapes in CI; reproduce with a real request dump during Execute and fix the actual cause | rq13 hypothesis (shape mixing / thinking / effort) is unconfirmed until a dump exists | auto; **verify in-phase** |
| RFC-0007 | Land a Draft RFC distilled from the 2026-09-03 synthesis; this PR is Cycle A | ROADMAP has no next unstarted row; Bet 1 must not be an orphan cycle | auto |
| Provisional-delete | Remove it. A first-turn failure keeps the conversation in the dock | The delete lives in `useConversationThread.discardProvisional`, not the backend | auto |
| Span storage | Additive nullable `quoted_text` / `start_char` / `end_char` on `conversation_turn_citations` | One span per stored citation (the first for that chunk). No new table | auto |
| Logging | On provider 4xx, log request shape (`citations` vs `json_schema`), HTTP status, and `request_id`. Never prompt bodies beyond existing redaction | Handoff diagnostic bar; NFR-SEC-004 stands | auto |

**Open questions:** none — all resolved or logged above.

---

## User Stories

### P1: Never lose the thread ⭐ MVP

**User Story**: As a learner, I want my question and its conversation to stay after a failed answer, so I can retry instead of starting from a vanished dock row.

**Why P1**: Observed 2026-09-03: 400 → generic error → conversation deleted. Table-stakes vs ChatGPT/NotebookLM (rq01 §8 item 4). Blocks activation (rq07 Move 1).

**Acceptance Criteria**:

1. (ASK-01) WHEN generation fails after a conversation has been created THEN the system SHALL leave that conversation in place (no `DELETE`) and SHALL persist the user's message as a turn with `answer_status` equal to `failed`.
2. (ASK-02) WHEN a persisted failed turn is read (GET conversation or restored thread) THEN the system SHALL return the original user message, empty answer text, and no citations.
3. (ASK-03) WHEN generation fails THEN the thread SHALL show a readable error in the conversation (not only a transient banner) and SHALL offer a retry control that sends the same message as a new turn on the same conversation.
4. (ASK-04) IF the learner stops or the stream disconnects after a first message has been sent THEN the system SHALL NOT delete the conversation.
5. (ASK-05) WHEN a later turn on an already-kept conversation fails THEN the system SHALL leave prior turns unchanged and SHALL persist the new failed turn.
6. (ASK-06) IF a test reintroduces delete-on-failure for a first-turn stream error THEN that test SHALL fail.

**Independent Test**: create-then-stream, inject a 502/400, assert the conversation still GETs and contains the user message with `failed`; UI test that error+retry remain and `deleteConversation` is not called.

### P1: Diagnose and pin the Anthropic 400

**User Story**: As an operator, I want a failed live Ask to leave enough in the logs to see *which* request shape and `request_id` Anthropic rejected, and I want CI to catch mixing the two incompatible shapes.

**Why P1**: The 400 is the other half of the launch blocker. Shape mixing is a documented 400 (Citations ⊕ `output_config.format`). Thinking/effort remains a hypothesis until a real dump.

**Acceptance Criteria**:

7. (ASK-07) WHEN the answering adapter builds a request THEN it SHALL send citations-enabled `document` blocks and SHALL NOT send `output_config.format` (JSON schema / structured output).
8. (ASK-08) WHEN the quiz/judge structured-output adapter builds a request THEN it SHALL send `output_config.format` as JSON schema and SHALL NOT send citations-enabled documents.
9. (ASK-09) The system SHALL keep those two shapes in separate tests so a regression that mixes them fails CI on the deterministic path (no live key).
10. (ASK-10) WHEN the Anthropic answering adapter receives an HTTP 4xx THEN it SHALL log request shape, HTTP status, and `request_id`, and SHALL NOT log prompt bodies, document `data`, or the user message beyond existing redaction.
11. (ASK-11) WHEN Execute reproduces the live 400 THEN the fix SHALL be the cause shown by that dump (not a guessed parameter), and the PR body SHALL record the dump's status, `request_id` class, and the shape that was sent.

**Independent Test**: inspect captured `messages.create` / `messages.stream` kwargs in `test_answering_anthropic.py` and quiz adapter tests; a unit test that a 4xx log line contains status + request_id and omits document body.

### P1: Claim-level citation spans

**User Story**: As a learner, I want hovering a `[^n]` mark to show the sentence Claude cited, and "Show in book" to highlight that span, so I can check the claim without hunting the chapter.

**Why P1**: Table-stakes trust UX (rq01 §8 item 1). The API already returns the quote; dropping it is the gap (rq13 Cycle 1).

**Acceptance Criteria**:

12. (ASK-12) WHEN the Citations API returns `cited_text` with `char_location` offsets THEN the adapter SHALL map them to a Learny-owned `CitedSpan` (`chunk_id`, `quote`, `start`, `end`) and SHALL NOT expose `document_index` on the domain DTO or the HTTP wire.
13. (ASK-13) The system SHALL compute `start`/`end` against the exact snippet bytes sent as that document's `source.data`; a golden test SHALL fail if those offsets drift from the document body.
14. (ASK-14) WHEN a span's `chunk_id` is discarded by grounding THEN that span SHALL be discarded with it.
15. (ASK-15) WHEN the UI renders `[^n]` THEN hovering (or focusing) the mark SHALL show the quoted sentence for that citation.
16. (ASK-16) WHEN the learner activates "Show in book" for a citation that carries a span THEN the reader SHALL highlight that span inside the section, not only flash the section.
17. (ASK-17) WHERE a stored citation has no span (legacy rows, deterministic adapter) the system SHALL keep today's snippet passage and section-level "Show in book" behavior.

**Independent Test**: adapter unit test with a fixture document body and known offsets; frontend test that the hover card text equals `quoted_text` and that the reader paint uses that quote.

---

## Edge Cases

- IF the 4xx has no `request_id` THEN the log SHALL still include status and request shape, with `request_id` absent or null — it SHALL NOT omit the line.
- IF an API citation's offsets fall outside the document body THEN the adapter SHALL drop that span and still keep the chunk id for grounding.
- IF retry is clicked while a turn is already streaming THEN the system SHALL ignore the second submit (existing `isStreaming` guard).
- IF the deterministic adapter is selected THEN it SHALL return no spans (ASK-17) and the thread-survival ACs SHALL still hold.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
|---|---|---|---|
| ASK-01 | P1: Never lose the thread | T7, T9 | In Tasks |
| ASK-02 | P1: Never lose the thread | T2, T7, T11 | In Tasks |
| ASK-03 | P1: Never lose the thread | T10 | In Tasks |
| ASK-04 | P1: Never lose the thread | T9 | In Tasks |
| ASK-05 | P1: Never lose the thread | T7 | In Tasks |
| ASK-06 | P1: Never lose the thread | T9 | In Tasks |
| ASK-07 | P1: Pin the 400 | T4 | Done |
| ASK-08 | P1: Pin the 400 | T5 | Done |
| ASK-09 | P1: Pin the 400 | T4, T5 | Done |
| ASK-10 | P1: Pin the 400 | T6 | In Tasks |
| ASK-11 | P1: Pin the 400 | T1 (arc) + Execute dump | In Tasks |
| ASK-12 | P1: Citation spans | T2, T3, T8 | In Tasks |
| ASK-13 | P1: Citation spans | T3 | Done |
| ASK-14 | P1: Citation spans | T3 | Done |
| ASK-15 | P1: Citation spans | T12 | In Tasks |
| ASK-16 | P1: Citation spans | T13 | In Tasks |
| ASK-17 | P1: Citation spans | T8, T12, T13 | In Tasks |

**Coverage:** 17 total, 17 mapped to tasks, 0 unmapped

---

## Success Criteria

- [ ] First-turn generation failure leaves a GET-able conversation whose latest turn is the user's question with `failed`.
- [ ] A test fails if `discardProvisional` / `deleteConversation` runs on stream error.
- [ ] A test fails if Citations document offsets and `CitedSpan` offsets disagree.
- [ ] `make check` green; one manual real-provider Ask on the compose stack documented in the PR body.
