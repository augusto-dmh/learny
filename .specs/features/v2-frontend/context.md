# v2-frontend — Context & Decisions (RFC-002 Cycle D)

Gray areas resolved via the ship-cycle auto-decision protocol (options formulated with
why-recommend AND why-not; recommended option chosen; auditable here + STATE.md AD rows).
Escalation rule checked for each: none changes product direction beyond the cycle, none
locks an undecided provider (RFC-002 already names the Vercel AI SDK stack for Cycle D
and the research doc carries the trade-off analysis), and every decision has a clear
defensible recommendation — so no user prompt was required.

## D-1 — Rebuild scope: replace the UI layer, keep the transport layer (→ AD-065)

- **Chosen:** Rebuild pages/components/global styles on Tailwind v4 + shadcn/ui + AI
  Elements (vendored source via CLI). Keep `app/lib/*` fetch clients, the proxy, and
  their 13 test files — extend them (ingestion client, streaming transport config)
  rather than rewrite. Restores AD-010's full vertical slice after 5 backend-only
  cycles (AD-064).
- **Why:** the UI layer is unstyled semantic HTML with zero CSS — a true greenfield;
  the transport layer is tested, convention-bearing, and provider-free. Replacing only
  what F6 indicts minimizes churn and keeps the test suite as a regression net.
- **Why not full rewrite (incl. clients/proxy):** rewrites working, tested code for no
  behavioral gain; loses the fetchImpl-injection test convention.
- **Why not additive styling of existing panels:** leaves F6's navigation dead-ends,
  no streaming, no reader — fails the cycle's purpose.

## D-2 — Streaming client: AI SDK `useChat` + `DefaultChatTransport` (→ AD-066)

- **Chosen:** `ai` + `@ai-sdk/react` (current published major, verified at install;
  research 2026-07-12: v7), `useChat` with `DefaultChatTransport` pointed at the
  same-origin proxy stream routes; `prepareSendMessagesRequest` reshapes the payload to
  Learny's contracts (`{question}` / `{message}` — latest message only, never AI-SDK
  message history) and injects `X-CSRF-Token`. Transport config isolated in one module
  (`app/lib/streaming.ts`) mirroring how `ui_message_stream.py` isolates the protocol
  server-side.
- **Why:** the backend already emits UI Message Stream v1 with the
  `x-vercel-ai-ui-message-stream: v1` header (Cycle C, AD-061) — this is the designed
  consumer. useChat provides message state, streaming assembly, abort/status, and
  unlocks AI Elements (`Conversation`, `Response`, `InlineCitation`, `Sources`,
  `PromptInput`).
- **Why not a hand-rolled SSE hook:** reimplements message state, optimistic messages,
  abort, streaming-markdown flushing; forfeits AI Elements; protocol coupling is the
  same either way (the wire format is already v1) but with none of the payoff.

## D-3 — Section read model: new `GET /api/sources/{id}/section?anchor=` (→ AD-067)

- **Chosen:** one new owner-scoped backend read endpoint returning
  `{anchor, title, section_path, markdown}` for a single section resolved by its stable
  anchor; 200 on hit, 404 for missing/non-owner/no-corpus/unknown-anchor (mirrors the
  structure endpoint's semantics, no disclosure). Anchor rides as a **query param**
  because its format is `href[#fragment]` (slashes + hash — hostile as a path param).
- **Why:** section markdown is already stored (`corpus_sections.markdown`, AD-018) but
  deliberately excluded from the TOC read model to keep it O(TOC); a per-section
  endpoint is the minimal read model that makes citations navigable — the stated point
  of the structured corpus.
- **Why not markdown-in-structure:** makes the TOC read O(book size) — explicitly
  avoided in the existing repo comment.
- **Why not snippet-only popovers (no reader):** leaves citations decorative and drops
  the RFC's SectionReader deliverable.

## D-4 — Reader route + anchor highlighting (→ AD-068)

- **Chosen:** `/sources/[id]/read?anchor=<encoded>` client page: fetches the section,
  renders its markdown, scrolls the section heading into view (`scroll-mt` under the
  sticky header) with a transient highlight. Citation popovers' "Open in book" links
  here. Without an `anchor` param the page shows a pick-a-section empty state (the
  sidebar tree is the entry). Highlight granularity is the **section** — chunk anchors
  are section anchors in the corpus model.
- **Why:** matches the citation payload exactly (`EvidenceView.anchor`), needs no new
  identifiers, keeps the URL shareable/deep-linkable.
- **Why not snippet-text highlighting inside the section:** snippet text is derived
  from chunk text and may not survive markdown rendering verbatim; best-effort string
  matching is fragile — deferred (out of scope).
- **Why not a full-book scrolling reader:** O(book) payloads and virtualization work
  with no cycle payoff.

## D-5 — App shell: shadcn Sidebar + header, next-themes dark mode (→ AD-069)

- **Chosen:** shadcn `Sidebar` (composable, collapsible) hosting the library (all
  sources w/ status badges) and a per-book collapsible section tree (ready sources,
  from the existing structure endpoint, `Collapsible` primitives — no tree lib);
  header with user email, account link, logout, and a theme toggle; `next-themes`
  class-strategy dark mode, system default; login/register render outside the shell.
- **Why:** the official composable sidebar is the research-recommended shell; the
  book tree is the F6 navigation fix; next-themes is the shadcn-documented dark-mode
  path.
- **Why not top-nav only:** no home for the book tree — navigation dead-ends persist.
- **Why not a custom sidebar or a tree library:** rebuilds/duplicates maintained
  primitives; TOC depth ≤4 needs no virtualization.

## D-6 — Ingestion progress: fixed-interval polling (→ AD-070)

- **Chosen:** new frontend client for the existing `GET /api/sources/{id}/ingestion`;
  the library polls each `processing` source every 3 s, updates the badge in place,
  stops on terminal status (`ready`/`failed`) and on unmount; failed sources surface
  the latest event message + the existing restart control.
- **Why:** the backend endpoint already exists unconsumed; fixed 3 s at author scale
  is trivially cheap and F6 names polling explicitly.
- **Why not SSE/WebSocket push:** new backend surface out of the cycle's scope.
- **Why not exponential backoff:** complexity without a load problem to solve.

## D-7 — Test strategy: keep vitest conventions, no new test infra (→ AD-071)

- **Chosen:** keep the two existing conventions — node-env client tests with injected
  `fetchImpl`, jsdom component tests with `routedFetch` fetch-stub maps. Streaming
  component tests feed `ReadableStream` SSE fixtures (UI Message Stream v1 chunks)
  through the stubbed fetch. Vendored shadcn/AI Elements source is exercised through
  our compositions, not unit-tested itself. New backend endpoint gets pytest coverage
  matching existing web-layer tests. Gates unchanged: vitest run, `tsc --noEmit`,
  `next build` (frontend); pytest + ruff (backend).
- **Why:** 13 test files already encode these conventions; SSE fixtures through a
  stubbed fetch exercise the real transport + parsing path deterministically.
- **Why not MSW:** new dependency duplicating a working pattern.
- **Why not Playwright/E2E:** out of scope; CI compose-smoke already boots the stack.

## D-8 — Execution: one worker per phase (ship-cycle protocol)

- **Chosen:** tlc sub-agent offer auto-accepted per the ship-cycle autonomy contract
  (>3 phases → one Opus worker per phase; Verifier always Opus). Recorded here since
  tlc's default is offer-then-confirm.

## Deviations

- **Phase A (accepted):** React exact-pinned 19.1.1→19.1.2 (peer requirement of `@ai-sdk/react@4.0.33`). shadcn init is preset-based now (`-t next -b radix -p nova --css-variables`, style `radix-nova`); init added `hooks/use-mobile.ts` + runtime deps `shadcn`/`tw-animate-css` (globals.css imports `shadcn/tailwind.css` + `tw-animate-css`). AI Elements registry reorg: **no standalone `Response`/`Loader`** — markdown renderer is `MessageResponse` (memoized `Streamdown`) in `components/ai-elements/message.tsx`; loading indicators are `Spinner` (`components/ui/spinner.tsx`) / `Shimmer` (`components/ai-elements/shimmer.tsx`). Design references to `Response`/`Loader` map to these. Umbrella CLI installs all components; pruned to the import closure of the 6 needed entries (6 ai-elements files + 21 ui files), 8 unused heavy deps removed. Fonts: Geist via `geist` package bound to `--font-sans` in `app/layout.tsx`.
- **Phase B (accepted):** (1) `SectionContent` domain entity added to `app/domain/entities.py` (+ fake in `tests/fakes.py`) — repo port needed a return type; keeps the CorpusRepository fake faithful. (2) `lib/ingestion.ts` re-exports the existing faithful `IngestionSummary` type from `lib/sources.ts` instead of design.md's illustrative narrower `IngestionView` — mirrors the real backend payload, avoids type drift. (3) `get_section` orders by `position` + LIMIT 1 so duplicate anchors resolve to the first section in reading order (matches `teaching.py` target-anchor resolution; anchor has no unique constraint).
- **Phase A (contract confirmation):** `DefaultChatTransport.prepareSendMessagesRequest` confirmed in `ai@7.0.30` types — receives `{id, messages, body, headers, api, trigger, ...}`, returns `{body, headers?, credentials?, api?}` (sync or promise). Phase D reads latest user text from `messages` and returns `{body: {question|message}, headers: {"X-CSRF-Token": csrf}}`.
