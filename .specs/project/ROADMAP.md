# ROADMAP

The authoritative roadmap is the **TDD-001 Implementation Plan** (`docs/tdd/0001-mvp-architecture.md`, Phases 1–10).
This file only tracks how those phases map onto tlc cycles. Do not duplicate TDD content here.

| tlc Cycle | TDD Phases | Status |
|---|---|---|
| `scaffold-and-identity` | 1 (Repository scaffold) + 2 (Identity foundation) | Done (PR #4) |
| `source-storage` | 3 (Source storage) | Done (PR #7, #8) |
| `worker-foundation` | 4 (Worker foundation) | Done (PR #9) |
| `epub-corpus-pipeline` | 5 (EPUB corpus pipeline) | Done (PR #10) |
| `retrieval-indexes` | 6 (Retrieval indexes) | Done (PR #12) |
| `cited-qa` | 7 (Cited Q&A) | Done (PR #13) |
| `teaching-sessions` | 8 (Teaching sessions) | Done (PR #14) |
| `golden-fixtures` | 9 (Golden fixtures) | Done (PR #15) |
| `production-readiness` | 10 (Production-like readiness) | Done (PR #16) |

All 10 TDD-001 phases are now shipped — the MVP roadmap is complete.

## v2 (RFC-002)

v2 is driven by the accepted [RFC-002 roadmap](../../docs/rfc/0002-learny-v2-roadmap.md)
(cycles A–G); it resolves the MVP's open follow-ups (cloud LLM/embedding provider ADR,
TDD open question #10 lands in Cycle G). Research evidence: `docs/research/2026-07-12/`.

| tlc Cycle | RFC-002 Cycle | Scope | Status |
|---|---|---|---|
| `v2-foundation` | A | QA artifacts + F2/F3/F4 fixes + CI + OSS hygiene | Done (PR #17, v0.1.0) |
| `v2-embeddings` | B | Real embeddings (OpenAI 3-large@1536) + language-aware FTS | Done (PR #20) |
| `v2-generation` | C | Claude generation: cited answers + teaching + eval harness | Done (PR #23) |
| `v2-frontend` | D | Frontend v2: product UI + streaming | Done (PR #24) |
| `v2-active-recall` | E | Active recall: quizzes + FSRS | Done (PR #25) |
| `v2-ingestion-breadth` | F | PDF (Docling) + EPUB hardening | Done (PR #26) |
| `v2-deploy` | G | Deploy (GHCR→VPS, Caddy) + presentation | Done (PR #27) |

RFC-002 is complete — all seven v2 cycles shipped (v0.2.0).

## v3 (RFC-003)

v3 is driven by the accepted [RFC-003 roadmap](../../docs/rfc/0003-learny-v3-roadmap.md)
(cycles A–F): notes & second-brain as the research-gated flagship, plus eval maturity,
ops maturity, and scanned-PDF OCR. Cycles E–F scopes are provisional until the Cycle D
notes-domain ADR is accepted.

| tlc Cycle | RFC-003 Cycle | Scope | Status |
|---|---|---|---|
| `v3-ops-maturity` | A | Backups + monitoring (TDD OQ #10) + image hygiene | Done (PR #28) |
| `v3-eval-maturity` | B | Real-provider baselines + judge threshold gate | Not started |
| `v3-ocr` | C | Scanned-PDF OCR + localized normalization | Done (PR #29) — ran before B per AD-103 |
| `v3-notes-research` | D | Second-brain research + notes-domain ADR (gate for E–F) | Done (PR #30) — ADR-0026 Accepted 2026-07-18, E–F unblocked |
| `v3-notes-foundation` | E | Capture + organize: highlights, notes, links (provisional) | Not started |
| `v3-notes-loop` | F | Retrieve + reinforce: notes in RAG + quiz, export (provisional) | Not started |
