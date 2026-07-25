# RFC-006: Reading-First UX Overhaul

- **Status**: Draft — proposed 2026-07-24; supersedes RFC-005's window (RFC-005 paused, see Background)
- **Date**: 2026-07-24
- **Driver**: Augusto
- **Approvers**: Augusto
- **Contributors**: Claude
- **Impact**: HIGH — reworks the app's information architecture, retires two routes, changes a shipped schema, and supersedes AD-147
- **Due Date**: cycle-by-cycle; no calendar deadline
- **Resources**: [study-activity artifact (approved)](https://claude.ai/code/artifact/fdd15c70-a49f-45b7-9e5d-f65d48e238dd), [book-workspace artifact](https://claude.ai/code/artifact/da516edf-6d86-46d8-a4c6-62282ffe34a9), [RFC-005](0005-evidence-gated-hardening-roadmap.md), [RFC-004](0004-student-experience-roadmap.md)

## Background

**Current state.** Every prior roadmap is shipped or in flight: the MVP, RFC-002 (v0.2.0), RFC-003 (v0.3.0), RFC-004's six student-experience cycles (dogfood window open since 2026-07-21), and RFC-005's Cycle A (PR #47). The app works end to end — but the RFC-004 dogfood window did exactly what it was designed to do: on 2026-07-24 the author walked the running product as a student and produced thirteen concrete UX findings in one session. They are recorded in this RFC's Relevant Data section.

**Problem.** The findings cluster into three structural defects, not thirteen cosmetic ones:

1. **The app is organized around features, not around reading.** Five doors (`/read`, `/ask`, `/teach`, `/notes`, `/review`) where the student wants one. From inside the book — the only screen that matters mid-study — none of the other four are reachable.
2. **Two foundations are missing, and their absence leaks everywhere.** There is no *page unit* (EPUB reflows; nothing plays Kindle's locations role), so the reader has no pagination, the progress percentage jumps in saves rather than tracking scroll, and the study heatmap has no meaningful volume figure. And there is no *unified conversation model*: Ask is stateless and unpersisted, Teach is persisted but unmanageable, the two split what is one product idea (a grounded conversation about a book, scoped and moded) across two tables' worth of divergent behavior — while `teaching_turns` already stores exactly the shape both need.
3. **Nothing measures the app itself.** Perceived slowness has no diagnosis path: netdata (ADR-0024) watches the host and containers, but no instrument answers "which endpoint took four seconds and why".

**Why now.** The dogfood window is the evidence-producing mechanism RFC-004 promised, and it has produced evidence three weeks early. Deferring these findings to a post-retrospective RFC — the original plan — means dogfooding a UI already known to be wrong for another ten days, and letting the ~08-04 retrospective re-litigate findings that are already specific, verified against the code, and in two cases already designed and approved.

**What happens if we don't decide:** the reader stays a dead end and dogfooding keeps measuring friction we already understand; the heatmap fix (approved) sits parked; Q&A conversations keep evaporating on every reload; and any performance work stays guesswork.

### The RFC-005 pause

RFC-005 (evidence-gated hardening) remains sound but loses the window: **it is paused after Cycle A, by explicit driver decision (2026-07-24)**. Its Cycles B–F (Opus judge recalibration + ADR-0028, generation de-noise, eval dashboard, worker liveness, spoiler-safe retrieval) stay queued and unmodified — nothing in this RFC touches the eval stack, the workers, or retrieval ranking, so RFC-005's cycles resume unchanged when this RFC completes or pauses in turn. The pause is recorded in RFC-005's status line. ADR-0028 stays reserved for the decline-faithfulness convention.

One deliberate collision is accepted: RFC-005 Cycle E (worker liveness) was "pullable forward if worker pain bites." That escape hatch survives this pause — if workers stall during RFC-006 work, Cycle E may be pulled in between any two RFC-006 cycles.

## Assumptions

| # | Assumption | Confidence | Invalidation Trigger |
|---|------------|------------|----------------------|
| 1 | The per-section `word_count` already stored on corpus records (and used by `percent_at`) is a sound basis for a derived page unit — no re-ingestion needed for existing books | High — verified in `entities.py`; the same data already drives the whole-book percent | A book whose sections lack word counts, or a decision to require print-fidelity page numbers |
| 2 | `teaching_turns` + `teaching_turn_citations` generalize to all grounded conversations; unification is a migration (nullable/list scope + mode column), not a rewrite | High — schema read confirms the turn shape is already generic; only the session's three NOT NULL target columns block it | A requirement that Ask and Teach diverge in turn shape (e.g., teaching-only artifacts per turn) |
| 3 | Retrieval already supports multi-anchor scoping via `anchors` + `expand_anchors` (AD-085); chapter-scoped chat needs no retrieval-engine work | High — port and repository read confirms it; one caller passes one anchor today | Performance of large multi-anchor scopes proves unacceptable |
| 4 | The dogfood window tolerates shipping reader-surface changes mid-window — i.e., RFC-005's "don't touch surfaces the author studies on" rule is knowingly waived by this RFC | Medium — the author is the approver and is choosing this; but it does mean the ~08-04 retrospective measures a moving target | The retrospective becomes uninterpretable; if so, extend the window after Cycle D ships |
| 5 | The author remains the only user; no migration compatibility for third parties is owed beyond redirects for retired routes | High | Any external user before the workspace ships |
| 6 | Provider decisions hold: Anthropic generation (ADR-0020), OpenAI embeddings (ADR-0019). Cycle E's thinking/effort work is request-parameter tuning through the existing adapter, not a provider change | High | A provider-SDK change proves necessary |

## Decision Criteria

Stated before options. The chosen roadmap shape must:

| Priority | Criterion | Description | Weight |
|----------|-----------|-------------|--------|
| 1 | **Foundations before facades** | The page unit and the conversation model are built once, before the surfaces that consume them — no UI built twice | Must-have |
| 2 | **Honest measurement before optimization** | No performance work, and no claimed latency win, without app-level instrumentation first | Must-have |
| 3 | **Schema changes ride behind an ADR** | Retiring endpoints, superseding AD-147, and altering `teaching_sessions` require an accepted ADR before the implementing cycle | Must-have |
| 4 | **Reviewable cycles** | Each cycle is one shippable PR-sized unit in the established ship-cycle flow; no cycle mixes a schema migration with an IA rework | High |
| 5 | **Early visible value** | The author is dogfooding; at least one early cycle must land a user-visible improvement | High |
| 6 | **RFC-005 resumability** | Nothing here may touch the eval stack, worker mechanics, or retrieval ranking, so RFC-005 resumes without rebasing its plans | High |
| 7 | **Gamification cap intact** | I-4 (server-verbatim adherence) and I-7 (silent grace) survive every touched surface; no streaks, badges, warnings | Must-have |

## Relevant Data

The thirteen findings from the 2026-07-24 dogfood session, verified against the code:

| # | Finding | Verified root cause |
|---|---------|---------------------|
| 1 | Study heatmap scattered across the card | `grid-flow-col` with no column track in `study-heatmap.tsx`; implicit `auto` columns stretch. **Redesign approved** (artifact above): GitHub-style axis/key/tooltips, monkeytype-style mono figures |
| 2 | No feedback between click and render ("Resume" looks frozen) | No navigation-pending state anywhere in the frontend |
| 3 | Reader: no paragraph rhythm, no page separation, prose slides under sticky header | Presentation only; corpus preserves structure |
| 4 | Reading % jumps on save instead of tracking scroll | Percent is computed server-side per saved position; client never interpolates |
| 5 | No page unit exists | EPUB reflows; define 1 page ≈ 275 words from stored per-section `word_count` (Kindle-locations approach); PDFs can later prefer Docling's real page spans |
| 6 | Notes creatable without any reading context | Three creation paths; `notes-screen.tsx` title-only creation is rootless |
| 7 | Teaching sessions persisted but unmanageable | Only a per-source list endpoint; no global list, rename, delete, or route |
| 8 | Q&A conversations not persisted at all | `ask-panel.tsx` holds turns in `useChat` client state; no table |
| 9 | Ask: dead air before first token; no visible reasoning | Retrieval runs eagerly before the stream opens; `claude-sonnet-5` with `thinking` omitted runs adaptive thinking with `display` defaulting to omitted — empty thinking blocks stream while the UI shows nothing; `generation_max_tokens=1024` caps thinking+answer together; `effort` never set (defaults `high`) |
| 10 | Citations: numbered chips + full-height quote overlay | Popover covers the reading column; unnatural against the answer |
| 11 | Too many doors; the book screen should hold everything | Reader already has an Ask/Teach dock (`reader-panel.tsx`); `/ask` and `/teach` duplicate it without the book; notes/review unreachable from the reader. **Workspace design drafted** (artifact above) |
| 12 | "Include my notes" unclear | Label doesn't convey retrieval scope; defaults silently differ per surface (AD-147: Ask on, Teach off) |
| 13 | App feels slow; no way to know why | netdata is host/container-level only; no per-request timings, slow-query capture, or task durations |

Additional finding from the Ask/Teach analysis: the two surfaces are two points in a two-axis space (scope × mode) that the retrieval layer already supports; the schema alone forbids expressing the rest of the space.

## Options Considered

### Option 1: Five cycles, foundations-first, RFC-005 paused ⭐ (Recommended; chosen by driver 2026-07-24)

**Description.** Pause RFC-005 after its shipped Cycle A. Run five cycles ordered by dependency: instrument, page unit, conversation model (behind ADR-0029), workspace, answer experience.

**How it works.** See Proposed Roadmap below.

**Pros:**
- Satisfies all three Must-haves by construction: measurement first, foundations before surfaces, ADR before the schema cycle.
- `study-heatmap.tsx` and the dock are each touched exactly once.
- The dock (Cycle D) is built against the final conversation model, not against a split it would then have to unlearn.
- One roadmap active at a time; review context and git history stay coherent.

**Cons:**
- The workspace — the change the author most wants to see — lands fourth.
- The conversation-model cycle (C) is the riskiest and is invisible to the user when it ships.
- RFC-005's judge recalibration, already twice-deferred, is deferred again.

**Estimated cost**: LARGE overall — five ship-cycles (A: S, B: M, C: M, D: L, E: M). Risk: MEDIUM, concentrated in Cycle C's migration.

### Option 2: Workspace-first (D before C)

**Description.** Ship the visible IA rework immediately after the page unit; unify conversations afterwards.

**Pros:**
- The most-wanted change lands second instead of fourth; morale and dogfood value arrive early.

**Cons:**
- The dock ships built against the Ask/Teach split, then gets reworked when scope+mode lands — the most complex panel in the app built twice, violating criterion 1.
- The conversation list, rename, and delete UI would target endpoints scheduled for retirement.

**Estimated cost**: LARGE, plus the rework tax. Risk: MEDIUM-HIGH. **Rejected by driver 2026-07-24** in favor of Option 1.

### Option 3: Finish RFC-005 first, queue this as RFC-007

**Description.** Complete RFC-005 Cycles B–F, hold these findings for the post-retrospective RFC that RFC-005 itself anticipated.

**Pros:**
- Honors RFC-005's original sequencing and its "don't touch dogfood surfaces mid-window" rule (Assumption 4 wouldn't be needed).
- The judge recalibration debt stops compounding.

**Cons:**
- Five more cycles of dogfooding a UI already diagnosed as structurally wrong — the window keeps measuring known friction instead of new signal.
- The approved heatmap design and the drafted workspace design go stale.

**Estimated cost**: defers, doesn't reduce. Risk: LOW technically, HIGH on evidence value. **Rejected by driver 2026-07-24** — the pause was chosen explicitly.

### Option 4: Do nothing (fold findings into the ~08-04 retrospective)

**Pros:** zero disruption; the retrospective was always meant to collect UX evidence.

**Cons:** the evidence already exists at code-level specificity; re-deriving it in ten days adds latency and loses the two designs already approved/drafted. The thirteen findings would compete for attention with whatever new signal the remaining window produces.

**Estimated cost**: SMALL upfront, LARGE in wasted window time.

## Options Comparison

| Criterion | Opt 1 (chosen) | Opt 2 | Opt 3 | Opt 4 |
|---|---|---|---|---|
| Foundations before facades | ✅ | ❌ (dock built twice) | ✅ (later) | — |
| Measurement before optimization | ✅ | ✅ | ❌ (deferred) | ❌ |
| ADR before schema change | ✅ | ✅ | ✅ | — |
| Early visible value | Partial (B is cycle 2) | ✅ | ❌ | ❌ |
| RFC-005 resumability | ✅ | ✅ | n/a | ✅ |
| Author preference (2026-07-24) | **Chosen** | Declined | Declined | Declined |

## Proposed Roadmap

Ordering rationale: A is independent and gates every performance claim. B is the highest visible-value-per-effort cycle and unblocks three downstream consumers of the page unit. ADR-0029 then C build the conversation model before any UI consumes it (driver's explicit call: C before D). D assembles the workspace against the finished model. E lands last because its latency claims need A's instrument and its UI lives in D's container.

### Cycle A — Instrument (S) — *finding 13*

- App-level observability for development first, prod-safe by construction: per-request server timings (middleware; slowest endpoints ranked), SQLAlchemy slow-query capture with statement + duration, Celery task durations, and a `Server-Timing` header so the browser's own devtools show the split.
- Surface: a dev-only page or structured log view — the Laravel-Pulse role, sized to a single-user app. No SaaS, consistent with ADR-0024's self-hosted stance.
- Explicitly out: any optimization. This cycle produces the ruler; later cycles cite it.
- Depends on: nothing. Unblocks: every performance claim in D/E and the "why is it slow" diagnosis.

### Cycle B — The page unit and its surfaces (M) — *findings 1, 3, 4, 5*

- **Define the unit**: 1 page ≈ 275 words, derived from the per-section `word_count` already stored (same basis as `percent_at`) — retroactive to every ingested book, no re-processing. PDFs may later prefer Docling's true page spans; out of scope here.
- **Reader typography**: paragraph rhythm, page-rule separators at the unit boundary, sticky-header clipping fixed, per the approved workspace artifact's reading column.
- **Live progress**: the visible percentage interpolates client-side from scroll position over the chapter's word span (display format unchanged); the server-computed percent on save remains authoritative (I-4-style: client interpolation is presentation, never persisted).
- **Study heatmap**: implement the approved artifact — fixed column tracks, month/weekday axis, Less→More key, tooltips, mono figures. The readout ships "Studied N of the last 14 days" + reviews total; the **pages figure ships only if** a per-day pages-read counter lands in this cycle (a small `study_days` extension fed by position saves reporting words advanced), else it is deferred to a follow-up task — the sentence's `textContent` stays byte-identical and I-7 silent grace holds either way.
- Depends on: nothing. Unblocks: page-range conversation scopes (future), pages figure.

### ADR-0029 — Unified grounded conversations (precedes Cycle C)

- One conversation model per source: **scope** (empty = whole book; else a list of section anchors, chapter subtrees expanded via `expand_anchors`/AD-085) × **mode** per turn (answer | teach). Supersedes AD-147's per-surface notes defaults with one explicit per-conversation choice.
- Records: the migration shape (`teaching_sessions` → `conversations` with nullable/list scope; mode on the turn), the scope-is-a-promise rule (a scoped conversation must answer "not found in your selection" and offer to widen — never silently search the whole book), the teaching-anchor invariant (teach-mode turns still require a resolvable anchor), endpoint retirement + redirect plan, and the single rate-limit policy.
- Page-range scoping is explicitly deferred until the page unit has a stable mapping to sections (rounds outward to whole sections; UI must show the resolved scope).

### Cycle C — The conversation model (M) — *findings 7, 8; enables chapter-scoped chat*

- Implement ADR-0029 backend-first: migration, unified endpoints (list/rename/delete/start/turn/stream), Q&A turns persisted from the first release, scope enforcement in retrieval calls, `not_found_in_scope` distinguished from `not_found_in_source`.
- Existing Ask/Teach panels keep working against compatibility endpoints for the duration of the cycle — no UI churn; the review is about data modeling alone.
- Depends on: ADR-0029 accepted. Unblocks: D's dock tabs and conversation management UI.

### Cycle D — The workspace (L) — *findings 6, 11, 12; consumes B and C*

- The reader becomes the hub per the book-workspace artifact: contents rail (with chapter-scope selection), reading column, four-tab dock (Ask/chat with scope picker · Teach · Notes · Review), topbar with live progress.
- Routes: `/sources/[id]/ask` and `/sources/[id]/teach` become redirects into the reader with the dock open; `/notes` and `/review` re-scope to cross-book surfaces; per-book filters added where missing (notes by source, due cards by source).
- Notes provenance: title-only creation retired; notes are created from a passage selection or from saving an answer (both carry anchors). The Q&A save-to-note path survives — it is anchored, resolving finding 6's open question in favor of "anchored, not strictly reader-only".
- Copy: "Include my notes" → "Search my notes too" with an explanatory tooltip; one explicit default per conversation (per ADR-0029).
- Depends on: B (reading column), C (conversation endpoints). This is the largest cycle; if it needs splitting at spec time, the seam is "dock + redirects" / "notes & review re-scoping".

### Cycle E — The answer experience (M) — *findings 2, 9, 10*

- **Generation config** (through the existing adapter, ADR-0020 intact): explicit `thinking` with summarized display, `max_tokens` raised to fit thinking + answer, `effort` set deliberately — values chosen against Cycle A measurements, not guessed.
- **Visible states**: retrieval phase surfaced ("Searching the book…" — requires emitting a status event before eager retrieval), thinking phase with collapsible streamed reasoning, then token streaming; per the workspace artifact's Ask demo.
- **Citations**: inline numbered marks; passage opens in flow beneath the answer, clamped, with "Show in book" jumping the reading column — no full-height overlay.
- **Loading pattern app-wide**: navigation-pending feedback (route transitions, resume buttons) using one shared pattern.
- Depends on: A (to prove the latency change), D (the container it renders in).

## Exclusions (bind for the life of this RFC)

- No provider SDK changes (ADR-0019/0020 hold; Cycle E is request parameters only).
- No RAG/orchestration framework (ADR-0009 holds).
- No gamification: I-4 and I-7 bind every touched surface.
- No multi-tenant or sharing features.
- No eval-stack, worker-mechanics, or retrieval-ranking changes — that ground belongs to the paused RFC-005.
- Page-range conversation scoping and PDF true-page preference: deferred, noted in ADR-0029.

## Action Items

| Action | Owner | Status |
|--------|-------|--------|
| Record the pause in RFC-005's status line | Claude | DONE (this change set) |
| Accept or amend this RFC | Augusto | NOT STARTED |
| Run Cycle A via `learny-ship-cycle` | Augusto + Claude | DONE — cycle `v6-instrument` built on `feat/app-instrumentation`; ROADMAP has the v6 section |
| Run Cycle B (heatmap artifact is the accepted spec) | Augusto + Claude | DONE — cycle `v6-page-unit`, PR #51 |
| Draft ADR-0029 for acceptance before Cycle C | Claude | NOT STARTED |
| Cycles C, D, E in order | Augusto + Claude | NOT STARTED |
| Decide RFC-005 resumption point after Cycle E (or earlier if this RFC pauses) | Augusto | NOT STARTED |

## Open Questions

1. **Does the ~08-04 retrospective still run?** Recommendation: yes, but reframed — it closes RFC-004 and evaluates the *remaining* findings plus whatever B–D shipped by then, rather than gating this RFC (which is evidence-driven by the same dogfooding it would gate on). The moving-target caveat (Assumption 4) should be recorded in the retrospective itself.
2. **Cycle D size.** L is at the top of the ship-cycle comfort range; the split seam is pre-identified. Decide at spec time, not now.
3. **Conversation naming.** "Ask" and "Teach" become reply modes, not destinations; final labels are a Cycle D spec decision.

## Outcome

**Decision**: _pending — sequencing decisions (Option 1; C before D; RFC-005 paused) made by the driver on 2026-07-24; formal acceptance of the full RFC to follow review._

**Decision Date**: —

**Decided By**: —

**Rationale**: —
