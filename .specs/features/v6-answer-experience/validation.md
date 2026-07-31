# v6-answer-experience Validation

**Date**: 2026-07-30
**Spec**: `.specs/features/v6-answer-experience/spec.md`
**Diff range**: `8277af54..HEAD` (12 implementation commits on `feat/answer-experience`)
**Verifier**: independent sub-agent (author ≠ verifier, fresh context)

---

## Task Completion

All 12 tasks (T1–T12) have a matching implementation commit in the diff range; per-task commit messages match tasks.md exactly. No blocked or partial tasks.

---

## Spec-Anchored Acceptance Criteria

### P1: Visible answer phases (ANSW-01/02/03)

| Criterion | Spec-defined outcome | Evidence | Result |
|---|---|---|---|
| AC1 searching event before retrieval | phase frame emitted before retrieval executes; panel shows "Searching the book…" | `backend/tests/test_application_conversations.py:2137` — `assert first == StreamPhase(phase="searching")` then `:2139` `assert retrieve.calls == []`; wire: `backend/tests/test_web_conversations.py:1641-1653` frame order + `phase["data"] == {"phase": "searching"}`; UI: `frontend/tests/ask-panel.test.tsx:858-865` phase line from submit until next event | ✅ PASS |
| AC2 thinking → reasoning parts, collapsible, live, collapses when text begins | `reasoning-start/delta/end` on wire; region open while streaming, folds on first answer token | `backend/tests/test_web_conversations.py:1771-1791` — exact 13-frame order incl. `reasoning-delta` payloads and distinct part ids; `frontend/tests/ask-panel.test.tsx:882-898` — region open + text visible while thinking, `queryByText(...)` null after text starts; teach parity: `frontend/tests/teach-panel.test.tsx:493-532` | ✅ PASS |
| AC3 answer streams as today; reasoning stays available (collapsed) for the completed turn | reopenable after finish | `frontend/tests/ask-panel.test.tsx:911-917` — "Thought process" toggle reopens the reasoning text after `finish` | ✅ PASS |
| AC4 no thinking → no reasoning region | no empty shell | `frontend/tests/ask-panel.test.tsx:921-937` — `reasoningRegion()` null; `frontend/tests/teach-panel.test.tsx:534-547`; local adapter emits none: `backend/tests/test_answering_local.py:127` | ✅ PASS |
| AC5 no evidence → searching → not-found, no reasoning/text phases | phase then existing not-found, no reasoning frames | `backend/tests/test_web_conversations.py:1694-1711` — frame list without reasoning, `assert "reasoning-start" not in _part_types(parts)`, status `not_found_in_scope`; `backend/tests/test_application_conversations.py:2086` | ✅ PASS |
| AC6 stream error → existing error part; panel error state replaces phase | error part + generic message; phase line gone | `backend/tests/test_web_conversations.py:1854-1858` — `types[-2:] == ["error","[DONE]"]`, generic `errorText`, no leak; `frontend/tests/ask-panel.test.tsx:975-1003` — alert shown, `phaseLine()` null | ✅ PASS |
| AC7 guards eager: HTTP status before any stream bytes | 404/422/409 pre-stream | `backend/tests/test_web_conversations.py:1882-1887` — statuses asserted and `"start" not in resp.text`; `:1890` identical 404s, `:1916` 403 CSRF, `:1925` 401; `backend/tests/test_application_conversations.py:2444` guards raise before first event | ✅ PASS |
| AC8 restored conversation renders as today, no reasoning | text+citations only; no reasoning/phase parts | `frontend/tests/streaming.test.ts:280-288` — part types exactly `["text","data-citations","data-answer-status"]`, `view.reasoning === ""`, `view.phase === null`; `frontend/tests/ask-panel.test.tsx:1006-1039` | ✅ PASS |

### P1: Deliberate generation config (ANSW-04/05/06)

| Criterion | Spec-defined outcome | Evidence | Result |
|---|---|---|---|
| AC1 both calls, both modes carry thinking + output_config + max_tokens | `thinking={"type":"adaptive","display":"summarized"}`, `output_config={"effort":…}` | `backend/tests/test_answering_anthropic.py:202-206` (buffered, parametrized both modes) and `:225-228` (stream) — `call["thinking"] == _SUMMARIZED_THINKING`, `call["output_config"] == {"effort": _EFFORT}`, `call["max_tokens"] == _MAX_TOKENS` | ✅ PASS |
| AC2 effort default `medium`; invalid value rejected at startup | field default + ValidationError | `backend/tests/test_config.py:76` — `settings.generation_effort == "medium"`; `:104-108` all five levels accepted; `:111-117` — `pytest.raises(ValidationError)` on `"maximum"` | ✅ PASS |
| AC3 max_tokens default 4096 | field default | `backend/tests/test_config.py:77` — `settings.generation_max_tokens == 4096` | ✅ PASS |
| AC4 log includes effort | `effort=` on the generation log line | `backend/tests/test_answering_anthropic.py:255-257` (buffered) and `:267-269` (stream) — `f"effort={_EFFORT}" in lines[0]` | ✅ PASS |
| AC5 local provider unchanged, no thinking/effort anywhere | network-free contract; no reasoning events | `backend/tests/test_answering_local.py:127` — streamed output carries no reasoning; `:275` no provider SDK import; factory threads effort only to Anthropic: `backend/tests/test_answering_factory.py:32` | ✅ PASS |

### P1: Citations in flow (ANSW-07/08)

| Criterion | Spec-defined outcome | Evidence | Result |
|---|---|---|---|
| AC1 markers → inline numbered marks at their positions | mark inside the sentence; token not rendered as text | `frontend/tests/cited-answer.test.tsx:67-72` — mark's `closest("p")` contains surrounding prose, `not.toContain("[^1]")`; backend insertion: `backend/tests/test_answering_anthropic.py:436` (mark n names citation n), `:1188-1194` (streamed positions) | ✅ PASS |
| AC2 activation opens passage in flow beneath answer, clamped, snippet + breadcrumb | in-tree region (no overlay), `max-h-` + `overflow-y-auto` | `frontend/tests/cited-answer.test.tsx:77-89` — `container.contains(passage)`, breadcrumb "Chapter 1 › Core Idea", clamp classes asserted | ✅ PASS |
| AC3 "Show in book" jumps via `onShowInBook`, dock stays open | callback invoked with the raw anchor | `frontend/tests/cited-answer.test.tsx:92-94` — `toHaveBeenCalledWith(first.anchor)`; end-to-end in dock: `frontend/tests/ask-panel.test.tsx:735-788` | ✅ PASS |
| AC4 citations without markers still reachable | chip row as fallback inventory | `frontend/tests/cited-answer.test.tsx:155-170` — no marks, chip opens passage | ✅ PASS |
| AC5 note-origin keeps "Open note" | link to `/notes/{id}`, no book action | `frontend/tests/cited-answer.test.tsx:173-189` — `href === "/notes/note-123"`, no "Show in book" | ✅ PASS |
| AC6 persisted turn: marks + passages identical | restored markers render as marks | `frontend/tests/ask-panel.test.tsx:789-838`; `frontend/tests/streaming.test.ts:268-288` — stored `[^1]` survives replay | ✅ PASS |
| Stream/buffered text parity (design invariant) | streamed concatenation == persisted text | `backend/tests/test_answering_anthropic.py:1289-1292` — `streamed == buffered.text` across 5 message shapes incl. repeated/malformed citations; `:1134-1152` same parser both paths | ✅ PASS |

### P2: Navigation pending (ANSW-09/10)

| Criterion | Spec-defined outcome | Evidence | Result |
|---|---|---|---|
| AC1 link pending via `useLinkStatus` | indicator while pending, nothing otherwise | `frontend/tests/nav-pending.test.tsx:84-98` — empty render when idle, `nav-pending` testid when pending; `:100` real Next hook shape | ✅ PASS |
| AC2 programmatic pending via `useTransition` | `isPending` true in flight, false after | `frontend/tests/nav-pending.test.tsx:155-180` | ✅ PASS |
| AC3 no flash on instant navigation | animation-delayed appearance | `frontend/tests/nav-pending.test.tsx:58-69` — `animationDelay === "150ms"`, `fade-in-0` + `fill-mode-backwards` (mounts invisible); instant resolution leaves nothing: `:169`, `frontend/tests/toc-panel.test.tsx:196-205` | ✅ PASS |
| AC4 applied to Home cards, library entries, sidebar, TOC | each surface shows the indicator | `frontend/tests/home-screen.test.tsx:229-263` (Resume/Review/Pick a book); `frontend/tests/library-screen.test.tsx:148-180`; `frontend/tests/app-sidebar.test.tsx:91-105`; `frontend/tests/toc-panel.test.tsx:182-193` (clicked entry only) | ✅ PASS |

**Status**: ✅ All 23 AC rows covered with located assertions. 0 spec-precision gaps.

---

## Edge Cases

- [x] Thinking deltas interleaved with sentinel hold-back — `backend/tests/test_application_conversations.py:2145-2176`: reasoning yielded while text held; buffered text still released as one whole flush.
- [x] SSE consumer disconnect closes the provider stream — `backend/tests/test_answering_anthropic.py:1317-1332` (`gen.close()` → `stream.closed is True`); `backend/tests/test_application_conversations.py:2061-2084` (`generation.stream_closed is True`, nothing persisted). Note: both tests close after a text delta; the `with`-block close path does not branch on event type, so mid-thinking disconnect exercises the same code.
- [x] Sentinel-only turn shows no reasoning-then-retraction artifact — backend: `test_application_conversations.py:2179-2211` (verdict last, nothing after it); UI: `frontend/tests/ask-panel.test.tsx:939-973` (reasoning region and its text gone beside the not-found notice).
- [x] Citations after `text-end` hydrate marks in place; dangling markers plain text — `frontend/tests/ask-panel.test.tsx:735-788`; `frontend/tests/cited-answer.test.tsx:101-123`.
- [x] Effort/max_tokens knobs via env touch only config/adapter — `backend/tests/test_config.py:82-98` env overrides; `backend/tests/test_answering_factory.py:32` threading; diff confirms effort appears only in `config.py`, `answering/__init__.py`, `anthropic.py`.

---

## Discrimination Sensor

All mutations injected in scratch state and reverted (`git status` clean, stash list empty after each).

| # | Mutation (behavior-level fault) | File | Killed by | Result |
|---|---|---|---|---|
| M1 | `linkCitationMarkers` bounds check removed (dangling marker becomes a control) | `frontend/app/lib/citations.ts` | `cited-answer.test.tsx` — 2 failed | ✅ Killed |
| M2 | `stripCitationMarkers` made a no-op (markers leak into saved notes) | `frontend/app/lib/citations.ts` | `answer-notes.test.ts` — "strips the answer's inline citation markers" | ✅ Killed |
| M3 | Ask panel renders reasoning beside a not-found verdict (`!notFound` dropped) | `frontend/app/components/ask-panel.tsx` | `ask-panel.test.tsx` — "collapses a not-found turn's thinking" | ✅ Killed |
| M4 | Retrieval runs before the searching phase is yielded | `backend/app/application/conversations.py` | `test_application_conversations.py` — phase-ordering + retrieval-failure tests (2 failed) | ✅ Killed |
| M5 | Reasoning deltas held back while text is buffered | `backend/app/application/streaming.py` | `test_application_conversations.py` — reasoning-passthrough + sentinel-only tests (2 failed) | ✅ Killed |
| M6 | Stream's marker walk diverges from `_parse_message` (numbering state reset per block) | `backend/app/infrastructure/answering/anthropic.py` | `test_answering_anthropic.py` — block-marks + streamed/persisted parity (2 failed) | ✅ Killed |
| M7 | Sentinel comparison run on marked text instead of unmarked | `backend/app/infrastructure/answering/anthropic.py` | `test_answering_anthropic.py` — "sentinel reply stays not found even when the model cites it" | ✅ Killed |
| M8 | `reasoning-end` no longer emitted before `text-start` | `backend/app/infrastructure/web/ui_message_stream.py` | `test_web_conversations.py` — "frames reasoning between the phase and the answer" | ✅ Killed |

**Sensor depth**: elevated (8 mutations — streaming-order and parity invariants are this cycle's named silent-failure risks)
**Result**: 8/8 killed — PASS ✅

---

## Code Quality

| Principle | Status |
|---|---|
| Minimum code / no scope creep (diff maps 1:1 to T1–T12) | ✅ |
| Surgical changes (layering intact: no SDK types outside `anthropic.py`, wire vocabulary only in `ui_message_stream.py`/`streaming.ts`) | ✅ |
| Matches patterns (dataclass events, Protocol fakes, jsdom SSE helper reuse) | ✅ |
| Spec-anchored outcome check (asserted values match spec) | ✅ |
| Per-layer coverage expectation met (application branches 1:1; route happy+edge+error; components happy+all listed edge cases) | ✅ |
| No unclaimed tests (new tests reference ANSW-nn / spec AC in names or comments) | ✅ |
| Overlay `Popover` fully removed (no references remain in `citations.tsx`/`cited-answer.tsx`) | ✅ |
| Documented guidelines followed: CLAUDE.md verification vocabulary, tasks.md gate commands | ✅ |

---

## Gate Check

- **`make test-backend`**: 1929 passed, 11 skipped, 1 failed — the failure is `tests/test_eval_retrieval_metrics.py::TestDeterministicRetrievalMetrics::test_metrics_meet_thresholds`, the pre-existing local-only HNSW-variance failure (green in CI, untouched by this cycle; excluded per brief). Skips: 11 = live/eval-marked tests without keys (justified, pre-existing).
- **`npm test` (frontend)**: 71 files, 734 passed, 0 failed.
- **`make lint`**: ruff check + format, tsc --noEmit, architecture boundaries — all clean, exit 0.
- **Test counts**: match the pre-validation baselines given for this cycle (1929/734); diff adds ~1,000 backend + ~1,000 frontend test lines, no test deletions.

---

## Requirement Traceability Update

| Requirement | Status |
|---|---|
| ANSW-01 … ANSW-10 | ✅ Verified |

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 23/23 AC rows matched spec outcomes; 0 spec-precision gaps
**Sensor**: 8/8 mutations killed
**Gate**: backend 1929 passed (1 known local-only failure, pre-existing), frontend 734 passed, lint clean

**What works**: phase-before-retrieval ordering, reasoning passthrough under sentinel hold-back, stream/buffered marker parity by shared walk, eager guards, restore parity, in-flow citation passages with overlay removed, debounced nav pending on all four named surfaces.

**Issues found**: none.

**Next steps**: none required — feature is publishable from a verification standpoint.
