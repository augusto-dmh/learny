# teach-becomes-tutor Validation

**Date**: 2026-09-04
**Spec**: `.specs/features/teach-becomes-tutor/spec.md`
**Diff range**: `cc81dc3221037febf3c3a52e12475fb466bb4967...HEAD`
**Verifier**: independent sub-agent (author ≠ verifier)

**Result**: PASS

---

## Task Completion

| Task | Status  | Notes |
| ---- | ------- | ----- |
| T1   | ✅ Done | Frozen playbook prompt + sentinel strings |
| T2   | ✅ Done | Phase/hint on generation port user turn |
| T3   | ✅ Done | Teach citation-free persist carve-out |
| T4   | ✅ Done | Opening retrieve by title/anchor |
| T5   | ✅ Done | `0019_tutor_state` columns |
| T6   | ✅ Done | `TeachingPolicy` + `LEARNY_TUTOR_CHECK_AFTER_TURNS` default 3 |
| T7   | ✅ Done | Opening/close/mode lock on turns |
| T8   | ✅ Done | Views expose phase; close → 409 |
| T9   | ✅ Done | `0020_tutor_cards` origin + SET NULL |
| T10  | ✅ Done | Accept tutor card 201/200/409/404 |
| T11  | ✅ Done | Reconcile tutor cards by anchor |
| T12  | ✅ Done | Chat dock strip + aliases |
| T13  | ✅ Done | Tutor Start speaks first |
| T14  | ✅ Done | Chips + close handoff to Answer |
| T15  | ✅ Done | One review-card offer |

All T1–T15 Done-when boxes are checked. No blocked or partial tasks.

---

## Spec-Anchored Acceptance Criteria

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| TUTOR-01 system prompt byte-stable, two calls identical bytes | Two generates share identical system bytes; constant encode matches | `backend/tests/test_answering_anthropic.py:1192` - `assert first_system == second_system`; `:1206-1208` - `assert first == second` | ✅ PASS |
| TUTOR-02 playbook constraints in teaching system prompt | Prompt encodes one move, single question, pump→hint→prompt→assert, assert-and-cite after two failed elicitations, tell+restatement, Socratic may omit citations, book claims must cite, off-book uses existing sentinel, end after unaided check | `backend/tests/test_answering_anthropic.py:1215-1225` - `assert "one move per turn" in lowered` … `assert SENTINEL in prompt` … `assert "end after a passing unaided check" in lowered` | ✅ PASS |
| TUTOR-03 `tutor_phase`/`hint_level` in user text, not system | `Phase: open` and `HintLevel: pump` in user turn; absent from system | `backend/tests/test_answering_anthropic.py:1372-1376` - `assert "Phase:" not in system_text`; `assert "Phase: open" in user_text`; `assert "HintLevel: pump" in user_text` | ✅ PASS |
| TUTOR-04 answering system prompt byte-identical to pre-cycle | Exact pre-cycle UTF-8 bytes | `backend/tests/test_answering_anthropic.py:1238` - `assert ANSWER_SYSTEM_PROMPT.encode("utf-8") == pre_cycle.encode("utf-8")` | ✅ PASS |
| TUTOR-05 teach non-sentinel zero citations → `answered` with text, no citations | `answer_status == "answered"`, reply text kept, `citations == ()` | `backend/tests/test_application_conversations.py:1536-1538` - `assert turn.answer_status == "answered"`; `assert turn.answer_text == "What is this section trying to convince you of?"`; `assert turn.citations == ()` | ✅ PASS |
| TUTOR-06 teach exact sentinel → existing not-found, not a Socratic pass | Port `found is False`; persist `not_found_in_scope` with empty text | `backend/tests/test_answering_anthropic.py:1436-1438` - `assert result.found is False`; `backend/tests/test_application_conversations.py:1595-1596` - `assert turn.answer_status == "not_found_in_scope"`; `assert (turn.answer_text, turn.citations) == ("", ())` | ✅ PASS |
| TUTOR-07 answer zero surviving citations → AD-027 not-found collapse | `not_found_in_scope`, empty text and citations | `backend/tests/test_application_conversations.py:1622-1623` - `assert turn.answer_status == "not_found_in_scope"`; `assert (turn.answer_text, turn.citations) == ("", ())` | ✅ PASS |
| TUTOR-08 Tutor Start creates conversation and streams opening turn stored as `TUTOR_OPENING_MESSAGE` | Create then stream `message: "(session start)"`; stored turn message equals sentinel | `frontend/tests/teach-panel.test.tsx:351-368` - `expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(1)` and `expect(bodyOf(turnPost)).toEqual({ message: "(session start)", mode: "teach" })`; `backend/tests/test_application_conversations.py:1853` - `assert turns.list_for_conversation(...)[0].message == TUTOR_OPENING_MESSAGE` | ✅ PASS |
| TUTOR-09 opening retrieve query is `target_title` else `target_anchor`; subtree `anchors` unchanged | `query == "Chapter 1"` / `query == "ch1.xhtml"`; expanded anchors include subtree + alias | `backend/tests/test_application_conversations.py:1845-1847` - `assert retrieve.calls[0]["query"] == "Chapter 1"`; `assert retrieve.calls[0]["anchors"] == ["ch1.xhtml", "ch1.xhtml#core", "ch1-old.xhtml"]`; `:1919` - `assert retrieve.calls[0]["query"] == "ch1.xhtml"` | ✅ PASS |
| TUTOR-10 subsequent teach retrieve query is the learner message | Second retrieve `query == "what is anchoring?"` | `backend/tests/test_application_conversations.py:1949` - `assert retrieve.calls[1]["query"] == "what is anchoring?"` | ✅ PASS |
| TUTOR-11 first teach on empty thread that is not opening sentinel → 422, persist nothing | `InvalidConversationMode` (mapped to 422); no retrieve; no turns; phase stays null | `backend/tests/test_application_conversations.py:1962-1975` - `pytest.raises(InvalidConversationMode)`; `assert retrieve.calls == []`; `assert turns.add_calls == 0`; `assert stored.tutor_phase is None`; `backend/tests/test_web_rate_limit_validation.py:283-284` - `assert bad_mode.status_code == 422`; `backend/app/infrastructure/web/error_handlers.py:90` - `InvalidConversationMode: _HTTP_422` | ✅ PASS |
| TUTOR-12 failed opening (message was opening sentinel) accepts another opening as a new turn | Failed row `answer_status == FAILED`; retry `turn_index == 1` and `message == TUTOR_OPENING_MESSAGE` | `backend/tests/test_application_conversations.py:2001-2026` - `assert failed[0].answer_status == FAILED`; `assert retry.turn_index == 1`; `assert retry.message == TUTOR_OPENING_MESSAGE` | ✅ PASS |
| TUTOR-13 composer hidden while opening stream in flight; appears after persist (answered, not-found, or failed) | Placeholder absent in flight; present after answered / not-found / failed | `frontend/tests/teach-panel.test.tsx:377` - `expect(screen.queryByPlaceholderText(/send a message/i)).toBeNull()`; `:413` answered composer; `:1078-1080` not-found; `:1089-1090` failed | ✅ PASS |
| TUTOR-14 opening turn does not show a learner bubble for `TUTOR_OPENING_MESSAGE` | No `(session start)` text and no `user-message` | `frontend/tests/teach-panel.test.tsx:375-376` - `expect(screen.queryByTestId("user-message")).toBeNull()`; `expect(screen.queryByText("(session start)")).toBeNull()` | ✅ PASS |
| TUTOR-15 Answer Start / first send stays lazy-create | No conversation row until first learner message | `frontend/tests/ask-panel.test.tsx:441-444` - `expect(callsTo(fetchMock, CREATE_URL)).toHaveLength(0)` before send | ✅ PASS |
| TUTOR-16 opening teach accepted → `tutor_phase=open`, `hint_level=pump` | Policy and persist both `("open", "pump")` | `backend/tests/test_application_teaching_policy.py:61` - `assert (advanced.phase, advanced.hint_level) == ("open", "pump")`; `backend/tests/test_application_conversations.py:1850` - `assert (stored.tutor_phase, stored.hint_level) == ("open", "pump")`; `backend/tests/test_web_conversations.py:1307-1308` - `assert body["tutor_phase"] == "open"`; `assert body["hint_level"] == "pump"` | ✅ PASS |
| TUTOR-17 ordinary message while `open` → following generate `tutor_phase=elicit` | Generate kwargs `tutor_phase == "elicit"`; stored phase `elicit` | `backend/tests/test_application_teaching_policy.py:79` - `assert advanced.phase == "elicit"`; `backend/tests/test_application_conversations.py:2189-2193` - `assert generation.calls[0]["tutor_phase"] == "elicit"`; `assert stored.tutor_phase == "elicit"` | ✅ PASS |
| TUTOR-18 exact `TUTOR_DONT_KNOW_MESSAGE` advances hint `pump → hint → prompt → assert`; scaffold miss not ordinary | `hint_level == "hint"`, `scaffold_misses == 1`, `ordinary_turns == 0`; already-assert stays assert; chip posts exact string | `backend/tests/test_application_teaching_policy.py:91-94` - `assert advanced.hint_level == "hint"`; `assert advanced.scaffold_misses == 1`; `assert advanced.ordinary_turns == 0`; `:105-106` already-assert; `frontend/tests/teach-panel.test.tsx:1121-1124` - `expect(bodyOf(...)).toEqual({ message: "I don't know.", mode: "teach" })` | ✅ PASS |
| TUTOR-19 exact `TUTOR_JUST_EXPLAIN_MESSAGE` → generate `hint_level=assert`, then persist `tutor_phase=check` | Generate hint assert; stored phase check; chip posts exact string | `backend/tests/test_application_teaching_policy.py:125-129` - `assert advanced.hint_level == "assert"`; `assert persisted.phase == "check"`; `backend/tests/test_application_conversations.py:2231-2234` - `assert generation.calls[0]["hint_level"] == "assert"`; `assert stored.tutor_phase == "check"`; `frontend/tests/teach-panel.test.tsx:1107-1110` - `message: "Just explain this."` | ✅ PASS |
| TUTOR-20 ordinary turns reach `LEARNY_TUTOR_CHECK_AFTER_TURNS` (default 3) in elicit/scaffold → generate `tutor_phase=check` | Third ordinary `phase == "check"`; setting default 3 | `backend/tests/test_application_teaching_policy.py:142-143` - `assert third.phase == "check"`; `assert third.ordinary_turns == 3`; `:153` scaffold path; `backend/tests/test_config.py:374` - `assert settings.tutor_check_after_turns == 3` | ✅ PASS |
| TUTOR-21 two scaffold misses → generate `hint_level=assert`, then persist `check` | Second miss `hint_level == "assert"`; `after_tutor_turn` phase `check` | `backend/tests/test_application_teaching_policy.py:169-174` - `assert second.hint_level == "assert"`; `assert persisted.phase == "check"` | ✅ PASS |
| TUTOR-22 ordinary non-empty while `check` → `tutor_phase=close` and `tutor_check_text` is that message | Phase close; check text stored; chips in check are not a pass | `backend/tests/test_application_teaching_policy.py:181-182` - `assert advanced.phase == "close"`; `assert advanced.check_text == _REST`; `backend/tests/test_application_conversations.py:2281-2282` - `assert stored.tutor_phase == "close"`; `assert stored.tutor_check_text == "it argues that anchors must stay stable"`; policy `:193-196` just-explain in check stays check | ✅ PASS |
| TUTOR-23 while `close`, any new turn → 409 and persist nothing | HTTP 409; turn list unchanged; retrieve/add not called | `backend/tests/test_web_conversations.py:1378-1389` - `assert buffered.status_code == 409`; `assert [turn["message"] for turn in body["turns"]] == [TUTOR_OPENING_MESSAGE]`; `backend/tests/test_application_conversations.py:2044-2058` - `pytest.raises(ConversationClosed)`; `assert turns.add_calls == 0` | ✅ PASS |
| TUTOR-24 list and read include `tutor_phase` and `hint_level` (null when ladder does not apply) | After open: `"open"`/`"pump"` on GET and list; start response null | `backend/tests/test_web_conversations.py:1307-1317` - `assert body["tutor_phase"] == "open"`; `assert row["tutor_phase"] == "open"`; `:431-432` - `assert body["tutor_phase"] is None`; `assert body["hint_level"] is None` | ✅ PASS |
| TUTOR-25 turn with `mode=answer` on a conversation that has `tutor_phase` set → 422 | `InvalidConversationMode`; nothing retrieved or persisted; class maps to 422 | `backend/tests/test_application_conversations.py:2094-2104` - `pytest.raises(InvalidConversationMode)`; `assert retrieve.calls == []`; `assert turns.add_calls == 0`; `backend/tests/test_web_rate_limit_validation.py:283` - `assert bad_mode.status_code == 422` | ✅ PASS |
| TUTOR-26 null `tutor_phase` (Answer / pre-cycle teach with existing turns) does not require opening sentinel and does not 409 | Pre-cycle teach accepts ordinary first follow-up; phase stays null | `backend/tests/test_application_conversations.py:2143-2149` - `assert turn.message == "what is anchoring?"`; `assert generation.calls[0]["tutor_phase"] is None`; `assert stored.tutor_phase is None` | ✅ PASS |
| TUTOR-27 dock strip is Chat, Notes, Review (no Ask or Teach tabs) | Tab labels `["Chat", "Notes", "Review"]`; Ask/Teach tabs absent | `frontend/tests/reader-panel.test.tsx:218-222` - `toEqual(["Chat", "Notes", "Review"])`; `expect(screen.queryByRole("tab", { name: "Ask" })).toBeNull()` | ✅ PASS |
| TUTOR-28 `?panel=ask` → Chat+Answer; `teach` → Chat+Tutor; `chat` → last-used else Answer | `dockTabFromParam("ask"|"teach"|"chat") === "chat"`; composer arming ask/teach/last-used | `frontend/tests/reader-panel.test.tsx:186-201` - `expect(dockTabFromParam("ask")).toBe("chat")`; `expect(composerModeFromParam("ask", "teach")).toBe("ask")`; `expect(composerModeFromParam("chat", null)).toBe("ask")`; `:238-239` ask body; `:257-258` teach body; `:305` chat defaults Answer | ✅ PASS |
| TUTOR-29 Chat empty names Answer and Tutor as distinct modes | Empty Answer and Tutor surfaces both mention Answer and Tutor | `frontend/tests/ask-panel.test.tsx:439-440` - `toMatch(/Answer/)` and `toMatch(/Tutor/)`; `frontend/tests/teach-panel.test.tsx:1059-1060` - same | ✅ PASS |
| TUTOR-30 Tutor armed, no thread: section picker defaults to on-screen chapter and Start | Select value `c2.xhtml`; Start session control present | `frontend/tests/teach-panel.test.tsx:1068-1070` - `expect((target as HTMLSelectElement).value).toBe("c2.xhtml")`; `getByRole("button", { name: "Start session" })` | ✅ PASS |
| TUTOR-31 resume composer follows `last_turn_mode` (`teach` → Tutor, else Answer) | Teach last-turn resumes Tutor even from ask alias; answer last-turn resumes Answer from teach alias | `frontend/tests/reader-panel.test.tsx:573-576` - `expect(onModeChange).toHaveBeenCalledWith("teach")`; `expect(screen.getByTestId("teach-panel-body")).toBeTruthy()`; `:590-592` - `toHaveBeenCalledWith("ask")`; ask body present | ✅ PASS |
| TUTOR-32 capture Explain/Ask still auto-submits in Answer (pending-request) | Explain stream body `mode: "answer"` with fixed template | `frontend/tests/ask-panel.test.tsx:1503-1505` - `toEqual({ message: 'Explain this passage from the book:\n\n"the selected sentence"', mode: "answer" })` | ✅ PASS |
| TUTOR-33 while tutor `close`, hide composer and offer a control that starts a new Answer conversation on the same source (does not POST onto the closed thread) | Composer/chips/submit absent; Ask about this does not POST `/turns/stream`; arms Answer | `frontend/tests/teach-panel.test.tsx:1151-1160` - `queryByPlaceholderText` null; `expect(callsTo(fetchMock, TURN_STREAM)).toHaveLength(turnCount)`; `frontend/tests/reader-panel.test.tsx:280-290` - `onTabChange` `"ask"`; no turns/stream POST | ✅ PASS |
| TUTOR-34 on `close`, offer exactly one card: question template + `tutor_check_text` | One offer article; question `In your own words, what is "Chapter 1" arguing?`; answer is check text | `frontend/tests/teach-panel.test.tsx:1190-1196` - `offer.textContent` contains the frozen question and `checkText`; `getAllByRole(...).toHaveLength(1)` | ✅ PASS |
| TUTOR-35 accept inserts one `origin=tutor` `free_recall`, due-now, no `suggest_cards` | `origin == TUTOR`, `FREE_RECALL`, due now, `generation.calls == []`, one row | `backend/tests/test_application_cards.py:1768-1781` - `assert item.origin == QuizItemOrigin.TUTOR`; `assert item.item_type == QuizItemType.FREE_RECALL`; `assert world.generation.calls == []`; `assert world.items.scheduling[item.id].due == _NOW`; `backend/tests/test_web_conversations.py:2760-2765` - `assert body["origin"] == "tutor"`; `assert body["item_type"] == "free_recall"` | ✅ PASS |
| TUTOR-36 second accept returns existing item; no second row; no reschedule | Same id; `create_scheduling_calls` unchanged; `update_scheduling_calls == 0`; HTTP 200 | `backend/tests/test_application_cards.py:1801-1808` - `assert second.id == first.id`; `assert world.items.create_scheduling_calls == after_create`; `assert world.items.update_scheduling_calls == 0`; `backend/tests/test_web_conversations.py:2805-2808` - `assert second.status_code == 200`; `assert second.json()["id"] == first.json()["id"]` | ✅ PASS |
| TUTOR-37 accept while not `close` → 409, no quiz row | HTTP 409; empty source items | `backend/tests/test_web_conversations.py:2831-2832` - `assert resp.status_code == 409`; `assert ...list_for_source(...) == []`; `backend/tests/test_application_cards.py:1814-1817` - `pytest.raises(ConversationClosed)`; `assert world.items.list_all() == []` | ✅ PASS |
| TUTOR-38 card `anchor`/`section_path` from conversation target; `source_excerpt` opening first snippet else `target_title` | Anchor/path match snapshot; excerpt quote or title | `backend/tests/test_application_cards.py:1773-1776` - `assert item.anchor == "ch1#cells"`; `assert item.section_path == ("Chapter 1", "Cells")`; `assert item.source_excerpt == _QUOTE`; `:1790` - `assert item.source_excerpt == _TUTOR_TITLE`; `backend/tests/test_web_conversations.py:2766-2788` - citation snapshot + title fallback | ✅ PASS |
| TUTOR-39 delete origin conversation leaves tutor card; `conversation_id` becomes null | Card still present; `conversation_id is None`; origin still tutor | `backend/tests/test_repositories_quiz.py:1640-1644` - `assert stored is not None`; `assert stored.conversation_id is None`; `assert stored.origin == QuizItemOrigin.TUTOR` | ✅ PASS |
| TUTOR-40 reconcile: surviving anchor stays `active`; gone → `orphaned`; scheduling/`review_log` untouched | Active when anchor or alias survives (title-only excerpt); orphaned when gone; snapshots equal | `backend/tests/test_application_quiz.py:787-791` - `assert stored.status == QuizItemStatus.ACTIVE`; `assert items.scheduling[item.id] == before_sched`; `:853-857` - `assert stored.status == QuizItemStatus.ORPHANED`; `assert items.scheduling[item.id] == before_sched`; `assert items.review_log[item.id] == before_log` | ✅ PASS |
| TUTOR-41 dismiss offer: no quiz row; conversation stays `close` | No POST to tutor-card; offer gone; closed-session Answer control still present | `frontend/tests/teach-panel.test.tsx:1244-1247` - `expect(callsTo(fetchMock, TUTOR_CARD_URL)).toHaveLength(0)`; offer query null; `Ask about this` still present | ✅ PASS |
| TUTOR-42 non-owner accept → 404 (identical to missing); no insert | Both 404; same body; no quiz rows | `backend/tests/test_web_conversations.py:2847-2850` - `assert stranger.status_code == 404`; `assert stranger.json() == missing.json()`; `assert ...list_for_source(...) == []` | ✅ PASS |

**Status**: ✅ All ACs covered

---

## Discrimination Sensor

Isolated git worktree `/tmp/learny-tutor-sensor` at HEAD. Forbidden `git stash` not used. Real-tree `git status --porcelain` was empty before and matched after `git worktree remove --force`.

| Mutation | File:line | Description | Killed? |
| -------- | --------- | ----------- | ------- |
| 1        | `backend/app/application/conversations.py:785-789` | Opening retrieve always returned the learner message (dropped `target_title` / `target_anchor` fork) | ✅ Killed (`test_opening_teach_retrieves_by_section_title` expected `"Chapter 1"`, got `"(session start)"`) |
| 2        | `backend/app/application/conversations.py:716-717` | Removed close-phase turn lock | ✅ Killed (HTTP close test expected 409, got 201 and persisted a turn) |
| 3        | `frontend/app/components/reader-panel.tsx:126-129` | `dockTabFromParam` mapped only `chat` to Chat (dropped `ask`/`teach` aliases) | ✅ Killed (`expect(dockTabFromParam("ask")).toBe("chat")` got `null`) |

**Sensor depth**: lightweight
**Result**: 3/3 killed - PASS

---

## Interactive UAT Results (if performed)

| # | Test | Result | Details |
| - | ---- | ------ | ------- |
| — | User-facing UAT | ⏭️ Skip | No user in the loop (Verifier instruction). |

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code | ✅ |
| Surgical changes | ✅ |
| No scope creep | ✅ |
| Matches patterns | ✅ |
| Spec-anchored outcome check (asserted values match spec) | ✅ |
| Per-layer Coverage Expectation met (domain 1:1 ACs; routes happy+edge+error) | ✅ |
| Every test maps to a spec requirement - no unclaimed tests | ✅ |
| Documented guidelines followed: `CLAUDE.md` (`make lint`, pytest, npm test); FastAPI error map; AD-027 grounding kept for Answer | ✅ |

TUTOR-11 and TUTOR-25 assert `InvalidConversationMode` on the turn path and 422 on the shared error map, not a dedicated HTTP POST of those two cases. The mapped status is the spec 422. New tests map to TUTOR ACs, listed edge cases, or task Done-when (migrations, repository CHECKs, origin unique).

---

## Edge Cases

- [x] Opening generation fails → persist `failed` opening turn and allow retry of the opening sentinel (`backend/tests/test_application_conversations.py:2001-2024`)
- [x] Opening retrieval returns no evidence → existing empty-evidence not-found persist still runs through `_not_found_turn`; after persist, `after_tutor_turn` on `open` leaves phase `open`. No dedicated opening+empty-retrieve assertion; covered by the shared not-found persist plus TUTOR-16 persist-on-opening
- [x] `Just explain` while `check` is not a pass (`backend/tests/test_application_teaching_policy.py:193-196`)
- [x] `I don't know` while `check` is not a pass (`backend/tests/test_application_teaching_policy.py:205-208`)
- [x] Whitespace-only message still 422 (`backend/tests/test_web_conversations.py:1546`)
- [x] Concurrent opening streams: existing `(conversation_id, turn_index)` unique still 409 (`backend/tests/test_web_conversations.py:1678` claiming a taken index)
- [x] Tutor Start without a resolvable section → 409 target-unavailable (`backend/tests/test_web_conversations.py:1592`)

---

## Gate Check

- **Gate command**: `cd /home/augusto/projects/learny && make lint` plus cycle backend suites (`backend/.venv/bin/python -m pytest` on the files in tasks.md Test Coverage Matrix) and `cd frontend && npm test`. Env: `LEARNY_GENERATION_PROVIDER=local LEARNY_EMBEDDING_PROVIDER=local LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test`. Infra (`db`/`minio`/`redis`) was already up.
- **Result**: lint passed (ruff + tsc + boundaries); backend cycle 637 passed, 0 failed, 3 skipped; frontend 842 passed, 0 failed
- **Test count before feature**: backend `def test_` 2177; frontend `it(` 760 (merge-base `cc81dc32`)
- **Test count after feature**: backend 2256; frontend 781
- **Delta**: +79 backend tests, +21 frontend tests (no decrease)
- **Skipped tests**: `test_answering_anthropic.py` live Anthropic smokes (3) — `LEARNY_ANTHROPIC_API_KEY unset — live Anthropic smoke skipped (CI stays offline)`
- **Failures**: none

---

## Fix Plans (if issues found)

None.

---

## Requirement Traceability Update

| Requirement | Previous Status | New Status |
| ----------- | --------------- | ---------- |
| TUTOR-01 … TUTOR-42 | Done | ✅ Verified |

---

## Summary

**Overall**: Ready

**Spec-anchored check**: 42/42 ACs matched spec outcome | 0 spec-precision gaps
**Sensor**: 3/3 mutations killed
**Gate**: lint passed; backend 637 passed (3 live-provider skips); frontend 842 passed

**What works**: Frozen playbook and user-turn envelope; section-title opening retrieve; application-owned ladder and close lock; Chat dock aliases; one opt-in tutor FSRS card with idempotent accept and reconcile-by-anchor.

**Issues found**: None that fail an AC, the gate, or the sensor.

**Next steps**: none for this cycle.
