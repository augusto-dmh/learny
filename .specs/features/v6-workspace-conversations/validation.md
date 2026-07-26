# Validation — v6-workspace-conversations

**Final verdict: PASS** (round 2, after fix iteration 1)
**Round 1 verdict: FAIL** — 4 coverage regressions, no functional defect. Record kept below.

**Diff verified:** `8b8ea0fc..HEAD` — 31 commits, branch `feat/workspace-conversations`.
Round 1 covered `8b8ea0fc..3fe4e0e7` (29 commits); round 2 adds `0714b94c`
(restores the sensors) and `f00d1513` (corrects the design doc's knob count).
**Verifier:** independent; did not author any of this code, in either round. Every
claim rests on a command run during verification, not on the author's or the lead's
notes — including round 2, where the four mutations the lead reported as newly killed
were re-derived from scratch rather than accepted.

---

## Round 2 — what closed the FAIL

`0714b94c` adds nine sensors to `backend/tests/test_application_conversations.py` and
changes **no production code**. `git diff 3fe4e0e7..HEAD` touches exactly two files
(that test file and `design.md`), and the test-file diff is purely additive apart from
three import lines — no existing assertion is relaxed, deleted, or re-scoped. I read
the whole diff to confirm this rather than trusting the line counts.

### The five mutations re-run independently

| # | Mutation | Result | Killed by |
| --- | --- | --- | --- |
| M10 | Remove the sentinel hold-back so every delta passes straight through | ☠️ killed | `test_stream_never_shows_a_reader_the_whole_reply_sentinel`, `test_stream_flushes_a_divergent_sentinel_prefix_as_one_delta` |
| M11 | Remove the short-answer flush branch | ☠️ killed | `test_stream_flushes_a_short_answer_that_merely_looked_like_the_sentinel` |
| M12 | Grounding stops filtering evidence by what the adapter cited | ☠️ killed | `test_a_turn_cites_only_the_evidence_the_generator_referenced` |
| M15 | Completion log interpolates the reader's message and the answer text | ☠️ killed | all three log sensors |
| M16 | Grounding drops the blank-answer-text clause | ☠️ killed | both parametrizations of `test_a_turn_whose_answer_text_is_blank_is_not_found_despite_its_citations` |

On the lead's note about M10: my formulation used `event.text` off the real
`AnswerTextDelta`, so the mutant genuinely passed deltas through. I confirmed the kill
is for the right reason by reading the failure — `assert ['NOT_FOUND', '_IN_SOURCE']
== []`. The sentinel text really does reach the reader under the mutant, and the test
really does catch it. Not a pass-for-the-wrong-reason.

### Two further mutations, not previously run

| # | Mutation | Result | Killed by |
| --- | --- | --- | --- |
| M20 | A stream ending with no completed event yields an empty answer instead of raising | ☠️ killed | `test_stream_that_ends_without_a_completed_event_is_a_generation_failure` |
| M21 | `_persist` emits a second completion log line | ☠️ killed | all three log sensors — the "exactly one" half of the claim, not just the content-free half |

### Branch reachability — the check that caught round 1

A sensor that passes without reaching the branch is the exact failure mode of round 1,
so the instrumentation was re-run in full (atexit-dumped hit set, whole suite,
`-p no:randomly`).

`hold_back_deltas` — now reached: `B0_passthrough`, **`B1_buffering`**,
`B2_divergence_flush`, **`B3_short_answer_flush`**, **`B4_no_completed_event`**, and
`B7_held_and_suppressed` (an extra probe I added for the whole-sentinel case: held,
accumulated, and correctly *not* flushed). Every branch dead in round 1 now executes.

`ground()` — now reached: **`G_blank_text`**, **`G_filtered_some`**, and
`G_reordered_vs_citation_order` (a probe confirming the evidence-rank reordering is
genuinely exercised — the new test cites out of rank order with one unretrieved id
mixed in, so the ordering assertion is not trivially satisfied).

### Do the new sensors mirror the implementation?

No. Each is derived from the product consequence, not the code shape, and each states
that consequence in its own comment:

- The sentinel tests split `SENTINEL` across delta boundaries and assert on what a
  *reader* receives (`_deltas(events) == []`), not on the internal `held` flag.
- The citation test has the generator cite out of rank order and include an id that
  was never retrieved, then asserts the persisted tuple is the cited subset in
  **evidence-rank** order — three independent properties in one assertion, none of
  which restates the filter expression.
- The blank-text test is parametrized over `""` and `"   \n\t"`, so it pins the
  `.strip()` semantics rather than an emptiness check, and additionally asserts the
  persisted turn is the not-found one.
- The log tests assert on *absence* of two specific private strings plus `len == 1`,
  which is a property no implementation detail can satisfy accidentally.

One structural note: the log sensors filter records by the logger name
`"app.application.conversations"`, which couples them to the module path. That is a
weak coupling (a module rename would fail the test loudly, not silently) and is the
normal shape for a `caplog` assertion. Not a finding.

### WSC-09

**Now met.** The requirement is "every behavior those tests protected that still
exists SHALL be asserted against the unified surface". All four regressions (R1–R4)
plus the lower-ranked B4 case are closed, each confirmed by both a dying mutant and a
branch that now executes. I re-walked the deleted-test inventory looking for anything
I missed in round 1 and found nothing further.

---

## Round 2 baseline (re-run, not inherited)

| Gate | Result |
| --- | --- |
| `uv run pytest tests/` | **1850 passed**, 11 skipped, 1 deselected |
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 246 files already formatted |
| `uv run python scripts/check_boundaries.py` | architecture boundaries clean |
| `npm test` (frontend) | 642 passed across 66 files — unchanged, confirmed not assumed |
| `npx tsc --noEmit` | clean |
| `git status` | clean (every mutation restored) |

+11 backend tests: 9 new sensors, of which two are parametrized (blank text ×2). Only
the known local HNSW failure is deselected; the ingestion flake did not reproduce in
either round-2 run.

**Design doc correction (`f00d1513`) is accurate.** It records that five knobs were
retired rather than three, and explains why the two `*_max_chars` bounds — reserved by
the written plan as "actively read" — became dead once the panels re-pointed. This
matches `_RETIRED_KNOBS` in `app/core/config.py`, which carries all five, and closes
the scope note I raised in §4.

---

## Round 1 record (the original FAIL)

Kept in full below. The implementation was correct as far as I could drive it: 19
injected behavior-level faults, 15 killed, and every one of the cycle's own named
traps (the AD-205 mode discriminator, the tie-ordering guarantee, the
create-then-stream orphan window, ownership, the rate-limit claim, the delete cascade)
had a sensor that fired. The FAIL was entirely about **WSC-09**: the retirement
deleted five suites, and four still-live behaviors lost their only sensor.

### Round 1 baseline

| Gate | Result |
| --- | --- |
| `uv run pytest tests/` | 1839 passed, 11 skipped, 2 deselected |
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 246 files already formatted |
| `uv run python scripts/check_boundaries.py` | architecture boundaries clean |
| `npm test` (frontend) | 642 passed across 66 files |
| `npx tsc --noEmit` | clean |
| `git status` | clean (every mutation restored) |

Deselected: the two conditions named as known-local in the brief. Both reproduce as
described and neither is touched by this diff.

---

## 1 — Spec-anchored outcome check

Each row names the test I ran and confirmed asserts the **spec's** value, not merely
that the code does what it does.

| Req | Spec-defined outcome | Sensor | OK |
| --- | --- | --- | --- |
| WSC-01 | Ask/Teach create via `POST /api/conversations`, first turn posted to it; follow-up goes to the same conversation | `frontend/tests/ask-panel.test.tsx`, `teach-panel.test.tsx`, `conversations-client.test.ts:40`; killed by M17 | ✅ |
| WSC-02 | Reload restores turns **from the server**, not client state | `ask-panel.test.tsx:428` ("restores an active thread's turns from the server after a reload" — re-renders a fresh tree after `vi.restoreAllMocks()`, so client state cannot satisfy it); `teach-panel.test.tsx:463` | ✅ |
| WSC-03 | Rendered answer/citations/status identical to pre-re-point for an identical grounded request | `test_golden_citations.py::test_answer_text_is_still_the_adapter_composition_of_its_evidence` (byte comparison against the adapter's own composition); committed replay snapshots in `tests/eval/` unchanged by the diff and their parametrized invariant tests run (only the *recorder* skips) | ✅ |
| WSC-04 | Scope miss renders a message **distinct from** the whole-book miss | `frontend/tests/not-found-notice.test.tsx:18` asserts `scoped !== wholeBook` and that the whole-book text does not contain "elsewhere"; killed by M8 | ✅ |
| WSC-05 | Dock lists this book's conversations, newest first, title + turn count; resume in place | `frontend/tests/reader-panel.test.tsx` — "lists this book's conversations with their titles and turn counts", "shows one list holding both a scoped and a whole-book conversation", "says so when a book has no conversations yet", "resumes an asked conversation in the Ask panel without switching tabs", "resumes a taught conversation in the Teach panel", "starts a fresh thread on request without touching the other surface" | ✅ |
| WSC-06 | Rename persists + shows without reload; delete removes and turns become unretrievable; empty state; ask and teach in one list | `conversation-dock.test.tsx` — "persists the new title and shows it in the list without a reload", "leaves the stored title unchanged when the new one is blank", "keeps the old title and explains itself when the server rejects the new one", "removes it from the list", "returns the panel to its empty state when the open conversation is deleted"; `test_web_conversations.py::test_delete_leaves_no_turn_or_citation_row_behind` ( counts rows in `conversation_turns` and `conversation_turn_citations` directly, with a second conversation kept as a scoping control); `reader-panel.test.tsx` — "shows one list holding both a scoped and a whole-book conversation" | ✅ |
| WSC-07 | Retired paths respond **404** | `test_retired_surface.py::test_every_retired_path_answers_404_to_its_owner` — all 7 paths, called by a user who **owns** the named source, with a body carrying every field the old wires wanted, so neither absence nor malformation can produce the 404 | ✅ |
| WSC-08 | Modules absent; knobs not fields; boot survives the env vars | `test_retired_surface.py::test_no_retired_module_is_importable` (uses `importlib.util.find_spec` — absence, not merely unrouted), `::test_the_app_declares_no_route_on_a_retired_path` (reads the assembled app's route inventory), `::test_the_app_boots_with_every_retired_variable_still_set`; `test_config.py::test_retired_knobs_are_no_longer_fields`, `::test_every_retired_variable_names_a_setting_that_still_exists`, `::test_a_deployment_still_setting_a_retired_variable_boots`, `::test_setting_a_retired_knob_warns_once_naming_the_value_in_force` | ✅ |
| WSC-09 | Every still-live behavior the deleted tests protected is asserted on the unified surface | Round 1: **not met — see §3**. Round 2: closed by `0714b94c` | ✅ |
| WSC-10 | One port; mode explicit; single non-union model type; `TeachingGenerationPort` gone; deterministic output byte-identical | `test_generation_port.py` (all 3 tests — the third reads `typing.get_type_hints` and asserts `get_origin(...) is None`, which is the union check the spec asks for); `test_answering_local.py:85,106` (both modes, frozen prose); killed by M1, M2 | ✅ |
| WSC-11 | Label reads "Search my notes too"; description available; start sends an explicit boolean | `include-notes-toggle.test.tsx:18,26`; `conversations-client.test.ts:66` ("sends the notes choice even when the choice is the default"); killed by M18 | ✅ |
| WSC-12 | Bounded default page; named window; 422 outside bounds; no row skipped or duplicated on ties | `test_web_conversations.py::test_list_without_pagination_returns_a_bounded_default_page`, `::test_list_limit_and_offset_return_that_window_of_the_order`, `::test_list_paged_to_the_end_returns_every_conversation_exactly_once`, `::test_list_rejects_a_page_outside_its_bounds`; killed by M3, M4 | ✅ |
| WSC-13 | A failed/aborted first message leaves no orphan conversation | `conversation-orphans.test.tsx` (3 tests, driven against a fake server that **holds** state, so the assertion is about what the server has); killed by M9a, M9b | ✅ |
| WSC-14 | 409 on turn-index race and stale teach target; 422 on unresolvable scope — preserved through convergence | `test_application_conversations.py::test_a_turn_index_race_surfaces_as_a_conflict`, `::test_a_turn_index_race_surfaces_as_a_conflict_while_streaming`, `::test_teach_turn_on_a_whole_book_conversation_is_a_state_conflict`, `::test_teach_turn_whose_target_section_disappeared_is_a_state_conflict`; `test_web_conversations.py::test_teach_turn_in_whole_book_conversation_returns_409`, `::test_teach_turn_with_vanished_target_returns_409`, `::test_post_turn_claiming_a_taken_index_returns_409`, `::test_start_unresolvable_scope_anchor_returns_422_and_creates_nothing` | ✅ |
| WSC-15 | No surviving mutating route loses its limiter | `test_web_conversations.py::test_every_mutating_conversation_route_carries_the_one_policy`, `::test_no_mutating_conversation_route_answers_while_the_budget_is_spent`; `test_retired_surface.py::test_no_throttle_outlives_the_routes_it_guarded`; killed by M5 | ✅ |

### Requirements whose wording is imprecise

- **WSC-03** ("the same as before the re-point") names no artifact to compare
  against. In practice it is discharged by the deterministic golden and the
  committed replay snapshots, which is the strongest reading available, but the
  spec does not say so and a weaker implementation could claim the same words.
- **WSC-09** is the only requirement stated as a property over a set that is not
  enumerated anywhere ("every behavior those tests protected that still exists").
  Nothing in the tree lists that set, which is exactly how §3's gaps got through.

### Tests that mirror the implementation

None found that materially weaken a requirement. `test_generation_port.py` is
structural (it inspects signatures and type hints rather than behavior), but that is
the honest shape for "this protocol no longer exists" and it is paired with the
behavioral sensors at `test_application_conversations.py::test_scoped_answer_turn_generates_as_an_answer_despite_its_target_snapshot`
and `::test_scoped_answer_stream_generates_as_an_answer_despite_its_target_snapshot`.

---

## 2 — Discrimination sensor

Method: inject one behavior-level fault, run the target module (full suite where
survival was claimed), restore. Working tree confirmed clean afterwards.

| # | Mutation | File | Result | Killed by |
| --- | --- | --- | --- | --- |
| M1 | `_target_path` reads the conversation's stored target snapshot instead of the mode — **the AD-205 trap exactly** | `app/application/conversations.py` | ☠️ killed | `test_scoped_answer_turn_generates_as_an_answer_despite_its_target_snapshot`, `..._stream_...`, `test_answer_mode_sends_the_bounded_history_to_the_answer_port` |
| M2 | Anthropic adapter dispatches on `target_section_path is not None` instead of `mode` — the same trap one layer down | `app/infrastructure/answering/anthropic.py` | ☠️ killed | `test_answer_mode_with_a_target_still_sends_the_answer_request`, `..._stream_...` |
| M3 | Drop the `id DESC` tiebreaker from the list ORDER BY | `db/repositories.py` | ☠️ killed | `test_list_paged_to_the_end_returns_every_conversation_exactly_once` |
| M4 | Remove the `limit` cap and the bounded default | `web/conversations.py` | ☠️ killed | `test_list_without_pagination_returns_a_bounded_default_page`, `test_list_rejects_a_page_outside_its_bounds` |
| M5 | Drop `rate_limit_conversations` from the DELETE route | `web/conversations.py` | ☠️ killed | `test_every_mutating_conversation_route_carries_the_one_policy`, `test_no_mutating_conversation_route_answers_while_the_budget_is_spent` |
| M6 | Remove the ownership check in `authorized_conversation` | `application/conversations.py` | ☠️ killed | 10 tests — read/rename/delete/turn/turn-stream at both web and application level |
| M7 | Remove the `sources.user_id` join predicate from `list_for_user` | `db/repositories.py` | ☠️ killed | `test_list_filters_by_source_and_excludes_other_users`, `test_conversation_list_for_user_filters_by_source_and_excludes_other_owners` |
| M8 | Collapse the scope-miss message into the whole-book message | `not-found-notice.tsx` | ☠️ killed | `not-found-notice.test.tsx:18`, `teach-panel.test.tsx:456`, `ask-panel.test.tsx` |
| M9a | `onFinish` discards only on `isError` (abort/disconnect no longer discard) | `use-conversation-thread.ts` | ☠️ killed | `conversation-orphans.test.tsx` "leaves no conversation behind when the reader stops the turn" |
| M9b | A completed first message never clears `provisionalRef` | `use-conversation-thread.ts` | ☠️ killed | `conversation-orphans.test.tsx` "keeps the thread when a later message fails" |
| **M10** | **Remove the sentinel hold-back entirely (every delta passes straight through)** | `application/streaming.py` | 🧟 **SURVIVED** (full suite) | — |
| **M11** | **Remove the short-answer flush branch** | `application/streaming.py` | 🧟 **SURVIVED** (full suite) | — |
| **M12** | **Grounding stops filtering evidence by what the adapter actually cited** | `application/grounding.py` | 🧟 **SURVIVED** (full suite) | — |
| M13 | Silence the retired-knob startup warning | `core/config.py` | ☠️ killed | `test_setting_a_retired_knob_warns_once_naming_the_value_in_force` |
| M14 | Collapse the not-found verdict to `not_found_in_source` always | `application/conversations.py` | ☠️ killed | 7 tests across application + web |
| **M15** | **Turn-completion log emits the reader's message and the answer text** | `application/conversations.py` | 🧟 **SURVIVED** (full suite) | — |
| **M16** | **Grounding drops the blank-answer-text guard** | `application/grounding.py` | 🧟 **SURVIVED** (full suite) | — |
| M17 | `resolveConversationId` always creates a new conversation | `use-conversation-thread.ts` | ☠️ killed | 4 tests across 3 files |
| M18 | `include_notes` omitted from the start body when true (implicit default) | `lib/conversations.ts` | ☠️ killed | `conversations-client.test.ts:66` |
| M19 | Composition root hardcodes `evidence_top_k`/`history_turns`, ignoring settings | `web/dependencies.py` | 🧟 SURVIVED — **pre-existing**, see below | — |

**15 killed / 19.** M19 is not attributable to this cycle: `git show
8b8ea0fc:backend/app/infrastructure/web/dependencies.py` has the same wiring and
`git grep evidence_top_k 8b8ea0fc -- backend/tests` shows no sensor for it before
the cycle either. Reported for the record, not as a cycle defect.

### Branch-reachability instrumentation

Because a surviving mutant can also mean "the branch never runs", I instrumented
both modules with an atexit-dumped hit set and ran the full suite (`-p no:randomly`).

`app/application/streaming.py::hold_back_deltas` — branches reached across the
**entire** suite: `B0_passthrough`, `B2_divergence_flush`, `B5_port_failure_wrap`,
`B6_close`. **Never reached:** `B1` (buffering while the text is still a sentinel
prefix), `B3` (short-answer flush), `B4` (stream ends with no completed event).
`B2` is reached only in its trivial form — the first delta always diverges
immediately — which is why M10 survives despite `B2` "executing".

`app/application/grounding.py::ground` — reached: `G_found_false`,
`G_no_citation_survives`. **Never reached:** `G_blank_text` (`found=True` with blank
text) and `G_filtered_some` (a generated answer citing a strict subset of the
retrieved evidence — i.e. the filter ever actually removing anything).

---

## 3 — Coverage-regression analysis of the −142

161 tests were deleted from five files; ~19 were added, netting −142.

| Deleted file | Tests | Disposition |
| --- | --- | --- |
| `test_web_teaching.py` | 38 | wire-freeze for a deleted wire |
| `test_web_questions.py` | 32 | wire-freeze for a deleted wire |
| `test_application_qa.py` | 34 | service deleted |
| `test_application_teaching.py` | 45 | service deleted |
| `test_web_rate_limit_validation.py` | 2 of 12 | **file retained** — only the two legacy limiter-dependency tests went, alongside the dependencies themselves. The auth rate-limit and auth-validation tests all survive (verified by reading the current file: 10 tests remain). |

I walked all 161 deleted names against the current tree. The overwhelming majority
are correctly re-anchored — the wire-level behaviors onto `test_web_conversations.py`
(SSE frame sequence :1544, status framing :1595, mid-stream error + no persistence
:1634, synchronous handlers :1768, note-citation origin :1942, message bounds :1286,
:1308, 404-collapse :1394), and the service-level behaviors onto
`test_application_conversations.py` (history bound :1400, empty-evidence short-circuit
:1312, port-failure-persists-nothing :1773, cancellation persists nothing and closes
the port stream :1865/:1886, index race :1735/:1755). A handful are correctly *gone*
rather than moved (`test_ask_stays_out_of_the_teaching_panel`,
`test_list_excludes_conversations_without_a_teach_target` — both retired by AD-208;
the legacy discard-on-failure tests, whose behavior moved to the frontend and is
covered by `conversation-orphans.test.tsx`).

**Four behaviors are live and lost their only sensor.** Each is confirmed by a
surviving mutant *and* by branch instrumentation showing the code path is never
executed by any test in the suite.

> **All four closed in round 2** by `0714b94c`. Each fix task below was implemented as
> written; see "Round 2 — what closed the FAIL" above for the mutation and
> branch-reachability evidence.

### R1 — The sentinel hold-back (HIGH)

`hold_back_deltas` still runs on every streamed turn. Its job is to stop the literal
string `NOT_FOUND_IN_SOURCE` from streaming to a reader as if it were an answer: the
provider emits that token as a whole reply to mean "I cannot ground this", and the
hold-back buffers deltas while the accumulated text is still a prefix of it.

- Sensors deleted: `test_application_qa.py::test_stream_whole_reply_sentinel_suppresses_deltas_and_is_not_found`, `::test_stream_flushes_a_divergent_prefix_as_one_delta`, `::test_stream_flushes_short_answer_that_looked_like_a_sentinel_prefix`; `test_application_teaching.py::test_stream_whole_reply_sentinel_persists_not_found`.
- Replacement: **none**. M10 deletes the entire mechanism and the full suite stays green (1839 passed). M11 deletes only the short-answer flush; also green.
- Branches `B1` and `B3` are never executed by any test.
- Note: `test_answering_anthropic.py` covers the sentinel in the *buffered* parse (`test_whole_reply_sentinel_is_not_found_with_empty_text`). That is a different code path — the adapter's `_parse_message`, not the application's streaming hold-back — and does not substitute.

**Fix task:** add streaming sensors on `PostConversationTurn.stream` for (a) a port stream whose deltas spell the sentinel exactly — no `StreamDelta` is yielded and the turn persists not-found; (b) a stream whose deltas begin with a sentinel prefix then diverge — the buffered prefix is flushed as **one** delta; (c) a genuine short answer that is a proper prefix of the sentinel — flushed once at completion.

### R2 — The grounding citation filter (HIGH)

`ground()` keeps only the evidence the adapter actually cited. It is the AD-027
citation-integrity guard: without it a turn cites passages the model never referenced.

- Sensor deleted: `test_application_qa.py::test_ask_answered_grounds_orders_and_dedupes_citations`.
- Replacement: **none**. M12 replaces the filter with "cite everything retrieved whenever the adapter cited anything at all"; the full suite stays green.
- `G_filtered_some` is never executed — no test in the suite has an adapter citing a strict subset of the retrieved evidence. Every existing test either cites all of it or cites none of it.
- `test_scoped_turn_never_cites_evidence_outside_its_scope` (`test_web_conversations.py::test_scoped_turn_never_cites_evidence_outside_its_scope`) does **not** cover this: it constrains what retrieval *returns*, not what grounding filters out of it.

**Fix task:** a turn test where the generator cites a strict subset of the evidence, asserting the persisted citations are exactly that subset, in evidence-rank order.

### R3 — The blank-answer-text guard (MEDIUM)

`ground()` returns the not-found outcome when the adapter reports `found=True` with
blank or whitespace-only text.

- Sensors deleted: `test_application_qa.py::test_ask_blank_answer_text_is_not_found`, `test_application_teaching.py::test_turn_blank_text_not_found`.
- Replacement: **none**. M16 removes the `not generated.text.strip()` clause; full suite green. `G_blank_text` never executes.
- Consequence if it regressed: a turn persists with `answer_status=answered` and empty `answer_text`, which the panel renders as a blank answer with citations attached.

**Fix task:** a turn test with a `found=True`, blank-text generated answer, asserting the not-found verdict and that nothing is persisted as answered.

### R4 — The content-free completion log (MEDIUM)

`PostConversationTurn._persist` emits exactly one `logger.info` per completed turn,
carrying ids and counts only — never the reader's message or the answer text.

- Sensors deleted: `test_application_qa.py::test_ask_emits_one_content_free_completion_log`, `::..._on_not_found`, `test_application_teaching.py::test_turn_emits_one_content_free_completion_log`.
- Replacement: **none**. M15 makes the log interpolate `turn.message` and `turn.answer_text` into the message; full suite green. The only `caplog` users left in the suite are `test_config.py`, `test_logging_redaction.py`, `test_web_instrument.py`, none of which touches the conversation path.
- `test_logging_redaction.py` masks *sensitive keys* in structured args; it does not stop book content or a reader's question appearing in a log message body.

**Fix task:** a `caplog` sensor on the turn path asserting exactly one completion record and that neither the message nor the answer text appears in it, for both the answered and not-found outcomes.

### Also missing a stated behavior, lower severity

`test_application_qa.py::test_stream_ending_without_completed_event_raises` — branch
`B4` (a port stream that ends with no `AnswerCompleted`) is never executed. This is a
port-contract violation rather than a reachable product state, so I rank it below
R1–R4, but it is the same class of loss.

---

## 4 — Retirement completeness (independently confirmed)

- **Paths 404** — `test_every_retired_path_answers_404_to_its_owner`, all 7, owner-authenticated.
- **Modules unimportable** — `importlib.util.find_spec` returns `None` for all 5.
- **No orphaned throttles** — `test_no_throttle_outlives_the_routes_it_guarded` walks the assembled app's dependency tree and requires every `rate_limit_*` the module offers to be reachable from a route. M5 confirms it fires.
- **Boot with retired vars set** — passes; the list is read off `_RETIRED_KNOBS`, so a knob retired later is covered without the test being edited.
- **Warning still fires** — M13 killed by `test_setting_a_retired_knob_warns_once_naming_the_value_in_force`.
- **No stale references** — grepped `teaching-sessions`, `/questions/stream`, `teaching_sessions` across `.py/.ts/.tsx/.md/.yml`. Every hit outside `.specs/` and the ADR/RFC/TDD historical record is gone.

**Scope note (not a defect):** the spec says "the three superseded knobs"; five were
retired (`LEARNY_QA_QUESTION_MAX_CHARS` and `LEARNY_TEACHING_MESSAGE_MAX_CHARS` were
added by commit `231d339c` once the re-point left nothing reading them). The design
doc explicitly reserved `teaching_message_max_chars` as "actively read and not part of
this deletion", so this is a deliberate in-cycle widening beyond the written plan. It
is correctly covered by `_RETIRED_KNOBS` and its tests; flagged only so the record
matches.

---

## 5 — What I could not verify

- **Real provider behavior.** All Anthropic coverage runs against an injected fake; the live smoke tests skip without `LEARNY_ANTHROPIC_API_KEY`. I-A4 ("failure and timeout behavior preserved verbatim") is verified against the fake's raise paths only.
- **True byte-identity across the convergence commit.** I confirmed the committed replay snapshots are unchanged by the diff and that their parametrized invariant tests run, and that the deterministic golden re-derives the answer from the adapter itself. I did not check out the pre-cycle tree and re-run generation to compare outputs directly.
- **Browser-level reload.** WSC-02 is verified at the component level (a fresh React tree with mocks restored), not in a real browser.
