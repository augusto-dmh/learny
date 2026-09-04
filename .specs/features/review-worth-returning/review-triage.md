# PR #66 Review Triage — review-worth-returning

8 inline comments + 2 PR-level comments from the 6-lane review. Every finding checked against the code; verdicts below are the surviving record (comments get deleted per ship-cycle Stage 6). PR-level requirements and summary comments are consolidation, not findings.

Verified inline before triage: `get_due_reviews` loops `items.get_scheduling(due.item.id)` after `due_for_user` already joined `quiz_item_scheduling`; flag HTTP tests cover 200/404/403 CSRF/origin but not 401/429; `handleUndo` splices `shortTerm` when `last.requeued` with no vitest of that branch; `flagQuizItem`/`updateQuizItem` client tests are happy-path only; due handler type-hints `SqlAlchemyQuizItemRepository`; `_interval_labels` lives in `web/quiz.py`; `_ground` has a dead `located is None` return after `discard_reason` already mapped that case; `isTypingTarget` is duplicated in `review-screen.tsx`.

| # | Source (comment id) | Location | Finding | Verdict | Action | Rationale |
|---|---|---|---|---|---|---|
| 1 | 3938085275 (performance) | `quiz.py:436` | N+1 `get_scheduling` on the due queue | **Real** | **Fix** | Confirmed: `due_for_user` already inner-joins scheduling and selects `due`. The handler then PK-reads the same row per card (N ≤ 100) before `preview`. Project the snapshot on that join and label in `GetDueQueue`. |
| 2 | 3938088621 (tests) | `quiz.py:524` | Flag handler missing 401 and 429 tests | **Real** | **Fix** | Confirmed: undo has `test_undo_unauthenticated_returns_401` and `test_undo_rate_limit_returns_429`; flag only has happy path, 404, CSRF 403, origin 403. Same `rate_limit_quiz` + auth deps. Mirror the undo pair. |
| 3 | 3938088712 (tests) | `review-screen.tsx:279` | Undo after short-term requeue untested | **Real** | **Fix** | Confirmed: `handleUndo` splices the extra `shortTerm` copy when `last.requeued`. Requeue and long-due undo are tested separately; the combination is not. A splice bug would duplicate the card or leave the short-term count. |
| 4 | 3938088772 (tests) | `quiz.ts:307` | `flagQuizItem` / `updateQuizItem` omit error-path assertions | **Real** | **Fix** | Confirmed: siblings pin `toQuizError` on 4xx detail. These two helpers only assert 200. Mirror the undo 409 case. |
| 5 | 3938093563 (architecture) | `quiz.py:420` | Due handler injects `SqlAlchemyQuizItemRepository` | **Real** | **Fix** | Confirmed: only quiz/review route that takes a concrete persistence type, solely to feed the N+1 in #1. Fold snapshot + labels into `GetDueQueue`; delete `get_quiz_item_repository` from the router. |
| 6 | 3938095036 (architecture) | `quiz.py:112` | Interval-label policy runs in the HTTP adapter | **Real** | **Fix** | Confirmed: `_interval_labels` calls `scheduling.preview` and `interval_bucket` in `web/quiz.py`, and uses `datetime.now(UTC)` instead of `GetDueQueue`'s `Clock`. Move preview + buckets into application; views only attach the returned map. Same commit as #1/#5. |
| 7 | 3938101363 (regression) | `quiz.py:348` (`application/quiz.py`) | Unreachable unknown-chunk branch in `_ground` | **Real** | **Fix** | Confirmed: missing chunk passes `chunk_text=None` → `discard_reason` returns `ungrounded` → first return. The follow-up `if located is None` cannot run. Delete it; keep the success-path assert/narrowing. |
| 8 | 3938101447 (regression) | `review-screen.tsx:106` | `isTypingTarget` copied from `use-key-shortcuts` | **Real** | **Fix** | Confirmed: byte-for-byte duplicate. Ctrl/Cmd+Z cannot use `useKeyShortcuts` (modifier chords are ignored there), so the guard is still needed — export one copy. |

**Tallies:** 8 findings — 8 real, 8 fix, 0 false, 0 won't-fix.

**PR-level:** requirements track (45/45 REV implemented; interactive product UAT still open in DoD) and the review summary — no extra product defects.
