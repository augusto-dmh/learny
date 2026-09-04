# PR #65 Review Triage — teach-becomes-tutor

4 inline comments + 2 PR-level comments from the 6-lane review. Every finding checked against the code; verdicts below are the surviving record (comments get deleted per ship-cycle Stage 6). PR-level requirements and summary comments are consolidation, not findings.

Verified inline before triage: `TeachChat` refetches `getConversation` on `[conversationId, isStreaming, messages.length]` (`teach-panel.tsx` ~499–520) while restore already GETs once; `_accept_tutor_card` HTTP helper exists and the 201/200/409/404 cases do not cover 401/403; `_is_closing_restatement` is tested only on `PostConversationTurn.__call__`; `handleAcceptCard` has `.then` and no `.catch`.

| # | Source (comment id) | Location | Finding | Verdict | Action | Rationale |
|---|---|---|---|---|---|---|
| 1 | 3937072303 (performance) | `teach-panel.tsx:504` | Full conversation refetch after every tutor turn (`getConversation` keyed on `messages.length`) | **Real** | **Fix** | Confirmed: each completed turn (and resume-after-stream) hits `ReadConversation` → `list_for_conversation` with every citation, to copy three ladder columns `_persist` already wrote. Restore has already paid that cost once. Echo `tutor_phase` / `hint_level` / `tutor_check_text` on `StreamTurn` and a `data-tutor-state` terminal SSE part (same family as `data-answer-status`); Teach derives live ladder from the last assistant part and drops the effect. Restore GET stays. Answer streams omit the part when `tutor_phase` is null, so existing Ask frame-sequence sensors stay exact. |
| 2 | 3937076175 (tests) | `conversations.py:551` | New tutor-card route lacks 401/403 HTTP cases | **Real** | **Fix** | Confirmed: 201/200/409/owner-vs-stranger 404 exist; unauthenticated and missing CSRF do not. Every other mutating route on this router has the TestClient pair. Add the two cases next to the tutor-card block, asserting `list_for_source` stays empty. |
| 3 | 3937076294 (tests) | `conversations.py:636` | Closing restatement has no stream-path test | **Real** | **Fix** | Confirmed: `_is_closing_restatement` is pinned on the buffered `__call__` (`test_ordinary_message_in_check_closes_and_stores_the_restatement`). Tutor UI uses `.stream`. Add a sibling that drives `.stream(...)` in `check` with an ordinary message: no retrieve, no generate, no `StreamPhase`, one `StreamTurn`, persisted phase `close` and `tutor_check_text` equal to the message. |
| 4 | 3937076375 (tests) | `teach-panel.tsx:530` | Tutor Accept has no failure-path vitest (and no `.catch`) | **Real** | **Fix** | Confirmed: `void acceptTutorCard(...).then(...)` has no catch; `TutorCardError` already exists. A 409/404/network failure leaves the offer up with no explanation. Catch, keep the offer, show the existing error copy, and add vitest for 409 and 404 (no `/cards/suggestions`). |

**Tallies:** 4 findings — 4 real, 4 fix, 0 false, 0 won't-fix.

**PR-level:** requirements track (42/42 TUTOR implemented; interactive UAT skipped in DoD) and the review summary — no extra product defects.
