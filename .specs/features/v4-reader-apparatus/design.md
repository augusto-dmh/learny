# v4-reader-apparatus Design

Frontend-only cycle: Ask/Teach become side-panel modes inside `ChapterReader`, citations render as passages that jump the book in place, the selection popover grows to the five-verb set, and answers can be saved as anchored notes. No backend changes — every needed seam shipped in earlier cycles (chapter/section routes, question/turn SSE streams, highlight capture, notes CRUD).

## Architecture Overview

```
/sources/[id]/read?anchor=&panel=ask|teach
        │
  ChapterReader ──────────────────────────────┐
   │  panel state ← useSearchParams("panel")  │
   │  pendingRequest state (explain/ask verbs)│
   ├─ ChapterFlow (article, .prose-reading)   ├─ ReaderPanel (w-[26rem], own scroll)
   │   ├─ FlowSection × N (section anchors)   │   ├─ mode tabs Ask | Teach, close
   │   └─ SelectionVerbs popover (5 verbs)────┤   ├─ AskPanel  → createQuestionTransport
   │        Highlight/Note → capture flow     │   │    suggested prompts, caret,
   │        Explain/Ask ───→ pendingRequest ──┤   │    CitationList(onShowInBook)
   │        Create card (disabled)            │   └─ TeachPanel → createTurnTransport
   ├─ handleShowInBook(anchor) ←──────────────┘        target picker, sessions,
   │    in-chapter → scroll+flash                      CitationList(onShowInBook),
   │    else → router.push(anchor+panel preserved)     save-to-note action
   └─ /sources/[id]/ask, /teach → server redirect() into ?panel=

Save-to-note: lib/answer-notes.ts → captureHighlight(anchor₀, first¶ of snippet₀, body=answer)
                                   ↘ 409/empty → createNote(answer + jump-back link)
```

## Code Reuse Analysis

| Existing seam | Reused for |
|---|---|
| `createQuestionTransport` / `createTurnTransport`, `assistantView`, `errorMessageFor`, `turnsToUIMessages` (`lib/streaming.ts`) | Panel chat — unchanged transports (RA-07, RA-10) |
| `AskScreen`/`TeachScreen` inner chat composition (AI-Elements `Conversation`, `PromptInput*`) | Ported into `AskPanel`/`TeachPanel`; screens then deleted |
| `CitationList`/`CitationPopover` (`citations.tsx`) — already breadcrumb + `.prose-reading` blockquote of verbatim snippet | Passage presentation; gains `onShowInBook` callback (RA-12/13) |
| `ChapterReader` scroll-to-target effect + `flashAnchor` + `handleSameChapterNavigate` | Citation jump + taught-passage scroll (RA-11/13) |
| `CapturePopover` + `deriveCaptureSelection` (`notes/capture-popover.tsx`) | Five-verb popover extends it — Highlight/Note flow untouched (RA-16) |
| `captureHighlight`, `createNote`, `NoteError` (`lib/notes.ts`) | Save-answer-to-note (RA-20/21) |
| `readUrl(sourceId, anchor)` (`toc-panel.tsx`) | URL building; extended to carry panel params |
| `routedFetch` + fake SSE fixture patterns (tests) | Panel parity tests migrate the existing ask/teach test bodies |

## Components

### Frontend (all under `frontend/app/`)

1. **`components/reader-panel.tsx`** — `ReaderPanel({ sourceId, csrf, mode: PanelMode, onModeChange, onClose, pendingRequest, onPendingConsumed, onShowInBook, onRequireAuth })`. Right-hand column (`w-[26rem]` fixed, border-l, own `overflow-y-auto`, full height); header with Ask/Teach segmented control + close button; body renders `AskPanel` or `TeachPanel`. `PanelMode = "ask" | "teach"`.
2. **`components/ask-panel.tsx`** — `AskPanel({ sourceId, csrf, pendingRequest, onPendingConsumed, onShowInBook, onRequireAuth })`. Ported `AskChat` internals. Empty state: `SUGGESTED_PROMPTS` (3 fixed strings) as buttons → submit. Streaming caret: while the last assistant message is streaming, append `<span data-testid="streaming-caret">` (CSS blink via existing tokens); removed on finish. Pending: `explain` → auto-submit `Explain this passage from the book:\n\n"<quote>"`; `ask` → holds quote as attached context chip; submit sends `Regarding this passage:\n\n"<quote>"\n\n<typed question>`. Save-to-note action on completed cited answers.
3. **`components/teach-panel.tsx`** — `TeachPanel({ sourceId, csrf, onShowInBook, onRequireAuth })`. Ported `TeachScreen` internals (target picker via `fetchSourceStructure`+`flattenSections`, resume list, `TeachChat` on turn transport). On session start/resume with a target anchor: call `onShowInBook(target.anchor)` exactly once per session activation (RA-11). Save-to-note on turn answers.
4. **`components/citations.tsx` (modified)** — `CitationList`/`CitationPopover` gain optional `onShowInBook?: (anchor: string) => void`. Provided → "Show in book" button invoking it; absent → existing `Link` fallback. Popover body stays breadcrumb + verbatim passage blockquote; never renders `chunk_id`/`score`.
5. **`components/chapter-reader.tsx` (modified)** —
   - Panel state from `useSearchParams().get("panel")` (unknown → closed). Toggle/close via `router.replace` preserving `anchor`; loaded-chapter identity keyed so panel-param changes never refetch (RA-03).
   - Cross-chapter anchor changes: when the `anchor` search param changes to an anchor not in the loaded chapter's section set, refetch the chapter for it (RA-14); same-chapter changes keep the existing scroll path.
   - `handleShowInBook(anchor)`: in-chapter → `scrollIntoView` + flash (existing machinery); else `router.push(read URL with anchor + current panel params)`.
   - `pendingRequest: PendingPanelRequest | null` state (`{ kind: "explain" | "ask", quote: string, anchor: string }`); set by selection verbs (opens panel in ask mode via `router.replace` when closed), cleared by `onPendingConsumed`.
   - Layout: found-state becomes a flex row (article + panel); article container keeps `.prose-reading` width behavior when panel closed.
6. **`components/notes/capture-popover.tsx` (extended)** — gains `onExplain(quote)`, `onAskAbout(quote)` and a disabled "Create card" button (`title`/hint "Coming soon"); existing Highlight/Note capture flow byte-identical. Renders exactly five verbs when the new props are provided.
7. **`lib/answer-notes.ts` (new)** — pure `firstParagraph(text: string): string | null` (split on blank line, trimmed, null when empty); `saveAnswerAsNote({ sourceId, question, answerText, citations, csrfToken, captureImpl?, createImpl? }): Promise<{ outcome: "anchored" | "plain" }>` — capture path with `citations[0].anchor` + first paragraph of `citations[0].snippet`, title = question truncated to 80 chars, body = answer markdown; falls back to `createNote` (body = answer + `[Open in book](/sources/<id>/read?anchor=…)`) on `NoteError` kind `"stale"` or null paragraph; rethrows other errors.
8. **`(app)/sources/[id]/ask/page.tsx`, `teach/page.tsx` (rewritten)** — server components: `redirect(\`/sources/${id}/read?panel=ask|teach\`)` (Next 15 async `params`).
9. **`components/shell/app-sidebar.tsx` (modified)** — Ask/Teach links → `/sources/${id}/read?panel=ask|teach`.
10. **Deleted:** `components/ask-screen.tsx`, `components/teach-screen.tsx` (after ports land).

### Backend

None. Phase D runs the backend suite once as a no-regression check.

## Data Models

Frontend-local only:

```ts
type PanelMode = "ask" | "teach";
type PendingPanelRequest = { kind: "explain" | "ask"; quote: string; anchor: string };
type SaveOutcome = { outcome: "anchored" | "plain" };
```

URL contract: `/sources/[id]/read?anchor=<anchor>&panel=<ask|teach>` — both params optional and independent; unknown `panel` values render closed.

## Error Handling Strategy

- Stream/auth errors: parity — `errorMessageFor`, `StreamRequestError` 401 → `onRequireAuth` (unchanged code paths, migrated tests keep asserting them).
- Save-to-note: `stale` (409) and empty-paragraph → silent fallback to plain note (still success UI); any other `NoteError`/network error → inline error text near the action, no retry loop.
- Chapter 404 / not-ready: existing not-found state; panel params ignored there.

## Risks & Concerns

- **ChapterReader load-effect rework** (cross-chapter refetch) is the only change touching shipped reader-core behavior — mitigated by keeping the same-chapter path untouched and extending `chapter-reader.test.tsx` with both directions (panel toggle ⇒ no refetch; foreign anchor ⇒ refetch).
- **AI-Elements in a narrow column**: components were composed full-page; panel constrains width. CSS-only risk; tests assert structure, not pixels.
- **jsdom selection mechanics** for the verb popover — reuse the existing capture-popover test pattern (selection stubbing already solved there).
- **Deleted screens**: `tsc` + full vitest run catch dangling imports; redirect tombstones keep old URLs alive.

## Tech Decisions (feature-local; project-level ones live in context.md → STATE AD-129..132)

- Panel column is fixed-width (26rem) with its own scroll region; no resizer this cycle (polish is Cycle F).
- Suggested prompts are a const in `ask-panel.tsx`, not config.
- The streaming caret is a styled span keyed off `useChat` status + last-message role — no timer machinery.
- `readUrl` helper grows an options bag (`{ panel? }`) rather than a second helper.

## Test-Coverage Matrix (verifier input)

| AC | Test surface (file) | Layer |
|---|---|---|
| RA-01/02/03 + unknown-panel edge | `frontend/tests/reader-panel.test.tsx` + `chapter-reader.test.tsx` (panel open/mode/close, no refetch on toggle) | component |
| RA-04 | `frontend/tests/route-redirects.test.tsx` (redirect() target per route) | route |
| RA-05 | `frontend/tests/app-sidebar.test.tsx` (link hrefs); tsc/build prove screens gone | component |
| RA-06 | `chapter-reader.test.tsx` (position hook + painting active with panel open) | component |
| RA-07 | `frontend/tests/ask-panel.test.tsx` (migrated SSE fixture parity: deltas, citations, not-found, error legs) | component |
| RA-08 | `ask-panel.test.tsx` (prompts rendered when empty; click submits) | component |
| RA-09 | `ask-panel.test.tsx` (caret present mid-stream, absent after finish) | component |
| RA-10 | `frontend/tests/teach-panel.test.tsx` (migrated parity: picker, start, resume, turn stream) | component |
| RA-11 | `teach-panel.test.tsx` (`onShowInBook` called once with target anchor) | component |
| RA-12 | `frontend/tests/citations.test.tsx` (passage text + breadcrumb; no chunk_id/score in DOM) | component |
| RA-13/14 + panel preservation | `chapter-reader.test.tsx` (in-chapter scroll+flash vs push with anchor+panel) | component |
| RA-15/19 | `frontend/tests/capture-popover.test.tsx` (five verbs; Create card disabled, no action) | component |
| RA-16 | existing capture tests unchanged and green | component |
| RA-17/18 | `chapter-reader.test.tsx` or `ask-panel.test.tsx` (explain auto-submits template w/ quote; ask attaches context to typed question) | component |
| RA-20/21/22 + empty-paragraph edge | `frontend/tests/answer-notes.test.ts` (unit) + `ask-panel.test.tsx` (action visibility/feedback) | unit + component |
