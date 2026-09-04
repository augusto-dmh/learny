# reader-people-read-in — Review Triage (PR #64)

Six review lanes produced **6 inline findings** plus PR-level requirements and consolidation comments. Judged against the code as it exists, not the reviewer's authority. Verdicts: **5 fix**, **1 fix (worker sensor, not EVAL goldens)**.

CI was green at review time (head `68585bf1`).

Submitted GitHub *reviews* (not comments) cannot be deleted in Stage 6; leftover review objects are expected.

| # | Source | File:line | Verdict | Action | Rationale |
|---|---|---|---|---|---|
| F1 | tests `3935073457` | `backend/tests/eval_runner.py:112` | **real** | **fix** | Confirmed: `valid_book()` packages `cover.png` as PNG magic only (`fixtures_epub.py`), so Pillow drops it. Worker ingest wires the real encoder. Pin composition with a real tiny raster on the worker path (stored WebP + rewritten cover markdown + pre-rewrite chunk text). Do **not** rewrite `golden_book` / EVAL expected files — those goldens are image-free by design and would churn EVAL-01..04 without tightening this cycle's figure contract. |
| F2 | regression `3935073880` | `backend/app/domain/entities.py:286-289` | **real** | **fix** | Confirmed: `ParsedBook` redeclares `title` / `authors` / `language` / `sections` after `media`. Dict insertion keeps field order valid, but the second block is dead source. Delete it. |
| F3 | tests `3935074001` | `backend/app/application/corpus.py:163` | **real** | **fix** | Confirmed: `pack_chunks(block_texts, …)` uses pre-rewrite Markdown while `record.markdown` is rewritten. Tests only assert display markdown. Pin `"![Cover image](cover.png)"` in `chunks[].text` and the rewritten URL only on `markdown` — a missing sensor, not a wrong split. |
| F4 | tests `3935074654` | `backend/app/application/corpus.py:265` | **real** | **fix** | Confirmed: `_resolve_media` falls back to basename; `by_name.setdefault` is first-wins. Every figure test used identical `"cover.png"`. Add a packaged-href vs basename `src` case and a same-basename first-wins case. |
| F5 | architecture `3935093593` | `backend/app/application/sources.py:154` | **real** | **fix** | Confirmed: `except Exception` maps `StorageUnavailable` to `SourceNotFound` (404). S3 already raises `ObjectNotFound` for a miss and `StorageUnavailable` for an outage; the web layer maps the latter to 503. Re-raise `StorageUnavailable`; keep miss/KeyError/`ObjectNotFound` as 404. Add HTTP 503 on GET media when storage is down. |
| F6 | architecture `3935093595` | `backend/app/application/corpus.py:239` | **real** | **fix** | Confirmed: bare `except Exception` around encode drops the figure and continues (required so one image cannot fail ingest). Unexpected crashes leave no log. Keep the swallow; log `source_id` and `src` with `exc_info`. Do not narrow so far that an unexpected encoder crash fails the job. |
| R1 | requirements issue `5542033520` | spec READ-01..26 | **real, informational** | **won't-fix** | Requirements lane reports all 26 criteria match the diffs. No code change. |
| S1 | summary issue `5542127157` | consolidation | **real, informational** | **won't-fix** | Restates F1–F6. No additional defect. |

## Counts

- Findings judged: 8 (6 inline, 2 PR-level)
- Real / fix: 6
- Real / won't-fix: 2 (informational)
- False: 0
