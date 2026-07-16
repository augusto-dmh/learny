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
| `v2-embeddings` | B | Real embeddings (OpenAI 3-large@1536) + language-aware FTS | In review (PR #20) |
| — | C | Claude generation: cited answers + teaching + eval harness | Not started |
| — | D | Frontend v2: product UI + streaming | Not started |
| — | E | Active recall: quizzes + FSRS | Not started |
| — | F | PDF (Docling) + EPUB hardening | Not started |
| — | G | Deploy (GHCR→VPS, Caddy) + presentation | Not started |
