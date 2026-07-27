# `v6-workspace-notes` — review triage

PR #54. Six review lanes (Security, Requirements, Test Coverage, Architecture,
Regression/Hallucination, Performance) produced 8 inline comments and 1 issue comment.
Each is judged against the code as it exists, not against the reviewer's authority.
Comments are deleted after this record is written — this file is the surviving reasoning.

| # | Source | Location | Finding | Verdict | Action | Rationale |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | regression `3654182095` | `web/notes.py:432` | Deleting `POST /api/notes` removed the only create-time `enqueue_embed`; `capture_highlight` takes no enqueuer, so no new note is ever embedded | **REAL — severe** | **fix** | Verified directly: `enqueue_embed` now has exactly one call site (`update_note:368`), and the notes semantic arm filters `WHERE embedding IS NOT NULL` (`db/retrieval.py:178`). Every note created after this cycle would be invisible to notes retrieval until its body happened to be edited — a shipped capability (ADR-0026 §4) silently broken by a deletion this cycle made. My design never named embedding as an invariant, so the Verifier had no mutation for it: a sensor-blind gap, which is precisely what an independent review is for |
| 2 | requirements `5086875907` | `dock-notes-panel.tsx` `NoteRowPassage` | The quote `<blockquote>` renders unconditionally, but section-level anchors carry `quote_exact = ""` | **REAL** | **fix** | This PR is what makes empty quotes reachable (the answer-save fallback, any quote-less capture). An empty bordered block would render for exactly the notes the cycle newly enables. None of the nine dock-notes tests uses an empty quote |
| 3 | architecture `3654176237` + tests `3654174992` | `dock-review-panel.tsx:96` | The Review count has no refresh contract; grading inside the dock leaves the tab strip stale | **REAL** | **fix** | Two lanes reached this independently. The mutation happens *inside* the dock, and the Notes tab in this same PR already ships the correct contract (`useBookNotes(sourceId, refreshToken)` bumped at `chapter-reader.tsx:521/563`). The asymmetry is the defect |
| 4 | performance `3654172340` | `application/notes.py:253` | Page derivation is O(notes × sections): `locate` scans the index and `words_before_row` re-sums from scratch, once per note | **REAL** | **fix** | Confirmed by reading the helpers. The list is unbounded (AD-218), so cost is super-linear in a way my bounds disclosure did not cover — it reasoned about row count only. The fix mirrors the `first_by_anchor`/`alias_to_section` hoist already used by `ReconcileNoteAnchors` in the same file |
| 5 | tests `3654174443` | `test_notes_application.py:901` | The section-level reconcile test seeds anchor `ch1` against a surviving section whose anchor is also `ch1`, so it passes whether or not the code rewrites to the canonical anchor; `section_path` asserted nowhere | **REAL** | **fix** | A tautological assertion is worse than no test — it reports coverage it does not provide. The alias leg is the only way the stored anchor can differ from the survivor's, and it is covered for quoted anchors but not through the new quote-less short-circuit |
| 6 | tests `3654174489` | `application/notes.py:344` | `if quote_exact.strip():` — the `.strip()` has no test | **REAL — minor** | **fix** | Cheap and genuine: with plain truthiness a whitespace-only quote would 409 instead of 201 and persist whitespace into the snapshot. One test pins the branch |
| 7 | tests `3654174910` | `notes-screen.tsx:99` | The documented "library fails to load → picker simply absent" contract is untested | **REAL — minor** | **fix** | A documented contract with a swallowing `.catch` and no sensor. One test |
| 8 | architecture `3654176478` | `reader-panel.tsx:74` | The `?panel=` contract is split with an inverted dependency — `read-url.ts` imports `DockTab` from a UI module while the param parser lives in the panel | **REAL — pre-existing shape** | **won't-fix** | The inversion predates this cycle; what changed is that `DockTab` is now the query-param vocabulary. Correcting it means moving the URL contract into `lib/`, touching a shipped URL boundary for no behavioural gain — a structural cleanup that deserves its own change rather than riding a feature PR. Recorded as follow-up |
| 9 | requirements `5086875907` | records | Spec Goals/Success Criteria still unticked and requirements still "Pending"; `ROADMAP.md:126` still "Not started"; AD-211…AD-218 landed under `## Known Gaps` instead of the decisions table; `validation.md:115` says "Thirteen" where the table lists 17 | **REAL** | **fix** | All four are record defects, and the misplaced decisions are my own insertion error — eight decisions filed under "Known Gaps" would mislead every future reader. The prior cycle set the precedent for ticking these at this point |

## Not accepted

Finding 8 only. Everything else is accepted and fixed.

## What the review caught that verification did not

Findings 1, 2, and 3 are all *reachability* defects: states this cycle newly created
(a note born without an embed enqueue, an empty quote snapshot, a count mutated from
inside its own panel) that no invariant in `design.md` named — so the Verifier, whose
discrimination sensor can only mutate branches an invariant points at, had nothing to
mutate. The lesson is recorded: when a cycle *deletes* a path, the invariants must
enumerate what that path did besides its headline job.
