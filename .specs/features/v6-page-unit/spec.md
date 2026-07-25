# Spec — `v6-page-unit` (RFC-006 Cycle B: the page unit and its surfaces)

**Source of scope:** `docs/rfc/0006-reading-first-ux-overhaul.md` § "Cycle B — The page unit and
its surfaces (M) — *findings 1, 3, 4, 5*".
**Accepted design spec:** `approved-artifact-spec.md` in this directory (both driver-approved
artifacts, extracted verbatim). Where it conflicts with RFC-006's cycle text, RFC-006 wins —
the one live conflict is flagged in that file (percent display format).

## Problem

Four dogfood findings share one missing foundation. The book has no **page**: EPUB reflows, so
the reader offers no unit a person can hold on to ("I'm on page 60"), the prose runs as an
undifferentiated column, and the progress figure moves in section-sized jumps. Separately the
Home study heatmap renders as scattered squares because its grid declares seven rows and no
column track, so implicit `auto` columns stretch to the card width.

The unit already exists in the data and has never been named: `corpus_sections.word_count` is
stored per section and already backs `percent_at`. Defining **one page ≈ 275 words** gives every
already-ingested book pages retroactively — no re-processing, no corpus migration.

## Non-goals (bind for this cycle)

- No contents rail, dock tabs, route redirects, or notes/review re-scoping — that is Cycle D.
- No conversation-model change, no ADR-0029 work — that is Cycle C.
- No generation-parameter, streaming, or citation changes — that is Cycle E.
- No PDF true-page spans from Docling (deferred by the RFC), no re-ingestion of any corpus.
- No eval-stack, worker-mechanics, or retrieval-ranking changes (RFC-006 exclusion; that ground
  belongs to the paused RFC-005).
- No gamification: I-4 and I-7 bind every surface this cycle touches.

## Invariants (must hold; each needs a sensor)

- **I-PU-1 — Retroactivity.** Page numbers derive from already-stored `word_count` alone. No
  corpus table gains a column, and no ingested book needs re-processing to show pages.
- **I-PU-2 — One source of truth for the quantum.** The words-per-page constant lives in backend
  settings and reaches the client over the wire. No client hardcodes 275.
- **I-PU-3 — Interpolation is presentation, never persistence.** The client-side live percentage
  is display-only: it is never written to the server, and the percent stored on a position save
  remains the server-computed `percent_at` value.
- **I-PU-4 — Forward-only credit.** Words credited to a study day never go negative; re-reading
  or scrolling backwards credits nothing.
- **I-PU-5 — No baseline, no claim.** The first position save for a source (no prior stored
  position) credits zero words — opening a book at 50% must not claim half the book as read today.
- **I-PU-6 — Atomic credit.** The words credit is issued on the same connection/transaction as
  the position upsert and only on the success path; a 404'd anchor stores nothing and credits
  nothing.
- **I-PU-7 — Shading formula unchanged.** Heatmap intensity stays `reviews_count +
  reading_updates`; the new words counter must not alter any cell's level.
- **I-4 (carried) — The adherence number is the server's.** `studied_last_14` is rendered
  verbatim; nothing about adherence is recomputed or stored client-side.
- **I-7 (carried) — Silent grace.** Zero-activity days stay plain empty cells: no tooltip, no
  `title`, no badge, no celebration, and no "missed / broken / lost" language anywhere.
- **I-PU-8 — The sentence is byte-identical.** `textContent` of the adherence line stays
  `Studied N of the last 14 days`, and the existing assertions in
  `frontend/tests/study-heatmap.test.tsx` that check it pass **unmodified**. Widening a fixture
  to carry a genuinely new wire field is permitted (see AD-191); weakening, retargeting, or
  deleting any assertion in that file is not.

## Requirements

### The unit (backend)

- **PAGE-01** — A words-per-page setting exists with default `275`, owned by backend settings
  alongside the other `LEARNY_*` settings, and is the only definition of the quantum.
- **PAGE-02** — The chapter read response carries the page size, so the reader derives page
  numbers without hardcoding the constant (I-PU-2).
- **PAGE-03** — Page derivation is a pure function of word counts already stored: given words
  before a point and the quantum, it yields that point's page number. It is exercised directly by
  unit tests, independent of HTTP and the DB (I-PU-1).
- **PAGE-04** — Page numbering starts at page 1 at the book's first word, and a chapter's first
  page follows from `words_before_chapter` — so the reader's first rule continues the book's
  numbering rather than restarting per chapter.

### Per-day reading volume (backend)

- **PAGE-05** — `study_days` gains a per-day words-advanced counter, added by a migration chained
  off `0015_study_days`. Existing rows take 0 without backfill; the column is `NOT NULL` with a
  server default.
- **PAGE-06** — `StudyDayRepository.record` accepts a words-advanced increment alongside the
  existing per-kind counters, and its atomic upsert increments it the same way (AD-153 pattern).
- **PAGE-07** — Saving a reading position credits `words_before(new anchor) − words_before(prior
  stored anchor)`, floored at zero (I-PU-4). Prior position absent → credit zero (I-PU-5). A
  prior anchor that no longer resolves against the current index → credit zero, and the save
  still succeeds.
- **PAGE-08** — The credit is issued on the same connection as the position upsert and only after
  the anchor resolves (I-PU-6). An unresolvable anchor raises `CorpusNotFound`, stores nothing,
  and credits nothing.
- **PAGE-09** — The study window API exposes a per-day pages figure derived server-side from the
  stored words and the PAGE-01 quantum. The raw words counter is an implementation detail of the
  rollup; the client is served pages (I-PU-2).
- **PAGE-10** — `reviews_count` and `reading_updates` keep their current meaning and increments;
  adding words changes no existing counter and no existing response field (I-PU-7).

### The reading column (frontend)

- **PAGE-11** — The reading column adopts the approved column spec: measure, paragraph rhythm,
  chapter-title treatment, and the paper surface tokens, per `approved-artifact-spec.md` §B.
- **PAGE-12** — The Aa controls stay authoritative over size and leading: the approved
  typography must express itself through the existing `--reading-size`/`--reading-leading`
  variables and the persisted reading settings, not as fixed values that override the user's
  choice.
- **PAGE-13** — A page rule renders at each ~275-word boundary within the chapter: it is placed
  **between paragraphs, never inside one**, never after the final paragraph, carries the
  remainder forward across boundaries rather than resetting, and is `aria-hidden` (it is
  scaffolding, not prose).
- **PAGE-14** — Each rule is labelled with its page number, continuing the book's numbering
  (PAGE-04), rendered in the approved mono treatment.
- **PAGE-15** — Prose no longer slides under the sticky header: the scroll offset that keeps a
  jumped-to section clear of the header derives from one shared value rather than a magic number
  that can drift from the header's real height.
- **PAGE-16** — The visible reading percentage tracks scroll **continuously** — it changes as the
  reader scrolls within a single section, not only when the section changes. It is monotonic with
  scroll direction and clamped to 0..100.
- **PAGE-17** — The displayed format is unchanged (`N% read · M min left`, integer percent), and
  the ink-line progress indicator follows the same live value.
- **PAGE-18** — The interpolated percentage is never sent to the server; position saves keep
  their existing payload and the stored percent stays the server's (I-PU-3).

### The study heatmap (frontend)

- **PAGE-19** — The grid renders as a compact block: fixed-width implicit columns and
  start-aligned, per `approved-artifact-spec.md` §A. Cells and gap take the approved sizes.
- **PAGE-20** — Month labels sit above the column where each month's first day lands; Mon/Wed/Fri
  label the weekday rows.
- **PAGE-21** — A Less→More key names the five levels, and the window is labelled.
- **PAGE-22** — Active days show a tooltip on **both hover and keyboard focus**, carrying reviews,
  pages, and the day, in the approved format. Only days with activity are interactive and
  focusable; empty days show nothing and expose no `title` (I-7).
- **PAGE-23** — Today's cell is locatable by a ring; empty cells are given definition by a
  hairline inset edge.
- **PAGE-24** — The adherence figures are set in tabular mono at the approved sizes, with the
  sentence's `textContent` unchanged (I-PU-8), and a reviews total accompanies it.
- **PAGE-25** — The pages total renders from the PAGE-09 server figure. (RFC-006 makes this
  conditional on the counter landing this cycle; PAGE-05..09 land it, so it ships.)
- **PAGE-26** — Existing test hooks survive unchanged: `data-testid` values, `data-day`,
  `data-level`, `data-placeholder`, the 84-cell window, and the hide toggle with its
  device-local persistence.

## Acceptance criteria

Each requirement above is met when a test asserts the spec-defined outcome (not the
implementation), the affected suite is green, and — for the invariants — a sensor exists that
fails if the invariant is broken. Specifically:

1. A unit test derives page numbers from word counts with no DB and no HTTP (PAGE-03).
2. A test proves the words-per-page value reaches the reader over the wire rather than being
   duplicated client-side (PAGE-02 / I-PU-2).
3. Tests cover the credit arithmetic at its edges: forward advance, backward move, first-ever
   save, and an unresolvable prior anchor (PAGE-07 / I-PU-4 / I-PU-5).
4. A test proves a failed save credits nothing (PAGE-08 / I-PU-6).
5. A test proves adding words leaves every existing heatmap level unchanged (PAGE-10 / I-PU-7).
6. A test proves a rule never lands inside a paragraph and never after the last one (PAGE-13).
7. A test proves the percentage changes on scroll within one section (PAGE-16) and that the save
   payload is unchanged by interpolation (PAGE-18 / I-PU-3).
8. Every existing assertion in `frontend/tests/study-heatmap.test.tsx` still passes unmodified
   (I-PU-8), and a test proves empty cells expose no tooltip and are not focusable
   (PAGE-22 / I-7).

## Verification gates

- Backend: `cd backend && uv run pytest` green; `ruff check` + `ruff format --check` clean.
- Frontend: `npm test` green; `tsc --noEmit` clean.
- DB-backed tests require `make infra` and `LEARNY_TEST_DATABASE_URL`.
- Known local baseline (do not chase): `test_eval_retrieval_metrics.py::TestDeterministic
  RetrievalMetrics::test_metrics_meet_thresholds` fails on this machine only (pgvector HNSW
  approximate-recall variance) and passes in CI.
