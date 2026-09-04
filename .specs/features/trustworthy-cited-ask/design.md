# trustworthy-cited-ask Design

**Spec**: `.specs/features/trustworthy-cited-ask/spec.md`
**Context**: `.specs/features/trustworthy-cited-ask/context.md`
**Status:** Approved (ship-cycle auto)

---

## Architecture Overview

Three seams, one PR:

1. **Survival** — application persist-on-failure + frontend stops deleting the conversation.
2. **Shape** — answering vs quiz/judge request builders stay mutually exclusive; 4xx logs identify which shape was sent.
3. **Spans** — adapter maps Citations `cited_text` / `char_location` into a Learny `CitedSpan`; grounding filters by `chunk_id`; wire and UI carry optional quote offsets.

Provider types stay in `infrastructure/answering/anthropic.py`. Domain sees `CitedSpan`, never `document_index`.

```
Ask send
  → POST /conversations (empty shell)
  → POST .../turns/stream
       → retrieve → GenerationPort.generate_stream
            → Anthropic: citations documents + thinking/effort
            → 4xx: log shape+status+request_id → AnswerGenerationFailed
       → on failure: persist turn (failed, user message, no citations)
       → SSE error part
  → UI: keep conversation, show error + Retry in thread
  → Retry: POST .../turns/stream again (new turn_index)
```

---

## Approaches (same scope)

| | A. UI-only keep | B. Persist `failed` + stop DELETE (chosen) | C. Two-phase persist (user row first) |
|---|---|---|---|
| Reload keeps the question | No | Yes | Yes |
| Schema | Untouched | New status string + optional span columns | Split user/assistant rows (breaks "one row = message+response") |
| Matches AD-033 turn shape | Yes | Yes | No |
| **Why-recommend B:** durable message without exploding the turn model. **Why-not A:** handoff says the message stays; A loses it on refresh. **Why-not C:** a new aggregate for one status. |

---

## Code reuse

| Existing | Role |
|---|---|
| `PostConversationTurn._persist` | Same writer; call it on the failure path with `failed` |
| `_CitationMarks` / `_parse_message` | Extend to collect spans while resolving `document_index` → `chunk_id` |
| `_build_documents` | Document `data` is the offset origin (ASK-13) |
| `ground()` | Drop spans whose `chunk_id` is not in the surviving set |
| `useConversationThread` | Delete the provisional DELETE; keep `onError` banner *and* a failed assistant placeholder + retry |
| `CitationMark` | Add hover/focus quote; click still toggles the passage region |
| `findQuoteOffset` + highlight paint | Needle = span quote (or snippet if no span) |
| Quiz `output_config.format` tests | The other shape half of ASK-08/09 |
| `errorMessageFor` / stream error part | Unchanged copy |

---

## Components

### 1. `CitedSpan` (domain)

**Where:** `backend/app/domain/entities.py`

```
CitedSpan(chunk_id: UUID, quote: str, start: int, end: int)
GeneratedAnswer(..., spans: tuple[CitedSpan, ...] = ())
```

`document_index` never appears. Deterministic adapter omits spans.

### 2. Anthropic parser + request + 4xx log

**Where:** `backend/app/infrastructure/answering/anthropic.py`

- `_CitationMarks` (or sibling walk): for each citation object, resolve index → `chunk_id`; if `cited_text` and `start_char_index` / `end_char_index` (or `char_location`) are present and in range of `source.data`, append a `CitedSpan`. Out-of-range → drop span, keep chunk id.
- `_build_request`: assert-by-test that kwargs have documents with `citations.enabled` and **no** `output_config.format`. `output_config` remains `{effort}` only.
- Catch SDK 4xx on create/stream: log `request_shape=citations`, status, `request_id`; re-raise into existing `AnswerGenerationFailed`.

Quiz adapter (`infrastructure/quiz/anthropic.py`) is not rewritten; tests pin it has no citation documents.

### 3. Persist-on-failure

**Where:** `backend/app/application/conversations.py`

Today: port exception → `AnswerGenerationFailed`, nothing persisted (`:479-549`, stream `:551-612`).

Change: on `AnswerGenerationFailed` after a message is known, `_persist` a turn with `answer_status=FAILED`, `answer_text=""`, `citations=()`, `model` = configured model or `"unknown"` if the adapter never returned. Then raise / emit the error part so the HTTP contract stays a failure.

`FAILED = "failed"` added beside `ANSWERED` / not-found constants. No DB CHECK exists (text column).

Sync POST and stream share this. Grounding not-found stays `not_found_in_*` (success persist). Only provider/transport failure is `failed`.

### 4. Citation snapshot columns

**Where:** migration `0018_citation_spans`, `metadata.py` `conversation_turn_citations`

Nullable `quoted_text` (Text), `start_char` (Integer), `end_char` (Integer). Serializer emits them only when set (book citations stay small; ASK-17).

Frontend `Citation` type: optional `quoted_text`, `start_char`, `end_char`.

### 5. Thread survival UI

**Where:** `frontend/app/components/use-conversation-thread.ts`

- `discardProvisional` must not call `deleteConversation`. Prefer deleting the function's destructive half entirely; keep the ref-clear that says "no longer provisional".
- `onConversationKept` (or started) fires so the dock lists the row after create, including on error.
- Retry: a control in the failed turn that calls `send(originalUserText)` — not a page reload.

Error-in-thread: a failed assistant message (status text from `errorMessageFor`) plus Retry. Banner may remain; ASK-03 requires the in-thread state.

### 6. Hover + exact-span highlight

**Where:** `cited-answer.tsx` (`CitationMark`), `citations.tsx` / chapter-reader show-in-book

Hover/focus on the mark shows `quoted_text` when present. "Show in book" passes the quote into `findQuoteOffset`; fallback is current section flash when no span.

Do not import unused `frontend/components/ai-elements/inline-citation.tsx` unless it maps cleanly onto book passages (it models web sources). Default: a small shadcn HoverCard on the existing button.

### 7. RFC + ROADMAP

**Where:** `docs/rfc/0007-public-launch-roadmap.md`, `.specs/project/ROADMAP.md`

Draft RFC: seven bets as cycles, Bet 1 = this slug, sequencing from synthesis. ROADMAP gains a v7 table with Cycle A in progress.

---

## Data Models

```
answer_status ∈ { answered, not_found_in_source, not_found_in_scope, failed }

CitedSpan { chunk_id, quote, start, end }  # offsets into document body == Evidence.snippet

conversation_turn_citations += quoted_text?, start_char?, end_char?
```

Wire `EvidenceView` / citation JSON: additive optional fields. Clients ignoring them stay valid.

---

## Request-shape contract (ASK-07..09)

| Path | Documents with citations.enabled | `output_config.format` | `thinking` / `effort` |
|---|---|---|---|
| `AnthropicGenerationAdapter._build_request` | yes, one per evidence chunk | **absent** | present (existing) |
| Quiz batch / suggest_* / judge | no | json_schema | absent (existing) |

A test that builds both request dicts and asserts the forbidden key is missing on each is the sensor.

---

## Risks & Concerns

| Concern | Mitigation |
|---|---|
| Live 400 is not shape mixing | ASK-11: dump first; shape tests still ship (they are the documented 400 class) |
| `thinking.display=summarized` or `effort` rejected with citations | Dump will show it; fix is adapter kwargs, pinned by the answering shape test |
| Failed-turn `model` empty | Use settings `generation_model` when the adapter did not return |
| Dock lists a conversation titled from a failed first message | Existing title-from-first-message path; if title is only set on success, set it from the user message on failed persist |
| Offset encoding (Python str vs UTF-16 vs bytes) | Anthropic `char_location` is Unicode code points on the submitted text. Treat `start`/`end` as Python `str` indices on the same `snippet` sent as `data`. Golden uses ASCII to make bytes≡codepoints; add one non-ASCII fixture so a bytes-index bug dies |
| Highlight in a different chapter than the open one | Existing `handleShowInBook` already navigates by anchor; paint after load using the quote |
| AD-034 consumers assuming 502 means zero rows | Grep tests for "persists nothing" / 502 and update those that encode the old contract |
| Skill-refresh dirty tree | Not part of this design; opening commits are research + RFC, not `.cursor/` |

---

## Binding decisions this design must not relitigate

- ADR-0020: Claude behind `GenerationPort`; `document_index` adapter-only; citations ⊕ structured outputs never combined.
- ADR-0003 / AD-027: grounding in the application service.
- AD-222: `[^n]` first-occurrence walk, stream text ≡ persisted text.
- ADR-0029: one conversation, per-turn mode.
- NFR-SEC-004: no secret/prompt leak in logs.
