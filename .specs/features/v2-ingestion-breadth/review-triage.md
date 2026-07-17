# PR #26 Review Triage — v2-ingestion-breadth

**Date:** 2026-07-17. Review ran via the project pr-review skill (6 specialist agents) against PR #26. Comments are deleted after fixes land (ship-cycle Stage 6); this file is the surviving record.

Specialist outcomes: Security 0 findings (2 sub-threshold observations: widened pre-validation read buffer is bounded+rate-limited; client-asserted content type is the accepted design). Performance 0. Regression 0 (port rename verified complete; golden change verified legitimate). Requirements: PR-level summary comment, 24/24 ACs implemented, no gaps. Test Coverage: 2 inline findings. Architecture: 1 inline finding.

| # | Source comment | Location | Verdict | Action | Rationale |
|---|---|---|---|---|---|
| 1 | inline 3604682085 (tests, ⚠️) | `backend/app/infrastructure/web/sources.py:102` | **Real** | **Fix** | The read bound moved from `epub_max_bytes+1` to `max(epub, pdf)+1`, but no web-layer test uploads a PDF sized between the caps. Verified the failure mode against the handler: a revert would truncate a >50 MiB PDF at read time, the truncated size would then PASS the 100 MiB PDF cap in validation, and a corrupt object would be stored silently — every existing test still green. Add a sources_client test with `pdf_max_bytes > epub_max_bytes`: between-caps PDF → 201 + stored bytes identical (untruncated); over-pdf-cap PDF → 413. |
| 2 | inline 3604682177 (tests, 💡) | `backend/tests/test_migrations.py:835` | **Real** | **Fix** | The test comment claims "defaults to the empty array (not NULL)" but the assertion only checks `data_type == "ARRAY"`; nothing exercises the `NOT NULL DEFAULT '{}'` server default (ORM tests always pass explicit lists). Make it discriminating: raw-SQL insert a corpus_sections row without `anchor_aliases`, assert it reads back `[]`. |
| 3 | inline 3604687938 (architecture, 💡) | `backend/app/infrastructure/worker/steps.py:44` | **Real** | **Fix** | `EpubCorpusIngestionStep` + "unparseable EPUB" docstrings now drive both formats via the dispatch parser. The kept name was a Phase C file-scope constraint, not a decision — design.md's reuse table explicitly said "rename EPUB-specific names". Rename to `CorpusIngestionStep`, reword docstrings, update the import in worker/tasks.py + tests. |
| 4 | issue comment 5005331505 (requirements) | PR-level | Real (informational) | **No action** | Review summary confirming all 24 ACs implemented, ADR conformance, no missing requirements; its three "DoD notes" restate deviations already accepted in validation.md (composition-tested PDF re-ingest, pre-existing markup h1–h6 path, encrypted-PDF shared branch). Nothing actionable. |

**Counts:** 4 comments → 3 real actionable (all fixed), 1 informational (no action), 0 false positives.
