# trustworthy-cited-ask — Review Triage (PR #63)

Six review lanes produced **2 inline findings** plus PR-level requirements and consolidation comments. Judged against the code as it exists, not the reviewer's authority. Verdicts: **2 fix**.

CI was 4/4 green at review time (head `83d5bbf2`): `lint`, `backend-test`, `frontend`, `compose-smoke`.

Submitted GitHub *reviews* (not comments) cannot be deleted in Stage 6; leftover review objects are expected.

| # | Source | File:line | Verdict | Action | Rationale |
|---|---|---|---|---|---|
| F1 | tests `3933831765` | `backend/app/infrastructure/web/dependencies.py:168` | **real** | **fix** | Confirmed: `auth_client` overrides `get_db_connection` to `yield db_conn` with no commit/rollback (`conftest.py:161`). `test_post_turn_generation_failure_returns_502_and_keeps_the_question` shares that uncommitted connection, so GET after POST never proves a later request can see the failed turn. Removing the `except AnswerGenerationFailed: trans.commit()` branch would still leave the in-transaction row visible to the same `db_conn`. The application-layer persist tests are real; this HTTP transaction seam is not. Add a generator-level test that records commit vs rollback. |
| F2 | tests `3933832684` | `frontend/app/components/chapter-reader.tsx:684` | **real** | **fix** | Confirmed: in-chapter quote paint is covered (`chapter-reader.test.tsx` "paints the cited sentence…"). `show-foreign` still calls `onShowInBook(anchor)` with no quote. `pendingCitationQuote` is written on the foreign path and consumed on `ChapterFlow` mount, with no test asserting `mark.reader-highlight` after remount. A drop of that stash would flash the foreign section and never the sentence. Add a remount test with a quoted foreign Show-in-book. |
| R1 | requirements issue `5540234307` | spec ASK-01–17 | **real, informational** | **won't-fix** | Requirements lane reports all 17 criteria plus cited constraints match the diffs; abort-persist on Stop is the documented generator-unwind deviation, not an ASK-04 miss. No code change. |
| S1 | summary issue `5540299901` | consolidation | **real, informational** | **won't-fix** | Restates F1/F2. No additional defect. |

## Counts

- Findings judged: 4 (2 inline, 2 PR-level)
- Real / fix: 2
- Real / won't-fix: 2 (informational)
- False: 0
