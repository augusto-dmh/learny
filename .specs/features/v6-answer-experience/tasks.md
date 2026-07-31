# v6-answer-experience Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. If the skill cannot be activated, STOP and tell the user.

**Design**: `.specs/features/v6-answer-experience/design.md`
**Status**: Done — T1–T12 committed (dcd9069b…76658867), Verifier PASS (validation.md: 23/23 ACs, 8/8 mutants killed); phase workers built all four phases, orchestrator verified gates inline (workers skipped reports)

---

## Test Coverage Matrix

> Generated from codebase + guidelines. Guidelines found: `CLAUDE.md` (verification vocabulary, `make` targets, infra prerequisite), `backend/pyproject.toml` (`[tool.pytest.ini_options]`, `live`/`eval` markers), `frontend/vitest.config.ts` (node default env, per-file jsdom opt-in), `Makefile` (CI-parity lint/test).

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
|---|---|---|---|---|
| Backend application (streaming hold-back, conversation service) | unit | All branches; 1:1 to ANSW-01/02/03 ACs; every listed edge case (reasoning passthrough during hold, sentinel-only turn, retrieval failure in-stream, generator close) | `backend/tests/test_application_conversations.py`, `backend/tests/test_application_streaming*.py` | `cd backend && uv run pytest tests/<file>` |
| Backend adapter (Anthropic request/params/events/markers) | unit (fake client) | Request kwargs asserted (thinking/effort/max_tokens on stream + buffered); thinking-delta mapping; marker insertion incl. sentinel/no-citation/malformed-index; stream↔buffered text parity | `backend/tests/test_answering_anthropic.py`, `test_generation_invariants.py` | `cd backend && uv run pytest tests/test_answering_anthropic.py tests/test_generation_invariants.py` |
| Backend web/SSE presenter | integration (TestClient) | Frame order incl. new `data-phase`/`reasoning-*`; guards still fail with HTTP status before first byte; error part mid-stream | `backend/tests/test_web_conversations.py` | `cd backend && uv run pytest tests/test_web_conversations.py` |
| Backend config/factory | unit | Defaults + literal validation (bad effort rejected); factory threads effort | existing settings/factory test files (`test_answering_factory.py` + settings tests) | `cd backend && uv run pytest tests/test_answering_factory.py <settings test file>` |
| Frontend lib (`streaming.ts`) | unit (node) | Part parsing 1:1 to new parts; restore parity (`turnsToUIMessages`) | `frontend/tests/streaming.test.ts` | `cd frontend && npx vitest run tests/streaming.test.ts` |
| Frontend components (panels, citations, nav) | unit (jsdom) | Happy + every listed edge case: phases, empty-reasoning skip, not-found collapse, mark activation → in-flow passage → onShowInBook, dangling marker, note-save strip, pending indicator | `frontend/tests/*.test.tsx` | `cd frontend && npx vitest run tests/<file>` |

Full-suite baselines: record `uv run pytest --collect-only -q | tail -1` and `npm test` totals at phase start; counts must not silently drop (deletions must be explained in the phase report).

## Parallelism Assessment

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
|---|---|---|---|
| Backend pytest | No (run sequentially, one invocation) | Shared DB fixtures for db-marked tests; suite is run as one `uv run pytest` | `Makefile` `test-backend`; CLAUDE.md infra prerequisite |
| Frontend vitest | Yes (vitest manages workers) | Per-file jsdom, hand-rolled fetch stubs per test file | `vitest.config.ts`; `tests/teach-panel.test.tsx:69-80` |

`[P]` below is ordering info only (no inter-task dependency); each phase runs in one worker sequentially regardless.

## Gate Check Commands

| Gate Level | When to Use | Command |
|---|---|---|
| Quick (backend) | Per-task | `cd backend && uv run pytest tests/<affected files>` |
| Quick (frontend) | Per-task | `cd frontend && npx vitest run tests/<affected files>` |
| Full | Phase boundary | `make test-backend` and/or `make test-frontend` (run `make infra` first for backend) |
| Build | Phase boundary + before push | `make lint` (ruff + format check + tsc + architecture boundaries) |

---

## Execution Plan

```
Phase A (backend: config + reasoning stream, sequential): T1 → T2 → T3 → T4 → T5
Phase B (backend: citation markers, sequential):          T6 → T7        (after A)
Phase C (frontend: answer experience, sequential):        T8 → T9 → T10  (after B)
Phase D (frontend: nav pending):                          T11 → T12      (after C; independent of A–C in content, last per AD-224)
```

4 phases → one Opus worker per phase, sequential, fresh Opus Verifier after T12 (AD-224).

---

## Task Breakdown

### T1: Generation effort knob + max_tokens default

**What**: Add `generation_effort` setting (validated literal low/medium/high/xhigh/max, default `medium`, env `LEARNY_GENERATION_EFFORT`), change `generation_max_tokens` default 1024 → 4096, thread effort through the answering factory into the adapter constructor.
**Where**: `backend/app/core/config.py:193-204`, `backend/app/infrastructure/answering/__init__.py:42-55`, `anthropic.py` constructor, settings/factory tests
**Depends on**: None — **Requirement**: ANSW-05
**Done when**: defaults + validation asserted (bad literal rejected at settings construction); factory passes effort; local provider path untouched; quick gate passes.
**Tests**: unit — **Gate**: quick — **Commit**: `feat(config): make generation effort and token budget deliberate`

### T2: Adapter request parameters + effort logging

**What**: Both Anthropic calls (`messages.stream` :218, `messages.create` :316) carry `thinking={"type":"adaptive","display":"summarized"}` and effort (`output_config={"effort":…}` as typed kwarg if `anthropic 0.116` accepts it, else `extra_body`); `_log_call` gains `effort=`; widen `_MessagesClient` Protocol + test fakes.
**Where**: `backend/app/infrastructure/answering/anthropic.py`, `backend/tests/test_answering_anthropic.py`
**Depends on**: T1 — **Requirement**: ANSW-04, ANSW-06
**Done when**: request kwargs asserted for both paths and both modes; log line includes effort; buffered path still skips non-text blocks; quick gate passes.
**Tests**: unit — **Gate**: quick — **Commit**: `feat(answering): request summarized thinking and explicit effort`

### T3: Reasoning deltas out of the adapter

**What**: Add `AnswerReasoningDelta` to the domain `AnswerStreamEvent` union; `_run_stream` maps provider thinking deltas to it (**trap**: today's `event.type == "text"` filter silently drops them — verify what event type the installed SDK's high-level stream emits for thinking and use it; a raw-event fallback is acceptable).
**Where**: `backend/app/domain/entities.py:435-460`, `anthropic.py:200-231`, adapter + invariant tests
**Depends on**: T2 — **Requirement**: ANSW-02
**Done when**: fake client emitting thinking deltas yields reasoning events interleaved before/among text; adapters without thinking emit none; local adapter contract test (no reasoning events) added; quick gate passes.
**Tests**: unit — **Gate**: quick — **Commit**: `feat(answering): surface model reasoning as stream events`

### T4: Application phases + retrieval inside the stream

**What**: Add `StreamPhase`/`StreamReasoningDelta` to `TurnStreamEvent`; `hold_back_deltas` passes reasoning through untouched (**invariant**: text/sentinel logic byte-identical); split `_preflight` — guards/conversation/history eager, retrieval moves into the generator behind an immediate `StreamPhase("searching")`; retrieval failure inside the generator → `AnswerGenerationFailed`.
**Where**: `backend/app/application/streaming.py`, `backend/app/application/conversations.py:535-641`, `backend/tests/test_application_conversations.py`
**Depends on**: T3 — **Requirement**: ANSW-01, ANSW-03
**Done when**: phase yielded before retrieval executes (sensor: retrieval spy not called until generator pulled past first event); reasoning streams while text held; sentinel-only turn emits phase→not-found with no text and no leaked reasoning-after-terminal; retrieval error → error path; generator close still closes port stream; existing guard tests untouched and green; quick gate passes.
**Tests**: unit — **Gate**: quick — **Commit**: `feat(conversations): stream the searching phase before retrieval`

### T5: SSE vocabulary for phases + reasoning

**What**: `to_ui_message_stream` emits `data-phase {"phase":"searching"}` and `reasoning-start/delta/end` (v1 protocol part shapes), preserving existing frame order and error handling.
**Where**: `backend/app/infrastructure/web/ui_message_stream.py`, `backend/tests/test_web_conversations.py`
**Depends on**: T4 — **Requirement**: ANSW-01, ANSW-02, ANSW-03
**Done when**: endpoint test asserts full frame order (start → data-phase → reasoning-* → text-* → data-citations → finish) and the not-found/error orders; guards still produce HTTP statuses pre-stream; **full backend gate at phase boundary** (`make infra` then `make test-backend`) + `make lint`.
**Tests**: integration — **Gate**: full+build — **Commit**: `feat(conversations): stream reasoning and phase frames over SSE`

### T6: Buffered-path citation markers

**What**: `_parse_message` inserts `[^n]` after each cited text block, n = first-occurrence index of the cited chunk (the existing `cited` walk); multiple citations on one block → markers in citation order; sentinel and no-citation replies carry no markers; malformed `document_index` skipped as today.
**Where**: `backend/app/infrastructure/answering/anthropic.py:94-122`, `backend/tests/test_answering_anthropic.py`
**Depends on**: T5 (same files, merge hygiene) — **Requirement**: ANSW-07
**Done when**: numbering matches `cited_chunk_ids` order by construction (test with repeated chunk citations asserting dedupe → same n); sentinel/malformed cases asserted; quick gate passes.
**Tests**: unit — **Gate**: quick — **Commit**: `feat(answering): mark cited passages inline in buffered answers`

### T7: Streaming citation markers + parity

**What**: `_run_stream` emits marker text deltas at citation attachment points (SDK citation events if the high-level stream exposes them; else raw-event/per-block insertion at block stop), numbering identical to T6's walk.
**Where**: `anthropic.py:200-231`, adapter tests
**Depends on**: T6 — **Requirement**: ANSW-07
**Done when**: for the same fake final message, concatenated stream text == buffered `_parse_message` text (parity sensor); markers never emitted before the sentinel hold-back could suppress a not-found turn (sentinel replies cite nothing); **full backend gate + lint at phase boundary**.
**Tests**: unit — **Gate**: full+build — **Commit**: `feat(answering): stream inline citation marks as they attach`

### T8: Frontend stream types + views

**What**: Type `data-phase`; extend `assistantView` to `{text, citations, status, reasoning, phase}` collecting `reasoning` parts and last phase; `messageText`/`turnsToUIMessages` restore parity unchanged.
**Where**: `frontend/app/lib/streaming.ts`, `frontend/tests/streaming.test.ts`
**Depends on**: T7 (wire shapes settled) — **Requirement**: ANSW-01, ANSW-02, ANSW-03
**Done when**: parsing tests cover reasoning/phase/absent cases + persisted-turn replay; quick gate passes.
**Tests**: unit — **Gate**: quick — **Commit**: `feat(reader): parse answer phases and reasoning from the stream`

### T9: Panel phases + collapsible reasoning

**What**: Ask and Teach panels render "Searching the book…" (Shimmer) until first reasoning/text part, a collapsible reasoning region (open while streaming, collapses when text starts, re-expandable, absent when empty), error state replacing the phase indicator; caret behavior kept consistent across both panels.
**Where**: `frontend/app/components/ask-panel.tsx`, `teach-panel.tsx`, shared phase/reasoning component (new), `frontend/tests/{ask,teach}-panel.test.tsx`
**Depends on**: T8 — **Requirement**: ANSW-01, ANSW-02, ANSW-03
**Done when**: SSE-helper tests drive phase→reasoning→text and assert region states incl. empty-reasoning skip and not-found collapse; restored threads show no reasoning; quick gate passes.
**Tests**: unit (jsdom) — **Gate**: quick — **Commit**: `feat(reader): show searching and thinking states while answering`

### T10: Inline marks + in-flow passage

**What**: Render `[^n]` tokens as numbered inline marks (pre-process or Streamdown footnote-component override); activating mark n or chip n expands one clamped passage region beneath the answer (snippet, breadcrumb, "Show in book" → existing `onShowInBook`, "Open note" preserved); delete the full-height overlay `Popover`; dangling markers render as plain text; `saveAnswerAsNote` strips markers; chips remain as fallback/inventory.
**Where**: `frontend/app/components/citations.tsx`, `message.tsx` integration point, note-save path, `frontend/tests/citations.test.tsx`, `citation-reader-loop.test.tsx`, panel tests
**Depends on**: T9 — **Requirement**: ANSW-07, ANSW-08
**Done when**: mark→passage→show-in-book loop tested; overlay gone (no full-height popover element); marker-strip on note save tested; restore parity tested; **full frontend gate + lint at phase boundary**.
**Tests**: unit (jsdom) — **Gate**: full+build — **Commit**: `feat(reader): open cited passages in flow beneath the answer`

### T11: Navigation pending primitives

**What**: `LinkPendingIndicator` (child of `<Link>`, `useLinkStatus`, animation-delayed ~120ms) and `useNavigateWithTransition` (`startTransition`-wrapped push exposing `isPending`), with unit tests.
**Where**: new `frontend/components/ui/nav-pending.tsx` (+ hook file if cleaner), new test file
**Depends on**: None (content) — runs in Phase D — **Requirement**: ANSW-09
**Done when**: indicator appears on slow navigation and not on instant resolution (delay honored); hook exposes pending state; quick gate passes.
**Tests**: unit (jsdom) — **Gate**: quick — **Commit**: `feat(ui): shared pending states for navigation`

### T12: Apply pending pattern app-wide

**What**: Adopt the primitives on Home two-card actions (Pick a book / Resume / Review), library entries, sidebar links, TOC entries; other trivial adopters at worker's discretion.
**Where**: `frontend/app/components/home-screen.tsx`, `library-screen.tsx`, `shell/app-sidebar.tsx`, `toc-panel.tsx`, their tests
**Depends on**: T11 — **Requirement**: ANSW-10
**Done when**: each named surface shows pending feedback under a slow-navigation test (at least Home covered by explicit test; others smoke-asserted); **full frontend gate + `make lint`**.
**Tests**: unit (jsdom) — **Gate**: full+build — **Commit**: `feat(ui): give navigation immediate pending feedback`

---

## Task Granularity Check

| Task | Scope | Status |
|---|---|---|
| T1 | 1 settings block + factory thread | ✅ |
| T2 | 1 adapter concern (request params) | ✅ |
| T3 | 1 event type end-to-end in adapter | ✅ |
| T4 | 1 service restructure (cohesive: phase+passthrough+split) | ✅ (cohesive in 2 files) |
| T5 | 1 presenter vocabulary | ✅ |
| T6 / T7 | 1 function each (parse / stream) | ✅ |
| T8 | 1 lib module | ✅ |
| T9 | 1 UI concern across the 2 twin panels | ✅ (panels are deliberate twins) |
| T10 | 1 citation-UX rework | ✅ (cohesive: marks+passage+deletion) |
| T11 / T12 | primitives / adoption | ✅ |

## Diagram-Definition Cross-Check

| Task | Depends On (body) | Diagram | Status |
|---|---|---|---|
| T1 | None | phase A head | ✅ |
| T2 | T1 | T1→T2 | ✅ |
| T3 | T2 | T2→T3 | ✅ |
| T4 | T3 | T3→T4 | ✅ |
| T5 | T4 | T4→T5 | ✅ |
| T6 | T5 (merge hygiene) | A→B | ✅ |
| T7 | T6 | T6→T7 | ✅ |
| T8 | T7 | B→C | ✅ |
| T9 | T8 | T8→T9 | ✅ |
| T10 | T9 | T9→T10 | ✅ |
| T11 | none (content); Phase D after C | C→D | ✅ |
| T12 | T11 | T11→T12 | ✅ |

## Test Co-location Validation

| Task | Layer | Matrix Requires | Task Says | Status |
|---|---|---|---|---|
| T1 | config/factory | unit | unit | ✅ |
| T2, T3, T6, T7 | adapter | unit (fake client) | unit | ✅ |
| T4 | application | unit | unit | ✅ |
| T5 | web/SSE | integration | integration | ✅ |
| T8 | frontend lib | unit (node) | unit | ✅ |
| T9, T10, T11, T12 | frontend components | unit (jsdom) | unit (jsdom) | ✅ |

**Tools**: no MCPs; no additional skills loaded by workers (design/context carry the needed API facts; the `fastapi`/`pgvector` skills are not relevant to these seams). Per ship-cycle: workers get goal-shaped briefs, absolute paths, and the non-negotiable contract.
