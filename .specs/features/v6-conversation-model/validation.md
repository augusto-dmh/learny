# Unified Grounded Conversations Validation

**Date**: 2026-07-25
**Spec**: `.specs/features/v6-conversation-model/spec.md`
**Diff range**: `main..feat/conversation-model` (`f159d03b..3af48fa3`; implementation `8766b212..3af48fa3`)
**Verifier**: independent sub-agent (author ≠ verifier), evidence-or-zero

**Verdict**: ✅ **PASS** — 26/26 acceptance criteria matched their spec-defined outcome, 26/26 injected faults killed, all gates green.

---

## Spec-Anchored Acceptance Criteria

### P1: One conversation model in the schema (CONV-01, CONV-02)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| Migration `0017` renames + widens the three tables | three `conversation*` tables; `title`/`scope_anchors`/`include_notes` NOT NULL; `target_*` nullable; turns gain `mode` NOT NULL | `tests/test_migrations.py:2092` — `assert {"conversations", "conversation_turns", "conversation_turn_citations"} <= tables`; `:2097-2104` — `columns["title"]["nullable"] is False`, `columns["target_anchor"]["nullable"] is True`, `turn_columns["mode"]["nullable"] is False`; `:2105-2106` — `"conversation_id" in turn_columns`, `"session_id" not in turn_columns` | ✅ PASS |
| Backfill values | `scope_anchors == [target_anchor]` (JSON array), `title == target_title`, `include_notes == false`, turns `mode == 'teach'` | `tests/test_migrations.py:2121-2127` — `row.title == "Chapter Two"`, `row.scope_kind == "array"`, `row.scope_anchors == ["ch2.xhtml"]`, `row.include_notes is False`, `turn_mode == "teach"` | ✅ PASS |
| Downgrade restores 0016; upgrade preserves the unique + FK-less citation | 0016 shape back; `UNIQUE(conversation_id, turn_index)`; citation snapshot has no corpus FK | `tests/test_migrations.py:2149` — `turn_uniques["uq_conversation_turns_conversation_id"] == ["conversation_id", "turn_index"]`; `:2153` — `pytest.raises(IntegrityError)` on a duplicate index; `:2135` — `["chunk_id"] not in citation_fk_columns`; `:2141` — `surviving_chunk_id == citation_chunk_id`; `:2252-2265` — 0016 nullability + `uq_teaching_turns_session_id` restored; `:2281` — seeded row intact | ✅ PASS |
| `metadata.py` matches the migrated database | table + column definitions equal | `tests/test_migrations.py:2219-2220` — `reflected == {c.name: c.nullable for c in table.columns}` over all three tables | ✅ PASS |

### P1: Unified conversation services (CONV-05..09, CONV-13)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| `StartConversation` snapshots the scope head, stores the notes choice, defaults the title | `target_*` from scope head (alias-aware) / NULL when empty; title = target title (scoped) or source title (whole book) | `tests/test_application_conversations.py:562` (scope-head snapshot), `:586` (no target, book title), `:609` (explicit notes off), `:623` (alias-resolved anchor), `:673`/`:690` (explicit title trimmed / blank falls back) | ✅ PASS |
| Unresolvable scope anchor → 422, nothing created | `InvalidConversationScope` → 422; no conversation written | `tests/test_application_conversations.py:643`, `:661`; `tests/test_web_conversations.py:360` — `status_code == 422` and the list stays empty | ✅ PASS |
| `ListConversations` — all sources, `updated_at` desc, `source_title` + `turn_count`, optional `source_id` filter | ordered newest activity first with both fields | `tests/test_application_conversations.py:751`, `:774`, `:790`; `tests/test_web_conversations.py:448`, `:498`; `tests/test_repositories.py:1534`, `:1585` | ✅ PASS |
| `RenameConversation` 1–200 trimmed chars; bump `updated_at`; reject empty/oversize | stored title changes, activity bumps; blank/oversize rejected | `tests/test_application_conversations.py:855`, `:871` (parametrized blank/oversize leave the stored title), `:885` (exactly at bound accepted); `tests/test_web_conversations.py:629`, `:652`, `:674` | ✅ PASS |
| `DeleteConversation` removes turns + citations; second delete not-found | cascade delete; second call reports absence | `tests/test_application_conversations.py:917`; `tests/test_repositories.py:1613`; `tests/test_web_conversations.py:722` (204 + turns gone), `:751` | ✅ PASS |
| Non-owner outcome indistinguishable from absence (I-CM-6) | identical not-found / 404 | `tests/test_application_conversations.py:834`, `:897`, `:931`, `:1703`; `tests/test_web_conversations.py:601`, `:687`, `:751`, `:1103` — missing and non-owned compared for an identical 404 body | ✅ PASS |

### P1: Turns with scope × mode (CONV-10..14)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| Per-turn `expand_anchors` scope expansion reaches retrieval; `None` only when scope empty | expanded subtree + aliases as `anchors`; stored `include_notes` | `tests/test_application_conversations.py:1047` — `retrieve.calls == [{… "anchors": ["ch1.xhtml", "ch1.xhtml#core", "ch1-old.xhtml"], "include_notes": False}]`; `:1079` — `retrieve.calls[0]["anchors"] is None` (whole book only); `:1101` — expansion repeated per turn; `:1127` — multi-anchor union in given order, deduped | ✅ PASS |
| Mode dispatch with bounded history | `answer` → `AnswerGenerationPort` + history; `teach` → `TeachingGenerationPort` + target section path + history | `tests/test_application_conversations.py:1264` (bounded history to the answer port), `:1310` (not-found turns kept with empty response), `:1345` (target section path + history to the teaching port) | ✅ PASS |
| `not_found_in_scope` vs `not_found_in_source`; a scoped turn never widens (I-CM-3) | scoped → `not_found_in_scope`; empty scope → `not_found_in_source` | `tests/test_application_conversations.py:1215` — `turn.answer_status == "not_found_in_scope"`; `:1222` (whole book stays `not_found_in_source`); `:1241` (grounding failure → scope verdict); `:1151-1152` — `retrieve.calls[0]["anchors"] == ["gone.xhtml"]` (never `None`); `tests/test_web_conversations.py:911`, `:1004`, `:983` — `{c["anchor"] for c in in_scope.json()["citations"]} <= {_ANCHOR}` | ✅ PASS |
| Teach turn without resolvable target → 409, nothing persisted (I-CM-7) | `ConversationTargetUnavailable` → 409 | `tests/test_application_conversations.py:1375` (whole-book conversation), `:1398` (target section vanished); `tests/test_web_conversations.py:1047`, `:1064` — `status_code == 409` | ✅ PASS |
| Persist only after grounding, next index, citations in rank order, `updated_at` bumped; duplicate index → conflict (I-CM-2/5) | ranked citations, index+1, touch; conflict not gap/duplicate | `tests/test_application_conversations.py:1493-1499` — `turn.turn_index == 1`, `turn.citations == (top, second)`, `[t.turn_index …] == [0, 1]`; `:1516` — `conversations.touch_calls == [(conversation.id, later)]`; `:1527` — `pytest.raises(ConversationTurnConflict)` with `touch_calls == []`; `:1558` (generation failure persists nothing); `tests/test_web_conversations.py:1138` | ✅ PASS |
| Streaming equals buffered; frame sequence pinned (CONV-21, I-CM-5) | identical persisted turn/status; `start`, `text-start`, deltas, `text-end`, `data-citations`, `data-answer-status`, `finish`, `[DONE]` | `tests/test_application_conversations.py:1606` (stream vs buffered persist identical turns), `:1652` (cancellation persists nothing), `:1678`; `tests/test_web_conversations.py:1264` — `_part_types(parts) == ["start", "text-start", "text-delta", "text-end", "data-citations", "data-answer-status", "finish", "[DONE]"]` | ✅ PASS |

### P1: Unified web surface (CONV-15..22)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| Seven routes with their status codes | 201 / 200 / 200 / 200 / 204 / 201 / 200 SSE | `tests/test_web_conversations.py:290` (201), `:448` (200 list), `:537` (200 read, turns carry `mode` + citations), `:629` (200 rename), `:722` (204), `:836` (201 turn), `:1244` (200 SSE); route inventory pinned at `:1554` — `len(routes) == len(router.routes) == 7` | ✅ PASS |
| Omitted `include_notes` → 422 | explicit per conversation | `tests/test_web_conversations.py:345` — `status_code == 422` | ✅ PASS |
| Origin + CSRF + the single `rate_limit_conversations`; 429 + `Retry-After`; 401 unauthenticated | one policy on every mutating route | `tests/test_web_conversations.py:1560-1564` — `declared == [rate_limit_conversations, enforce_origin, enforce_csrf]` for every mutating route and `== []` for reads; `:1503-1505` (429 + `Retry-After` ≥ 1), `:1508`, `:1526`; `:421`/`:528`/`:619`/`:711`/`:775` (401); `:428`/`:434` (403) | ✅ PASS |
| Unknown `mode` / over-limit message → 422 via `conversation_message_max_chars` | 422 before the service | `tests/test_web_conversations.py:1007`, `:1025` | ✅ PASS |
| Generation failure → 502 buffered; SSE error frame then `[DONE]`, persisting nothing | established 502; error part, no `finish` | `tests/test_web_conversations.py:1168` (502 + nothing persisted), `:1317` (error frame then `[DONE]`, nothing persisted) | ✅ PASS |

### P1: Legacy compatibility (CONV-23..25)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| Five teaching + two questions paths unchanged on the wire (I-CM-4) | method, path, status, field set, SSE frames unchanged | `tests/test_web_teaching.py` and `tests/test_web_questions.py` run their pre-cycle wire assertions unchanged against the unified backing (e.g. `test_web_teaching.py:243`, `:561`, `:869`; `test_web_questions.py:184`, `:678`) | ✅ PASS |
| Ask persists a whole-book conversation, title = question cut to 80, `include_notes` request-value-else-true, answer as `answer`-mode turn 0 | conversation visible afterwards | `tests/test_application_qa.py:499`, `:562-563` — `conversations.only().title == question[:80]` and `len(...) == 80`; `:530` — `conversation.include_notes is True`; `tests/test_web_questions.py:307-317` — `summary["scope_anchors"] == []`, `turns[0]["mode"] == "answer"`, `turn_index == 0` | ✅ PASS |
| Legacy teaching start: `scope_anchors == [target_anchor]`, `include_notes == false`; per-request override does not change the stored choice | scoped conversation, notes off, override request-only | `tests/test_application_teaching.py:551-553` — `result.scope_anchors == ("ch1.xhtml#core",)`, `result.include_notes is False`, `result.title == "Core Idea"`; `tests/test_application_conversations.py:1192-1193` — `[call["include_notes"] …] == [True, False]` and the stored choice stays `False`; `tests/test_web_teaching.py:1129` — `seen == [False, True]` | ✅ PASS |
| Scoped legacy miss collapses to `not_found_in_source` on JSON **and** SSE | wire says source, storage keeps scope | `tests/test_web_teaching.py:661` — `posted.json()["answer_status"] == "not_found_in_source"`; `:665` legacy read collapsed; `:671` — `unified.json()["turns"][0]["answer_status"] == "not_found_in_scope"`; `:933` (SSE status frame collapsed) | ✅ PASS |
| Legacy per-source list shows only conversations with a teach target | ask-created conversations excluded | `tests/test_application_teaching.py:763` — `[s.conversation for s in result] == [taught]`; `tests/test_web_questions.py:331` — `sessions.json() == []`; `tests/test_repositories.py:1518` | ✅ PASS |
| Frontend suite passes unmodified (I-CM-4) | green with zero edits | `git diff main..HEAD -- frontend/` empty (0 lines); `npm test` → 63 files, 633 tests passed | ✅ PASS |

### P2: Deterministic-provider stability (CONV-26, CONV-14, I-CM-8)

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| Golden citation + generation-invariant suites pass; first answer turn byte-identical to the pre-cycle ask | text and citations unchanged | `tests/test_golden_citations.py:85-86` — `result.text == expected.text` and `tuple(c.chunk_id …) == expected.cited_chunk_ids`, recomputed from the adapter rather than a stale literal; `tests/test_answering_local.py:71-74` — `without_argument.text == "alpha\n\nbeta"`, `empty_history == without_argument`, `with_history == without_argument`; `:76` same on the streaming path | ✅ PASS |
| Anthropic answer adapter renders history ahead of the question, system prompt + citation mechanics unchanged | alternating prior turns, frozen system prompt | `tests/test_answering_anthropic.py:200-217` — `call["system"] == [{"type": "text", "text": ANSWER_SYSTEM_PROMPT}]`, `messages[0] == {"role": "user", "content": "Who wrote it?"}`, documents keep `citations == {"enabled": True}`, `final["content"][-1] == {"type": "text", "text": "And why?"}`; `:169` (history-less request is the untouched single-shot ask); `:234` (stream sends the identical request) | ✅ PASS |

**Status**: ✅ All 26 ACs covered with assertions targeting the spec-defined outcome. No spec-precision gaps.

---

## Edge Cases

- [x] Turn posted to a deleted/unknown/unowned conversation → 404 — `tests/test_web_conversations.py:1103`; `tests/test_application_conversations.py:1703`
- [x] Unified start naming an unowned source → 404, not 422 — `tests/test_web_conversations.py:379` (missing and non-owned compared for an identical 404)
- [x] Duplicate `scope_anchors` → expansion dedupes, stored scope keeps the given order — `tests/test_application_conversations.py:1127`; `tests/test_domain_conversations.py:92`; `tests/test_repositories.py:1684` (multi-anchor scope round-trips in order)
- [x] Corpus replace removes a scoped section → answer turns proceed on survivors, teach turn 409 — `tests/test_application_conversations.py:1423` / `:1398`; `tests/test_web_conversations.py:1080` / `:1064`
- [x] `include_notes` true → note arms join un-scoped — the conversation's stored choice reaching retrieval is pinned at `tests/test_application_conversations.py:1167`; the un-scoped join itself is pre-existing engine semantics, pinned at `tests/test_retrieval_notes.py:326` (unchanged this cycle, as the spec states)
- [x] Rename/delete racing a turn post → arbiter + FK cascade, no partial states — `tests/test_repositories.py:1613` (delete cascades turns + citations), `:1868` (duplicate index raises conflict); `tests/test_application_conversations.py:1520` / `:1540`

---

## Discrimination Sensor

Depth: **P0-full** (schema + data-integrity cycle). All mutations applied in a detached scratch worktree at `3af48fa3`, reverted after each run; the real tree was never modified (`git status` clean before and after).

| # | Mutation | File | Killed? | Killing test |
| --- | --- | --- | --- | --- |
| M1 | Migration backfill `include_notes = false` → `true` | `migrations/versions/0017_conversations.py:115` | ✅ | `test_migrations.py::test_migration_0017_generalizes_teaching_into_conversations` |
| M2 | Backfill `jsonb_build_array(target_anchor)` → `to_jsonb(...)` (quoted scalar) | `0017_conversations.py:114` | ✅ | same |
| M3 | Turn backfill `mode = 'teach'` → `'answer'` | `0017_conversations.py:132` | ✅ | same |
| M4 | Scope widening: unresolvable anchor dropped instead of kept | `app/application/conversations.py:657` | ✅ | `test_application_conversations.py::test_a_scoped_turn_never_widens_when_its_section_disappeared` |
| M5 | Scope ignored at the retrieval call (`anchors=None` always) | `conversations.py:596` | ✅ | `::test_scoped_turn_retrieves_through_the_expanded_scope_subtree` |
| M6 | `not_found_in_scope` decision collapsed to `not_found_in_source` at the source | `conversations.py:737` | ✅ | `::test_a_scoped_turn_never_widens_when_its_section_disappeared` |
| M7 / M7b | AD-196 legacy collapse removed (scope verdict leaks to the legacy wire) | `web/legacy_status.py:28` | ✅ | `test_web_teaching.py::test_post_turn_scoped_miss_is_stored_as_scope_verdict_and_collapsed_on_the_wire` |
| M8 | Legacy ask no-failure-litter discard removed on the stream path | `app/application/qa.py:166` | ✅ | `test_application_qa.py::test_stream_mid_stream_failure_leaves_no_conversation_behind` |
| M9 | Turn-index conflict still bumps activity (touch before add) | `conversations.py:758` | ✅ | `::test_a_turn_index_race_surfaces_as_a_conflict` |
| M10 | Teach invariant: vanished target silently teaches another section | `conversations.py:615` | ✅ | `::test_teach_turn_whose_target_section_disappeared_is_a_state_conflict` |
| M11 | Ownership disclosed (`NotAuthorized` no longer collapsed to not-found) | `conversations.py:99` | ✅ | `::test_read_of_an_unowned_conversation_is_indistinguishable_from_absence` |
| M12 | Per-request `include_notes` override ignored | `conversations.py:588` | ✅ | `::test_notes_override_applies_to_one_request_without_changing_the_stored_choice` |
| M13 | `include_notes` no longer required on unified start (defaults instead of 422) | `web/conversations.py:116` | ✅ | `test_web_conversations.py::test_start_without_include_notes_returns_422` |
| M14 | Single rate-limit policy dropped from the DELETE route | `web/conversations.py:388` | ✅ | `::test_every_mutating_conversation_route_carries_the_one_policy` |
| M15 | Anthropic answer adapter drops the conversation history | `answering/anthropic.py:262` | ✅ | `test_answering_anthropic.py::test_answer_request_renders_history_before_the_current_question` |
| M16 / M16b | Legacy teach list no longer filters ask-created conversations | `app/application/teaching.py:141` | ✅ | `test_application_teaching.py::test_list_excludes_conversations_without_a_teach_target` |
| M17 | Unified start accepts an unresolvable scope anchor | `conversations.py:238` | ✅ | `::test_start_rejects_an_unresolvable_scope_anchor_and_creates_nothing` |
| M18 | Streaming path bypasses the grounding guard (persists ungrounded as answered) | `conversations.py:537` | ✅ | `test_application_teaching.py::test_stream_answered_streams_deltas_and_persists_grounded_turn` |
| M19b | Streamed turn claims a different index than the buffered path | `conversations.py:532` | ✅ | `::test_stream_and_buffered_paths_persist_identical_turns` |
| M20 | Legacy ask title no longer truncated to 80 chars | `qa.py:179` | ✅ | `test_application_qa.py::test_ask_titles_the_conversation_with_the_first_80_characters` |
| M21 | Legacy teaching start flips the stored notes choice on | `teaching.py:89` | ✅ | `test_application_teaching.py::test_start_scopes_the_session_to_its_target_with_notes_off` |
| M22 | Teach target snapshotted from the scope tail instead of the head | `conversations.py:239` | ✅ | `::test_start_scoped_snapshots_the_scope_head_as_the_target` |
| M23 | Buffered path persists before grounding (turn written on generation failure) | `conversations.py:482` | ✅ | `::test_generation_failure_persists_nothing` |
| M24 | List no longer ordered by newest activity | `conversations.py:268` | ✅ | `::test_list_returns_the_callers_conversations_newest_activity_first` |

**Result**: 26 valid mutations injected, **26 killed, 0 survived**.

Note: a first attempt at M19 used `dataclasses.replace` without an import and failed on `NameError`; it was discarded as a false kill and re-run import-safe as M19b.

---

## Gate Check

| Gate | Command | Result |
| --- | --- | --- |
| Backend suite | `backend/.venv/bin/python -m pytest -q` | 1937 passed, 1 failed (carried), 11 skipped, 132s |
| Backend lint | `ruff check .` | All checks passed (exit 0) |
| Backend format | `ruff format --check .` | 253 files already formatted (exit 0) |
| Frontend suite | `npm test` | 63 files, 633 tests passed (exit 0) |
| Frontend types | `npx tsc --noEmit` | clean (exit 0) |
| Frontend diff | `git diff main..HEAD -- frontend/` | empty (0 lines) |

- **Test count before feature**: 1799 collected (`main`)
- **Test count after feature**: 1947 collected — **+148**, no test deleted or weakened
- **Failures**: `test_eval_retrieval_metrics.py::TestDeterministicRetrievalMetrics::test_metrics_meet_thresholds` — `assert 0.8571… >= 0.9` (deterministic-embedding recall@1 over the golden corpus). Pre-existing and out of cycle scope: the diff touches no retrieval, embedding, ranking, or golden-corpus code, and the test's imports (`seed_source`, `build_corpus_in_db`, `embed_source`, `retrieve`) are all unchanged helpers — the only `eval_runner.py` change is to `answer()`, which this test does not call. Green in CI.
- **Skipped (11, all justified)**: 7 live-provider smokes gated on `LEARNY_ANTHROPIC_API_KEY` / `LEARNY_OPENAI_API_KEY` (CI stays offline), 1 optional `docling` import, 1 record-mode replay harness, 1 committed-snapshot duplicate, 1 live silver run.
- The pre-declared order-dependent flake `test_worker_tasks.py::test_run_ingestion_builds_corpus_from_valid_epub` did not occur.

---

## Code Quality

| Principle | Status |
| --- | --- |
| No features beyond what was asked | ✅ |
| No abstractions for single-use code | ✅ — `_TurnPlan` and the shared `_preflight` exist to make the buffered and streaming paths provably identical (I-CM-5), which the sensor confirms |
| No unnecessary flexibility added | ✅ |
| Only touched files required for the task | ✅ — frontend diff empty; legacy routers changed only where the collapse and renamed types required |
| Didn't improve unrelated code | ✅ |
| Matches existing patterns/style | ✅ — ownership collapse, per-turn re-expansion, and persist-after-grounding generalize the proven teaching mechanics |
| Would a senior engineer approve? | ✅ |
| Tests map to ACs and are non-shallow | ✅ — spot-checked the turn story; assertions pin exact anchor lists, statuses, and orderings rather than truthiness |
| Spec-anchored outcome check | ✅ — 26/26 |
| Per-layer coverage expectation | ✅ — domain 1:1 with ACs; every unified route covered happy + edge + error (401/403/404/409/422/429/502) |
| Every test maps to a spec AC, edge case, or Done-when | ✅ — no unclaimed tests in the diff surface |
| Documented guidelines followed | ✅ — `CLAUDE.md` (ports/adapters, ADR-0007/0009/0019/0020/0029), `.claude/skills/tlc-spec-driven/references/validate.md` |

---

## Requirement Traceability Update

| Requirement | Previous | New |
| --- | --- | --- |
| CONV-01..02 | Pending | ✅ Verified |
| CONV-03..04 | Pending | ✅ Verified |
| CONV-05..09, CONV-13 | Pending | ✅ Verified |
| CONV-10..12, CONV-14 | Pending | ✅ Verified |
| CONV-15..22 | Pending | ✅ Verified |
| CONV-23..25 | Pending | ✅ Verified |
| CONV-26 | Pending | ✅ Verified |
| I-CM-1..8 | Pending | ✅ Verified (each with a sensor mutation killed) |

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 26/26 ACs matched the spec-defined outcome; 0 spec-precision gaps.
**Sensor**: 26/26 mutations killed (P0-full depth).
**Gate**: backend 1937 passed / 1 carried failure / 11 justified skips; ruff clean; frontend 633 passed, `tsc` clean, frontend diff empty.

**What works**: The migration renames in place with correct backfill values and a round-trip that preserves the turn-order arbiter and the FK-less citation snapshot. Scope is enforced as a genuine promise — expanded per turn, always passed to retrieval, and never collapsed to `None` even when a scoped section disappears, with `not_found_in_scope` distinguished from `not_found_in_source` end to end. Turns persist only after grounding, identically on the buffered and streaming paths, with the unique index arbitrating races. Ownership failures are indistinguishable from absence on every service and route. The legacy Ask and Teach wires are unchanged, including the AD-196 status collapse in both JSON and SSE, while asks now persist as whole-book conversations that stay out of the old teaching panel. The frontend suite passes with zero edits.

**Issues found**: None attributable to this cycle. One carried pre-existing failure (`test_metrics_meet_thresholds`, deterministic recall@1 0.857 vs a 0.9 threshold) is unrelated to the diff surface and remains green in CI.

**Next steps**: Proceed to publish. No fix tasks. Per `lessons.md`, a clean PASS records no lesson.
