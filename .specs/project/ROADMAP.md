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

All 10 TDD-001 phases are now shipped — the MVP roadmap is complete. Further work
starts from new ADRs/TDDs (see the open follow-ups in STATE.md: TDD open question
#10 + the cloud LLM/embedding provider ADR).
