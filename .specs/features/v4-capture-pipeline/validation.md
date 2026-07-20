# v4-capture-pipeline Validation

**Spec**: `spec.md` · **Design**: `design.md` · **Tasks**: `tasks.md`
**Diff range**: `main..HEAD` (21 commits, HEAD `1a5de8b`) — 55 files, ~8455 insertions
**Verifier**: fresh sub-agent, author ≠ verifier, evidence-or-zero
**Date**: 2026-07-19

> **Status after review (2026-07-19, later).** This record is a snapshot of the branch as
> verified, and the branch has moved since. Both ranked gaps are closed: the rate-limit
> sensor exists (M16's survivor is dead — removing `rate_limit_quiz` now fails three
> tests), and the unconsumed `updateCard` client was removed. Six review lanes then found
> two real defects this pass did not — an `AcceptCard` fall-through that could schedule
> against a row that was never inserted, and an `UpdateCard` text collision reaching the
> database as a 500. Both are fixed with sensors. Neither was reachable by mutation
> testing: each lives on a branch no test executed, so there was nothing to mutate.
> Full reasoning in `review-triage.md`.

---

## Verdict: **PASS**, with one gap that should be closed before merge

All 36 acceptance criteria carry evidence: for each one, a named test asserts the
outcome the spec states, not merely that the code path runs. Twenty behaviour-level
mutations were injected — the seven priority targets named in `tasks.md` plus thirteen
of the verifier's own, aimed at the places coverage looked thinnest. **Nineteen were
killed. One survived.**

The survivor (M16, below) is a *missing sensor*, not a missing behaviour: the rate
limiter is correctly wired on all three card routes, but nothing in the suite would
notice if it were removed. That is why this is a PASS rather than a FAIL — no
acceptance criterion is unmet and no user-facing defect was found. It is still the
top-ranked gap, because the undefended dependency is the stated mitigation for the
design's own highest-ranked risk.

Three criteria are met at a coarser granularity than a literal reading of the spec
implies (CAP-18, CAP-21, and the untestable half of CAP-26). In every case the tests
are honestly named and do not overclaim. They are recorded as spec-precision gaps
rather than failures.

---

## Gates (re-run and confirmed by the verifier, not taken on report)

| Gate | Command | Result |
| --- | --- | --- |
| Backend suite | `.venv/bin/python -m pytest -q` (local providers, `learny_test`) | **1360 passed, 10 skipped**, exit 0 |
| Backend lint | `.venv/bin/python -m ruff check .` | **All checks passed!** |
| Frontend suite | `npm test` | **463 passed across 48 files** |
| Types | `npx tsc --noEmit` | exit 0, no diagnostics |
| Build | `npm run build` | succeeds |

The 10 backend skips are all pre-existing and environmental (no `docling`, no live
provider keys, snapshot-recording opt-in) — none relate to this cycle.

`ruff format --check` reports 95 of 205 files would be reformatted, on `main` as well
as here. The project selects `E,F,I,UP,B` for `ruff check` and configures no formatter,
so this is a repo-wide pre-existing condition and not a regression from this cycle.

### Environment note for future runs

Mutations that change a migration require the schema to be rebuilt; reverting the
migration file alone leaves the previous mutant's schema in place. All mutation runs
here used a throwaway `learny_mut` database, dropped and recreated between migration
mutants, so `learny_test` was never written to beyond the initial baseline run. It was
verified afterwards to be at `0012_card_provenance` with zero rows in `users`,
`sources`, `notes`, `note_anchors`, and `quiz_items`. The working tree was confirmed
clean (`git status --porcelain` empty) after every mutation.

---

## Per-criterion evidence

Legend: **✓** outcome asserted and confirmed · **✓\*** met, with a precision caveat below.

### P1 — Create a card from a highlighted passage

| ID | Criterion | Evidence | |
| --- | --- | --- | --- |
| CAP-01 | Activating "Create card" requests quote-scoped suggestions, rendered as pending chips | `capture-popover.test.tsx` "is a live verb that hands the card flow to the reader"; `chapter-reader.test.tsx` "captures the highlight first, then asks for suggestions on the anchor it produced"; `cards-client.test.ts` "POSTs the suggestions path with the CSRF token and the highlight id" | ✓ |
| CAP-02 | At most `LEARNY_QUIZ_MAX_SUGGESTIONS` (default 3) candidates | `test_application_cards.py::test_suggestions_are_capped_at_the_configured_maximum`; adapter-level caps in `test_quiz_local.py::test_suggest_cards_never_exceeds_the_limit` and `test_quiz_anthropic.py::test_suggest_cards_never_exceeds_the_limit`; default pinned by `test_config.py::test_quiz_settings_defaults` (`quiz_max_suggestions == 3`) | ✓ |
| CAP-03 | Candidate whose `anchor_quote` is absent from the section text is discarded, never returned | `test_candidate_whose_quote_is_absent_from_the_section_is_discarded` | ✓ |
| CAP-04 | Cloze candidate with an invalid mask is discarded, never returned | `test_cloze_candidate_with_an_invalid_mask_is_discarded` | ✓ |
| CAP-05 | Accepting persists exactly one item and creates initial FSRS scheduling, due immediately | `test_accepting_persists_exactly_one_card_due_immediately`; `test_web_cards.py::test_accept_returns_201_with_provenance_and_schedules_the_card`; `test_accepted_card_appears_in_the_due_queue` | ✓ |
| CAP-06 | Edited question/answer is the text persisted | `test_accepting_stores_the_edited_text_not_the_suggested_text`; `test_web_cards.py::test_accept_persists_the_edited_text_as_submitted`; `card-suggestions.test.tsx` "persists the edited text, not the suggested text" | ✓ |
| CAP-07 | Discarding persists nothing | `test_discarding_a_suggestion_persists_nothing`; `card-suggestions.test.tsx` "drops the candidate without any request at all" (asserts zero requests) | ✓ |
| CAP-08 | Generation failure surfaces a retryable error, highlight untouched | `chapter-reader.test.tsx` "keeps the highlight and retries only generation when suggestions fail"; `card-suggestions.test.tsx` "renders the failure on the chip and accepts a retry" and "keeps a failure on its own chip, leaving the others acceptable" | ✓ |
| CAP-09 | Request not owned by the caller → 404 | `test_anchor_whose_note_belongs_to_another_user_is_not_found`, `test_anchor_belonging_to_a_different_source_is_not_found`, `test_unknown_anchor_is_not_found`; `test_web_cards.py::test_suggestions_cross_owner_and_wrong_source_anchors_return_identical_404` (asserts *identical* responses, so nothing's existence leaks) | ✓ |

### P1 — Stable identity and typed provenance

| ID | Criterion | Evidence | |
| --- | --- | --- | --- |
| CAP-10 | Item records a typed origin of `deck` or `highlight` | `test_domain_quiz.py::test_item_origins_are_exactly_deck_and_highlight`, `test_quiz_item_defaults_to_deck_origin_with_no_provenance`; `test_repositories_quiz.py::test_upsert_persists_origin_and_provenance`, `test_deck_items_default_to_deck_origin_with_no_provenance`; migration default proven on a genuine pre-0012 row by `test_migration_0012_adds_card_origin_and_note_provenance` | ✓ |
| CAP-11 | Card accepted from a highlight links to the originating anchor | `test_accepted_card_records_highlight_origin_and_provenance`; `test_web_cards.py::test_accept_returns_201_with_provenance_and_schedules_the_card` | ✓ |
| CAP-12 | Text change keeps identity, FSRS scheduling, and review log unchanged | `test_repositories_quiz.py::test_update_text_leaves_scheduling_and_review_log_byte_identical` (DB-level, the load-bearing sensor); `test_web_cards.py::test_patch_rewrites_text_and_leaves_identity_and_scheduling_untouched`; `test_application_cards.py::test_editing_a_card_keeps_its_id_and_due_date` and `test_editing_a_card_never_writes_scheduling_or_the_review_log` (fake-level — see G5) | ✓ |
| CAP-13 | Two `deck` items sharing a `content_key` for one source collapse to one row (unchanged) | `test_two_deck_items_with_one_content_key_collapse_to_one_row`; pre-existing `test_upsert_same_content_key_updates_content_and_returns_false` and `test_reupsert_preserves_scheduling_and_review_log` still green | ✓ |
| CAP-14 | A `highlight` item sharing a `content_key` across a different origin, source, or anchor is a distinct row | `test_two_highlight_items_share_a_content_key_across_different_anchors`, `test_highlight_item_does_not_collide_with_a_deck_item_of_the_same_key`, `test_reaccepting_identical_text_from_one_anchor_is_idempotent` (the same-anchor idempotence carve-out) | ✓ |
| CAP-15 | Deleting the note/anchor keeps the card, clears provenance, keeps it renderable | `test_repositories_quiz.py::test_deleting_the_origin_note_keeps_the_card_due_with_null_provenance`; `test_web_cards.py::test_deleting_the_origin_note_leaves_the_card_due_with_null_provenance`; `test_migrations.py::test_migration_0012_adds_card_origin_and_note_provenance` exercises the FK's SET NULL for real and asserts `source_excerpt == "the quoted sentence"` survives | ✓ |
| CAP-16 | A card with provenance shows its origin note's title at review | `test_repositories_quiz.py::test_due_queue_carries_origin_note_provenance`; `test_web_cards.py::test_due_queue_shows_the_origin_note_title_for_a_highlight_card`; `review-screen.test.tsx` "shows the origin note's title for a card made at a passage" | ✓ |
| CAP-17 | Re-ingestion applies the existing ladder to `highlight` cards without touching scheduling or review log | `test_reconcile_quiz.py::test_reconcile_matrix_applies_to_highlight_origin_items` (keep/stale/relocate/orphan) and `test_reconcile_keeps_a_highlight_card_identity_scheduling_and_provenance`; step order pinned by `test_worker_tasks.py::test_note_reconcile_runs_after_quiz_reconcile` | ✓ |

### P1 — Margin rail

| ID | Criterion | Evidence | |
| --- | --- | --- | --- |
| CAP-18 | Rail lists the chapter's highlights and notes in document order | `margin-rail.test.tsx` "lists only the loaded chapter's highlights, in document order" and "keeps the server's order for several highlights inside one section"; `chapter-reader.test.tsx` "shows the loaded chapter's highlights and drops a highlight from another chapter" | ✓\* (G4) |
| CAP-19 | An entry with a note body shows the note's title | `margin-rail.test.tsx` "shows the origin note's title when the highlight carries a note body" and "identifies a bare highlight by its quote, with no note title"; backing data proven by `test_web_notes.py::test_list_source_highlights_carries_note_title_and_body_flag` and `test_domain_quiz.py::test_source_highlight_carries_note_title_and_body_flag` | ✓ |
| CAP-20 | An orphaned highlight is listed with an orphaned indicator, rendered from its snapshot | `margin-rail.test.tsx` "renders an orphaned highlight from its snapshot with the shared orphan indicator"; distinguished from stale by "marks a stale highlight without treating it as orphaned" and "shows no status badge for an active highlight" | ✓ |
| CAP-21 | Activating an entry whose highlight is painted scrolls to it and flashes it | `margin-rail.test.tsx` "jumps to the entry's anchor when its highlight is painted in the chapter"; `chapter-reader.test.tsx` "scrolls to and flashes the section a rail entry points at" (asserts `scrollIntoView({behavior:"smooth",block:"start"})`, `data-highlight="on"` on the section heading, and the URL anchor keeping step) | ✓\* (G3) |
| CAP-22 | Activating an orphaned entry does not attempt a scroll and offers the origin note | `margin-rail.test.tsx` "never attempts a scroll for an orphaned entry, offering its note instead" — asserts there is **no button at all** on the entry, so the rule holds structurally rather than by a conditional inside a handler | ✓ |
| CAP-23 | A chapter with no annotations renders an empty state, not an empty column | `margin-rail.test.tsx` "says the chapter has nothing in it rather than rendering an empty column" and "shows the empty state when every highlight belongs to another chapter" | ✓ |
| CAP-24 | The rail is hidden while the Ask/Teach panel is open | `chapter-reader.test.tsx` "hides the rail while the ask panel is open (AD-139)" and "renders the rail again once the panel is closed" | ✓ |

### P1 — Review pin

| ID | Criterion | Evidence | |
| --- | --- | --- | --- |
| CAP-25 | A card shown at review renders a pin control targeting its cited anchor | `review-screen.test.tsx` "offers the pin before the answer is revealed" | ✓ |
| CAP-26 | Activating the pin navigates to the reader at that source and anchor | `review-screen.test.tsx` "renders the pin through readUrl so the reader route never drifts" (asserts `href === readUrl(sourceId, anchor)`) | ✓\* |
| CAP-27 | A card with note provenance additionally offers the origin note | `review-screen.test.tsx` "shows the origin note's title for a card made at a passage" and "renders no note affordance for a card without provenance" | ✓ |

### P2 — Single-key shortcuts

| ID | Criterion | Evidence | |
| --- | --- | --- | --- |
| CAP-28 | Highlight key performs the "Highlight" verb | `chapter-reader.test.tsx` "captures the selection on the highlight key, exactly as the verb does" | ✓ |
| CAP-29 | Card key performs the "Create card" verb | `chapter-reader.test.tsx` "starts the card flow on the card key"; scoping proven by "does nothing on a bare key press with no selection open" | ✓ |
| CAP-30 | Reveal key reveals an unrevealed card's answer | `review-screen.test.tsx` "reveals the answer on the space bar"; `use-key-shortcuts.test.tsx` "maps the space bar to the space binding" | ✓ |
| CAP-31 | Grade keys 1–4 submit that grade on a revealed card | `review-screen.test.tsx` "submits the pressed grade once the answer is revealed" and "does not grade while the answer is still hidden" | ✓ |
| CAP-32 | Key ignored when the target is an input, textarea, or contenteditable | `use-key-shortcuts.test.tsx` three guard tests plus "still fires from a region explicitly marked not editable"; end-to-end in `review-screen.test.tsx` "ignores a grade key typed into a text field" and `chapter-reader.test.tsx` "ignores the highlight key typed into a text field" | ✓ |
| CAP-33 | Key ignored when Ctrl, Meta, or Alt is held | `use-key-shortcuts.test.tsx` per-modifier guard tests; `chapter-reader.test.tsx` "ignores the highlight key while a modifier is held, and never binds b"; `use-key-shortcuts.test.tsx` "leaves b alone so the sidebar keeps its own shortcut" | ✓ |

### P2 — Friction budget

| ID | Criterion | Evidence | |
| --- | --- | --- | --- |
| CAP-34 | Highlight from an existing selection ≤ 1 pointer action | `friction-budget.test.tsx` "costs one pointer action from an existing selection" — meters the clicks *and* asserts the POST actually landed | ✓ |
| CAP-35 | Card from an existing selection ≤ 2 pointer actions (invoke, accept) | `friction-budget.test.tsx` "costs two pointer actions from an existing selection: invoke, accept" — also asserts the highlight POST fired once, so the card is genuinely scheduled rather than merely requested | ✓ |
| CAP-36 | Review card → its passage costs 1 pointer action | `friction-budget.test.tsx` "costs one pointer action, with the pin reachable before any interaction" | ✓ |

**Totals: 36 of 36 covered. 0 with no evidence. 3 with a precision caveat (G3, G4, and the disclosed jsdom limit on CAP-26).**

---

## Discrimination sensor

Twenty behaviour-level faults injected into scratch state, each reverted immediately;
the working tree was confirmed clean after every one and nothing was committed.

### The seven priority targets from `tasks.md`

| # | Mutation | Result | Killed by |
| --- | --- | --- | --- |
| M1 | Deck partial unique index widened to cover all origins (`WHERE origin IS NOT NULL`) | **killed** | `test_two_highlight_items_share_a_content_key_across_different_anchors`, `test_highlight_item_does_not_collide_with_a_deck_item_of_the_same_key` |
| M2 | `update_text` also rewrites `quiz_item_scheduling.due` | **killed** | `test_update_text_leaves_scheduling_and_review_log_byte_identical`, `test_web_cards.py::test_patch_rewrites_text_and_leaves_identity_and_scheduling_untouched` |
| M3 | Provenance FK changed to `ON DELETE CASCADE` | **killed** | `test_deleting_the_origin_note_keeps_the_card_due_with_null_provenance`, `test_web_cards.py::test_deleting_the_origin_note_leaves_the_card_due_with_null_provenance`, `test_migration_0012_adds_card_origin_and_note_provenance` |
| M4 | QC filter dropped from `SuggestCards` (`survivors = list(candidates)`) | **killed** | 5 tests, incl. `test_candidate_whose_quote_is_absent_from_the_section_is_discarded` and `test_cloze_candidate_with_an_invalid_mask_is_discarded` |
| M5 | Embedding dedup (cosine ≥ 0.90) applied on accept | **killed** | `test_a_near_duplicate_of_an_existing_card_is_still_accepted` (+ 9 others) |
| M6 | `isTypingTarget` guard removed from the shortcut hook | **killed** | 5 tests across `use-key-shortcuts`, `review-screen`, `chapter-reader` |
| M7 | Rail's chapter filter removed | **killed** | `MarginRail` "lists only the loaded chapter's highlights", "shows the empty state when every highlight belongs to another chapter", `ChapterFlow` "drops a highlight from another chapter" |

### Thirteen additional probes by the verifier

| # | Mutation | Result | Killed by |
| --- | --- | --- | --- |
| M8 | `create_scheduling` call removed from `AcceptCard` | **killed** | `test_accepting_persists_exactly_one_card_due_immediately` (+ 5) |
| M9 | `SuggestCards` returns uncapped survivors | **killed** | `test_suggestions_are_capped_at_the_configured_maximum` |
| M10 | Rail rendered even while the panel is open | **killed** | `ChapterFlow` "hides the rail while the ask panel is open" |
| M11 | Orphaned rail entry rendered as a jump button | **killed** | `MarginRail` "never attempts a scroll for an orphaned entry" |
| M12 | Note title shown regardless of `has_body` | **killed** | `MarginRail` "identifies a bare highlight by its quote, with no note title" |
| M13 | Pin drops the cited anchor from its href | **killed** | `ReviewScreen` "renders the pin through readUrl", `Friction budget: review jump-back`, `ReviewScreen` session-flow leg |
| M14 | Provenance link rendered unconditionally | **killed** | `ReviewScreen` "renders no note affordance for a card without provenance" |
| M15 | `0012` downgrade duplicate guard disabled (`if False:`) | **killed** | `test_migration_0012_downgrade_refuses_to_destroy_duplicate_cards` |
| **M16** | **`Depends(rate_limit_quiz)` removed from all three card routes** | **SURVIVED** | — nothing. Full backend suite: 1360 passed, 10 skipped |
| M17 | `AcceptCard` mints with `note_anchor_id=None` | **killed** | `test_accepted_card_records_highlight_origin_and_provenance` (+ 5) |
| M18 | `items_for_reconcile` filters to `origin = 'deck'` | **killed** | `test_reconcile_and_list_reads_carry_origin_and_provenance` (+ 5) |
| M19 | Ingestion reconciles notes before quiz | **killed** | `test_note_reconcile_runs_after_quiz_reconcile` |
| M20 | Modifier bail-out removed from the shortcut hook | **killed** | 5 tests across the three suites |

**19 killed, 1 survived.**

---

## Adversarial review of the self-flagged weak areas

**The rail as a document-order sibling column.** The chosen proxy is honest. jsdom
cannot sense layout, and the tests never claim it does — they assert content, chapter
scoping, ordering, orphan treatment, empty state, and panel-conditioned visibility,
all of which are real DOM facts. No test is named or worded as if it verified
marginalia alignment. The genuine blind spot is that nothing confirms the `<aside>`
actually sits right of the article at `lg` and after it below `lg`; that is disclosed
in the design's Risks table and is a fair limit to accept rather than fake.

**`line-clamp-3` and real link navigation.** Both correctly identified as untestable
here and both inconsequential. `line-clamp-3` is presentational; worst case is a taller
rail entry. For navigation, asserting the `href` of a Next `<Link>` is the right
contract to pin — M13 confirms that assertion is a live sensor, not decoration.

**The review pin moved from the revealed footnote into the question block.** This is a
legitimate reading of both criteria, not a deviation. CAP-25 says the pin is rendered
"when a card is shown at review" — the question block renders on every card, so this
placement satisfies CAP-25 *more* completely than the footnote did, where the pin only
existed after a reveal. CAP-36's one-action budget then makes the move mandatory: from
the footnote the jump would cost two actions (reveal, then click). The two criteria
point the same way, and "offers the pin before the answer is revealed" pins the
result. The code comment's reasoning about a failed card becoming a re-read is sound.

**`lib/cards.ts` exports `updateCard` with no UI consumer.** Confirmed dead code — the
only references outside the module are its own tests. It is not a correctness problem
and CAP-12 is fully proven at the API and database layers, so no acceptance criterion
depends on it. But two things follow. Its three client tests exercise nothing a user
can reach, which inflates the apparent coverage of the edit path. And more
substantively, the shipped UI offers no way to edit a card at all, so the P1 story
behind CAP-12 — *"I want a card I made from a highlight to keep its scheduling even
after I reword it"* — has no user-facing reword path this cycle. The system property
holds; the user capability is backend-only. See G2.

**The `0012` downgrade guard.** Sound, and correct to raise rather than auto-delete.
The SQL is `SELECT source_id, content_key, count(*) FROM quiz_items GROUP BY
source_id, content_key HAVING count(*) > 1`, which cannot match when no duplicates
exist. Verified empirically: a clean `upgrade → downgrade → upgrade` round trip
completes without the guard firing. It also cannot fire on a database upgraded from
0011, because the old global unique made duplicates unreachable before 0012 existed —
any duplicate is therefore genuinely post-0012 and genuinely user-authored. The guard
runs before the index drops, so a refusal leaves the schema untouched. M15 confirms the
test is a real sensor. Deleting someone's study material to make a schema rollback
succeed would be irreversible and is properly an operator's decision; raising with the
affected sources named is the right call.

---

## Ranked gaps

**G1 — No rate-limit sensor on any card route.** *(highest; cheap to close)*
Removing `Depends(rate_limit_quiz)` from all three routes in
`app/infrastructure/web/cards.py` leaves the entire backend suite green (M16). The
dependency is correctly wired today, so there is no live defect — but nothing would
catch its removal. This matters more than a routine coverage hole for two reasons: the
spec lists it as an explicit edge case ("suggestion generation SHALL be throttled on
the same limiter as deck generation"), and the design's Risks table names
`rate_limit_quiz` as the mitigation for its own top-ranked risk — the app's first
synchronous LLM call inside a request handler. The mitigation is undefended. The
`test_web_cards.py` fixture installs a 1000-attempt limiter, so a test must override
it, exactly as `test_web_quiz.py::test_deck_post_rate_limit_returns_429` (line 350)
already does. One test, following an existing pattern. *Recommend closing before merge.*

**G2 — `updateCard` is dead code and no edit affordance ships.** `lib/cards.ts`
exports it with tests and no consumer. Either wire an edit control into the review or
suggestion surface, or drop the function and its tests and let the PATCH route wait for
the cycle that uses it. As it stands the reword half of the P1 identity story is
reachable only via the API.

**G3 — CAP-21 is delivered at section granularity.** The spec says activating a rail
entry scrolls to *the highlight* and flashes *it*; the implementation reuses
`handleShowInBook`, which scrolls to the containing section and flashes the section
heading. Two highlights in one section therefore produce identical jumps, and the rail
cannot distinguish them. The design named this reuse explicitly and the test is
honestly titled "scrolls to and flashes **the section** a rail entry points at" — no
overclaim — but a literal reading of CAP-21 is finer-grained than what ships.

**G4 — CAP-18 says "highlights and notes"; the rail shows only anchored highlights.**
Its sole data source is `highlights_for_source`, so a note with no anchor in the loaded
chapter never appears. This is consistent with CAP-A7's framing of the rail as
reading-column furniture with `/notes` as the cross-book surface, and every note created
through capture does carry an anchor — so in practice the gap is narrow. Worth
recording so the wording is not later read as a promise that was met.

**G5 — Some application-layer tests cannot enforce the invariant they name.**
`test_editing_a_card_keeps_its_id_and_due_date` survived M2, and
`test_the_same_text_from_a_different_highlight_is_a_distinct_card` survived M1, because
both run against fakes that do not enforce database behaviour. Both criteria are
genuinely covered — the DB-level tests exist and killed both mutants. Recorded so that
nobody deletes a DB-level test believing the fake-level one covers it.

**G6 — The rail renders `<details open>` at every breakpoint.** The design specified a
plain sibling column at `lg` and up with the collapsible form only below `lg`, so the
"In this chapter" disclosure control appears at desktop width too. Cosmetic, untested
either way, and not covered by any criterion.

---

## Nothing else found

Beyond the above, the verifier looked specifically for and did not find: ownership
leaks (the 404 non-disclosure is asserted as *identical* responses across the
cross-owner and wrong-source legs), CSRF or origin gaps (all three routes tested on
both), scheduling or review-log writes on any edit path, deck-generation regressions
(the pre-existing upsert and re-upsert tests are untouched and green), or reconcile
coupling between the two aggregates. The suspected weak spots named by the builders
were each probed with a dedicated mutation; all were killed.
