# `v6-workspace-notes` — Validation

**Verdict: PASS** (one spec-precision gap recorded below; no failed criterion, no
surviving mutant, no spec deviation.)

- **Diff under verification:** `f6f4ce38..59615751` (12 commits; the first is planning
  docs), compared against `main` @ `fcb545d6`.
- **Verifier:** independent — did not write this code; coverage re-derived from
  `spec.md` against the tests, not from the authors' notes.
- **Date:** 2026-07-27.

## Gate

| Gate | Result |
| --- | --- |
| `make test-backend` | **1880 passed, 11 skipped, 1 failed** — the single failure is `tests/test_eval_retrieval_metrics.py::TestDeterministicRetrievalMetrics::test_metrics_meet_thresholds` (`recall@1 0.857 < 0.9`), pre-existing on `main`, local-only (local pgvector build ≠ CI's), outside this cycle. Baseline was 1858 passed → **+22 backend tests, none weakened or deleted.** |
| `make test-frontend` | **693 passed, 69 files** (baseline 665 / 67) → **+28 frontend tests.** |
| `make lint` | Clean — ruff check, ruff format, `tsc --noEmit`, architecture boundaries. |

The one changed pre-existing test file, `backend/tests/test_web_vault.py`, swapped its
`POST /api/notes` seed helper for a direct repository insert because the route is gone.
Its assertions are unchanged; nothing was weakened.

## Per-acceptance-criterion evidence

Backend tests are in `backend/tests/`; frontend in `frontend/tests/`.

### P1 — This book's notes, in the dock

| AC | Sensor | Asserts the spec outcome |
| --- | --- | --- |
| 1 — only that book's notes, newest-edited first | `test_web_notes.py::test_list_notes_scoped_to_a_book_lists_only_its_notes_with_their_passages`; `test_repositories_notes.py::test_list_summaries_scoped_to_a_book_lists_only_its_notes`, `…_book_scope_keeps_a_total_newest_edited_first_order`; `dock-notes-tab.test.tsx::"lists this book's notes, each with the passage it came from"` | Yes — another book's note and an anchorless note are both excluded; order asserted incl. the id tiebreak |
| 2 — row shows title, section title, page, quote | `test_web_notes.py::test_list_notes_scoped_to_a_book_lists_only_its_notes_with_their_passages` (page 3 derived from 25 preceding words at 10 words/page); `dock-notes-tab.test.tsx::"lists this book's notes…"` (row text `["On mechanism", "Prefácio · p. 62", "the analytical engine"]`) | Yes — spec's own row shape, not the implementation's |
| 3 — multi-anchored note listed once | `test_repositories_notes.py::test_list_summaries_lists_a_twice_anchored_note_once_with_its_earliest_passage`; `test_web_notes.py::test_list_notes_scoped_to_a_book_lists_a_twice_anchored_note_once`; `dock-notes-tab.test.tsx::"shows a note anchored to the book more than once exactly once"` | Yes — one row, and the *earliest* anchor represents it |
| 4 — verbatim empty-state copy | `dock-notes-tab.test.tsx::"invites the first note when the book has none"` | Yes — full sentence matched verbatim, and no list rendered |
| 5 — note count on the tab | `dock-notes-tab.test.tsx::"carries the book's note count on the tab"` | Yes (`"Notes2"`) |
| 6 — orphaned anchor still renders, from its quote, no page | `test_notes_application.py::test_list_notes_keeps_an_unresolvable_anchors_row_with_its_quote_and_no_page`; `test_web_notes.py::test_list_notes_scoped_to_a_book_keeps_an_orphaned_rows_quote_and_shows_no_page`; `dock-notes-tab.test.tsx::"keeps a note whose passage has orphaned…"` | Yes — row present, quote present, `page is None`, no `p.` in the DOM |

### P2 — What's due from this book

| AC | Sensor | Asserts the spec outcome |
| --- | --- | --- |
| 1 — count + caption "cards due from this book" | `dock-review-tab.test.tsx::"says how many cards this book has waiting, on the tab and in the panel"` | Yes — caption matched verbatim |
| 2 — gradable in the dock, no navigation away | `dock-review-tab.test.tsx::"grades a card in the dock, with the book's page never left behind"`; `chapter-reader.test.tsx::"grades this book's due card in the dock, without leaving the chapter"` | Yes — POST reached `/api/quiz-items/i1/reviews`, queue advanced, reader still mounted |
| 3 — nothing due → empty state, no review action | `dock-review-tab.test.tsx::"offers no grading when this book has nothing due"` | Yes |
| 4 — due count on the tab | same test as AC 1 (`"Review3"`) | Yes |
| 5 — queue count only, no gamification (I-7) | `dock-review-tab.test.tsx::"counts the queue and nothing else — no streak, badge, or reproach"` | Yes — regex sweep over the whole dock's text |

The dock reads the count via `getDueReviews({sourceId, limit: 1})` and takes `total_due`.
That is sound: `due_for_user` computes `total` before the limit
(`backend/app/infrastructure/db/repositories.py:1573`), pinned by the pre-existing
`test_repositories_quiz.py::test_due_for_user_respects_limit_but_counts_full_total`.

### P3 — Every note keeps where it came from

| AC | Sensor | Asserts the spec outcome |
| --- | --- | --- |
| 1 — anchorless create rejected, nothing persisted | `test_web_notes.py::test_creating_a_note_without_an_anchor_has_no_route` (405 + list still empty) | Yes |
| 2 — passage capture persists note + anchor atomically | `test_notes_application.py::test_capture_highlight_creates_a_note_and_anchor`, `…_without_a_quote_creates_a_section_level_anchor`, `…_without_a_quote_persists_nothing_when_the_body_is_over_cap`; `test_web_notes.py::test_capture_highlight_without_a_quote_over_cap_body_persists_nothing` (neither note nor highlight survives a 422) | Yes |
| 3 — save-an-answer persists with the citation's anchor | `answer-notes.test.ts::"captures a highlight on the first citation with the exact payload"`, `…"still saves the answer, on the same anchor with no quote, after a stale capture"`, `…"goes straight to the anchor-only capture when the snippet has no paragraph"`; `ask-panel.test.tsx::"still saves the answer, anchored, through the real notes clients on a stale capture (409)"` | Yes — and the `stale_capture` error kind is preserved (trap 2) |
| 4 — legacy anchorless notes list, render, edit, delete | `test_web_notes.py::test_anchorless_note_still_lists_and_opens`, `…_still_edits_and_stays_anchorless`, `…_still_deletes`, `…_anchorless_and_anchored_notes_list_side_by_side` | Yes — and the edit test pins WSN-16 (no anchored/anchorless transition) |
| 5 — no title-only creation control | `notes-screen.test.tsx::"offers no title-only creation control (P3 AC 5)"`; `notes-client.test.ts::"exposes no helper that creates a note without an anchor"`, `…"has no browser-side module posting to the notes collection"` (source-tree scan) | Yes — the source scan is a structural sensor a re-added client cannot slip past |

### P4 — `/notes` as the cross-book surface

| AC | Sensor | Asserts the spec outcome |
| --- | --- | --- |
| 1 — unfiltered lists across every book | `notes-screen.test.tsx::"lists notes across every book when no book is picked (P4 AC 1)"` (request carried no scope); `test_web_notes.py::test_list_notes_newest_edited_first_and_owner_scoped` (`anchor` is `null` on the cross-book list) | Yes |
| 2 — book filter narrows to that book | `notes-screen.test.tsx::"narrows the list to one book and restores it when cleared (P4 AC 2, 3)"` | Yes |
| 3 — clearing restores the cross-book list | same test | Yes |
| 4 — unowned `source_id` → 404, no disclosure | `test_web_notes.py::test_list_notes_non_owned_and_unknown_source_return_identical_404` (asserts the two response bodies are equal); `test_notes_application.py::test_list_notes_scoped_to_an_unowned_book_is_not_found` + `…_unknown_book_is_the_same_not_found`; `notes-screen.test.tsx::"reads a book the caller does not own as a message, not a crash (P4 AC 4)"` | Yes |

### Edge cases

| Edge case | Sensor |
| --- | --- |
| `source_id` with zero notes → empty list, not an error | `test_web_notes.py::test_list_notes_scoped_to_a_book_with_no_notes_is_an_empty_list`; `test_repositories_notes.py::test_list_summaries_scoped_to_a_book_with_no_notes_is_empty`; `notes-screen.test.tsx::"says a picked book has nothing yet rather than nothing at all"` |
| Note anchored to a book the caller no longer owns is not returned under that filter | Collapses into the 404 rule — `test_list_notes_non_owned_and_unknown_source_return_identical_404` |
| New capture appears in the open Notes tab without a reload | `dock-notes-tab.test.tsx::"shows a note written from the page without a reload"`; `chapter-reader.test.tsx::"shows a note captured from the page in the open Notes tab, no reload"` |
| Zero note count → no badge, not a "0" | `dock-notes-tab.test.tsx::"carries no count at all when the book holds no notes"`; `dock-review-tab.test.tsx::"offers no grading when this book has nothing due"` |
| Review started but the queue emptied elsewhere → existing flow handles it | `review-screen.test.tsx::"shows a nothing-due empty state when the queue is empty"` (shipped, unchanged — the dock reuses the component rather than forking it) |

### Requirements WSN-01…WSN-16

| Req | Covered by |
| --- | --- |
| WSN-01 | P1 AC 1 sensors |
| WSN-02 | P1 AC 2 sensors + `test_repositories_notes.py::test_list_summaries_scoped_to_a_book_carries_the_passages_snapshot` |
| WSN-03 | P1 AC 3 sensors |
| WSN-04 | P1 AC 4 sensor |
| WSN-05 | P1 AC 5 + P2 AC 4 sensors |
| WSN-06 | P2 AC 1 sensor |
| WSN-07 | P2 AC 2 sensors (shipped `ReviewScreen` rendered, not re-implemented) |
| WSN-08 | P3 AC 1/5 sensors |
| WSN-09 | P3 AC 4 sensors |
| WSN-10 | P4 AC 2/4 sensors |
| WSN-11 | **Partial** — `test_web_notes.py::test_list_notes_rejects_a_source_id_that_is_not_a_uuid` covers UUID validation; the "list bounds" half has no implementation and no sensor. See Gap 1. |
| WSN-12 | P3 AC 2 sensors (over-cap body persists neither note nor anchor) |
| WSN-13 | P4 AC 4 sensors; the capture limiter is still pinned by `test_capture_rate_limit_returns_429` and `test_capture_untrusted_origin_returns_403` |
| WSN-14 | `test_repositories_notes.py::test_list_summaries_book_scope_keeps_a_total_newest_edited_first_order` (two notes at the same instant, id tiebreak asserted) |
| WSN-15 | P1 AC 6 sensors |
| WSN-16 | `test_web_notes.py::test_anchorless_note_still_edits_and_stays_anchorless` |

### Design invariants I-1…I-10

All ten have a sensor. I-1 additionally verified structurally: `notes.add(...)` is called
from exactly one place in the whole backend — `CaptureHighlight`
(`backend/app/application/notes.py:370`) — and `web/notes.py` now has one `router.post`,
the highlights route. I-8 verified by mutation (M-B7 below). I-9 by
`reader-panel.test.tsx::"leaves the open Ask thread exactly where it was after a trip
through Notes"` and `chapter-reader.test.tsx::"renders no panel for a value naming no tab
(edge case)"`.

## Discrimination sensor (mutation testing)

Seventeen behaviour-level faults injected into the changed code, each run against only the
relevant test file(s). **Every mutant was killed.** All mutations were reverted with
`git checkout`; the working tree is clean and `make lint` passes on it.

| # | Mutation | Where | Result |
| --- | --- | --- | --- |
| B1 | Drop the ownership check on the book-scoped list | `application/notes.py` `ListNotes.__call__` | **Killed** — 3 tests |
| B2 | Return an empty list instead of 404 for an unowned source | `application/notes.py` `ListNotes.__call__` | **Killed** — 3 tests |
| B3 | Representative anchor = **latest** instead of earliest | `db/repositories.py` `list_summaries` order_by | **Killed** — 2 tests |
| B4 | Semi-join → row-per-anchor join (twice-anchored note appears twice) | `db/repositories.py` `list_summaries` | **Killed** — 4 tests |
| B5 | Skip the anchor write on a quote-less capture (note without anchor) | `application/notes.py` `CaptureHighlight` | **Killed** — 4 tests |
| B6 | Return a page (`1`) for an anchor that no longer resolves | `application/notes.py` `ListNotes._page_of` | **Killed** — 2 tests |
| B7 | Page ignores book-global word counts (`page_at(0, …)`) | `application/notes.py` `ListNotes._page_of` | **Killed** — 2 tests |
| B8 | Endpoint silently drops `source_id` (lists every book) | `web/notes.py` `list_notes` | **Killed** — 6 tests |
| B9 | Passage dropped from the wire (`anchor=None` always) | `web/notes.py` `NoteSummaryView.from_summary` | **Killed** — 3 tests |
| B10 | Drop the `id` tiebreak from the list order (order no longer total) | `db/repositories.py` `list_summaries` | **Killed** — 1 test |
| F1 | Conversation list rendered on every tab (`isConversationTab` → true) | `reader-panel.tsx` | **Killed** — 1 test |
| F2 | Tab renders a `0` badge instead of no badge | `reader-panel.tsx` `TabCount` | **Killed** — 2 tests |
| F3 | Page rendered for an orphaned anchor (`page ?? 1`) | `dock-notes-panel.tsx` `NoteRowPassage` | **Killed** — 1 test |
| F4 | Answer-save fallback capture deleted (answer silently lost) | `lib/answer-notes.ts` | **Killed** — 3 tests |
| F5 | Client drops `source_id` from the query | `lib/notes.ts` `listNotes` | **Killed** — 6 tests |
| F6 | Notes tab ignores the capture refresh signal | `reader-panel.tsx` `useBookNotes(sourceId, 0)` | **Killed** — 2 tests |
| F7 | Unknown `?panel=` no longer falls back to closed | `reader-panel.tsx` `dockTabFromParam` | **Killed** — 1 test |

(17 mutations in total; the table numbers B1–B10 backend and F1–F7 frontend.)

## Gaps

### Gap 1 — WSN-11's "list bounds" clause is unimplemented and unsensed (spec-precision)

`spec.md:59` resolves the bounds dimension as "the dock's list is bounded like the shipped
list conventions — WSN-11". Nothing bounds it. `GET /api/notes` takes no `limit`
(`backend/app/infrastructure/web/notes.py:302-317`) and `list_summaries` issues no `LIMIT`
(`backend/app/infrastructure/db/repositories.py:1782-1849`), so a book with thousands of
notes returns every row into a 26rem dock column. The clause is also too vague to have a
single correct assertion: the shipped conventions it points at disagree with each other —
`GET /api/reviews/due` takes `limit` (default 20, `le=100`) and the conversations list
paginates, so "like the shipped conventions" names no specific bound.

**Severity: low.** Not a regression — the notes list was unbounded before this cycle and
the diff neither adds nor removes a bound — and no correctness or authorization property
depends on it. But WSN-11 is marked covered by task B3, and half of what it claims has no
sensor. Recorded rather than fixed (verifiers report, they do not fix).

### Observation — fake/real ordering tiebreak diverge (no impact on this verdict)

`FakeNoteRepository.list_summaries` sorts `(updated_at, str(id))` with `reverse=True`
(`backend/tests/fakes.py:768`), i.e. id **descending** on a tie, while the real repository
orders `updated_at DESC, id` — id **ascending** (`repositories.py:1795`). Pre-existing, not
introduced here, and harmless today because I-7's real sensor is the repository test, which
asserts the true ascending tiebreak (mutation B10 confirms it discriminates). Noted only so
a future application-layer ordering assertion is not written against the fake.

## Things I could not verify

None. Every acceptance criterion, every WSN requirement, and every design invariant has a
named sensor above, except the "list bounds" half of WSN-11, which is reported as Gap 1
rather than passed.
