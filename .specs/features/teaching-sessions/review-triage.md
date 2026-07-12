# PR #14 Review Triage — teaching-sessions (Cycle 7)

Review run: fresh-context subagent invoking `pr-review` (six dimensions). The
reviewer session was lost after all six dimension agents posted; the
consolidation pass did not run — a no-op with 3 non-overlapping comments.
Dimension results: Security 0 findings, Test Coverage 0, Regression 0,
Requirements 1 PR-level summary, Performance 1 inline, Architecture 1 inline.
Comments are deleted in Stage 6; this file is the surviving record.

| # | Source comment | Location | Verdict | Action | Rationale |
|---|---|---|---|---|---|
| 1 | inline 3565684183 (performance) | `backend/app/application/teaching.py:275` | **Real** | **Fix** | Confirmed: `PostTeachingTurn` calls `list_for_session`, which joins `teaching_turns × teaching_turn_citations` and materializes an `Evidence` per citation row, but the service consumes only `len(prior)` (turn_index) and the last `history_turns` `(message, answer_text)` pairs. Per-turn cost grows O(total turns × citations) with conversation length on the hottest endpoint. Fix: new `TeachingTurnRepository.recent_history(session_id, limit) -> (total_count, list[HistoryTurn])` (no citation join, `ORDER BY turn_index DESC LIMIT n` re-ascended), used by `PostTeachingTurn`; `list_for_session` remains the read-path contract for `ReadTeachingSession`. |
| 2 | inline 3565684828 (architecture) | `backend/app/application/teaching.py:243` | **Real** | **Fix** | Confirmed verbatim duplication: the resolve-session → resolve-source → authorize → collapse-to-`TeachingSessionNotFound` block appears identically in `ReadTeachingSession.__call__` (145–154) and `PostTeachingTurn.__call__` (243–252), while the source-rooted equivalent already has a single home (`authorized_source`). Fix: module-level `authorized_session(*, user, session_id, sessions, sources, authorize) -> tuple[TeachingSession, Source]` in `application/teaching.py`, called from both services. Behavior unchanged; existing tests are the regression net. |
| 3 | issue 4949997965 (requirements) | PR-level | **Not a defect** | **No action** | Informational review summary: verifies all 24 acceptance criteria implemented, none missing; notes only forward-carry caveats already recorded elsewhere (shared-IP rate-limit KNOWN LIMITATION; loosely specified "readable detail" met). Nothing to change. |

**Counts:** 3 comments → 2 real/fix, 0 real/won't-fix, 0 false, 1 informational (no action).
