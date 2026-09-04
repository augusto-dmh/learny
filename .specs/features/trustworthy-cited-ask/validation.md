# trustworthy-cited-ask Validation

**Date**: 2026-09-04
**Spec**: `.specs/features/trustworthy-cited-ask/spec.md`
**Diff range**: `4529a9bd..b674cec8` (merge-base with main; plan `351c519b`; implementation after that)
**Verifier**: independent sub-agent (author ≠ verifier)
**Result**: PASS

## Validation: trustworthy-cited-ask - PASS

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| T1 | Done | RFC-0007 Draft at `docs/rfc/0007-public-launch-roadmap.md` |
| T2 | Done | `CitedSpan`, `FAILED`, default `spans=()` |
| T3 | Done | Span mapping, offset golden, out-of-range drop, grounding |
| T4 | Done | Answering request: citations documents, no `output_config.format` |
| T5 | Done | Quiz/judge: JSON schema, no citations documents |
| T6 | Done | 4xx log: shape, status, `request_id`; bodies redacted |
| T7 | Done | Persist `failed` on sync and stream generation failure |
| T8 | Done | Migration 0018; nullable span columns; omit null keys |
| T9 | Done | No `deleteConversation` on error/abort/disconnect |
| T10 | Done | In-thread error + Retry as a new turn |
| T11 | Done | Restore `answer_status=failed` into the thread |
| T12 | Done | Hover/focus shows `quoted_text` |
| T13 | Done | Show in book paints the cited sentence |

All thirteen tasks are marked done in `tasks.md`. No blocked or partial tasks.

---

## Spec-Anchored Acceptance Criteria

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| ASK-01 WHEN generation fails after a conversation has been created THEN leave it in place (no DELETE) and persist the user message as `answer_status=failed` | Conversation still GET-able; one turn with `FAILED`, original message, empty answer, no citations; HTTP 502 still raised | `backend/tests/test_application_conversations.py:1983` `len(persisted) == 1`; `:1985` `turn.answer_status == FAILED`; `:1986` `turn.message == _PRIVATE_MESSAGE`; `:1987` `turn.answer_text == ""`; `:1988` `turn.citations == ()`; stream twin `:2426`–`:2432`; HTTP `:1579` `status_code == 502` and `:1585`–`:1590` GET returns that turn | PASS |
| ASK-02 WHEN a persisted failed turn is read THEN return original user message, empty answer text, and no citations | GET / restore shows the question, `text=""`, `citations=[]` | HTTP GET `:1587`–`:1590`; stream GET `:1972`–`:1975`; UI restore `frontend/tests/ask-panel.test.tsx:774` user text and `:776` error; mapper `frontend/tests/streaming.test.ts:304`–`:311` empty text, no citations, `status === "failed"` | PASS |
| ASK-03 WHEN generation fails THEN the thread shows a readable error (not only a banner) and Retry sends the same message as a new turn on the same conversation | In-thread error copy + Retry; second stream POST same `message`; no second create | `frontend/tests/ask-panel.test.tsx:541` Retry role; `:542` failed-turn contains "Answer generation failed"; `:559` create count stays 1; `:552`–`:557` both stream bodies `message: "the same question"`; Teach twin `frontend/tests/teach-panel.test.tsx:543`–`:559` | PASS |
| ASK-04 IF the learner stops or the stream disconnects after a first message has been sent THEN SHALL NOT delete the conversation | `deleteConversation` not called; active conversation id kept | `frontend/tests/ask-panel.test.tsx:516`–`:518` stop path; first-turn stream error `:466`–`:468`; pre-stream 502 `:486`–`:488` | PASS |
| ASK-05 WHEN a later turn fails THEN prior turns unchanged and the new failed turn is persisted | Prior turn identity preserved; new row `FAILED` at next index | `backend/tests/test_application_conversations.py:2022` `[0, 1]`; `:2023` `persisted[0] == answered`; `:2024` `answer_status == FAILED`; `:2025` `message == "second"`; dock `frontend/tests/conversation-orphans.test.tsx:339`–`:341` | PASS |
| ASK-06 IF a test reintroduces delete-on-failure for a first-turn stream error THEN that test SHALL fail | `deleteConversation` spy must not have been called | `frontend/tests/ask-panel.test.tsx:466` `expect(deleteConversationSpy).not.toHaveBeenCalled()`; sensor restored the call and this assertion failed | PASS |
| ASK-07 WHEN the answering adapter builds a request THEN citations-enabled documents and SHALL NOT send `output_config.format` | Documents `citations.enabled == True`; `output_config == {effort}` with no `format`; buffered and stream | `backend/tests/test_answering_anthropic.py:219`–`:224` buffered; `:242`–`:246` stream; both modes parametrized; also `:177` `citations == {"enabled": True}` | PASS |
| ASK-08 WHEN the quiz/judge structured-output adapter builds a request THEN `output_config.format` JSON schema and SHALL NOT send citations-enabled documents | `format.type == json_schema`; no `document` blocks; judge messages are plain strings | Quiz `backend/tests/test_quiz_anthropic.py:493`–`:494`, `:504`–`:505`, `:514`–`:515`; judge `backend/tests/test_eval_judge.py:100`–`:102` `json_schema` and `isinstance(message["content"], str)` | PASS |
| ASK-09 The two shapes live in separate tests so mixing fails CI on the deterministic path | Answering tests reject `format`; quiz/judge tests require schema and reject documents | Pair T4 `:223` `assert "format" not in call["output_config"]` with T5 `:494` `_document_blocks(...) == []`. Sensor 4 mixed format onto the answering request; T4 failed | PASS |
| ASK-10 WHEN answering adapter receives HTTP 4xx THEN log shape, status, and `request_id`; SHALL NOT log prompt bodies, document `data`, or the user message | One line with `request_shape=citations`, `status=400`, `request_id=...`; secret snippet/question/prompt absent | `backend/tests/test_answering_anthropic.py:436`–`:438`; redaction `:446`–`:448`; missing id still logs `:454`–`:456` | PASS |
| ASK-11 Process AC: shape sensors exist (Verifier does not require a paid live dump) | Mixing citations ⊕ JSON schema fails CI without a live key | Shape sensors: ASK-07/ASK-08/ASK-09 tests above. Live Anthropic smokes skipped when `LEARNY_ANTHROPIC_API_KEY` unset (`test_answering_anthropic.py:1882` skip). RFC-0007 Draft exists (`docs/rfc/0007-public-launch-roadmap.md:1`) | PASS |
| ASK-12 WHEN Citations API returns `cited_text` with `char_location` THEN map to `CitedSpan(chunk_id, quote, start, end)` and SHALL NOT expose `document_index` on domain DTO or HTTP | Span fields only; `document_index` absent from `CitedSpan`/`GeneratedAnswer`/`EvidenceView`/`Citation` | Mapping `backend/tests/test_answering_anthropic.py:659`–`:662`; domain `backend/tests/test_domain_conversations.py:96`–`:97` `"document_index" not in` fields; HTTP schema `backend/app/infrastructure/web/retrieval.py:90`–`:102` (no `document_index`); frontend `frontend/app/lib/citations.ts:21`–`:39`; unquoted wire keys `backend/tests/test_web_conversations.py:2510` `set(unquoted) == _CITATION_KEYS` | PASS |
| ASK-13 start/end against the exact snippet sent as document `source.data`; golden fails if offsets drift | `_sent_document_body(client)[span.start:span.end] == quote` | `backend/tests/test_answering_anthropic.py:662`; character-not-byte pin `:678`–`:680`. Sensor 2 shifted `start` by 1; golden failed (`olcanoes vent magma.` ≠ quote) | PASS |
| ASK-14 WHEN a span's `chunk_id` is discarded by grounding THEN that span SHALL be discarded with it | Grounded spans keep only surviving chunks | Adapter `backend/tests/test_answering_anthropic.py:758` `ground_spans(...) == ["Volcanoes vent magma."]`; application ghost chunk `backend/tests/test_application_conversations.py:1904` `turn.citations == (evidence,)` (no ghost quote) | PASS |
| ASK-15 WHEN the UI renders `[^n]` THEN hovering or focusing the mark SHALL show the quoted sentence | Tooltip text equals `quoted_text` | `frontend/tests/cited-answer.test.tsx:301` `findByRole("tooltip").textContent).toBe(quoted)` after focus; `:307` after pointer move | PASS |
| ASK-16 WHEN Show in book for a citation that carries a span THEN the reader highlights that span, not only the section | Callback gets `(anchor, quoted_text)`; reader paints `mark.reader-highlight` with that quote | `frontend/tests/citations.test.tsx:215` `toHaveBeenCalledWith(citation.anchor, quoted)`; paint `frontend/tests/chapter-reader.test.tsx:1041`–`:1043` one mark, `textContent === "the analytical engine"`; reader `frontend/app/components/chapter-reader.tsx:680`–`:692` | PASS |
| ASK-17 WHERE a stored citation has no span, keep snippet passage and section-level Show in book | No empty hover; Show in book one-arg; no span paint; deterministic adapter `spans=()` | Hover `frontend/tests/cited-answer.test.tsx:323` tooltip null and `:326` passage opens; Show in book `frontend/tests/citations.test.tsx:233`–`:234` length 1; reader `frontend/tests/chapter-reader.test.tsx:1024`–`:1025` zero `mark.reader-highlight`; local adapter `backend/tests/test_answering_local.py:103` `answered == frozen` (frozen constructed without spans); domain default `backend/tests/test_domain_conversations.py:108` `plain.spans == ()` | PASS |

**Status**: All 17 ACs covered. ASK-11 checked as a process AC (shape sensors), not a live provider dump.

---

## Discrimination Sensor

Isolated scratch: `git worktree add /tmp/learny-verify-trustworthy-cited-ask HEAD` at `b674cec8`. Real-tree porcelain captured first (`/tmp/learny-verify-porcelain-baseline.txt`, 22 lines). After `git worktree remove --force`, porcelain matched that baseline. No `git stash`.

| Mutation | File:line | Description | Killed? |
| -------- | --------- | ----------- | ------- |
| 1 | `frontend/app/components/use-conversation-thread.ts` `onError` | Restored `deleteConversation(id, csrf)` on stream error (ASK-06) | Killed — `frontend/tests/ask-panel.test.tsx:466` `deleteConversationSpy` called once with `("conv1", "csrf-xyz")` |
| 2 | `backend/app/infrastructure/answering/anthropic.py` `_collect_span` append | Shifted `CitedSpan.start` by +1 after the body/quote check (ASK-13) | Killed — golden `:662` and `:678` (`olcanoes vent magma.` ≠ quote) |
| 3 | `backend/app/application/conversations.py` `_persist_failed` | Skipped `_persist` on `AnswerGenerationFailed` (ASK-01) | Killed — `:1983` `assert 0 == 1`; stream `:2426`; HTTP GET `:1586` |
| 4 | `backend/app/infrastructure/answering/anthropic.py` `messages.create` / `messages.stream` | Put `output_config.format` JSON schema on the answering request (ASK-07) | Killed — `:223` and `:245` `output_config == {effort}` (answer + teach, buffered + stream) |

**Sensor depth**: P0-full (4 mandatory behavior-level faults; all highest-risk paths from tasks.md)
**Result**: 4/4 killed - PASS

---

## Interactive UAT Results

Not performed. This Verifier pass is automated spec-anchored evidence plus the discrimination sensor. Ask/Teach error+retry and citation hover/highlight are covered by jsdom tests cited above.

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code | Pass |
| Surgical changes | Pass — span columns additive; failed persist is an append; request-shape pins are tests around existing adapters |
| No scope creep | Pass — RFC-0007 is T1; no Haiku routing, no autorater |
| Matches patterns | Pass — `EvidenceView` wrap-serializer for optional span keys; shared `useConversationThread` for Ask and Teach |
| Spec-anchored outcome check (asserted values match spec) | Pass |
| Per-layer Coverage Expectation met (domain 1:1 ACs; routes happy+edge+error) | Pass for this cycle's surfaces |
| Every new test maps to a spec requirement — no unclaimed cycle tests | Pass — new assertions cite ASK ids or the independent tests in the spec |
| Documented guidelines followed | `CLAUDE.md` verification vocabulary; `tasks.md` Build gate; architecture boundaries clean |

Noted, not a fail: intermediate UI props still type `onShowInBook?: (anchor: string) => void` while `CitationList` calls `(anchor, quoted_text)`. The live callback is `handleShowInBook(anchor, quote?)`; the extra argument still arrives at runtime. ASK-16 is pinned at both ends.

Documented `SPEC_DEVIATION` at `backend/app/application/conversations.py:656`: user abort still persists nothing (`test_stream_cancelled_before_completion_persists_nothing`). ASK-04 requires the conversation not be deleted, which the client tests pin. Persist-on-abort is an assumption in the spec table, not ASK-04. The marker does not fail an AC.

---

## Edge Cases

- [x] 4xx with no `request_id`: log still emitted with status and shape (`backend/tests/test_answering_anthropic.py:451`–`:456`)
- [x] Offsets outside the document body: span dropped, chunk kept (`backend/tests/test_answering_anthropic.py:695`–`:697`)
- [x] Retry while a turn is already streaming: Retry disabled (`frontend/tests/ask-panel.test.tsx:591`–`:595`; Teach `:563`)
- [x] Deterministic adapter returns no spans and thread-survival still holds (`backend/tests/test_domain_conversations.py:108`; `backend/tests/test_answering_local.py:103`; failure persist tests use `FakeGeneration`, not Anthropic)

---

## Gate Check

- **Gate command**: `make lint` plus cycle suites from `tasks.md` (backend modules in the coverage matrix; frontend `ask-panel`, `citations`, `cited-answer`, `chapter-reader`, `streaming`, `teach-panel`, `conversation-orphans`, `highlight-paint`). Prefix `LEARNY_GENERATION_PROVIDER=local LEARNY_EMBEDDING_PROVIDER=local`. `LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test`.
- **Lint**: Pass — ruff check/format, `tsc --noEmit`, `check_boundaries.py`
- **Cycle backend**: 357 passed, 4 skipped, 0 failed
- **Cycle frontend**: 181 passed, 0 failed (8 files)
- **Test count before feature** (touched test files at `4529a9bd`): 436 (`def test_` + `it(`)
- **Test count after feature** (same files at `HEAD`): 481
- **Delta**: +45 tests in the feature's test files
- **Skipped tests**:
  - `test_answering_anthropic.py` three `@pytest.mark.live` smokes — `LEARNY_ANTHROPIC_API_KEY` unset; CI stays offline
  - `test_eval_judge.py` live judge tier — same
- **Failures**: none in this cycle's suites
- **Known pre-existing flake** (not this cycle): `tests/eval/test_eval_retrieval_metrics.py::TestDeterministicRetrievalMetrics::test_metrics_meet_thresholds` (recall@1). Re-run on this pass: **passed**. Not used as a feature fail.

Full `make test-backend` / `make test-frontend` were not re-run beyond the cycle suites + lint. Cycle suites are the Build gate named in `tasks.md`.

---

## Fix Plans

None. No surviving mutant, no uncovered AC, no gate failure.

---

## Requirement Traceability Update

Recorded here only (spec.md not edited by this Verifier):

| Requirement | Previous Status | New Status |
| ----------- | --------------- | ---------- |
| ASK-01 | Done | Verified |
| ASK-02 | Done | Verified |
| ASK-03 | Done | Verified |
| ASK-04 | Done | Verified |
| ASK-05 | Done | Verified |
| ASK-06 | Done | Verified |
| ASK-07 | Done | Verified |
| ASK-08 | Done | Verified |
| ASK-09 | Done | Verified |
| ASK-10 | Done | Verified |
| ASK-11 | In Tasks | Verified (shape sensors + live dump: HTTP 400, `req_` id, citations shape with no `output_config.format`, provider `invalid_request_error` / credit balance — not a mixed request) |
| ASK-12 | Done | Verified |
| ASK-13 | Done | Verified |
| ASK-14 | Done | Verified |
| ASK-15 | Done | Verified |
| ASK-16 | Done | Verified |
| ASK-17 | Done | Verified |

---

## Summary

**Overall**: Ready
**Spec-anchored check**: 17/17 ACs matched spec outcome; 0 spec-precision gaps
**Sensor**: 4/4 mutations killed
**Gate**: lint pass; 357 backend + 181 frontend passed; 4 live skips

**What works**: Failed generation keeps the conversation and the question as a `failed` turn with Retry. Answering vs quiz/judge request shapes are pinned apart. Citation spans map from provider offsets onto `source.data`, stay off the HTTP `document_index` field, drive hover text, and paint in the reader. Legacy/local citations keep passage-level Show in book.

**Issues found**: Documented `SPEC_DEVIATION` at `backend/app/application/conversations.py:656` (abort still persists nothing). Out of ASK-04's SHALL-NOT-delete scope.

**Live dump (ASK-11)**: Execute reproduced Anthropic `POST /v1/messages` HTTP 400 with `request_id` class `req_` (length 28). Sent shape: citations-enabled plain-text documents, `thinking` adaptive/summarized, `output_config.effort` only (no `format`). Provider body: `invalid_request_error` — credit balance too low. Mixing citations with structured output was **not** the live cause. The 4xx log now also records `error_type` so a billing 400 is distinguishable from a mixed-shape 400 without logging the error message (which echoes the request).

**Next steps**: Feature is ready to publish. The abort-persist deviation is recorded in this report; it was not written to the shared lessons store because adding a candidate today would drop every lesson older than the 45-day window.
