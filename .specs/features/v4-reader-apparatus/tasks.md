# v4-reader-apparatus Tasks

## Execution Protocol (MANDATORY — do not skip)

1. One task = one atomic commit, gate green first (test runner decides, never self-assessment).
2. Tests derive from spec ACs (RA-01..22), never from the implementation.
3. Never weaken/skip/delete tests to pass. SPEC_DEVIATION markers + phase summary for any divergence.
4. After the last task: fresh Verifier (author ≠ verifier), spec-anchored check + discrimination sensor.

## Test Coverage Matrix

See design.md §Test-Coverage Matrix — it is the canonical AC→test-file map for the Verifier.

## Parallelism Assessment

Phases strictly sequential (A → B → C → D): B ports chat into A's panel; C wires verbs/citations into both; D's save action sits on B's messages. `[P]` within a phase is informational only.

## Gate Check Commands

- **Quick (per task):** `cd frontend && npx vitest run tests/<touched test files>`
- **Full (phase boundary):** `cd frontend && npx vitest run && npx tsc --noEmit`
- **Build (final):** `cd frontend && npm run build`
- **Backend no-regression (D3 only):** `cd backend && .venv/bin/python -m pytest -q` (offline baseline: 825 passed, 0 failed) and `.venv/bin/python -m ruff check .` — expected untouched.

Test-count floor: frontend suite starts at **324 passed** — migrated ask/teach tests must keep their scenario count (parity), so the final count must be ≥ 324 with zero deletions unaccounted in the phase summary.

## Execution Plan

| Phase | Tasks | ACs |
|---|---|---|
| A — Panel shell & routing | A1 ✅ acc9262, A2 ✅ 3735ce3 (full gate: 340 passed + tsc clean) | RA-01..06 |
| B — Ask & Teach panel modes | B1 ✅ 2df78dd, B2 ✅ c34792a, B3 ✅ 0ce3838 (full gate: 346 passed + tsc clean; ask 7→11, teach 6→8 scenarios, auth legs adapted to reader-owned auth) | RA-07..11 |
| C — Citations as passages + selection verbs | C1 ✅ 4e1f166, C2 ✅ 1e262f8 (squashed from a duplicate-worker overlap, tree verified identical), C3 ✅ 5ca4bd0 (full gate: 362 passed + tsc clean; citations 2→5, chapter-reader 29→36, capture-popover +6 new; NF-12 "Highlight + note"→"Note" label adapted for the five-verb set) | RA-12..19 |
| D — Save-to-note + hardening | D1 ✅ 91ceeb7, D2 ✅ 0acaa4d, D3 ✅ no-commit (sweep clean; final gates: frontend 380 passed + tsc + build, backend 824 passed/0 failed + ruff; SPEC_DEVIATION: fallback keys off NoteError kind `stale_capture`, design.md had guessed `stale`) | RA-20..22 |

## Task Breakdown

### A1: ReaderPanel shell + panel URL state + layout

- **Files:** `frontend/app/components/reader-panel.tsx` (new), `frontend/app/components/chapter-reader.tsx`, `frontend/app/components/toc-panel.tsx` (readUrl options), `frontend/tests/reader-panel.test.tsx` (new), `frontend/tests/chapter-reader.test.tsx`
- **Do:** `ReaderPanel` shell (mode tabs, close, placeholder bodies), `panel` search-param state in `ChapterReader` (unknown → closed), flex-row layout, toggle/close via `router.replace` preserving `anchor`, no chapter refetch on panel-param change. `readUrl` grows `{ panel? }`.
- **Done when:** RA-01/02 panel opens per param; RA-03 close/mode switch replaces URL without refetch (assert fetch impl call count); RA-06 scroll-position hook + highlight painting still active with panel open; unknown `panel` renders closed.
- **Tests:** component. **Gate:** quick.
- **Commit:** `feat(reader): add side panel shell driven by the panel url param`

### A2: Old-route redirects + sidebar deep links

- **Files:** `frontend/app/(app)/sources/[id]/ask/page.tsx`, `frontend/app/(app)/sources/[id]/teach/page.tsx`, `frontend/app/components/shell/app-sidebar.tsx`, `frontend/tests/route-redirects.test.tsx` (new), `frontend/tests/app-sidebar.test.tsx`
- **Do:** Rewrite both pages as server components calling `redirect()` to `/sources/{id}/read?panel=…` (Next 15 async params). Sidebar Ask/Teach links target the panel deep links.
- **Done when:** RA-04 each old route redirects to its exact target; RA-05 sidebar hrefs updated (screens deleted later in B3).
- **Tests:** route + component. **Gate:** full (phase boundary).
- **Commit:** `feat(reader): redirect ask and teach routes into the reader panel`

### B1: AskPanel port + suggested prompts + streaming caret

- **Files:** `frontend/app/components/ask-panel.tsx` (new), `frontend/app/components/reader-panel.tsx`, `frontend/tests/ask-panel.test.tsx` (new, migrating `ask-screen.test.tsx` scenarios)
- **Do:** Port `AskChat` composition onto `createQuestionTransport` unchanged; empty-state `SUGGESTED_PROMPTS` (3, click ⇒ submit); caret span while last assistant message streams; pendingRequest contract consumed here (explain auto-submit template, ask context chip + combined submit) — wiring from the reader arrives in C3, tested here via props.
- **Done when:** RA-07 parity legs (deltas, citations part, not-found, 401→onRequireAuth, error messages) pass against fake SSE fixtures; RA-08 prompts render only when empty and submit on click; RA-09 caret visible mid-stream, gone on finish; RA-17/18 submitted message bodies match the fixed templates exactly.
- **Tests:** component. **Gate:** quick.
- **Commit:** `feat(reader): port ask into the reader panel with prompts and caret`

### B2: TeachPanel port + taught-passage callback

- **Files:** `frontend/app/components/teach-panel.tsx` (new), `frontend/app/components/reader-panel.tsx`, `frontend/tests/teach-panel.test.tsx` (new, migrating `teach-screen.test.tsx` scenarios)
- **Do:** Port target picker, session start/resume list, `TeachChat` on `createTurnTransport` + `turnsToUIMessages`; call `onShowInBook(target.anchor)` exactly once per session activation.
- **Done when:** RA-10 parity legs pass; RA-11 `onShowInBook` called once with the session's target anchor on start AND on resume, not on every turn.
- **Tests:** component. **Gate:** quick.
- **Commit:** `feat(reader): port teach sessions into the reader panel`

### B3: Delete standalone screens + full-suite checkpoint

- **Files:** delete `frontend/app/components/ask-screen.tsx`, `frontend/app/components/teach-screen.tsx`, `frontend/tests/ask-screen.test.tsx`, `frontend/tests/teach-screen.test.tsx` (scenarios live on in the panel tests — phase summary must account scenario-for-scenario)
- **Done when:** RA-05 screens gone; full vitest + tsc green; no scenario lost (counted in summary).
- **Tests:** none new. **Gate:** full (phase boundary).
- **Commit:** `refactor(reader): remove the standalone ask and teach screens`

### C1: Citation passage presentation + onShowInBook

- **Files:** `frontend/app/components/citations.tsx`, `frontend/app/components/ask-panel.tsx`, `frontend/app/components/teach-panel.tsx`, `frontend/tests/citations.test.tsx`
- **Do:** Optional `onShowInBook` on `CitationList`/`CitationPopover` (button when provided, `Link` fallback otherwise); popover = section-path locator + verbatim passage blockquote in `.prose-reading`; assert no `chunk_id`/`score` in DOM; panels pass the callback through.
- **Done when:** RA-12 covered incl. negative machinery assertion; callback invoked with `citation.anchor`.
- **Tests:** component. **Gate:** quick.
- **Commit:** `feat(reader): render citations as passages that open in the book`

### C2: In-reader citation jump (same-chapter scroll / cross-chapter navigate)

- **Files:** `frontend/app/components/chapter-reader.tsx`, `frontend/tests/chapter-reader.test.tsx`
- **Do:** `handleShowInBook`: anchor ∈ loaded chapter sections → scrollIntoView + flash (existing machinery, panel untouched); else `router.push` read URL with anchor + current panel params; refetch chapter when the anchor param changes to a foreign anchor (same-chapter path unchanged).
- **Done when:** RA-13 in-chapter jump scrolls + flashes with panel still open (no fetch); RA-14 foreign anchor pushes URL carrying `panel=` and refetches; existing reader-core scroll tests stay green.
- **Tests:** component. **Gate:** quick.
- **Commit:** `feat(reader): jump to cited passages without leaving the answer`

### C3: Five-verb selection popover + panel wiring

- **Files:** `frontend/app/components/notes/capture-popover.tsx`, `frontend/app/components/chapter-reader.tsx`, `frontend/app/components/reader-panel.tsx`, `frontend/tests/capture-popover.test.tsx`, `frontend/tests/chapter-reader.test.tsx`
- **Do:** Extend `CapturePopover` with `onExplain`/`onAskAbout` + disabled "Create card" (hint copy, no action); `ChapterReader` sets `pendingRequest` and opens the panel in ask mode (`router.replace` w/ `panel=ask`) on those verbs; `onPendingConsumed` clears it.
- **Done when:** RA-15 exactly five verbs listed; RA-16 existing capture tests untouched and green; RA-17/18 verb → panel opens in ask mode with the pendingRequest payload (quote + anchor); RA-19 Create card disabled, fires nothing.
- **Tests:** component. **Gate:** full (phase boundary).
- **Commit:** `feat(reader): offer five verbs on text selection`

### D1: answer-notes lib (pure + orchestration)

- **Files:** `frontend/app/lib/answer-notes.ts` (new), `frontend/tests/answer-notes.test.ts` (new)
- **Do:** `firstParagraph` (blank-line split, trim, null on empty); `saveAnswerAsNote` — capture with `citations[0].anchor` + first paragraph of `citations[0].snippet`, title = question truncated 80 chars, body = answer markdown; fallback `createNote` (answer + jump-back markdown link) on `NoteError("stale")` or null paragraph; other errors rethrow; returns `{ outcome }`.
- **Done when:** RA-20 capture payload asserted field-by-field; RA-21 fallback body contains answer + exact link, outcome `"plain"`; empty-snippet edge goes straight to fallback; non-stale errors propagate.
- **Tests:** unit. **Gate:** quick.
- **Commit:** `feat(notes): save panel answers as anchored notes`

### D2: Save action UI on Ask/Teach answers

- **Files:** `frontend/app/components/ask-panel.tsx`, `frontend/app/components/teach-panel.tsx`, `frontend/tests/ask-panel.test.tsx`, `frontend/tests/teach-panel.test.tsx`
- **Do:** "Save to note" on completed assistant messages with ≥1 citation (both modes); saved/error feedback states; hidden for not-found/citation-less answers.
- **Done when:** RA-20 UI calls the lib with the message's question+answer+citations; RA-22 action absent on not-found and citation-less messages; error leg shows inline message.
- **Tests:** component. **Gate:** quick.
- **Commit:** `feat(reader): add save-to-note on panel answers`

### D3: Sweep + full gates

- **Files:** sweep-only (dangling refs, UI copy pass on touched files per AD-120)
- **Do:** Repo-wide check for references to deleted screens/routes; full frontend suite + tsc + build; backend suite + ruff as no-regression proof.
- **Done when:** all gates green; frontend ≥ 324 passed; backend 825 passed unchanged; build passes.
- **Tests:** none new. **Gate:** build + backend no-regression.
- **Commit:** `test(reader): harden the reader apparatus suite` (or `chore(reader): …` if sweep-only changes)

## Diagram-Definition Cross-Check

Every component in design.md §Architecture appears in exactly one task (ReaderPanel A1; redirects/sidebar A2; AskPanel B1; TeachPanel B2; deletions B3; citations C1; jump C2; verbs C3; answer-notes D1/D2). No task introduces a component absent from design.md.

## Test Co-location Validation

All new tests live in `frontend/tests/*.test.tsx|ts` per house convention; no backend test files change.

## Task Granularity Check

11 tasks / 4 phases; each task ≤ ~5 files, one deliverable, independently committable. Phase B carries the largest ports but each panel is one bounded component + one migrated test file.
