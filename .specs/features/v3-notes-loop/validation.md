# v3-notes-loop Validation

**Date**: 2026-07-20
**Spec**: `.specs/features/v3-notes-loop/spec.md`
**Diff range**: `ebed9e1..e341cbb` (`main...HEAD`, branch `feat/v3-notes-loop`, 26 commits)
**Verifier**: independent sub-agent (author ≠ verifier; re-derived from spec, evidence-or-zero)
**Verdict**: ✅ PASS

---

## Task Completion

All tasks T1–T19 recorded done in `tasks.md` (T14 intentionally unused). Recorded deviations are accepted decisions (source_id widened to string|null in client fixtures; `SubmitReview` authz rewired to `item.user_id` per AD-149; `DueItem.note_changed` required in fixtures; frontend `package-lock.json` root version left stale mirroring the 0.2.0 bump). Pre-existing "grades each card" revealed-reset race noted as a flake predating this cycle — did not flake in the gate run.

---

## Spec-Anchored Acceptance Criteria

### P1: Ask my books and my notes

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| NL-01 note create/update → whole-note embedding (vector 1536, model recorded) + tsvector over title+body, never in corpus_chunks | embedding non-null, model `<model>@<dims>`; trigger-fed search_vector (title A / body D, 'simple'); empty note → empty tsvector | `test_embed_note.py:110` `assert row.embedding is not None` + `:112` `row.embedding_model == adapter.model`; `test_migrations.py:1543` `"photosynthesis" in sv` + `:1559` `"mitochondria" in updated_sv` + `:1578` `empty_sv == ""` | ✅ PASS |
| NL-02 Q&A with notes → two note RRF arms, deterministic fused rank | distinctive note ranks first; identical inputs → identical order | `test_retrieval_notes.py:207` `results[0].origin == "note"` + `:288` `[(chunk_id,score)] == [(chunk_id,score)]` | ✅ PASS |
| NL-03 note citation visibly distinct ("your note", title, note link); book unchanged | origin='note' + note_id/note_title; book citation byte-identical | `test_web_questions.py:867` `note_cits[0]["note_id"]==str(note_id)` + `:875` `set(bc)==_CITATION_KEYS`; FE `citations.test.tsx:159` `"Your note — My Insight"` + `:166` href `/notes/note-123` | ✅ PASS |
| NL-04 include_notes false → no note in evidence/prompt/citations; absent → Q&A true, teaching false | zero note origins/citations off; defaults per surface | `test_web_questions.py:879` `"note" not in off_origins` + `:794` `seen==[True,False]`; `test_web_teaching.py:1058` default False; `test_application_qa.py:251`/`test_application_retrieval.py:358` forwarding | ✅ PASS |
| NL-05 only requesting user's notes are candidates | other user's note never appears | `test_retrieval_notes.py:230` `all(e.origin=="book" for e in results)` | ✅ PASS |
| NL-06 empty body excluded both arms; not-yet-embedded still lexical, no error | empty-body absent; null-embedding note retrievable lexically | `test_retrieval_notes.py:246` `any(origin=="note" and note_id)` (null emb) + `:259` `all(origin=="book")` (empty); `test_embed_note.py:141` empty clears vector | ✅ PASS |
| NL-07 deleted note stops appearing immediately | absent after delete | `test_retrieval_notes.py:275` `all(e.note_id != note_id for e in after)` | ✅ PASS |

### P1: Promote a note to review, edit without fear

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| NL-08 "add to review" → suggestions from note body via quiz port, QC against note body, anchor context when anchored | grounded-only survive; body passed; anchor context carried | `test_application_cards.py:1300` `result==[grounded]` + `:1303` `body==_NOTE_BODY` + `:1314` `"Biology" in context`; `test_quiz_local.py:199` grounded in body | ✅ PASS |
| NL-09 accepted card: origin='note', minted id, content_key (no collision), note provenance, fresh FSRS, in due queue | origin/user_id/source_id=None/note_id, `note:<id>` anchor, fresh scheduling, due | `test_application_cards.py:1372-1389` origin/source_id/note_id/anchor/content_key/scheduling; `test_web_cards.py:1007-1017` due-queue roundtrip `source_title=="Your notes"` | ✅ PASS |
| NL-10 promoted-note save → matched items' text updated in place; scheduling + review_log byte-equal | text rewritten, scheduling/log unchanged (byte-equal) | `test_refresh_note_cards.py:198` `_scheduling_row==before_sched` + `:199` `_log_rows==before_log`; `test_application_cards.py:1582` `update_scheduling_calls==0` | ✅ PASS |
| NL-11 unmatched item → note-changed flag (not deleted/rescheduled) | text untouched, note_changed_at set | `test_application_cards.py:1615` `updated.question=="Original?"` + `:1616` `note_changed_at==_NOW` | ✅ PASS |
| NL-12 changed note-derived item → "your note changed" badge + explicit reset only | badge when flagged; reset fresh + clears badge; log preserved | `test_application_reviews.py:419-431` fresh state + `note_changed_at is None` + `log_after==log_before`; `test_web_quiz.py:707` badge True + `:739` retires after reset; FE `review-screen.tsx:464-471,522-551` | ✅ PASS |
| NL-13 note-derived item review shows provenance (title+excerpt, note link) | provenance note_id/title at review | `test_web_quiz.py:709` `provenance["note_id"]==str(note_id)`; FE `review-screen.tsx:470` href `/notes/n7` | ✅ PASS |
| NL-14 promoted note deleted → items survive, keep schedule, provenance line absent | note_id SET NULL, card intact, renders from own text | `test_migrations.py:1750` `row.note_id is None` + `:1751` `source_excerpt=="excerpt"`; `test_refresh_note_cards.py:204` deleted-note no-op | ✅ PASS |
| NL-15 re-promote → dedup against live items, no duplicate | re-accept returns existing id, one row | `test_application_cards.py:1413` `second.id==first.id` + `:1415` one row; `test_web_cards.py:1033-1036` 200 same id, one due | ✅ PASS |

### P1: Obsidian vault export

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| NL-16 export → zip with Learny/ folder, one file per book-with-highlights + one per note | zip tree, note+book files | `test_web_vault.py:170-176` note file + book file entries; `test_export_obsidian.py:131` only supplied serialized | ✅ PASS |
| NL-17 book file: `> [!quote]` callout titled section path + page span, `^lh-<id>` block, position-ordered; orphans trailing | callout + block id + order + orphan section | `test_export_obsidian.py:186-188` callout/block; `:200` order; `:237-240` orphan trailing section | ✅ PASS |
| NL-18 note file: only `learny-*` frontmatter, verbatim body (wikilinks untouched), anchor links into book block else cited quote | learny-* keys only; body verbatim; deep link or quote | `test_export_obsidian.py:268-276` learny-* keys; `:292` body verbatim; `:301` `[[The Book#^lh-<id>]]`; `:313-315` plain quote fallback | ✅ PASS |
| NL-19 same data twice → byte-identical zips | two builds equal | `test_export_obsidian.py:106` `first == second` | ✅ PASS |
| NL-20 export contains only requesting user's data | second user's note absent | `test_web_vault.py:191-192` `AlphaSecret.md not in`; `test_export_obsidian.py:131` builder scope | ✅ PASS |
| NL-21 filename collision/hostile chars → sanitize + de-collide deterministically | stripped + ` (2)` suffix, order-stable | `test_export_obsidian.py:147` `abcdefghij.md`; `:163-171` `Same (2)`/`Same (3)` stable across reversed input | ✅ PASS |

### P2: Close v3

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| NL-22 README describes capture→retrieve→reinforce→export | accurate feature set (build gate only per matrix) | build gate; T18 grep-verify recorded done | ⚠️ Spec-precision gap (docs — no automated assertion by design; matrix: "Docs → none, build gate only") |
| NL-23 v3 retrospective in v2 form | file present (build gate only) | `docs/retrospectives/2026-07-learny-v3.md` present in diff | ⚠️ Spec-precision gap (docs — no automated assertion by design) |
| NL-24 pyproject.toml + package.json read 0.3.0 | both == "0.3.0" | `test_versions.py:24` backend==0.3.0 + `:33` frontend==0.3.0 + match | ✅ PASS |

**Status**: ✅ 22/24 covered with spec-matching assertions; NL-22/NL-23 are documentation ACs with no test requirement per the Test Coverage Matrix (build-gate only) — flagged, not failed.

---

## Edge Cases

- [x] Zero notes → book-only: `test_retrieval_notes.py:319`
- [x] Body over embedding limit → deterministic truncation: `test_embed_note.py:183-185`
- [x] Concurrent regenerate / stale save → newest body wins: `test_refresh_note_cards.py`/`test_application_cards.py:1661`, `test_embed_note.py:153`
- [x] All suggestions fail QC → empty list not error: `test_application_cards.py:1331`, `test_web_cards.py:994`
- [x] Identical note titles → deterministic de-collision: `test_export_obsidian.py:163`
- [x] Anchored note's book deleted → note still exports from snapshot: `test_export_obsidian.py:250`

---

## Discrimination Sensor

Risk tier HIGH (scheduling integrity, auth boundaries, determinism). 7 behavior-level mutations, each injected in-place, targeted tests run, then reverted with `git checkout` (tree verified clean between each).

| # | File:line | Mutation | Killed by | Result |
| --- | --- | --- | --- | --- |
| 1 | `app/application/reviews.py:154` | Drop `clear_note_changed(item.id)` from schedule reset (badge would survive reset) | `test_application_reviews.py::test_reset_returns_fresh_state_clears_badge_and_preserves_log` | ✅ Killed |
| 2 | `app/infrastructure/db/repositories.py:1541` | Flip note_changed compare `>` → `<` (badge computation) | `test_repositories_quiz.py::test_due_for_user_flags_note_changed_after_a_change` + `test_due_for_user_badge_retires_after_review` + `test_web_quiz.py::test_due_queue_flags_a_changed_note_card_with_provenance` (3) | ✅ Killed |
| 3 | `app/infrastructure/db/retrieval.py:181` | Notes arm `user_id = :user_id` → `!=` (cross-user leak) | `test_retrieval_notes.py::test_other_users_note_is_never_a_candidate` (+4 more) | ✅ Killed |
| 4 | `app/infrastructure/web/teaching.py:92` | Teaching `include_notes` default `False` → `True` | `test_web_teaching.py::test_post_turn_defaults_include_notes_false_and_forwards_explicit_choice` | ✅ Killed |
| 5 | `app/application/cards.py:674` | RefreshNoteCards touches `update_scheduling` on matched update (NL-10 core invariant) | `test_application_cards.py::test_refresh_rewrites_a_matched_changed_card_and_flags_it` + `test_refresh_note_cards.py::test_refresh_rewrites_matched_card_and_preserves_memory` (2) | ✅ Killed |
| 6 | `app/infrastructure/export/obsidian.py:80` | Drop stable note sort in vault builder (de-collision order becomes input-dependent) | `test_export_obsidian.py::test_identical_note_titles_de_collide_deterministically` | ✅ Killed |
| 7 | `app/application/cards.py:443` | Skip groundedness QC on note suggestions | `test_application_cards.py::test_note_suggestions_are_generated_from_the_body_and_qc_filtered` + `test_note_suggestions_all_failing_qc_return_an_empty_list` (2) | ✅ Killed |

**Sensor depth**: P0-full (7 mutations, all HIGH-tier invariants). **Result**: 7/7 killed — ✅ PASS. Tree byte-identical after sensor (`git status` clean, HEAD `e341cbb`).

---

## Code Quality

| Principle | Status |
| --- | --- |
| Minimum code / surgical changes / no scope creep | ✅ (additive Evidence/citation fields with defaults; note arms reuse book RRF template; export is a pure builder) |
| Matches existing patterns | ✅ (embed_note mirrors reembed_document; export mirrors Anki seam; provenance reuses CardProvenance/AD-136) |
| Spec-anchored outcome check (asserted values match spec) | ✅ |
| Per-layer Coverage Expectation met (domain 1:1 ACs; routes happy+edge+error) | ✅ (routes cover 401/403/404/409/422/429/502 + happy) |
| Every test maps to a spec requirement — no unclaimed tests | ✅ |
| Documented guidelines followed | ✅ (`CLAUDE.md` golden fixtures / worker-not-handler; `CONTRIBUTING.md`; CI pytest·ruff·vitest·tsc·build) |

---

## Gate Check

- **Backend**: `LEARNY_EMBEDDING_PROVIDER=local LEARNY_GENERATION_PROVIDER=local LEARNY_TEST_DATABASE_URL=... pytest -q` → **1522 passed, 10 skipped** (exit 0); `ruff check` → **All checks passed!**
- **Frontend**: `npx vitest run` → **494 passed / 50 files** (exit 0); `npx tsc --noEmit` → exit 0; `npm run build` → exit 0.
- All 10 skips are pre-existing offline-provider / snapshot-committed guards (no keys in CI), matching the expected baseline.
- Matches tasks.md expected baseline exactly (1522/10 backend, 494/50 frontend).

---

## Requirement Traceability Update

| Requirement | Previous | New |
| --- | --- | --- |
| NL-01..NL-21, NL-24 | Implementing | ✅ Verified |
| NL-22, NL-23 | Implementing | ✅ Verified (docs — build-gate only, no test required by matrix) |

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 22/24 ACs matched spec outcome with `file:line` assertions; 2 (NL-22/NL-23) are documentation ACs the Test Coverage Matrix scopes to the build gate only — flagged as spec-precision gaps, not failures.
**Sensor**: 7/7 mutations killed (P0-full, HIGH tier).
**Gate**: backend 1522 passed / 10 skipped + ruff clean; frontend 494 passed + tsc + build.

**What works**: notes fused into hybrid retrieval with deterministic RRF and strict per-user scoping; distinct note citations end-to-end (JSON + stream + UI); one-action note promotion with edit-stability (scheduling/review_log byte-equal across regenerate-and-match); explicit-only schedule reset with a computed badge; deterministic byte-identical Obsidian vault export scoped to the caller.

**Issues found**: none blocking. NL-22/NL-23 carry no automated assertion by design (documentation ACs); accepted per the matrix.

**Next steps**: none required — PASS. No fix tasks.
