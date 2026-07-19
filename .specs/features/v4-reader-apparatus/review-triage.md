# PR #38 Review Triage — v4-reader-apparatus

9 comments (7 inline: 1 ⚠️ + 6 💡; 2 PR-level informational). Every finding checked against the code as it exists. Comments are deleted after fixes land; this file is the surviving record.

| # | Source (comment id) | file:line | Verdict | Action | Rationale |
|---|---|---|---|---|---|
| F1 | ⚠️ 3611278415 | `frontend/app/components/ask-panel.tsx:313` | REAL | FIX | The 409→plain-note fallback join between `SaveToNoteAction` and the real `lib/notes` clients is only tested with injected fakes; the component tests cover 201 and 500 but not the 409 middle leg. Exactly the seam where a wiring slip (cf. the `stale_capture` kind deviation) would hide. Add a routedFetch leg: highlights 409 + notes 201 → "Saved to notes." with the jump-back body asserted. |
| F2 | 💡 3611278439 | `frontend/app/components/ask-panel.tsx:264` | REAL | FIX | Attached-quote lifecycle untested: removing the chip must yield a bare submit, and the quote must not re-attach after a combined submit. A regression would silently scope questions to a discarded passage — user-facing behavior, no current test catches it. |
| F3 | 💡 3611278458 | `frontend/app/components/toc-panel.tsx:35` | REAL | FIX | `readUrl` is now an exported four-branch helper; three branches are pinned transitively, the bare no-anchor/no-panel branch nowhere. Direct unit describe is cheap and matches the house pure-lib pattern. Lands with F5's move. |
| F4 | 💡 3611279071 | `frontend/app/lib/answer-notes.ts:25` | PARTIALLY REAL | FIX (comment only) | Verified against the backend: `NoteWriteRequest.title` has NO length constraint (only the body cap exists, `NoteBodyTooLong` → 422). So there is no backend cap to drift from — the real defect is the in-code comment falsely claiming the backend enforces 80. The truncation itself is spec-pinned client UX (title = question truncated to 80) and stays; a future backend cap below 80 would surface through the already-handled error leg. Fix = correct the comment to state it is a client-side display choice. |
| F5 | 💡 3611279088 | `frontend/app/lib/answer-notes.ts:90` | REAL | FIX | The reader-route URL contract is hand-built in three places (`toc-panel.readUrl`, `citations.tsx` href, `answer-notes.ts` link). Move `readUrl` to `frontend/app/lib/read-url.ts` (it is a route contract, not TOC UI) and route all three call sites through it. |
| F6 | 💡 3611279106 | `frontend/app/components/teach-panel.tsx:64` | REAL | FIX | `SaveToNoteAction` is genuinely shared but homed as a secondary export of `ask-panel.tsx`, coupling teach-panel (and, via `PendingPanelRequest`, reader-panel/chapter-reader) to ask-panel internals. Extract `components/save-to-note-action.tsx`; move `PendingPanelRequest` to a shared lib home to avoid a parent↔child import cycle. |
| F7 | 💡 3611279118 | `frontend/app/components/teach-panel.tsx:323` | REAL | FIX | Message-text flattening exists as a private helper in ask-panel and an inline copy in teach-panel. Promote one `messageText()` next to the message types in `lib/streaming.ts`. |
| F8 | PR-level 5017210009 (requirements) | — | REAL (informational) | NO ACTION | 22/22 acceptance criteria confirmed implemented, zero gaps; nothing requested. |
| F9 | PR-level 5017224738 (summary) | — | REAL (informational) | NO ACTION | Consolidated lane summary; nothing requested. |

**Counts:** 7 actionable findings — 6 real fix, 1 partially-real fix (comment correction; premise about a backend cap was false), 0 false, 0 won't-fix; 2 informational.

**Fix plan (atomic commits):**
1. `test(reader): pin the save-to-note fallback and attached-quote lifecycle` — F1, F2.
2. `refactor(reader): share the reader url helper across call sites` — F3, F5, F4's comment correction (same file).
3. `refactor(reader): extract shared panel pieces into their own modules` — F6, F7.

Gates before push: full frontend vitest + tsc + build (floor 380 passed, only additions expected).
