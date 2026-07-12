# Golden Fixtures — Review Triage (PR #15)

Independent `pr-review` posted 3 inline findings (1 ⚠️, 2 💡) + 2 PR-level
comments (requirements review, summary). Each judged against the actual code
below. Comments are deleted after fixes land, so this file is the surviving
record of the review reasoning.

| # | Source comment | File:line | Verdict | Action | Rationale |
| --- | --- | --- | --- | --- | --- |
| 1 | inline `3567172658` (💡 architecture) | `backend/tests/golden_corpus.py:15` | Real | Fix | `golden_corpus` imports the underscore-private `_CONTAINER`/`_doc`/`_zip` of `fixtures_epub` (no `__all__`; documented surface is the `*_book()` builders). A refactor of those helpers would silently break the golden fixture. Extract the EPUB-packing primitives into a documented shared module both consume. Low-risk mechanical decouple; tests verify. |
| 2 | inline `3567173334` (⚠️ tests) | `backend/migrations/env.py:18` | Real | Fix | The `fileConfig` drop is a real behaviour change protecting app-owned redaction, but nothing asserts it: `test_configure_logging_redacts_emitted_output` calls `configure_logging()` itself, so re-adding `fileConfig` would fail no test — only incidental module ordering protects it. Add a regression test: run an in-process `command.upgrade(..., "head")` **after** `configure_logging()`, emit a record with sensitive fields, assert they are still redacted. Pins the change as an assertion, not an ordering accident. |
| 3 | inline `3567173501` (💡 tests) | `backend/tests/test_golden_citations.py:48` | Real | Fix | `cited_anchors <= GOLDEN_SECTION_ANCHORS` cannot fail while retrieval is source-scoped and the answer adapter is extractive (every cited anchor is necessarily a retrieved in-source anchor) — confirmed by the surviving grounding mutant. Keep the assertion; add an inline NOTE that it becomes discriminating only once a generative adapter that can cite freely replaces the extractive one. Cheap clarity fix, no behaviour change. |
| 4 | PR-level `4952867603` (requirements review) | — | Real (informational) | No action | Confirms all 10 EVAL criteria + both governing decisions met; the one unchecked DoD item is a human merge-gate sign-off on the two flagged departures (no-eval-store, backend-only), not a code gap. Surfaced at Stage 7. |
| 5 | PR-level `4952878280` (review summary) | — | Real (informational) | No action | Aggregate summary; 0 security/perf/regression findings, 3 non-blocking inline items handled by #1–#3. |

## Fix plan (Stage 5)

- **#3** (trivial): inline NOTE in `test_golden_citations.py`.
- **#2** (valuable): new `requires_db` regression test that an in-process migration
  after `configure_logging()` does not strip redaction.
- **#1** (decouple): new `tests/epub_builder.py` with public `CONTAINER` /
  `build_doc` / `zip_epub`; `fixtures_epub.py` and `golden_corpus.py` both import
  the public surface.

All three are non-blocking per the reviewer; applied to keep the harness clean and
the `env.py` fix assertion-backed.
