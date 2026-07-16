# v2-frontend Specification (RFC-002 Cycle D — Frontend v2: product UI + streaming)

## Problem Statement

The MVP frontend is unstyled semantic HTML with navigation dead-ends, no streaming, no
reader, and no ingestion feedback (QA finding **F6**). Cycle C shipped streaming SSE
endpoints (UI Message Stream v1) with no consumer. This cycle ships the product UI:
a real app shell, streaming Ask/Teach on the Vercel AI SDK, navigable citations into a
section reader, and live ingestion progress — restoring the full vertical slice after
five backend-only cycles.

## Goals

- [ ] Every authed screen reachable through in-app navigation (F6 closed).
- [ ] Ask and Teach answers stream token-by-token through the existing proxy.
- [ ] Citations navigate to the cited section in a reader with the target highlighted.
- [ ] Ingestion status updates in place without a manual reload.
- [ ] All gates green: vitest + tsc + next build; backend pytest + ruff.

## Out of Scope

| Feature | Reason |
| --- | --- |
| Quizzes / FSRS review UI | RFC-002 Cycle E |
| Snippet-level text highlighting inside the reader | Fragile string matching vs rendered markdown; section-level highlight covers the RFC deliverable (D-4) |
| Reading-position persistence / "resume where I left off" | Not in RFC Cycle D scope |
| Backend streaming/protocol changes (`ui_message_stream.py`, stream routes) | Cycle C shipped them; this cycle consumes |
| New backend surface beyond the single section read endpoint | Frontend cycle; FE-14 is the only stated gap |
| Proxy `content-encoding` fix | Already implemented + tested (`proxy.ts:65`); FE-22 adds the SSE-relay regression test only |
| Mobile-dedicated layouts | Basic responsive behavior only; polish deferred |
| MessageScroller jump-to-message / regenerate affordances | Not needed for the cycle's stories |

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| AI SDK major version | Current published major of `ai` + `@ai-sdk/react` at install time (research 2026-07-12: v7); UI Message Stream stays v1 | Backend already emits v1; pin exact majors in package.json | auto (D-2) |
| Stream request payload | `prepareSendMessagesRequest` sends only the latest user message as Learny's contract body (`{question}` / `{message}`) | Server owns history (teaching) or is stateless (Q&A); AI-SDK message arrays never cross the proxy | auto (D-2) |
| Section endpoint shape | `GET /api/sources/{id}/section?anchor=` → `{anchor,title,section_path,markdown}`; 404 missing/non-owner/no-corpus/unknown-anchor | Mirrors structure endpoint semantics; anchor is `href[#fragment]` so query param, not path | auto (D-3) |
| Reader highlight granularity | Section-level (scroll + transient highlight of the section) | Evidence anchors are section anchors | auto (D-4) |
| Poll cadence | Fixed 3 s per processing source, stop on terminal/unmount | Author-scale; no backoff complexity | auto (D-6) |
| Theme persistence | next-themes localStorage, system default | shadcn-documented pattern | auto (D-5) |
| Fonts | One `next/font`-loaded sans family (exact family chosen in Design) | Build-time self-hosted, no FOUC | auto |

**Open questions:** none — all resolved or logged above.

## Implicit-Requirement Dimensions (Large sweep)

| Dimension | Resolution |
| --- | --- |
| Input validation & bounds | Client mirrors server bounds: empty submit disabled (FE-10); server 422/400 render as readable errors (FE-09, FE-13). Server remains authoritative. |
| Failure / partial-failure | Stream `error` part or transport failure → readable error, partial text retained, input re-enabled (FE-09); reader/section 404 → not-found state (FE-17); upload errors readable (FE-21). |
| Idempotency / retry / duplicates | No auto-retry of streams (user resends); polling is read-only idempotent (FE-19); restart-ingestion reuses the existing POST (FE-20). |
| Auth boundaries & rate limits | 401 → redirect `/login` preserved on every screen (FE-05); 429 renders a readable throttle message (FE-09/FE-13); new section endpoint owner-scoped 404 no-disclosure (FE-14). |
| Concurrency / ordering | One in-flight stream per chat surface — submit disabled while streaming (FE-10); poll timers cleaned up on unmount and on terminal status (FE-19). |
| Data lifecycle / expiry | Theme in localStorage via next-themes (FE-02). N/A beyond that — no new persisted client state this cycle. |
| Observability | N/A because no new frontend telemetry is in scope; backend request/access logging (AD-041) already covers the new endpoint. |
| External-dependency failure | Backend unreachable → fetch failures render error states, never blank screens (FE-09/FE-13/FE-17). |
| State-transition integrity | Chat states follow useChat status (idle→streaming→idle/error); ingestion badge transitions only on server-reported status (FE-19). |

---

## User Stories

### P1: Product shell & navigation ⭐ MVP (fixes F6 navigation/styling)

**User Story**: As a reader, I want a styled app with persistent navigation so that I can move between my library, a book's Ask/Teach/Read screens, and my account without editing URLs.

**Why P1**: F6's core indictment; every other story renders inside this shell.

**Acceptance Criteria**:

1. **FE-01** WHEN the frontend builds THEN Tailwind v4 + shadcn/ui (CSS-variables mode) + AI Elements SHALL be installed as owned source AND `npm run build`, `tsc --noEmit`, and `vitest run` SHALL pass.
2. **FE-02** WHEN any page loads THEN a `next/font`-loaded font and the shadcn token stylesheet SHALL apply, AND toggling the header theme control SHALL switch light/dark AND persist across reload (next-themes, system default).
3. **FE-03** WHEN an authenticated user visits `/sources`, `/sources/[id]/ask`, `/sources/[id]/teach`, `/sources/[id]/read`, or `/account` THEN the app shell (sidebar + header with user email, account link, logout, theme toggle) SHALL render; WHEN visiting `/login` or `/register` THEN no shell SHALL render.
4. **FE-04** WHEN the sidebar renders THEN it SHALL list the user's sources with status badges, AND ready sources SHALL expand to their section tree (from `GET /api/sources/{id}/structure`), AND source entries SHALL link to Ask/Teach/Read, AND clicking a tree section SHALL open the reader at that section's anchor.
5. **FE-05** WHEN the user logs out or any API call returns 401 THEN the app SHALL redirect to `/login` (existing behavior preserved).

**Independent Test**: Log in, navigate library → book tree → ask/teach/read/account and back entirely through the UI; toggle theme and reload.

---

### P1: Streaming Ask ⭐ MVP

**User Story**: As a reader, I want answers to stream in as they generate with citations attached so that asking feels responsive and grounded.

**Acceptance Criteria**:

1. **FE-06** WHEN the user submits a question THEN the client SHALL POST to `/api/sources/{id}/questions/stream` through the same-origin proxy via `useChat` + `DefaultChatTransport` with body exactly `{"question": <text>}` and header `X-CSRF-Token`.
2. **FE-07** WHEN `text-delta` parts arrive THEN the answer text SHALL render progressively (partial text visible before `finish`).
3. **FE-08** WHEN the terminal `data-citations` part arrives THEN citations SHALL render (section-path breadcrumb + snippet) AND WHEN `data-answer-status` is `not_found_in_source` THEN a distinct not-found state SHALL render with no citations list.
4. **FE-09** WHEN the stream emits an `error` part, the request fails (network/4xx/5xx incl. 429), or the user presses stop THEN the UI SHALL show a readable error or stopped state, retain any partial text, and re-enable input.
5. **FE-10** WHEN a stream is in flight THEN submit SHALL be disabled and empty input SHALL never submit.

**Independent Test**: With a ready source, ask a question and watch text arrive incrementally, citations attach, and a nonsense question produce the not-found state.

---

### P1: Streaming Teach ⭐ MVP (fixes F6 teach dead-ends)

**User Story**: As a learner, I want teaching sessions with streamed turns and visible history so that studying a section is a conversation, not a form.

**Acceptance Criteria**:

1. **FE-11** WHEN the user opens Teach for a ready source THEN a target picker (section tree) and a resume list of previous sessions (with turn counts) SHALL render; picking either SHALL enter the session view.
2. **FE-12** WHEN the user sends a message THEN the client SHALL POST `{"message": <text>}` to `/api/teaching-sessions/{id}/turns/stream` through the proxy AND render deltas progressively; WHEN resuming a session THEN persisted turns (from `GET /api/teaching-sessions/{id}`) SHALL render with their citations.
3. **FE-13** WHEN a teach stream errors, is throttled (429), or reports `not_found_in_source` THEN the same readable state contract as Ask (FE-08/FE-09) SHALL apply.

**Independent Test**: Start a session on a section, exchange streamed turns, leave, resume the session and see full history.

---

### P1: Citations open the book ⭐ MVP

**User Story**: As a reader, I want to click a citation and land on the cited passage in its section so that citations are navigation, not decoration.

**Acceptance Criteria**:

1. **FE-14** WHEN an authenticated owner calls `GET /api/sources/{source_id}/section?anchor=<anchor>` THEN the backend SHALL return 200 `{anchor, title, section_path, markdown}` for a known anchor of a corpus-backed owned source, AND 404 for a missing/non-owned source, absent corpus, or unknown anchor, AND 401 unauthenticated.
2. **FE-15** WHEN the reader route `/sources/[id]/read?anchor=<encoded>` loads THEN it SHALL fetch the section and render its markdown with the section brought into view and transiently highlighted.
3. **FE-16** WHEN a citation is clicked in Ask or Teach THEN a popover SHALL show section path + snippet + an "Open in book" action that navigates to the reader at that citation's anchor.
4. **FE-17** WHEN the reader loads with an unknown anchor THEN a readable not-found state SHALL render; WHEN it loads with no anchor THEN a pick-a-section empty state SHALL render.

**Independent Test**: Ask a question, click a citation, land in the reader with the cited section highlighted.

---

### P1: Ingestion progress ⭐ MVP (fixes F6 polling)

**User Story**: As a reader, I want upload/ingestion progress to update by itself so that I know when a book is ready without refreshing.

**Acceptance Criteria**:

1. **FE-18** WHEN ingestion status is needed THEN a frontend client function SHALL call `GET /api/sources/{id}/ingestion` (unit-tested with injected `fetchImpl`).
2. **FE-19** WHEN the library shows a source with status `processing` THEN it SHALL poll that source's ingestion every 3 s, update the badge in place on change, and stop polling on terminal status (`ready`/`failed`) and on unmount.
3. **FE-20** WHEN ingestion is `failed` THEN the latest event message SHALL be visible and the existing restart control SHALL remain available.

**Independent Test**: Upload an EPUB, start ingestion, watch the badge move processing → ready with no reload.

---

### P2: Upload experience in the new shell

**User Story**: As a reader, I want to add a book from the library screen with clear feedback.

**Acceptance Criteria**:

1. **FE-21** WHEN the library renders THEN the upload control (existing multipart flow, unchanged contract) SHALL be styled within the shell AND upload validation/errors SHALL render readable messages.

---

### P2: SSE relay regression coverage

**User Story**: As a maintainer, I want a proxy test proving SSE streams relay correctly so that streaming can't silently break at the boundary.

**Acceptance Criteria**:

1. **FE-22** WHEN a proxied response is a streamed SSE body THEN a test SHALL assert the body relays without buffering (chunks observable before stream end) AND that `x-vercel-ai-ui-message-stream`, `cache-control`, and `x-accel-buffering` headers survive relay while `content-encoding`/`content-length` remain stripped.

---

## Edge Cases

- WHEN the library is empty THEN the sidebar and library SHALL show an empty state with the upload affordance.
- WHEN a book's TOC is deep (≤4 levels typical) THEN the tree SHALL remain navigable via collapsible nesting (no virtualization).
- WHEN section markdown contains raw HTML THEN it SHALL NOT be injected into the DOM as live HTML (rendered inert/escaped by the markdown renderer).
- WHEN the CSRF token is missing/stale (403) THEN the chat surfaces SHALL render the error state, not crash.
- WHEN a stream disconnects mid-answer without an `error` part THEN the UI SHALL settle to a non-streaming state with partial text retained (no forever-spinner).
- WHEN a source is not ready (409 from stream endpoints) THEN a readable "not ready" message SHALL render.

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| --- | --- | --- | --- |
| FE-01..FE-05 | P1 Shell & navigation | A (A1–A4), C (C1–C3) | Implemented — verification pending |
| FE-06..FE-10 | P1 Streaming Ask | D (D1–D3) | Implemented — verification pending |
| FE-11..FE-13 | P1 Streaming Teach | D (D1, D2, D4) | Implemented — verification pending |
| FE-14..FE-17 | P1 Citations → reader | B (B1, B2, B4), D (D2), E (E1, E2) | Implemented — verification pending |
| FE-18..FE-20 | P1 Ingestion progress | B (B3), C (C4, C5) | Implemented — verification pending |
| FE-21 | P2 Upload UX | C (C4) | Implemented — verification pending |
| FE-22 | P2 SSE relay test | B (B5) | Implemented — verification pending |

**Coverage:** 22 total, 22 mapped to tasks, 0 unmapped.

## Success Criteria

- [ ] F6 fully closed: navigation, styling, polling, teach dead-ends all addressed.
- [ ] A cited answer streams and its citation opens the cited section in ≤2 clicks.
- [ ] Frontend gates (vitest, tsc, build) and backend gates (pytest, ruff) green.
- [ ] Full vertical slice restored (AD-010) — flagged as resolved at the merge gate.
