# v4-reader-apparatus — Decision Context

Auto-decided per the learny-ship-cycle autonomy contract (recommended option chosen, options recorded for audit). None met the escalation rule: no product-direction change beyond the cycle (the IA move itself is locked in accepted RFC-004), no new provider/dependency, and every decision has a defensible recommendation.

## D-1 — Panel state representation → URL query (AD-129)

- **(a) `?panel=ask|teach` query on the read route — CHOSEN.** Why: deep-linkable, old-route redirects map 1:1, browser back works, survives citation-driven chapter navigation by param preservation. Why not: URL churn on toggle (mitigated: shallow `router.replace`, no refetch).
- (b) Component state only. Why: simplest. Why not: redirects from the killed routes couldn't open the panel; not shareable; lost on navigation.
- (c) Next.js parallel/intercepting routes. Why: framework-native slots. Why not: route-group churn, materially harder to test, overkill for one panel.

## D-2 — Old-route redirects → server `redirect()` in page files (AD-129)

- **(a) `redirect()` from `next/navigation` in `ask/page.tsx` + `teach/page.tsx` — CHOSEN.** Why: keeps dynamic `[id]`, colocated with the app dir, trivially testable as components, no config coupling. Why not: two tiny files survive as tombstones (acceptable; they document the IA move).
- (b) `next.config.ts` `redirects()`. Why: declarative, cached 308s. Why not: config-level coupling; not exercised by the vitest suite; splits routing truth across two layers.
- (c) `middleware.ts`. Why not: introduces a middleware layer this app deliberately doesn't have.

## D-3 — Citation passage source → stored snippet, restyled (AD-130)

- **(a) Render the citation's stored `snippet` as the passage (it IS verbatim corpus chunk text), in `.prose-reading`, with `section_path` locators; never render `chunk_id`/`score` — CHOSEN.** Why: zero popover-open network dependency, zero backend change, the text is verbatim book text already; "no chunk machinery" is satisfied by not exposing ids/scores/diagnostics. Why not: after re-ingestion an old teaching turn's snippet snapshot may drift from the current book text — accepted, it's the status-quo semantics for stored turns.
- (b) Lazy `GET /section?anchor=` on popover open + client-side passage location. Why: always-current text, true "anchor-resolved". Why not: popover-open latency + failure states; sections can be thousands of words so a slicing heuristic is needed anyway; the heuristic would locate… the snippet text, adding a round-trip to reproduce what we hold.
- (c) New backend passage field on `EvidenceView`. Why not: backend addition in a frontend-boundary cycle; duplicates data already in the payload.

## D-4 — Citation jump → same-chapter scroll, else navigate preserving panel (AD-130)

- **(a) If anchor ∈ loaded chapter's section anchors → in-place `scrollIntoView` + flash; else `router.push` `?anchor=…&panel=…` (panel params preserved) — CHOSEN.** Why: reuses the reader's existing scroll/flash machinery; the server resolves alias anchors on the navigation path; panel survives. Why not: alias anchors of the *current* chapter fall through to a navigation that reloads the same chapter — harmless, server-resolved, rare.
- (b) Always navigate. Why not: needless chapter refetch + scroll jank for the common same-chapter case.
- (c) Client-side alias table. Why not: leaks corpus machinery into the client; the server already owns alias resolution.

## D-5 — Create card verb → visible but disabled (AD-131)

- **(a) Disabled with "coming soon" hint — CHOSEN.** Why: ships the RFC's five-verb popover contract now ("may ship thin"), no fake behavior, next cycle fills it in place. Why not: disabled controls are mild UX debt for one cycle.
- (b) Omit until Cycle D. Why: cleaner today. Why not: popover shape/tests churn again next cycle; RFC names five verbs for this cycle.
- (c) Wire to whole-source deck generation. Why not: misleading — generates cards for the book, not the selection; that scoping is exactly Cycle D's job.

## D-6 — Explain/Ask selection scoping → prompt-level quote embedding (AD-131)

- **(a) Embed the verbatim selection quote in the submitted question text (fixed template for Explain; quoted-context block for Ask) — CHOSEN.** Why: hybrid retrieval's lexical arm matches exact quotes strongly, so evidence converges on the passage; zero API/retrieval change (retrieval architecture frozen per RFC-004). Why not: less precise than true anchor-scoped retrieval on paraphrase-heavy corpora — acceptable; Cycle D/F can deepen if the dogfood gate surfaces it.
- (b) Add anchor scoping to the questions endpoint (teaching-style `expand_anchors`). Why: precise. Why not: backend behavior change in a frontend-boundary cycle; grows scope; teaching already covers the anchor-scoped tutoring case.
- (c) Route Explain through a one-turn teaching session. Why not: creates junk persisted sessions for throwaway explains.

## D-7 — Save-answer-to-anchored-note → capture reuse + plain-note fallback (AD-132)

- **(a) `POST /sources/{id}/highlights` (captureHighlight) with the first citation's anchor and `quote_exact` = first paragraph of that citation's snippet (first block's text, so the server's block binding matches); note body = answer markdown; on 409/empty-quote → `POST /api/notes` plain note with answer + jump-back link — CHOSEN.** Why: real anchored note (jump-back, reconcile lifecycle per ADR-0026) with zero backend change; the fallback makes failure non-fatal and honest. Why not: first-paragraph heuristic can miss (renormalized text) — degrades to the fallback, never data loss.
- (b) Plain note only, with a link. Why: simplest. Why not: not an *anchored* note — no reconcile lifecycle, no highlight; misses the RFC's stated outcome.
- (c) Extend `POST /api/notes` to accept anchors. Why: cleanest contract. Why not: backend addition + AnchorResolver bypass questions (offsets without resolution) in a cycle whose boundary is frontend-leads.

## D-8 — Teach entry point → panel mode switch only

- **(a) Teach reached via the panel's mode control; target picker lives in the panel (ported) — CHOSEN.** Why: the RFC's five verbs deliberately exclude Teach; parity port keeps behavior. Why not: one extra click vs a selection verb — matches the RFC.
- (b) Add Teach as a sixth selection verb. Why not: contradicts the locked verb set.

## D-9 — Suggested prompts → fixed static list

- **(a) Small fixed list (chapter-agnostic study prompts) — CHOSEN.** Why: RFC asks for "suggested prompts in the empty state", nothing more; zero machinery. Why not: not contextual — fine for a first pass.
- (b) Chapter-title-templated prompts. Why: light context. Why not: title interpolation reads awkwardly for many real chapter titles; adds prop plumbing for marginal value. Revisit at Cycle F polish.

## D-10 — Sidebar entries this cycle → deep-link into panel modes

- **(a) Ask/Teach sidebar links retarget to `/read?panel=…` — CHOSEN.** Why: nav collapse is Cycle E's scope; links must not dangle meanwhile; one-line change. Why not: sidebar keeps three entries one cycle longer — accepted.
- (b) Collapse nav now. Why not: pulls Cycle E scope forward.

## Execution decisions

- Worker-per-phase (4 phases A–D), session model for all workers (v4-B precedent); Verifier always fresh.
- Frontend-only cycle: gates = vitest + tsc + build per phase, full frontend suite at phase boundaries; backend suite once in Phase D as a no-regression check.

## Deviations

_(recorded during execution if any)_
