# v3-notes-research Specification (RFC-003 Cycle D — research-gated flagship, part 0)

## Problem Statement

RFC-003's flagship — notes & second-brain workflows on the canonical corpus — is deliberately under-specified: unlike active recall (researched 2026-07-12 before RFC-002), no evidence base exists for the notes domain model, anchoring granularity, editor stack, retrieval integration, or competitive positioning. Cycles E–F are provisional until a notes-domain ADR locks these; this cycle produces the research and that ADR.

## Goals

- [ ] Durable research reports under `docs/research/2026-07-18/` answering every RFC-003 Cycle D question, each with sourced evidence.
- [ ] ADR-0026 (notes & second-brain domain model) drafted as **Proposed** with a concrete recommendation per decision — acceptance is the user's gate for Cycles E–F.
- [ ] Confirmed-or-revised scopes for Cycles E–F recorded for the RFC.

## Out of Scope

| Feature | Reason |
|---|---|
| Any implementation (schema, endpoints, UI) | Cycles E–F, gated on the ADR |
| Auto-accepting ADR-0026 | RFC-003 explicit user gate; product direction |
| Re-litigating RFC-003 exclusions (BYOK, hosted, vector DB) | Locked by AD in the roadmap RFC |

## Research Questions (RQ-01..07, from RFC-003 Cycle D)

1. **RQ-01 Competitive landscape**: does anyone combine anchored book highlights + AI teaching + SRS + notes? (RemNote, Readwise/Reader, Obsidian ecosystem, Recall, LogSeq, Zettlr, Matter, supernotes/mem/others found during search). Per product: anchoring model, SRS integration, AI features, citation fidelity, lock-in/export. Verdict: is Learny's niche still open, and what table stakes exist?
2. **RQ-02 Highlight anchoring**: sub-section anchoring below Learny's section/block anchors — char-offset vs quote-based (text-fragment style) vs block-id models; how real products survive document re-processing (Hypothesis, Readwise, browser text-fragments literature); recommendation compatible with the existing anchor + `anchor_aliases` + content-hash scheme and re-ingest reconciliation precedent (quiz items).
3. **RQ-03 Notes data model**: notes as documents vs blocks; links/backlinks/tags representation in PostgreSQL (no graph DB — provider-neutral constraint); ordering/nesting; how quiz-item snapshot semantics (no corpus FK, content-key upsert) translate to notes/highlights.
4. **RQ-04 Editor stack**: Markdown textarea vs ProseMirror/TipTap vs CodeMirror vs Lexical for the Next.js 15/React 19 frontend; licensing, vendored-component fit (AI Elements precedent), offline-free constraint, effort tiers; recommendation with a smallest-viable option.
5. **RQ-05 Notes in retrieval**: notes/highlights joining hybrid retrieval — same `corpus_chunks` table vs parallel notes index; citation semantics when an answer cites the user's own note vs the book; embedding cost/refresh on edit; RRF implications; teaching/Q&A prompt implications ("the user's notes say…").
6. **RQ-06 Note→quiz**: feeding notes into `QuizGenerationPort` — provenance display at review, dedup vs book-derived items, groundedness when the "source" is user prose; scheduling identity (`content_key`) for evolving notes.
7. **RQ-07 Export/portability**: Markdown/Obsidian-compatible vault export shape (frontmatter, wikilinks, folder layout); what must be stored to make export lossless; genanki precedent for "export is a projection, not a sync".

Each RQ must end in a **recommendation with why-recommend AND why-not** (house decision style), not a survey.

## Acceptance Criteria

1. (NR-01) WHEN research completes THEN `docs/research/2026-07-18/` SHALL contain one report per RQ (or justified merges) each citing ≥3 independent sources (product docs, code, papers — not blog hearsay alone) with fetch dates.
2. (NR-02) WHEN claims about a product's current capabilities are made THEN they SHALL be verified against that product's own docs/changelog (not only reviews), flagged `unverified` otherwise.
3. (NR-03) WHEN the reports exist THEN a synthesis doc SHALL map each RQ recommendation to its Cycle E/F impact (confirm/revise the provisional scopes) and list any RFC-003 assumption invalidated (esp. the anchor-scheme assumption).
4. (NR-04) WHEN synthesis is done THEN `docs/adr/0026-*.md` SHALL exist as **Proposed**, one decision block per RQ-02..07 outcome + the RQ-01 positioning statement, each with considered options and the recommendation marked.
5. (NR-05) WHEN the cycle publishes THEN the PR SHALL contain research + ADR + spec artifacts; the ADR status stays Proposed through merge; the user decides acceptance separately.
6. (NR-06) WHEN research is dispatched THEN it SHALL run as parallel research agents with an adversarial verification pass on load-bearing claims (the RFC-002 research-fleet pattern), and a completeness critique before synthesis.

## Success Criteria

- [ ] User can accept/revise ADR-0026 from the documents alone, without re-research.
- [ ] Every Cycle E/F scope line traces to an RQ recommendation.
