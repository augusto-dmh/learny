# Tasks — `v6-page-unit`

Contract per task: tests derive from the spec's acceptance criteria and assert spec outcomes;
the gate is green before the task is done; one atomic commit per task; no internal IDs and no
tooling attribution in commit messages.

## Phase A — The unit and the counter (backend) · Opus

| # | Task | Requirements | Gate |
|---|---|---|---|
| A1 | Words-per-page setting + pure page derivation beside `percent_at` | PAGE-01, PAGE-03, PAGE-04, I-PU-1, I-PU-2 | `pytest tests/test_reading_pure.py tests/test_config.py` |
| A2 | Migration off `0015_study_days` + `StudyDay` field + repository record/window | PAGE-05, PAGE-06 | `pytest tests/test_repositories_study.py tests/test_migrations.py` |
| A3 | Credit arithmetic in `SaveReadingPosition` (forward-only, no-baseline, atomic) | PAGE-07, PAGE-08, I-PU-4, I-PU-5, I-PU-6 | `pytest tests/test_application_reading.py tests/test_web_reading.py` |
| A4 | Wire: page size on the chapter response, pages figure on the study window | PAGE-02, PAGE-09, PAGE-10, I-PU-7 | `pytest tests/test_web_reading.py tests/test_web_study.py tests/test_application_study.py` |

Phase gate: full `uv run pytest` + `ruff check` + `ruff format --check`.

## Phase B — The reading column (frontend) · Opus

| # | Task | Requirements | Gate |
|---|---|---|---|
| B1 | Column typography through the Aa variables (measure, rhythm, chapter title, paper) | PAGE-11, PAGE-12 | `npm test -- chapter-reader reading-controls use-reading-settings` |
| B2 | Page rules at the quantum boundary, between paragraphs only, labelled | PAGE-13, PAGE-14 | `npm test -- chapter-reader` |
| B3 | One shared header offset feeding the bar and the section scroll margin | PAGE-15 | `npm test -- reader-chrome chapter-reader` |
| B4 | Continuous percentage + ink line; save payload untouched | PAGE-16, PAGE-17, PAGE-18, I-PU-3 | `npm test -- chapter-reader reading-client` |

Phase gate: full `npm test` + `tsc --noEmit`.

## Phase C — The study heatmap (frontend) · Opus

| # | Task | Requirements | Gate |
|---|---|---|---|
| C1 | Fixed column tracks + month/weekday axes + Less→More key + today ring + cell edge | PAGE-19, PAGE-20, PAGE-21, PAGE-23, PAGE-26 | `npm test -- study-heatmap` |
| C2 | Tooltip on hover **and** focus, active days only, empty days silent | PAGE-22, I-7 | `npm test -- study-heatmap` |
| C3 | Mono adherence figures + reviews and pages totals, sentence byte-identical | PAGE-24, PAGE-25, I-PU-8 | `npm test -- study-heatmap study-client` |

Phase gate: full `npm test` + `tsc --noEmit`.

## Close

Fresh Verifier (author ≠ verifier), Opus: spec-anchored outcome check across PAGE-01..26 and
I-PU-1..8, discrimination sensor, `validation.md`.
