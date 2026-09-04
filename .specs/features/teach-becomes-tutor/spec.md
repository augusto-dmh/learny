# teach-becomes-tutor Specification (RFC-0007 Cycle C / Bet 3)

## Problem Statement

Teach is a cited, section-scoped chat with a four-sentence "patient tutor" prompt. The tutor never speaks first, retrieval keys on whatever the learner typed (`"teach me"`), there is no hint ladder or stop condition, and a passing check never becomes a review card. Khanmigo's published correction is that an optional chatbot next to content is skipped; Claude Learning Mode's failure is endless Socratic with no exit. A stranger who opens Teach today gets Ask with a warmer label.

## Goals

- [ ] A frozen teach playbook (pump → hint → prompt → assert), one move per turn, session closes after an unaided check.
- [x] The tutor opens the session with section-first retrieval instead of waiting to be asked.
- [x] Ask and Teach merge into one Chat dock (Answer | Tutor), empty state naming both modes.
- [ ] A passed check offers exactly one FSRS card (opt-in, not auto-inserted).

## Out of Scope

| Feature | Reason |
|---|---|
| New tutor models / LearnLM / Gemini | ADR-0020 holds; RFC Cycle C out |
| Bayesian knowledge tracing / skill graphs | RFC out; FSRS is the mastery loop |
| Forbidding direct answers | "Just explain" stays one tap |
| Auto-inserting the review card | A bad card poisons the due queue; offer only |
| Generating a quiz deck from the session | One checked item, not a deck |
| Mixing Answer turns onto a tutor thread | Closed tutor sessions stay read-only; Ask is a new conversation |
| Pinning path-matched chunks as document 0..k | Title-as-query is the cycle's section-first retrieval; pinning is a follow-up |
| LLM-as-judge of "was that a miss?" | Structured trailers fight the Citations API; ladder is rule-based |
| Pedagogy preference arena vs Gemini | Shape tests and request pins only |
| Teach cache breakpoint move / cost ledger | Bet 7 |
| `first_cited_answer` / sample book / landing | Bet 5 |
| Notifications, undo, formulation gates | Bet 4 |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|
| Chat dock | One **Chat** tab replaces Ask and Teach in the strip. `?panel=ask` and `?panel=teach` remain aliases that open Chat with Answer vs Tutor armed | RFC conflict resolution 5; RFC-004 deep links and Explain/Ask verbs must keep working | auto (AD-288) |
| Tutor-opens vs CONV-10 | Tutor Start creates the conversation and streams a frozen opening sentinel as turn 0. Answer mode stays lazy-create | Khanmigo: the tutor must start. CONV-10 still holds for Ask (discarded first questions leave no row) | auto (AD-289) |
| Opening retrieval query | `target_title`, falling back to `target_anchor` if title is empty; subtree anchors unchanged | RFC "section-first retrieval"; avoids `query="teach me"`. Path-matched pin deferred | auto (AD-290) |
| Ladder storage | `tutor_phase`, `hint_level`, `tutor_ordinary_turns`, `tutor_check_text` on `conversations`; NULL on Answer threads and pre-cycle teach threads | Must-be-true: application-owned, never model memory. History is truncated to 6 turns | auto (AD-291) |
| Pass detection | An ordinary learner message WHILE phase is `check` *is* the unaided check (production, not graded). Empty / chip strings do not pass | No LLM judge this cycle; Bloom analog is "produced one restatement" | auto (AD-292) |
| Forced check | After `LEARNY_TUTOR_CHECK_AFTER_TURNS` (default 3) ordinary learner messages in `elicit`/`scaffold`, the next tutor turn is generated in `check` | Stops endless Socratic (Claude Learning Mode failure) without grading gist quality | auto (AD-293) |
| Chip strings | Exact trimmed match on frozen `TUTOR_JUST_EXPLAIN_MESSAGE` and `TUTOR_DONT_KNOW_MESSAGE`. UI chips send those strings | No new request field; Citations path stays text-only | auto (AD-294) |
| Grounding carve-out | WHERE mode is teach, a non-sentinel reply with zero surviving citations persists as `answered`. Sentinel still `not_found_*`. Answer mode keeps AD-027 | Playbook allows Socratic questions without citing; AD-027 would collapse them to not-found | auto (AD-295) |
| Envelope | `tutor_phase` and `hint_level` are optional `GenerationPort` kwargs interpolated into the **user** turn, never the system prompt | Byte-stable system prompt (cache + ADR-0020) | auto (AD-296) |
| Card | Opt-in `origin='tutor'` free-recall: question is a frozen template with the section title; answer is `tutor_check_text`. No `suggest_cards`. Idempotent re-accept | RFC "exactly one"; rq03 "promote this restatement"; LLM suggest can return empty | auto (AD-297) |
| Card snapshot | `anchor`/`section_path` from the conversation target; `source_excerpt` is the opening turn's first citation snippet, else `target_title` | Reconcile must see book text, not the paraphrase, or the next ingest orphans the card | auto (AD-298) |
| Close lock | WHILE phase is `close`, any new turn is 409. Answer is a new conversation | RFC: session closes after the check; Ask stays one tap away | auto (AD-299) |
| Pre-cycle teach threads | `tutor_phase` NULL and existing turns: behave as today (no forced opening). NULL and zero turns: opening required | Do not break in-flight dogfood threads | auto |
| include_notes | Tutor Start sends `false` (AD-147 teach default). Answer keeps the existing Ask default | Notes-as-evidence is an Ask affordance | auto |
| Rate limit / auth | Existing `rate_limit_conversations` on create/stream; card accept uses `rate_limit_quiz` + origin + CSRF. Cookie session; non-owner 404 | Same surfaces | auto |
| Observability | Opening and check turns use the existing per-turn log. No new scrape endpoint | AD-041 | auto |
| Local adapter | Still extractive; pedagogy is pinned on Anthropic **request shape** and on the state machine, not on local prose | Deterministic adapter ignores mode/history/target today; do not fake a tutor | auto (AD-300) |

**Open questions:** none — all resolved or logged above.

---

## User Stories

### P1: Frozen teach playbook ⭐ MVP

**User Story**: As a learner, I want the tutor to elicit, hint, then tell, one move per turn, so Teach is not a lecture dump and not endless questions.

**Why P1**: The entire pedagogical difference today is four frozen sentences. RFC Cycle C's first bullet.

**Acceptance Criteria**:

1. (TUTOR-01) The teaching system prompt SHALL be a byte-stable module constant with no per-request interpolation, and two calls SHALL return identical bytes.
2. (TUTOR-02) WHEN the teaching adapter builds a request THEN the system prompt SHALL encode: one move per turn, prefer a single question, pump then hint then prompt then assert, assert-and-cite after two failed elicitations, if the learner asks to be told then tell and demand a restatement, Socratic questions and checks may omit citations, claims about the book must cite, off-book claims reply with exactly the existing sentinel, end after a passing unaided check.
3. (TUTOR-03) WHEN a teach generate runs THEN `tutor_phase` and `hint_level` SHALL appear in the user-turn text and SHALL NOT appear in the system prompt.
4. (TUTOR-04) The answering system prompt SHALL remain byte-identical to its pre-cycle value.
5. (TUTOR-05) WHERE mode is teach, WHEN the model returns a non-sentinel reply with no cited chunk ids THEN the system SHALL persist `answer_status` equal to `answered` with the reply text and no citations.
6. (TUTOR-06) WHERE mode is teach, WHEN the model returns exactly the sentinel THEN the system SHALL persist the existing not-found outcome (port never treated as a Socratic pass).
7. (TUTOR-07) WHERE mode is answer, WHEN a reply has no surviving citations THEN the system SHALL keep the AD-027 not-found collapse.

**Independent Test**: pin prompt bytes and the teach user envelope in `test_answering_anthropic.py`; persist a citation-free teach reply in the conversation application tests; answer-mode zero-citation still not-found.

### P1: Tutor opens the session

**User Story**: As a learner, I want the tutor to speak first about the section on screen, so I am not staring at an empty composer wondering what to type.

**Why P1**: Khanmigo post-mortem; RFC second bullet; today's retrieval bug (`query=message`).

**Acceptance Criteria**:

8. (TUTOR-08) WHEN Tutor Start succeeds THEN the system SHALL create the conversation and SHALL stream a first teach turn whose stored message is exactly `TUTOR_OPENING_MESSAGE` before any learner-typed text.
9. (TUTOR-09) WHEN that opening turn retrieves THEN the retrieval query SHALL be the conversation `target_title` if it is non-empty, otherwise `target_anchor`, and SHALL still pass the expanded subtree as `anchors`.
10. (TUTOR-10) WHEN a subsequent non-opening teach turn retrieves THEN the retrieval query SHALL remain the learner message (unchanged from today).
11. (TUTOR-11) IF a teach turn is posted on a conversation with zero turns and the message is not `TUTOR_OPENING_MESSAGE` THEN the system SHALL reject it with 422.
12. (TUTOR-12) IF the previous teach turn is `failed` and its message was the opening sentinel THEN the system SHALL accept another opening sentinel as a new turn (retry).
13. (TUTOR-13) WHEN the opening stream is in flight THEN the Chat composer SHALL be hidden; WHEN the opening turn has persisted (answered, not-found, or failed) THEN the composer SHALL appear.
14. (TUTOR-14) WHEN the thread renders an opening turn THEN it SHALL NOT show a learner bubble for `TUTOR_OPENING_MESSAGE`.
15. (TUTOR-15) WHEN Answer Start (or the first Answer send) runs THEN the system SHALL keep lazy-create: no conversation row until the first learner message.

**Independent Test**: application test that opening retrieve is called with `query=target_title`; 422 on a non-sentinel first teach turn; frontend test that Start creates then streams the sentinel and hides that bubble.

### P1: Application-owned ladder and close

**User Story**: As a learner, I want the session to actually end after I restate the passage, and I want "just explain" to work in one tap, so I am neither trapped in Socratic mode nor dumped the chapter on turn one.

**Why P1**: RFC must-be-true (state is application-owned) and the "just explain stays one tap" out-item.

**Acceptance Criteria**:

16. (TUTOR-16) WHEN the opening teach turn is accepted THEN the conversation SHALL store `tutor_phase=open` and `hint_level=pump`.
17. (TUTOR-17) WHEN the learner sends an ordinary message WHILE `tutor_phase` is `open` THEN the system SHALL set `tutor_phase=elicit` for the following generate.
18. (TUTOR-18) WHEN the learner sends exactly `TUTOR_DONT_KNOW_MESSAGE` THEN the system SHALL advance `hint_level` one step along `pump → hint → prompt → assert` (already-`assert` stays `assert`) and SHALL count that message as a scaffold miss, not an ordinary turn.
19. (TUTOR-19) WHEN the learner sends exactly `TUTOR_JUST_EXPLAIN_MESSAGE` THEN the following generate SHALL use `hint_level=assert`, and after that tutor turn persists the system SHALL set `tutor_phase=check`.
20. (TUTOR-20) WHEN `tutor_ordinary_turns` reaches `LEARNY_TUTOR_CHECK_AFTER_TURNS` (default 3) WHILE phase is `elicit` or `scaffold` THEN the following tutor generate SHALL use `tutor_phase=check`.
21. (TUTOR-21) WHEN two scaffold misses have accumulated THEN the following tutor generate SHALL use `hint_level=assert`, and after it persists the system SHALL set `tutor_phase=check`.
22. (TUTOR-22) WHEN the learner sends an ordinary non-empty message WHILE `tutor_phase` is `check` THEN the system SHALL set `tutor_phase=close` and SHALL store that message as `tutor_check_text`.
23. (TUTOR-23) WHILE `tutor_phase` is `close` WHEN any new turn is posted THEN the system SHALL respond 409 and SHALL persist nothing.
24. (TUTOR-24) Conversation read and list views SHALL include `tutor_phase` and `hint_level` (null when the ladder does not apply).
25. (TUTOR-25) IF a conversation has `tutor_phase` set WHEN a turn is posted with `mode=answer` THEN the system SHALL respond 422.
26. (TUTOR-26) WHERE `tutor_phase` is null (Answer threads and pre-cycle teach threads with existing turns) the system SHALL NOT require the opening sentinel and SHALL NOT 409 on further turns.

**Independent Test**: table-driven `TeachingPolicy` tests for every transition above; HTTP 409 on a closed conversation; 422 mixing answer mode onto a tutor thread.

### P1: One Chat dock

**User Story**: As a learner, I want Ask and Teach in one Chat surface that names both modes, so I do not miss the tutor because it lives in a second tab.

**Why P1**: RFC third bullet; rq03 "discoverability comes from behavior, not from a tab."

**Acceptance Criteria**:

27. (TUTOR-27) The dock tab strip SHALL show Chat, Notes, and Review (no separate Ask or Teach tabs).
28. (TUTOR-28) WHEN `?panel=ask` THEN the dock SHALL open Chat with Answer armed. WHEN `?panel=teach` THEN the dock SHALL open Chat with Tutor armed. WHEN `?panel=chat` THEN the dock SHALL open Chat with the last-used mode, defaulting to Answer.
29. (TUTOR-29) WHEN Chat is empty (no active thread) THEN the empty state SHALL name both Answer and Tutor as distinct modes.
30. (TUTOR-30) WHEN Tutor is armed with no thread THEN the empty state SHALL let the learner pick a section (default: the chapter currently on screen) and Start.
31. (TUTOR-31) WHEN a conversation is resumed THEN the composer mode SHALL follow `last_turn_mode` (`teach` → Tutor, otherwise Answer), not the tab the learner happened to be on.
32. (TUTOR-32) WHEN the capture Explain or Ask verb opens the dock THEN it SHALL still auto-submit in Answer mode (existing pending-request contract).
33. (TUTOR-33) WHILE a tutor conversation is `close` the Chat SHALL hide the composer and SHALL offer a control that starts a new Answer conversation on the same source.

**Independent Test**: reader-panel tests for strip labels, alias params, empty-state copy, resume-by-`last_turn_mode`, and Explain pending-request.

### P1: Passed check offers one FSRS card

**User Story**: As a learner, I want to save the restatement I just produced as a review card, so the tutor session actually feeds memory.

**Why P1**: RFC fourth bullet; Learny's only unfair advantage vs Study Mode.

**Acceptance Criteria**:

34. (TUTOR-34) WHEN `tutor_phase` becomes `close` THEN the Chat SHALL offer exactly one card whose question is `In your own words, what is "{target_title}" arguing?` and whose answer is `tutor_check_text`.
35. (TUTOR-35) WHEN the learner accepts that offer THEN the system SHALL insert one `origin=tutor` `free_recall` quiz item, schedule it due-now with the existing FSRS adapter, and SHALL NOT call `suggest_cards` or deck generation.
36. (TUTOR-36) WHEN the learner accepts again on the same conversation THEN the system SHALL return the existing item and SHALL NOT insert a second row or rewrite scheduling.
37. (TUTOR-37) IF accept is posted WHILE `tutor_phase` is not `close` THEN the system SHALL respond 409.
38. (TUTOR-38) WHEN the card is written THEN `anchor` and `section_path` SHALL equal the conversation target snapshot, and `source_excerpt` SHALL equal the opening turn's first citation snippet when one exists, otherwise `target_title`.
39. (TUTOR-39) WHEN the origin conversation is deleted THEN the tutor card SHALL remain and its `conversation_id` SHALL become null.
40. (TUTOR-40) WHEN quiz reconcile runs THEN a tutor card whose target anchor still exists SHALL stay `active`; IF the anchor is gone THEN it SHALL become `orphaned` without rewriting scheduling or `review_log`.
41. (TUTOR-41) WHEN the learner dismisses the offer THEN the system SHALL persist no quiz row and SHALL leave the conversation `close`.
42. (TUTOR-42) IF accept is posted by a user who does not own the conversation THEN the system SHALL respond 404.

**Independent Test**: accept on a closed conversation creates one due card; second accept is idempotent; accept before close is 409; deleting the conversation leaves the card; reconcile orphan pin.

---

## Edge Cases

- IF opening generation fails THEN the system SHALL persist a `failed` opening turn (AD-262) and SHALL allow retry of the opening sentinel.
- IF opening retrieval returns no evidence THEN the system SHALL persist the existing empty-evidence not-found turn and SHALL still leave phase `open` so the learner can retry or leave.
- IF `Just explain` is sent WHILE phase is `check` THEN the system SHALL assert once more and SHALL remain in `check` (that message is not a pass).
- IF `I don't know` is sent WHILE phase is `check` THEN the system SHALL treat it as a scaffold miss / assert path, not as a pass.
- IF a whitespace-only message is posted THEN the existing 422 empty-message validator SHALL still reject it.
- WHEN two concurrent opening streams race THEN the existing `(conversation_id, turn_index)` unique SHALL make one turn win and the other 409, same as today.
- IF Tutor Start is attempted without a resolvable section THEN the system SHALL 409 with the existing target-unavailable mapping (whole-book teach is still impossible).

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
|---|---|---|---|
| TUTOR-01 | P1: Frozen playbook | T1 | Done |
| TUTOR-02 | P1: Frozen playbook | T1 | Done |
| TUTOR-03 | P1: Frozen playbook | T2 | Done |
| TUTOR-04 | P1: Frozen playbook | T1 | Done |
| TUTOR-05 | P1: Frozen playbook | T3 | Done |
| TUTOR-06 | P1: Frozen playbook | T3 | Done |
| TUTOR-07 | P1: Frozen playbook | T3 | Done |
| TUTOR-08 | P1: Tutor opens | T13 | Done |
| TUTOR-09 | P1: Tutor opens | T4 | Done |
| TUTOR-10 | P1: Tutor opens | T4 | Done |
| TUTOR-11 | P1: Tutor opens | T7 | Done |
| TUTOR-12 | P1: Tutor opens | T7 | Done |
| TUTOR-13 | P1: Tutor opens | T13 | Done |
| TUTOR-14 | P1: Tutor opens | T13 | Done |
| TUTOR-15 | P1: Tutor opens | T13 | Done |
| TUTOR-16 | P1: Ladder and close | T7 | Done |
| TUTOR-17 | P1: Ladder and close | T7 | Done |
| TUTOR-18 | P1: Ladder and close | T6 | Done |
| TUTOR-19 | P1: Ladder and close | T7 | Done |
| TUTOR-20 | P1: Ladder and close | T6 | Done |
| TUTOR-21 | P1: Ladder and close | T6 | Done |
| TUTOR-22 | P1: Ladder and close | T7 | Done |
| TUTOR-23 | P1: Ladder and close | T7 | Done |
| TUTOR-24 | P1: Ladder and close | T8 | Done |
| TUTOR-25 | P1: Ladder and close | T7 | Done |
| TUTOR-26 | P1: Ladder and close | T7 | Done |
| TUTOR-27 | P1: One Chat dock | T12 | Done |
| TUTOR-28 | P1: One Chat dock | T12 | Done |
| TUTOR-29 | P1: One Chat dock | T13 | Done |
| TUTOR-30 | P1: One Chat dock | T13 | Done |
| TUTOR-31 | P1: One Chat dock | T12 | Done |
| TUTOR-32 | P1: One Chat dock | T12 | Done |
| TUTOR-33 | P1: One Chat dock | T14 | Done |
| TUTOR-34 | P1: One FSRS card | Tasks | In Tasks |
| TUTOR-35 | P1: One FSRS card | T10 | Done |
| TUTOR-36 | P1: One FSRS card | T10 | Done |
| TUTOR-37 | P1: One FSRS card | T10 | Done |
| TUTOR-38 | P1: One FSRS card | T10 | Done |
| TUTOR-39 | P1: One FSRS card | T9 | Done |
| TUTOR-40 | P1: One FSRS card | T11 | Done |
| TUTOR-41 | P1: One FSRS card | Tasks | In Tasks |
| TUTOR-42 | P1: One FSRS card | T10 | Done |

**ID format:** `TUTOR-NN`

**Coverage:** 42 total, 42 mapped to tasks, 0 unmapped

---

## Success Criteria

- [ ] Starting Tutor on a ready section yields a tutor question before the learner types.
- [ ] Opening retrieval is pinned to `target_title`, not the sentinel string.
- [ ] A citation-free Socratic teach reply persists as answered; the same shape in Answer stays not-found.
- [ ] After a check restatement the composer is gone and exactly one card can be accepted into the due queue.
- [x] `?panel=ask` and `?panel=teach` still open the dock; the strip reads Chat | Notes | Review.
