# Learny v2 research — frontend-streaming

Generated 2026-07-12 by a web-research agent (v2 planning research fleet). Sources/dates inline; verify load-bearing claims before implementation.

---

# Frontend v2 Research: Streaming Chat on Next.js 15 / React 19

## Actionable conclusions (read this first)

1. **Adopt AI SDK `useChat` + emit Vercel's UI Message Stream protocol from FastAPI.** The protocol is a documented, stable, language-agnostic SSE format explicitly designed for non-JS backends ([stream protocol docs](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol), official [next-fastapi example](https://github.com/vercel/ai/tree/main/examples/next-fastapi)). A Python emitter is ~100 lines. This unlocks AI Elements components for free.
2. **Current AI SDK major is v7** — shipped 2026-06-25 ([changelog](https://vercel.com/changelog/ai-sdk-7)); v6 was the prior major. v7 is agent-platform focused; the `useChat`/transport/stream-protocol surface carries over from v5/v6 with codemods for migration. Pin `ai@^7` + `@ai-sdk/react`.
3. **UI stack: Tailwind v4 (latest 4.3.1, 2026-06-12, [releases](https://github.com/tailwindlabs/tailwindcss/releases)) + shadcn/ui + Vercel AI Elements.** shadcn/ui fully supports React 19 + Tailwind v4 ([docs](https://ui.shadcn.com/docs/tailwind-v4)); AI Elements is Vercel-official, built on shadcn conventions, installed as source via CLI ([repo](https://github.com/vercel/ai-elements)) and includes `Sources` and `InlineCitation` components that map directly onto Learny's citation model.
4. **Backend SSE: use FastAPI's built-in `EventSourceResponse`** (`fastapi.sse`, since FastAPI 0.135.0, [official tutorial](https://fastapi.tiangolo.com/tutorial/server-sent-events/)) — it auto-sets `Cache-Control: no-cache`, `X-Accel-Buffering: no`, and 15s keep-alive pings. No need for `sse-starlette` anymore.
5. **Learny's existing proxy already streams correctly** (verified in repo, see §4) with one latent bug to fix: `relayResponse` copies `content-encoding`/`content-length` from upstream after undici has already decompressed the body.

---

## 1. Streaming approach: `useChat` vs plain fetch/ReadableStream (honest weigh)

**Option A — AI SDK `useChat` with FastAPI speaking the UI Message Stream protocol (recommended).**
The protocol is SSE with JSON parts: `start` → `text-start`/`text-delta`/`text-end` (id-correlated blocks) → `finish` → `data: [DONE]`, plus first-class **`source-document`/`source-url` parts** (built for RAG citations) and **`data-*` custom parts** for arbitrary typed payloads ([stream protocol](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol), [streaming custom data](https://ai-sdk.dev/docs/ai-sdk-ui/streaming-data)). Requirements for a custom backend: emit those SSE events and set header `x-vercel-ai-ui-message-stream: v1`. Point the hook at the proxy via transport ([transport docs](https://ai-sdk.dev/docs/ai-sdk-ui/transport)):

```ts
const { messages, sendMessage, status, stop } = useChat({
  transport: new DefaultChatTransport({ api: "/api/qa/ask/stream" }),
});
```

- **Why:** you get message-state management, streaming text assembly, abort/regenerate, status, `message.parts` rendering (text + sources + data parts interleaved), and direct compatibility with AI Elements (`Conversation`, `Message`, `Response`, `Sources`, `InlineCitation`, `PromptInput`). Rebuilding this by hand is the single biggest hidden cost of Option B.
- **Why not:** couples your wire format to a Vercel-versioned spec (mitigate: keep the emitter in one FastAPI presenter module, behind the ports — domain never sees it); the Python side is hand-rolled (the official example exists; third-party [py-ai-datastream](https://github.com/elementary-data/py-ai-datastream) implements the protocol but verify it targets the v5+ UI-message stream, not the legacy v4 text-prefix format — **uncertain, check before depending on it**); Pydantic-AI's `VercelAIAdapter` also emits this protocol ([pydantic docs](https://pydantic.dev/docs/ai/integrations/ui/vercel-ai/)) — evidence the protocol is a de-facto standard, but don't adopt Pydantic-AI just for this.

**Option B — plain SSE + custom React hook.**
- **Why:** zero protocol coupling; you fully own the event vocabulary (`token`, `citation`, `done`); ~equally simple on the FastAPI side. Note `EventSource` API itself is unusable here (GET-only, no body) — you'd use `fetch` + `ReadableStream` + an SSE line parser anyway, so "simpler" is misleading.
- **Why not:** you reimplement message state, optimistic user messages, block assembly, error/abort/reconnect, and streaming-markdown flushing; you forfeit AI Elements' `useChat` integration, which is most of the UI you'd otherwise hand-build. For a portfolio product UI, that's the wrong place to spend effort.

**Verdict:** Option A. The protocol adaptation cost is one small, well-documented Python module; the payoff is the entire component ecosystem.

## 2. FastAPI emitter sketch (ask/teach streaming)

```python
# app/api/presenters/ui_message_stream.py  (edge module; domain-unaware)
from fastapi.sse import EventSourceResponse, ServerSentEvent  # FastAPI >= 0.135.0

async def stream_answer(events):  # events = domain AsyncIterator from AnswerGenerationPort
    yield ServerSentEvent(data={"type": "start"})
    yield ServerSentEvent(data={"type": "text-start", "id": "t1"})
    async for ev in events:
        if ev.kind == "token":
            yield ServerSentEvent(data={"type": "text-delta", "id": "t1", "delta": ev.text})
        elif ev.kind == "citation":     # mid-stream citation
            yield ServerSentEvent(data={
                "type": "source-document", "sourceId": ev.citation_id,
                "mediaType": "application/epub+zip", "title": ev.section_title,
                "providerMetadata": {"learny": {"anchor": ev.anchor, "sectionPath": ev.section_path,
                                                "snippet": ev.snippet, "documentId": ev.document_id}},
            })
    yield ServerSentEvent(data={"type": "text-end", "id": "t1"})
    yield ServerSentEvent(data={"type": "finish"})
    yield ServerSentEvent(raw_data="[DONE]")

@router.post("/qa/ask/stream", response_class=EventSourceResponse)
async def ask_stream(...):
    return EventSourceResponse(stream_answer(...),
        headers={"x-vercel-ai-ui-message-stream": "v1"})
```

Learny-specific anchor data rides in `providerMetadata` (or use a parallel `{"type": "data-citation", "data": {...}}` part — typed on the client via `UIMessage` generics; either works, `data-*` parts are the documented extension point for custom structured data). Anthropic's Citations API emits `citations_delta` events mid-stream, which map 1:1 onto this per-token → per-citation event flow. FastAPI's `EventSourceResponse` handles disconnects (generator gets `CancelledError` — clean up there) and pings every 15s; SSE comments are ignored by the client parser.

## 3. Integration path: FastAPI → Next proxy → browser

```
useChat (DefaultChatTransport, api:"/api/qa/ask/stream")
  → POST same-origin /api/qa/ask/stream  (cookie + x-csrf-token, JSON body {messages,...})
  → Next catch-all route.ts (Node runtime, force-dynamic)
      fetch(upstreamReq) resolves on headers; new Response(upstream.body) relays the stream
  → FastAPI EventSourceResponse
```

**Verified against the repo:** `/home/augusto/projects/learny/frontend/app/api/[...path]/route.ts` returns `relayResponse(upstreamRes)` which passes `upstream.body` (a `ReadableStream`) straight into `new Response(...)` — this streams; Next only buffers when handlers consume the body before returning ([Next streaming guide](https://nextjs.org/docs/app/guides/streaming), [discussion #48427](https://github.com/vercel/next.js/discussions/48427)). `export const dynamic = "force-dynamic"` is already set. Findings:

- **Bug to fix in `/home/augusto/projects/learny/frontend/app/lib/proxy.ts` (`relayResponse`):** `new Headers(upstream.headers)` copies `content-encoding`/`content-length` verbatim, but undici's fetch already decompressed the body. Harmless today (no gzip on FastAPI), breaks the day GZipMiddleware is added. Add both to a response-side strip list. (Also never gzip SSE routes.)
- `useChat` sends POST with a JSON `{messages}` body — the proxy forwards bodies with `duplex: "half"` already; no change needed. Use `prepareSendMessagesRequest` on the transport to reshape the payload into Learny's API contract (e.g. send only the latest question + session id, not full message history).
- **VPS nginx:** FastAPI's `X-Accel-Buffering: no` header is relayed through and disables nginx buffering; also set `proxy_buffering off;` + long `proxy_read_timeout` on the SSE location as belt-and-braces ([sse-starlette notes the 16KB nginx buffer issue](https://github.com/sysid/sse-starlette)).
- Next dev server and `next start` both stream route-handler responses; no Vercel-platform concerns since deploy target is your VPS.

## 4. UI stack

- **Tailwind v4** (CSS-first `@theme`, no config file; v4.1 added text-shadows/masks, v4.2 webpack plugin + palettes, v4.3.1 current — [blog](https://tailwindcss.com/blog/tailwindcss-v4-1), [releases](https://github.com/tailwindlabs/tailwindcss/releases)). New projects via `create-next-app` + shadcn init get v4 by default.
- **shadcn/ui**: full React 19 + Next 15 + Tailwind v4 support; components no longer use `forwardRef`, have `data-slot` attributes ([Tailwind v4 docs](https://ui.shadcn.com/docs/tailwind-v4), [React 19 docs](https://ui.shadcn.com/docs/react-19)). Its **June 2026 chat components release** ([changelog](https://ui.shadcn.com/docs/changelog/2026-06-chat-components)) added `MessageScroller` (anchored scrolling, streamed replies, jump-to-message), `Message`, `Bubble` — explicitly complementary to AI Elements, not a replacement.
- **AI Elements** ([elements.ai-sdk.dev](https://elements.ai-sdk.dev/), [repo](https://github.com/vercel/ai-elements)): 20+ components installed as owned source via `npx ai-elements@latest` (requires shadcn init, CSS-variables mode, AI SDK). Relevant: `Conversation`, `Message`, `Response` (streaming markdown), [`Sources`](https://elements.ai-sdk.dev/components/sources), [`InlineCitation`](https://elements.ai-sdk.dev/components/inline-citation) (citation pill + hover detail — exactly Learny's citation popover), `PromptInput`, `Reasoning`, `Suggestions`, `Loader`.
- **App shell:** shadcn `Sidebar` (composable, collapsible, official) for library/book nav; `DropdownMenu` + auth state from a `/api/auth/me` fetch for the header. Dark mode via `next-themes`.

## 5. Component inventory

**Shell:** `AppSidebar` (library list, per-book tree), `AuthHeader`, `ThemeProvider`.
**Library/ingestion:** `BookCard` (+ `Progress` for ingestion status polling), `UploadDropzone`, `IngestionStatusBadge`.
**Ask (Q&A):** `Conversation` + `MessageScroller`, `Message`/`Bubble`, `Response` (streamed markdown), `InlineCitation` → `CitationPopover` (snippet, section path, "open in book" → anchor link), `Sources` footer list, `PromptInput` with stop button, `EmptyState` with `Suggestions`.
**Teach:** same chat core + `SessionOutline` (side panel of section under study), `PassageCard` (quoted passage with anchor link), progress stepper.
**Quiz/SRS (flagship):** `QuizCard` (question, `RadioGroup`/free answer, reveal), `CitationFootnote` on each question (grounds it to a passage), `GradeBar` (Again/Hard/Good/Easy — SM-2/FSRS buttons), `ReviewQueue` (due-count `Badge`), `SessionSummary` (dataviz-lite stats), `DeckSettings`.
**Reader/source view:** `BookStructureTree`, `SectionReader` (rendered canonical markdown with anchor targets), `AnchorHighlight`.

## 6. Book structure trees & reading anchors

- shadcn has **no official tree component**; build `BookStructureTree` from `Collapsible` + `Button` primitives inside `Sidebar` (the sidebar docs show nested collapsible groups — sufficient for TOC depth ≤ 4). Only reach for virtualization if a book's TOC exceeds ~1–2k nodes.
- Anchors: render canonical sections with `id={anchor}`; deep-link as `/books/[id]/read/[sectionId]#anchor`. Use `scroll-margin-top` (Tailwind `scroll-mt-20`) so the sticky header doesn't cover the target; highlight the target briefly via the CSS `:target` pseudo-class or a `useEffect` flash. Track reading position with one `IntersectionObserver` over anchor elements; persist last anchor per book (backend or localStorage) for "resume".
- Citation → source: `InlineCitation` popover carries `documentId + sectionPath + anchor` from the `source-document` part; the "open in book" action navigates to the reader route and scrolls to the anchor. This makes citations navigable, not decorative — the whole point of the structured corpus.

## 7. Pitfalls checklist

1. **Protocol version skew:** the UI Message Stream is `v1` under AI SDK 5→7 so far, but pin `ai` and re-verify the part shapes on major upgrades; keep the Python emitter in one file.
2. **Missing `x-vercel-ai-ui-message-stream: v1` header** → useChat falls back to text-mode parsing and drops parts silently.
3. **`relayResponse` content-encoding bug** (§3) — fix before enabling any compression.
4. **Don't consume the stream in the route handler** — return `new Response(upstream.body)` immediately (already correct in Learny).
5. **`EventSource` can't POST** — irrelevant under useChat (fetch-based), but rules out naive plain-SSE tutorials.
6. **Abort propagation:** wire `useChat`'s `stop()` → the proxy relays fetch abort → FastAPI generator gets `CancelledError`; cancel the Anthropic stream there or you leak provider tokens.
7. **Streaming markdown flicker:** use AI Elements' `Response` (handles incomplete markdown blocks) instead of re-rendering `react-markdown` per token.
8. **FastAPI 0.135.0 floor** for `fastapi.sse`; if pinned lower, `sse-starlette` ([repo](https://github.com/sysid/sse-starlette)) is the equivalent.
9. **AI Elements requires shadcn CSS-variables mode** — choose it at `shadcn init`.
10. `py-ai-datastream` protocol version unverified (§1) — prefer the hand-rolled emitter.

Repo files referenced: `/home/augusto/projects/learny/frontend/app/api/[...path]/route.ts`, `/home/augusto/projects/learny/frontend/app/lib/proxy.ts`.
