# ADR-026: Notes And Second-Brain Domain Model

- **Date**: 2026-07-18
- **Status**: Accepted (2026-07-18)
- **Deciders**: Augusto, Claude
- **Tags**: notes, highlights, anchoring, retrieval, quiz, export, product

## Context and Problem Statement

RFC-003 made notes & second-brain workflows the v3 flagship but gated the build
cycles on a researched domain model. The research fleet (reports and synthesis in
`docs/research/2026-07-18/`, every load-bearing claim adversarially verified)
answered the seven open questions. This ADR converts those recommendations into
the binding domain model for Cycles E–F. Positioning: no surveyed product —
RemNote and Heptabase closest — combines anchored book highlights, cited AI
answers, teaching, FSRS scheduling, and notes, and none is self-hosted; the niche
Learny occupies remains open, and the notes feature's table stakes are capture
from the reading view, note↔passage↔quiz linkage with jump-back, re-ingest
survival, retrieval integration, one-action promotion to review, tags, and
Markdown export.

## Decision Outcome (one block per research question; full options analysis in the reports)

### 1. Highlight anchoring (rq02)

A highlight stores a **layered, value-based anchor with no corpus foreign key**:
section anchor + `section_path` snapshot, block content-hash + ordinal, char
offsets within the block (TextPositionSelector semantics), and a
quote-with-context snapshot (exact + 32-char prefix/suffix — Hypothesis's proven
width). Re-ingest runs a **4-tier exact reconcile cascade** once at ingest time:
section-by-anchor/alias → block-by-hash (offsets then provably valid) →
quote-in-section → quote-in-document (adopting the found anchor); anything else
becomes **orphaned — kept forever**, rendered from its quote snapshot,
resurrectable by later reconciles. Fuzzy re-attach (diff-match-patch tier) is
deliberately deferred until orphan telemetry proves real text mutation.
Rejected: char-offset-only (dies on any re-parse), quote-only text-fragment
semantics (silent loss), Readwise-style destroy-on-refresh.

### 2. Notes data model (rq03)

Notes are **whole Markdown documents**: a `notes` table whose `body_markdown` is
the single source of truth, with derived indexes rebuilt on save —
`note_links` (nullable resolved-target FK + always-populated target text),
first-class `tags`/`note_tags`, optional `notebooks` as an adjacency list with
integer sibling positions (recursive CTE traversal; no graph DB, no fractional
indexing at single-user scale). Book citations live in `note_anchors` rows
carrying the anchoring payload of decision 1. Notes and their anchors **never
cascade from corpus or source deletion** — deleting or re-ingesting a book can
orphan anchors, never destroy user prose. The block/outliner model (Logseq/
RemNote-style) is rejected for v3; in-body span markers remain a compatible later
increment.

### 3. Editor (rq04)

Cycle E ships a **plain Markdown textarea with a streamdown-rendered preview** —
zero new dependencies (streamdown is already vendored for chat), zero licensing
surface, React-19-native. **CodeMirror 6 is the named upgrade path** (MIT, zero
peer dependencies, stable since 2022, Obsidian precedent for
wikilinks-over-Markdown) to be adopted only when wikilink autocomplete or live
styling becomes a committed feature; because notes are canonical Markdown either
way, that upgrade is additive. Lexical rejected (0.x with breaking changes in 4
of the last 5 releases — verified); TipTap reserved for a WYSIWYG requirement
that does not exist.

### 4. Notes in retrieval (rq05)

Notes join hybrid retrieval as a **parallel notes index** — their own embedding
(`vector(1536)`) and trigger-maintained tsvector — fused into the existing
single hybrid query as **two additional RRF arms** with a notes weight and
smaller per-arm limits, behind a user-visible **"include my notes" toggle**
(default on for Q&A, off for teaching until proven). Notes never enter
`corpus_chunks` (whose rows die on atomic re-ingest — verified in-repo).
Citations of the user's own notes are rendered distinctly from book citations
("your note", linking to the note) via the existing per-document citation
metadata. v1 embeds whole notes; paragraph-level chunking is the recorded
upgrade when note length warrants it. Re-embed on debounced save (economically
negligible at author scale).

### 5. Note→quiz (rq06)

Notes feed the existing quiz pipeline with one identity change: a note-derived
item's identity is a **creation-minted stable ID** (RemNote/Anki-GUID
precedent), never the content hash — `content_key` is demoted to a rewritable
uniqueness fingerprint for these items. On debounced note-save, a
regenerate-and-match step updates matched items in place under their existing
identity; **FSRS scheduling and review logs are never touched by an edit**;
schedule reset is only ever an explicit user action surfaced through a "your
note changed" badge at review time. Provenance (note title + excerpt) shows at
review. Groundedness QC for note-derived items verifies against the note body
(the note IS the source), with book-anchor context carried when the note itself
is anchored.

### 6. Export (rq07)

A **one-way, deterministic Obsidian-vault projection** (genanki precedent
reaffirmed: export is a projection, never a sync): a regenerable `Learny/`
folder, one Markdown file per book plus per-note files, Obsidian Properties
frontmatter with namespaced `learny-*` keys, highlights as `> [!quote]` callouts
titled with section path + page span, stable `^lh-<id>` block IDs so any vault
note can deep-link a highlight, wholesale folder replace on re-export. Lossless
by construction — everything serialized is already stored by decisions 1–2.

### 7. Cycle E–F scopes (confirms the RFC's provisional scopes, with deltas)

- **Cycle E (capture + organize)**: schema per decisions 1–2, highlight/note
  capture from reader selection, notes list/detail with the decision-3 editor,
  tags, backlinks panel (cheap reverse index — no graph UI in v3), orphan
  surfacing. Anchor cascade ships exact tiers only.
- **Cycle F (retrieve + reinforce + export)**: decision-4 retrieval integration
  with toggle, decision-5 note→quiz with one-action promotion (added table
  stake), decision-6 export, README/demo refresh, v0.3.0.
- Deferred beyond v3 (recorded): fuzzy re-anchoring, graph visualization,
  CodeMirror upgrade, paragraph-level note chunking, block/outliner model.

## Consequences

- Positive: every mechanism reuses a shipped pattern (quiz snapshots/reconcile,
  hybrid RRF, projection export, vendored-UI discipline) — the flagship composes
  rather than invents; user prose is structurally indestructible (no cascades,
  orphans persist); the competitive moat (anchored + cited + scheduled + owned)
  is confirmed and documented.
- Negative: the anchor payload and cascade are the deepest new machinery and
  land in Cycle E; whole-note embedding will eventually need chunking; the
  editor is deliberately spartan in v1.
- Open (flagged for Cycle E design, not silently owned here): highlight↔note
  cardinality and margin UX; note title/slug rules; whether excerpt-drift
  re-verification applies to note anchors in E.

## Acceptance

Accepted by Augusto on 2026-07-18 (RFC-003's Cycle D gate) — Cycles E–F are
unblocked. Each decision block remains independently revisable by a superseding
ADR, except decisions 1↔2, which share the anchor payload.
