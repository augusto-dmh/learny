# RFC-004: Student-Experience Roadmap — Reading-First Learny

- **Status**: Proposed (2026-07-18; scope locked in the 2026-07-18 planning session, identity decided by [ADR-027](../adr/0027-iron-gall-visual-identity.md))
- **Date**: 2026-07-18
- **Driver**: Augusto
- **Approvers**: Augusto
- **Contributors**: Claude
- **Impact**: HIGH

## Background

The study loop works end to end, but the app is tool-shaped, not study-shaped. Five sibling pages (library, read, ask, teach, review) hang off a card list; citations render as raw retrieval snippets; the reader shows one section per click in 14px UI sans with no position, no progress, and no way to resume; nothing answers "what do I do when I open this app today?". The v3 flagship shipped a notes domain (ADR-026, notes foundation merged as PR #31) whose capture surfaces don't exist yet — there is no way to make a highlight while reading. For the one real user, studying still happens more comfortably in the physical book plus Anki than in Learny. That is the product failing its own thesis.

A five-report research fleet plus synthesis (`docs/research/2026-07-18/student-experience/`) surveyed how the strongest reading, study, and spaced-repetition products solve this, and an interactive prototype rendered four candidate visual identities against a real chapter of the user's own corpus. This RFC converts that research into a build roadmap.

## Locked product decisions (2026-07-18 planning session)

1. **The student is the author** — a self-studying lifelong learner reading whole books, including Portuguese-language corpora; the Readwise/RemNote lifelong-learner audience is the growth direction. Explicitly out: classroom/exam features, native mobile apps.
2. **Reading-first organizing principle.** The reader is the center of gravity; citations resolve to passages opened in the reader, never snippet cards.
3. **Full IA restructure**: **Home** (resume reading + due today) / **Reader** (Ask, Teach, highlight→note, card creation as inline modes) / **Review** (FSRS queue). Library demotes to a bookshelf; the standalone Ask and Teach pages are removed.
4. **Identity**: Iron Gall as the one app identity, with a Paper reading appearance scoped to the reader surface ([ADR-027](../adr/0027-iron-gall-visual-identity.md); direction specs in rq05).
5. **Boundary**: frontend leads; the backend may add only student-workflow-shaped state (reading position, per-book progress, highlight capture on the shipped notes domain). Frozen: providers (ADR-0019/0020), retrieval architecture (ADR-0006), infrastructure. Desktop-web first but responsive; single-user; gamification capped at progress + streaks in a calm register; the public landing page gets a minimal face-lift only.
6. **Success gate — dogfood**: the RFC closes when the author studies daily in Learny for 14 consecutive days (resume reading → ask/capture → review due cards). Every missed day's reason is backlog. Per-cycle verification includes a web-interface-guidelines audit of each redesigned surface.

## The redesign in one paragraph

A study session becomes one continuous surface: Home shows where you left off and what's due; the Reader renders whole chapters as flowing, book-grade typography with your highlights inline; selecting text offers five verbs (Highlight · Note · Explain · Ask · Create card), all anchor-inheriting; Ask and Teach stream into a side panel whose citations open the book at the passage, highlighted, in context; accepted cards enter the FSRS queue carrying a pin back to their source sentence; and Review closes the loop each day. Every stage reuses a shipped subsystem — anchors, notes domain, hybrid retrieval, generation ports, FSRS — which is why this is an experience roadmap, not a platform one.

## Proposed roadmap

Ordering rationale (from the synthesis): the smallest taste-gated work first so everything after lands styled; the reader rebuild next because every other surface hangs off it; AI-in-reader before capture because it deletes the standalone pages the IA removes and ships the citation component RFC-003 Cycle F needs; Home late because it consumes state the reader creates; polish + the dogfood gate last. Sizes: S ≈ a few tasks, M ≈ a normal ship-cycle, L ≈ the largest cycle in this RFC.

### Cycle A — Identity foundation: tokens, fonts, reading typography (S)

- The identity choice is already made (ADR-027, via the rendered prototype); this cycle ships it: `globals.css` token rewrite for Iron Gall light + dark (WCAG-verified pairs), `--font-serif` binding (Source Serif 4, self-hosted via `next/font`), direction-independent `--highlight-*` warm marker tokens, `.prose-reading` applied to the existing reader and citation popovers, ink-line rule utilities, micro-typography discipline in corpus Markdown rendering, and the Paper appearance's token scaffolding (reader-scoped palette layer per ADR-027).
- Depends on: nothing. Unblocks: styled surfaces in every later cycle.

### Cycle B — Reader core: chapter flow, position, progress (L)

- Chapter-flow view: all sections of the current chapter as one continuous scrollable article; block/heading anchors as DOM ids; `?anchor=` scrolls within the flow with transient highlight; sticky chapter boundaries; scroll, not pagination.
- Reading typography defaults (19px serif, ~65ch, 1.6 leading, `lang` from book language); the `Aa` popover (size, spacing, Default/Paper appearance, light/dark on the two-axis model); receding chrome; TOC sidebar with position context and back-after-jump; load-path fix (no auth→section waterfall).
- Backend (sanctioned): `reading_position` per (user, source) — corpus anchor + denormalized percent, written on scroll-idle; per-chapter position and minutes-left from corpus word counts. Existing highlights render inline as anchored spans.
- The ink-line signature (rule system + progress fill) ships here, with its host surface.
- Depends on: Cycle A.

### Cycle C — Ask & Teach in the reader: panel, verbs, citations-as-passages (M)

- Kill the standalone Ask and Teach pages; port the streaming transport into a non-modal Reader side panel; old routes redirect into the reader.
- Selection popover with the five verbs, all anchor-inheriting (Create card may ship thin, completed in Cycle D). Explain = one-tap fixed prompt over the selection; Ask = panel input scoped to it.
- Citations upgrade: the popover renders the verbatim anchor-resolved passage in the reading serif with section-path locators; click = in-reader scroll-to-anchor while the answer stays in the panel; the reader never sees chunk machinery.
- Teach becomes a panel mode keeping the taught passage visible; save-answer-to-anchored-note on Ask/Teach responses; suggested prompts in the empty state; the streaming caret lands here.
- Depends on: Cycle B. **Unblocks RFC-003 Cycle F** (notes-join-retrieval needs the panel + citation-passage component; note→quiz provenance reuses the same anchor-resolution surface).

### Cycle D — Capture pipeline: cards at the highlight, margin rail, review pins (M)

- Create-card completes: the existing quiz-generation pipeline scoped to the highlighted quote, rendered as accept/edit/discard suggestion chips; accepted cards minted with stable IDs and typed provenance per ADR-026; no silent bulk generation.
- Margin rail surfacing notes and orphaned highlights (quote snapshots per ADR-026); review cards carry a pin that opens the source passage in the reader; single-key shortcuts; enforced friction budget (highlight ≤1 action, note = 1 keystroke + typing, AI card = 2 actions, jump-back = 1 click).
- Explicitly excluded: inline card syntax in notes, standalone card-authoring pages, auto-highlight on selection as default (toggle, default off), priority-queue mechanics.
- Depends on: Cycle B (shares the popover with C). Completes the review-provenance half of the RFC-003 Cycle F unblock.

### Cycle E — Home + IA rewire (M)

- Two-card Home: continue-reading hero (book, chapter, position, resume) + due-cards with a "done for today" state; below the fold, a study heatmap and adherence-framed streak ("Studied 12 of the last 14 days" — the gate metric as UI), with silent grace and a hide-stats setting.
- Backend (sanctioned): `study_days` rollup; streak computed at read time, never stored. Library becomes the bookshelf; navigation collapses to Home / Reader / Review; landing face-lift (minimal).
- Gamification hard cap (RFC-level constraint): no XP, coins, badges, popups, or notifications.
- Depends on: Cycle B (hard), C (soft); can be pulled forward if B lands early.

### Cycle F — Polish + the dogfood gate (S–M)

- Annotation/citation restyle completion, signature-system finishing passes, WCAG re-verification across both appearances, papercut sweep.
- Then the gate: 14 consecutive days of real daily study, fixing blockers in place; the retrospective writes itself from the streak log and closes the RFC.
- Depends on: all previous cycles.

## Sequencing against RFC-003

- **RFC-003 Cycle B (eval maturity)** is UI-independent and now unblocked (provider keys exist); it may interleave anywhere, in parallel with any cycle above.
- **RFC-003 Cycle F (notes loop: retrieve + reinforce)** waits for RFC-004 Cycle C (ideally D) so its user-facing surfaces are built once, inside the new reader; its backend halves may start earlier if parallel capacity exists. RFC-003 wraps (v0.3.0) when its Cycle F lands; this RFC targets v0.4.0.

## Assumptions

| Assumption | Confidence | Invalidated if |
|---|---|---|
| The chapter-flow reader performs acceptably rendering a full chapter of corpus blocks as one article | High | Very large chapters need windowing — add virtualization inside Cycle B, not a new cycle |
| The shipped anchor scheme carries selection-to-highlight capture in the flow view | High | ADR-026's reconcile cascade needs extension — reopen as an ADR amendment, not silently |
| Source Serif 4 + the Iron Gall palette hold up over weeks of real reading (chosen on a prototype) | Medium | The dogfood gate exposes fatigue — the Paper appearance is the pressure valve; a palette re-tune is a Cycle F task |
| One person's daily-study habit is a fair success gate | Medium | Life intervenes for non-product reasons — the gate measures product blockers, not attendance; the retrospective judges |

## Operating cost envelope (delta over v3)

| Item | Cost |
|---|---|
| Fonts (Source Serif 4, optional Literata) | $0 — OFL, self-hosted at build time |
| New infrastructure | none (frozen boundary) |
| Provider usage during dogfood | existing keys, normal study volume |

## Out of scope (explicit)

Native mobile apps, collaboration/classrooms, notifications and email rituals, position-scoped ("spoiler-safe") retrieval, daily digest email, new providers or retrieval components, marketing site. The last four are recorded as designed-for-but-deferred in the synthesis.

## Follow-up decision records to write when cycles start

- ADR: reading-position and study-days state model (Cycle B/E backend additions), if the implementation deviates from the shapes sketched here.
- RFC-003 Cycle F scope confirmation against the shipped reader surfaces (short amendment note, not a new RFC).

## Outcome

_To be filled at acceptance and again at the gate retrospective._
