# v6-answer-experience Specification

RFC-006 Cycle E — "The answer experience" (findings 2, 9, 10). Last cycle of the v6 roadmap.

## Problem Statement

Asking the book a question produces dead air: retrieval runs eagerly before the SSE stream opens, the model runs adaptive thinking whose deltas are silently dropped (`display` defaults to omitted and the adapter filters to `text` events only), and `generation_max_tokens=1024` caps thinking + answer together. Citations render as numbered chips whose popover covers the reading column. Nothing in the app gives navigation-pending feedback, so "Resume" looks frozen. The user cannot tell whether the app is searching, reasoning, or stuck.

## Goals

- [x] Every conversation turn shows its phase: "Searching the book…" before retrieval, collapsible streamed reasoning while the model thinks, then token streaming.
- [x] Generation requests set `thinking` (adaptive + summarized display), `effort`, and a raised `max_tokens` deliberately, through the existing adapter — no provider SDK changes (ADR-0019/0020 hold, RFC-006 exclusion).
- [x] Citations appear as inline numbered marks; the passage opens in flow beneath the answer (clamped), with "Show in book" jumping the reading column — no full-height overlay.
- [x] One shared navigation-pending pattern applied to route transitions and navigating buttons app-wide.

## Out of Scope

| Feature | Reason |
|---|---|
| Provider SDK bump or new provider params beyond request config | RFC-006 exclusion; `anthropic 0.116.0` already supports everything needed |
| Persisting thinking/reasoning content | Transient display only (AD-215); persisted turns replay without it |
| Retrieval-ranking, eval-stack, or worker changes | Belongs to paused RFC-005 |
| Live latency measurement campaign before choosing effort | No baseline exists in repo; effort becomes a knob with documented default (AD-214) |
| Gamification of loading states | RFC-006 exclusion I-4/I-7 |
| Page-range conversation scoping | Deferred per ADR-0029 |

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|
| Effort value source | Config knob `LEARNY_GENERATION_EFFORT`, default `medium`, validated against low/medium/high/xhigh/max | RFC wanted "values chosen against Cycle A measurements"; no measured baseline exists in the repo. A knob + instrumentation lets the value be tuned from live data without a code change; `medium` is the documented cost/latency sweet spot for evidence-grounded Q&A (Sonnet 5 `medium` ≈ Sonnet 4.6 `high`) | AD-219 |
| max_tokens default | Raise `LEARNY_GENERATION_MAX_TOKENS` default 1024 → 4096 | `max_tokens` caps thinking + answer together on Sonnet 5; 1024 squeezes both. 4096 gives headroom without runaway cost; knob already exists | AD-219 |
| Thinking config | `thinking={"type": "adaptive", "display": "summarized"}` on both stream and buffered Anthropic calls | Adaptive is the only on-mode for Sonnet 5; `display` defaults to omitted (the empty-blocks dead air of finding 9). Applying to both paths keeps one request shape | AD-219 |
| Reasoning persistence | Not persisted; reasoning parts are transient stream-only UI | Persisted turns are the durable record of answers, not the model's scratchpad; avoids schema change and replay complexity | AD-220 |
| Reasoning applies to both modes | Ask and Teach both show phases/reasoning | Dock is mode-agnostic (AD-208); the unified port streams identically for both modes | AD-220 |
| Wire encoding for new phases | Vercel UI Message Stream v1 native part types (`reasoning-*` parts; a data part for the retrieval phase) | Frontend already speaks this protocol via `@ai-sdk/react`; native reasoning parts avoid inventing a parallel scheme | AD-221 |
| Local/deterministic adapter | Emits no reasoning events; frontend treats reasoning as optional | Offline tests and keyless runs stay network-free and unchanged | AD-220 |
| Navigation pending mechanism | Next.js `useLinkStatus` for links + `useTransition` for programmatic `router.push`, surfaced through one shared component | Next 15.5 App Router has no global router events; per-navigation pending state is the framework-native pattern | AD-223 |

**Open questions:** none — all resolved or logged above.

## User Stories

### P1: Visible answer phases ⭐ MVP

**User Story**: As a reader asking the book a question, I want to see what the system is doing — searching, thinking, then answering — so the wait never looks like a hang.

**Why P1**: Finding 9's core; the flagship UX of the cycle.

**Acceptance Criteria**:

1. WHEN a turn stream is requested THEN the system SHALL emit a retrieval-phase event ("searching") on the stream *before* retrieval executes, and the panel SHALL display "Searching the book…" until the next event arrives.
2. WHEN the provider streams thinking deltas THEN the backend SHALL translate them into reasoning stream parts and the panel SHALL render them in a collapsible reasoning region that streams live, collapsed-by-default once answer text begins.
3. WHEN answer text deltas begin THEN the panel SHALL stream them as today, and the reasoning region SHALL remain available (collapsed) for the completed turn until navigation away.
4. WHEN the provider emits no thinking (adaptive chose not to, or the local adapter) THEN the panel SHALL skip the reasoning region entirely — no empty shell.
5. WHEN retrieval finds no evidence THEN the phase SHALL transition from "searching" directly to the existing not-found message, with no reasoning or text phases.
6. WHEN the stream errors during any phase THEN the existing error part SHALL be emitted and the panel SHALL show the error state, replacing the phase indicator.
7. WHEN a request fails auth/ownership/validation guards THEN the endpoint SHALL still fail with the proper HTTP status before any stream bytes (guards stay eager; only retrieval moves inside the stream).
8. WHEN a persisted conversation is restored THEN turns SHALL render answer text and citations exactly as today, with no reasoning region (reasoning is not persisted).

**Independent Test**: Ask a question in the dock against the Anthropic adapter (or a fake streaming client in tests) and observe the ordered phases: searching → reasoning (collapsible) → streaming text → citations.

### P1: Deliberate generation config

**User Story**: As the product owner, I want the Anthropic request to set thinking display, effort, and max_tokens explicitly so latency and cost are chosen, not defaulted.

**Why P1**: Prerequisite for reasoning display; fixes the silent high-effort/1024-cap misconfiguration.

**Acceptance Criteria**:

1. WHEN the Anthropic adapter builds any request (stream or buffered, answer or teach mode) THEN it SHALL include `thinking={"type": "adaptive", "display": "summarized"}` and `output_config={"effort": <configured>}` alongside model and max_tokens.
2. WHEN `LEARNY_GENERATION_EFFORT` is unset THEN the effective effort SHALL be `medium`; WHEN set to a value outside {low, medium, high, xhigh, max} THEN settings validation SHALL reject it at startup.
3. WHEN `LEARNY_GENERATION_MAX_TOKENS` is unset THEN the effective value SHALL be 4096.
4. WHEN the adapter logs a generation call THEN the log SHALL include the effort value (observability of the chosen config).
5. WHEN the local/deterministic provider is selected THEN no thinking/effort parameters SHALL appear anywhere in its behavior (network-free contract unchanged).

**Independent Test**: Adapter unit tests assert the request kwargs; settings tests assert defaults and validation.

### P1: Citations in flow

**User Story**: As a reader, I want citations as inline numbered marks whose passages open beneath the answer, so I can check sources without losing my place.

**Why P1**: Finding 10; the citation experience is core to the product's cited-answer identity.

**Acceptance Criteria**:

1. WHEN an answer contains citation markers THEN the panel SHALL render them as inline numbered marks at their positions in the answer text.
2. WHEN a mark is activated THEN the cited passage SHALL open in flow beneath the answer (expanding the message, not overlaying the reading column), clamped to a bounded height, showing the snippet and its section breadcrumb.
3. WHEN "Show in book" is activated on an open passage THEN the reading column SHALL jump to the cited anchor (existing `onShowInBook` path) and the dock SHALL stay open.
4. WHEN an answer has citations but its text contains no inline markers THEN the citation list SHALL still be reachable below the answer (fallback preserves access to evidence).
5. WHEN a note-origin citation is present THEN its passage SHALL keep the "Open note" affordance.
6. WHEN a persisted turn is restored THEN inline marks and in-flow passages SHALL work identically to the live-streamed case.

**Independent Test**: Render a message with markers + citations in a component test; activate a mark; assert in-flow expansion and `onShowInBook` invocation. No full-height overlay element remains.

### P2: Navigation pending feedback

**User Story**: As a user, I want buttons and links that navigate to show a pending state immediately, so a click never looks ignored.

**Why P2**: Finding 2; independent of the dock work and shippable last.

**Acceptance Criteria**:

1. WHEN a navigation link using the shared pattern is clicked THEN a pending indicator SHALL appear within the interaction (via `useLinkStatus`) and disappear when the route renders.
2. WHEN a programmatic navigation (e.g. Resume button, TOC entry) is triggered THEN the initiating control SHALL show a pending/disabled state until the transition completes (via `useTransition`).
3. WHEN navigation is instantaneous (cached route) THEN the indicator SHALL not flash distractingly (indicator debounced or animation-delayed per `useLinkStatus` guidance).
4. The shared pattern SHALL be applied at minimum to: Home two-card actions (Pick a book / Resume / Review), library list entries, sidebar links, and TOC entries.

**Independent Test**: Component tests assert pending indicator on slow-resolving navigation; visual check via Home "Resume".

## Edge Cases

- WHEN thinking deltas arrive interleaved with the not-found sentinel hold-back THEN reasoning parts SHALL bypass `hold_back_deltas` text buffering without breaking sentinel detection (trap: the sentinel logic inspects text deltas only).
- WHEN the SSE consumer disconnects mid-thinking THEN the provider stream SHALL still close (existing `with` block contract).
- WHEN the answer consists solely of the not-found sentinel THEN no reasoning-then-retraction artifact SHALL be visible: reasoning shown during a turn that resolves to not-found collapses into the not-found state.
- WHEN citations arrive (after `text-end`) for markers already rendered THEN marks SHALL hydrate in place; markers with no matching citation index render as plain text, not broken controls.
- WHEN effort/max_tokens knobs are changed via env THEN no code path outside config/adapter needs touching.

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
|---|---|---|---|
| ANSW-01 | P1: Visible answer phases (AC1 searching event) | Execute | Verified |
| ANSW-02 | P1: Visible answer phases (AC2-4 reasoning stream + UI) | Execute | Verified |
| ANSW-03 | P1: Visible answer phases (AC5-8 not-found/error/guards/restore) | Execute | Verified |
| ANSW-04 | P1: Generation config (AC1 request params) | Execute | Verified |
| ANSW-05 | P1: Generation config (AC2-3 knobs + validation) | Execute | Verified |
| ANSW-06 | P1: Generation config (AC4-5 logging + local contract) | Execute | Verified |
| ANSW-07 | P1: Citations in flow (AC1-2 inline marks + in-flow passage) | Execute | Verified |
| ANSW-08 | P1: Citations in flow (AC3-6 show-in-book/fallback/notes/restore) | Execute | Verified |
| ANSW-09 | P2: Navigation pending (AC1-3 shared pattern) | Execute | Verified |
| ANSW-10 | P2: Navigation pending (AC4 applied surfaces) | Execute | Verified |

**Coverage:** 10 total, 10 mapped to tasks, 0 unmapped — all Verified (validation.md).

## Success Criteria

- [x] No phase of a turn ever shows a blank/frozen panel: searching, reasoning, streaming, error, and not-found all have visible states.
- [x] Adapter requests carry explicit thinking/effort/max_tokens; effort observable in logs.
- [x] Full-height citation overlay is gone; inline marks + in-flow passages pass component tests.
- [x] Home Resume shows pending feedback on click.
- [x] Gates green: backend pytest, frontend vitest, ruff, tsc, boundaries.
