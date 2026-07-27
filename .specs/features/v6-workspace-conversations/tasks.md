# Tasks — v6-workspace-conversations

Four phases, one Opus worker each, executed in order (AD-209). Every task: tests derive
from the spec's acceptance criteria, the gate passes before the task is done, one atomic
commit per task, no internal IDs and no attribution in commit messages.

Gate scoping: run the affected test module per task commit; run the full suite once at
each phase boundary and once before any push.

---

## Phase A — Generation port convergence

| # | Task | Requirements |
| --- | --- | --- |
| A1 | Collapse `AnswerGenerationPort` + `TeachingGenerationPort` into one `GenerationPort` with an explicit `mode` and an optional `target_section_path`; delete `TeachingGenerationPort` | WSC-10 |
| A2 | Merge the deterministic adapter pair into one adapter dispatching on `mode`, preserving byte-identical output for both modes | WSC-10, I-A1 |
| A3 | Merge the Anthropic adapter pair into one adapter dispatching on `mode`, preserving prompts, failure and timeout behavior | WSC-10, I-A4 |
| A4 | Remove `_port` / `_generate` / `_generate_stream` port-selection branching in `PostConversationTurn`; single non-union model identity | WSC-10, I-A3 |
| A5 | Wire one generator in the composition root; the ask path no longer receives an unreachable teaching generator | WSC-10 |
| A6 | Sensor: a chapter-scoped `mode=answer` conversation carrying a non-null target snapshot generates via the answer path | I-A2 (the AD-205 trap) |

**Phase gate:** full backend suite green; deterministic golden output unchanged.

---

## Phase B — Unified surface completion

| # | Task | Requirements |
| --- | --- | --- |
| B1 | `list_for_user` accepts bounded `limit`/`offset`, preserving `(updated_at DESC, id DESC)` total order | WSC-12, I-B1 |
| B2 | Thread pagination through `ListConversations` and `GET /api/conversations`; bounded default page; `limit` bounds rejected with 422 | WSC-12, I-B2, I-B3 |
| B3 | Sensor: paging a tie-heavy list in windows returns every conversation exactly once, no duplicates, no drops | I-B1 |

**Phase gate:** full backend suite green.

---

## Phase C — Frontend re-point

| # | Task | Requirements |
| --- | --- | --- |
| C1 | Ask panel drives `/api/conversations`: create-then-stream on a thread's first message, stream directly after; `mode=answer`, whole-book scope | WSC-01 |
| C2 | Ask thread restores from the server on reload instead of client state | WSC-02, I-C1 |
| C3 | Teach panel drives `/api/conversations` for start, read, turn, and turn-stream; `mode=teach`, target-anchor scope | WSC-01, WSC-03 |
| C4 | Dock lists this book's conversations (mode-agnostic, newest activity first, title + turn count) with resume in place and an empty state | WSC-05, WSC-06 |
| C5 | Rename and delete from the dock; deleting the open conversation returns the panel to its empty state | WSC-06, I-C4 |
| C6 | `not_found_in_scope` renders a scope-specific message distinct from the whole-book miss | WSC-04 |
| C7 | Notes-scope control reads "Search my notes too" with an explanatory description; start sends an explicit boolean | WSC-11 |
| C8 | Sensor: a failed or aborted first message leaves no conversation the dock will list | WSC-13, I-C3 |

**Phase gate:** full frontend suite green; `tsc --noEmit` clean.

---

## Phase D — Legacy retirement

| # | Task | Requirements |
| --- | --- | --- |
| D1 | Re-anchor the surviving behaviors onto the unified surface **before** deleting anything: uncollapsed scope-miss verdict on JSON and SSE, stream framing, synchronous-handler sensor, 409/422 state transitions | WSC-09, I-D4 |
| D2 | Delete the legacy web modules and the status-collapse presenter; the legacy paths 404 | WSC-07, I-D1 |
| D3 | Delete the legacy application adapters and their wording contextmanagers | WSC-07 |
| D4 | Delete `ConversationRepository.list_for_source_with_target` from port and implementation | WSC-08 |
| D5 | Delete the five superseded settings fields; re-base the retired-knob warning on environment-variable names; app boots with all five variables set | WSC-08, I-D2, AD-210 |
| D6 | Delete the legacy wire-freeze tests, each only after its behavior is asserted on the unified surface | WSC-09 |
| D7 | Sensor: every surviving mutating conversation route carries a rate limiter | WSC-15, I-D3 |
| D8 | Sensor: deleting a conversation removes its turns and citations | WSC-06, I-D5 |

**Phase gate:** `make check` green.

---

## Traceability

| Requirement | Tasks |
| --- | --- |
| WSC-01 | C1, C3 |
| WSC-02 | C2 |
| WSC-03 | C3 |
| WSC-04 | C6 |
| WSC-05 | C4 |
| WSC-06 | C4, C5, D8 |
| WSC-07 | D2, D3 |
| WSC-08 | D4, D5 |
| WSC-09 | D1, D6 |
| WSC-10 | A1–A5 |
| WSC-11 | C7 |
| WSC-12 | B1, B2, B3 |
| WSC-13 | C8 |
| WSC-14 | D1 |
| WSC-15 | D7 |

**Coverage:** 15 total, 15 mapped, 0 unmapped.
