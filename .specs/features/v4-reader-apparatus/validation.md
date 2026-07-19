# v4-reader-apparatus Validation

**Date**: 2026-07-19
**Spec**: `.specs/features/v4-reader-apparatus/spec.md`
**Diff range**: `d52a33a..HEAD` (commits acc9262, 3735ce3, 2df78dd, c34792a, 0ce3838, 4e1f166, 1e262f8, 5ca4bd0, 91ceeb7, 0acaa4d)
**Verifier**: independent sub-agent (author ≠ verifier)
**Verdict**: ✅ PASS

---

## Scope Check

`git diff --stat d52a33a..HEAD` touches 22 files, all under `frontend/` — zero backend files, confirming the frontend-only boundary the spec (Out of Scope: "Backend schema or endpoint additions") and tasks.md claim. Deleted screens (`ask-screen.tsx`, `teach-screen.tsx`, their tests) confirmed absent; no dangling references to them anywhere under `app/`/`components/` (grep clean).

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| A1 ReaderPanel shell + URL state | ✅ Done | acc9262 |
| A2 Redirects + sidebar links | ✅ Done | 3735ce3 |
| B1 AskPanel port | ✅ Done | 2df78dd |
| B2 TeachPanel port | ✅ Done | c34792a |
| B3 Delete screens | ✅ Done | 0ce3838 |
| C1 Citation passages | ✅ Done | 4e1f166 |
| C2 In-reader citation jump | ✅ Done | 1e262f8 (squashed) |
| C3 Five-verb popover | ✅ Done | 5ca4bd0 |
| D1 answer-notes lib | ✅ Done | 91ceeb7 |
| D2 Save action UI | ✅ Done | 0acaa4d |
| D3 Sweep + gates | ✅ Done | no-commit (sweep clean) |

---

## Spec-Anchored Acceptance Criteria

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| RA-01 `?panel=ask` renders chapter + Ask panel | panel open in ask mode | `chapter-reader.test.tsx:746` — `panel.getAttribute("data-mode")` `toBe("ask")` + `ask-panel-body` present | ✅ PASS |
| RA-02 `?panel=teach` opens Teach | teach mode | `chapter-reader.test.tsx:758` — `data-mode` `toBe("teach")` + `teach-panel-body` | ✅ PASS |
| RA-03 close/switch → shallow `router.replace`, no refetch, width restored | drops `panel`, keeps `anchor`; no chapter fetch | `chapter-reader.test.tsx:790` close → `replace("/sources/s1/read?anchor=…")`; `:805` switch → `…&panel=teach`; `:1044` panel toggle → `chapterCalls()` `toBe(1)` | ✅ PASS |
| RA-04 old routes redirect | `/sources/[id]/read?panel=ask`\|`teach` exact | `route-redirects.test.tsx:26` `redirect` `toHaveBeenCalledWith("/sources/s1/read?panel=ask")`; `:31` teach; `:36` id passthrough | ✅ PASS |
| RA-05 sidebar deep links; screens gone | hrefs `…/read?panel=…`; AskScreen/TeachScreen absent | `app-sidebar.test.tsx:157` ask href; `:159` teach href; deletion confirmed by `ls`/grep + tsc | ✅ PASS |
| RA-06 reading stays non-modal (scroll/position/paint) | scroll tracking + painting active w/ panel open | `chapter-reader.test.tsx:819` — 1 `mark.reader-highlight`, progress `10%`→`40%` on observer emit with panel open | ✅ PASS |
| RA-07 Ask parity (transport, citations, not-found, errors, 401) | POST `{question}`+CSRF; deltas; citations; not-found; 429/mid-error banner; 401→onRequireAuth | `ask-panel.test.tsx:124` body+CSRF; `:184` not-found no citations; `:214` mid-error banner+partial; `:246` 429; `:314` 401→onRequireAuth | ✅ PASS |
| RA-08 empty state suggested prompts submit on click | 3 prompts; click submits verbatim; gone after | `ask-panel.test.tsx:335` — 3 buttons, click → POST `{question: chosen}`, prompts removed | ✅ PASS |
| RA-09 streaming caret present mid-stream, gone on finish | caret visible while streaming, absent on complete | `ask-panel.test.tsx:370` — `streaming-caret` present after delta, null after finish | ✅ PASS |
| RA-10 Teach parity (picker/start/resume/stream) | picker built; start POST target; resume seeds cited history; error legs | `teach-panel.test.tsx:208` picker+start+stream+citation; `:290` not-found; `:323` 429; `:344` mid-error; `:378` resume ordered cited history; `:420` 401 | ✅ PASS |
| RA-11 taught passage scrolls once per activation | `onShowInBook(target.anchor)` once on start AND resume, not per turn | `teach-panel.test.tsx:524` start once (`c2.xhtml`), not re-fired on turn; `:572` resume once (`c1.xhtml`) | ✅ PASS |
| RA-12 citation = verbatim passage, `.prose-reading`, section locator, no chunk_id/score | blockquote in `.prose-reading` + breadcrumb; no chunk_id/score in DOM | `citations.test.tsx:81` — breadcrumb, snippet blockquote `.prose-reading`; body text excludes `chunk_id`/`score` | ✅ PASS |
| RA-13 in-chapter "Show in book" → scroll+flash, panel open | scrollIntoView + heading flash, no push | `chapter-reader.test.tsx:860` — scrollIntoView called, `data-highlight=on`, panel present, `push` not called, `replace` with `anchor+panel` | ✅ PASS |
| RA-14 foreign anchor → navigate w/ panel preserved + reload | `router.push` `…?anchor=…&panel=teach`; chapter refetch | `chapter-reader.test.tsx:885` push carries `&panel=teach`, no scroll; `:1004` foreign anchor `chapterCalls()` `toBe(2)` | ✅ PASS |
| RA-15 exactly five verbs | Highlight, Note, Explain, Ask, Create card | `capture-popover.test.tsx:37` — `buttons.map(textContent)` `toEqual([...five...])` | ✅ PASS |
| RA-16 Highlight/Note run capture flow unchanged | `onCapture("highlight")`/`("highlight-note")`; existing 409/painting untouched | `capture-popover.test.tsx:66` verb→onCapture; `chapter-reader.test.tsx:406` full capture payload+anchor; `:475` 409 reload prompt | ✅ PASS |
| RA-17 Explain one-tap fixed template | `Explain this passage from the book:\n\n"<quote>"` exact, one submit | `ask-panel.test.tsx:532` POST body `toEqual({question: 'Explain this passage from the book:\n\n"the selected sentence"'})`, consumed once | ✅ PASS |
| RA-18 Ask attaches quote as context to typed question | `Regarding this passage:\n\n"<quote>"\n\n<question>`; not auto-submitted | `ask-panel.test.tsx:570` chip shown, no auto-submit, then POST with exact combined body | ✅ PASS |
| RA-19 Create card disabled + no action | disabled, "Coming soon" hint, fires nothing | `capture-popover.test.tsx:82` — `disabled` `toBe(true)`, title `Coming soon`, `onCapture` not called | ✅ PASS |
| RA-20 Save cited answer → capture w/ anchor₀ + first¶ + answer body, confirm | capture(sourceId, {anchor, quote_exact=first¶, title=Q≤80, body_markdown=answer}); success UI | `answer-notes.test.ts:63` field-by-field payload; `:92` 80-char cap; `ask-panel.test.tsx:428` UI calls endpoint + `save-note-status`; `teach-panel.test.tsx:454` teach save | ✅ PASS |
| RA-21 409 stale → plain-note fallback w/ jump-back link, still succeeds | `createNote` body = answer + `[Open in book](…encoded anchor…)`, outcome `plain` | `answer-notes.test.ts:113` fallback body exact + outcome plain; `:141` empty-¶ → straight to fallback | ✅ PASS |
| RA-22 no save on citation-less / not-found | action absent | `ask-panel.test.tsx:485` not-found no button; `:511` answered-no-citations no button; `teach-panel.test.tsx:500` only cited turn offers it | ✅ PASS |

**Status**: ✅ All 22 ACs covered and matched to spec-defined outcomes.

---

## Edge Cases

- [x] Unauthenticated panel action → `onRequireAuth` — `ask-panel.test.tsx:314`, `teach-panel.test.tsx:420`.
- [x] Stream error → existing `errorMessageFor` messages — `ask-panel.test.tsx:214/246`, `teach-panel.test.tsx:323/344`.
- [x] Empty/formatting-only selection → no popover (existing `deriveCaptureSelection` null) — `chapter-reader.test.tsx:398`.
- [x] Unknown `?panel=` value → panel closed — `chapter-reader.test.tsx:780`.
- [x] Snippet with no non-empty first paragraph → plain-note fallback directly — `answer-notes.test.ts:141`.
- [x] No ready corpus (chapter 404) → not-found state, panel params ignored — `chapter-reader.test.tsx:548`.

---

## Discrimination Sensor

Full P1 feature → 7 behavior-level mutations across distinct risk areas, each applied in scratch (direct edit) and reverted via `git checkout` (working tree verified clean after each).

| # | File | Mutation | Test file | Killed? |
| --- | --- | --- | --- | --- |
| 1 | `chapter-reader.tsx:281` | unknown/absent panel value falls through to `"ask"` instead of `null` | `chapter-reader.test.tsx` | ✅ Killed (3 failed) |
| 2 | `chapter-reader.tsx:473` | `handleShowInBook` always navigates (drop in-chapter scroll branch, `if(!inChapter)`→`if(true)`) | `chapter-reader.test.tsx` | ✅ Killed (1 failed) |
| 3 | `chapter-reader.tsx:474` | cross-chapter push drops panel-param preservation (`{panel: panelMode}` removed) | `chapter-reader.test.tsx` | ✅ Killed (1 failed) |
| 4 | `ask-panel.tsx:76` | Explain template submits bare quote without the fixed prefix | `ask-panel.test.tsx` | ✅ Killed (1 failed) |
| 5 | `answer-notes.ts:84` | capture fallback condition swapped (`!==`→`===` "stale_capture") | `answer-notes.test.ts` | ✅ Killed (2 failed) |
| 6 | `ask-panel.tsx:231` | Save-to-note shown on citation-less answers (`length > 0`→`>= 0`) | `ask-panel.test.tsx` | ✅ Killed (1 failed) |
| 7 | `ask-panel.tsx:213` | caret left rendered after finish (`isLast && isStreaming`→`isLast`) | `ask-panel.test.tsx` | ✅ Killed (1 failed) |

**Sensor depth**: P1-full (7 mutations, all branches/risk areas).
**Result**: 7/7 killed — ✅ PASS.

---

## Code Quality

| Principle | Status |
| --- | --- |
| Minimum code / no scope creep | ✅ Frontend-only; no backend touched |
| Surgical changes, matches patterns | ✅ Ports reuse existing transports/seams; `routedFetch`/SSE test patterns mirrored |
| Spec-anchored outcome check | ✅ All asserted values match spec outcomes (exact templates, redirect targets, payloads) |
| Per-layer coverage (unit + component) | ✅ `answer-notes` unit 1:1; panels/reader cover happy + edge + error |
| Every test maps to a spec requirement | ✅ No unclaimed tests; migrated parity tests retained (ask 15, teach 10) |
| Documented deviations honest | ✅ `SPEC_DEVIATION` marker in `answer-notes.ts:81-83`; Phase B/C deviations in context.md §Deviations |

---

## Gate Check

- **Full gate**: `cd frontend && npx vitest run && npx tsc --noEmit`
- **Result**: 42 test files, **380 passed, 0 failed, 0 skipped**; `tsc --noEmit` exit 0.
- **Test-count floor**: tasks.md floor 324; final 380 (≥ floor). Migrated ask/teach scenarios preserved (screens' tests re-homed into panel tests).
- **Backend no-regression**: not re-run by verifier (frontend-only diff, zero backend files changed); Phase D recorded backend 824 passed / ruff clean.

---

## Accepted Deviations (not counted as gaps)

- Phase B — migrated auth scenarios adapted to reader-owned auth (401 stream start → `onRequireAuth`); behavior preserved at the integration boundary.
- Phase C — capture popover's "Highlight + note" label → "Note" for the five-verb set; capture action/payload/navigation/409 legs untouched (byte-identical when verbs unwired, asserted `capture-popover.test.tsx:102`).
- Phase D — plain-note fallback keys on `NoteError` kind `"stale_capture"` (the real kind in `lib/notes.ts`), not design's guessed `"stale"`; marked `SPEC_DEVIATION` in `answer-notes.ts`.

---

## Requirement Traceability Update

RA-01 .. RA-22 → ✅ Verified (all covered, spec-anchored, sensor-discriminated).

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 22/22 ACs matched spec outcome; 0 spec-precision gaps.
**Sensor**: 7/7 mutations killed.
**Gate**: 380 passed, 0 failed; tsc clean.

**What works**: Ask/Teach as non-modal panel modes driven by `?panel=`; old routes redirect into the reader; citations render as verbatim `.prose-reading` passages with in-place "Show in book" (same-chapter scroll vs cross-chapter navigate, panel preserved); five-verb selection popover with one-tap Explain (exact template) and quote-attaching Ask; answers save as anchored notes with honest plain-note fallback.

**Issues found**: none.

**Next steps**: merge-ready; unblocks RFC-003 Cycle F (panel + citation-passage component now exist).
