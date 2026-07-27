# Review triage — v6-workspace-conversations (PR #53)

Six lanes ran: security, requirements, tests/coverage, architecture, regression,
performance. **19 inline comments + 1 PR-level comment**, deduplicating to 17 distinct
findings (five were raised by two lanes independently).

Every finding below was judged against the code as it exists, not on the reviewer's
authority. PR comments are scaffolding and get deleted at the end of the cycle; **this
file is the surviving record of the reasoning.**

**Outcome: 17 real, 0 false. 14 fixed, 3 recorded won't-fix.**

## Substantive defects — fixed

| # | Location | Verdict | Action | Rationale |
| --- | --- | --- | --- | --- |
| F10 🚨 | `frontend/.../reader-panel.tsx:45` | **real — verified** | fix | `panelFor` returns `"teach"` when `scope_anchors.length > 0`. **This is the exact inference AD-205 removed from the backend, reintroduced client-side**: a chapter-scoped *ask* conversation carries scope anchors and would resume into the Teach panel. Invisible to the verification because every mutation was backend-side. Mode is on the summary — read it, don't infer it |
| F14 🚨 | `frontend/.../use-conversation-thread.ts:117` | **real** | fix | `baseHandlers` hard-codes the create leg to 201 in both panel suites, so the 409/429/404 that moved onto the new create-then-stream seam have zero coverage — including whether a rejection surfaces a banner or leaves a stuck spinner. The seam this cycle introduced is the one place with no failure coverage |
| F15 🚨 | `frontend/.../conversations.ts:231` | **real** | fix | The unparseable-error-body fallback survived, its only sensors (`questions-client.test.ts:158`, `teaching-client.test.ts:372`) did not. **Another instance of the class that failed round 1** — the verification's coverage analysis walked deleted *backend* suites only. `conversations.ts` is now the sole client in the repo lacking it |
| F19 ⚠️ | `backend/app/core/config.py:294` | **real — verified** | fix | `if env_var in os.environ` misses `backend/.env`, which pydantic-settings loads separately. **This inverts AD-210's own rationale** — the warning was kept precisely so a dead tuning would not become less visible — and contradicts the `.env.example` text this PR wrote. `model_fields_set` caught both cases |
| F3 ⚠️ | `frontend/.../conversation-list.tsx:57` | **real — verified** | fix | Dock calls `listConversations(sourceId)` with no `limit`/`offset` and renders no "load more", so with the new default of 20 a reader's 21st-oldest conversation is unreachable. The Teach list it replaced was unbounded, so this is a regression. **Raised independently by three lanes.** A product gap living in the seam between two individually-satisfied requirements |
| F12 ⚠️ | `frontend/.../ask-panel.tsx:234` | **real** | fix | The notes toggle renders mid-thread and silently no-ops. Conversation-scoped notes choice is *correct* per ADR-0029 ("one explicit default per conversation") — the defect is the affordance, not the scoping. Fix is to stop presenting a live-looking control that does nothing, not to restore per-turn behaviour |
| F4 ⚠️ | `frontend/.../use-conversation-thread.ts:105` + `backend/.../repositories.py:910` | **real** | fix | WSC-13's guarantee is weaker than its wording: orphan prevention is a client-side compensating DELETE whose failure is swallowed and which never runs if the tab closes mid-stream; `list_for_user` has no zero-turn filter, so a missed orphan *is* listed. All three orphan sensors drive the happy compensation path, which is why they passed. **Raised by two lanes.** Durable fix is server-side |

## Cleanup and coverage — fixed

| # | Location | Verdict | Action | Rationale |
| --- | --- | --- | --- | --- |
| F1 | `backend/.../conversations.py:456` | real | fix | `include_notes_override` orphaned — both production callers deleted here; reachable only from a test, docstring still describes it as a legacy-request knob. Raised by two lanes |
| F16 | `frontend/.../conversation-list.tsx:61` | real | fix | Two of three failure branches untested (list-load, delete); only rename covered |
| F17 | `frontend/.../active-conversation.ts:43` | real | fix | Documented resilience guards (corrupt JSON, throwing `setItem`, non-string filter) have no sensor; the sibling `use-reading-settings.test.tsx` covers both cases |
| F18 | `backend/tests/test_web_conversations.py:1503` | real | fix | Buffered 502's `detail` lost its only assertion; only the stream twin still pins it |
| F5 | `spec.md:195` | real | fix | Edge case "conversation deleted while a turn is streaming" maps to no requirement, has no test, and is absent from the verification's honest "could not verify" list — silently unassessed rather than deliberately deferred |
| F6 + F13 | `spec.md:11,49,125,126`, `tasks.md:64`, `.env.example:89` | real | fix | The three→five knob correction landed in `design.md` only. WSC-08 **AC-3/AC-4** still say three, so the ACs marked Verified are not the ACs satisfied. Same defect in the documented `.env.example` contract |
| F7 | `spec.md` Goals / Success Criteria | real | fix | Traceability flipped to Verified with all nine checkboxes left unticked |
| F9 | `validation.md` | real | fix | `test_application_conversations.py` line refs went stale when `0714b94c` shifted the file ~300 lines |
| F8 | PR #53 body | real | **already fixed** | Body claimed "the composition root ignores two configured values". Verified false — `dependencies.py:518-519` passes both. M19 was a *mutation* nothing caught; the gap is a missing sensor. Corrected in place |

## Found during fix verification (not from the review)

| # | Location | Verdict | Action | Rationale |
| --- | --- | --- | --- | --- |
| F21 | `frontend/.../reader-panel.tsx:66` + `backend/.../conversations.py:291` | **real — self-found** | fix | The F10 fix is correct (mode is read, not inferred) but had to fetch the whole conversation to learn the mode, because `ConversationSummaryView` does not expose it — and the panel then fetches it *again* to restore turns. Resuming therefore double-fetches the exact payload F2 flags as unbounded. Introduced by my own fix instruction, which barred the frontend worker from touching the backend. Fix: expose the resume mode on the summary so `panelFor` is pure |

## Recorded won't-fix

| # | Location | Verdict | Action | Rationale |
| --- | --- | --- | --- | --- |
| F2 | `frontend/.../ask-panel.tsx:140` → `repositories.py:1022` | **real** | won't-fix **this cycle** | Thread resume fetches every turn with every citation, unbounded, on a path that remounts each Ask↔Teach toggle. The asymmetry with this PR's own list pagination is a fair criticism. But bounding it properly means turn-level pagination — a new API surface with its own ordering and resume semantics — which is a cycle, not a patch. Carried forward explicitly rather than smuggled in. Present threads are short enough that this is latency, not breakage |
| F20 | `backend/.../anthropic.py:279` | **real** | won't-fix | Convergence made `target_section_path` optional, so a targetless teach turn yields an empty-section prompt instead of a type error. The invariant is still enforced upstream (preflight → 409) and sensed. Re-expressing it in the type system means splitting the port again, which is what this cycle exists to undo. Accepted consequence, recorded |
| F11 | `frontend/.../teach-panel.tsx:306` | **real** | won't-fix | AD-147's notes default now lives in a frontend constant. This follows from ADR-0029 making the choice explicit per conversation and `include_notes` mandatory on the request — the server deliberately no longer has a default to own. The finding correctly identifies the movement; the movement is the design |

## Sub-threshold observations (correctly not posted, recorded for the gate)

- **performance:** the `turn_count` correlated subquery in `_summary_select` could be
  evaluated for all matching rows rather than the page if the planner prefers a Sort
  node over the index scan. Plan-dependent, unconfirmable from the diff, and the
  index was added for exactly this ordering. Relevant only if list latency regresses.
- **tests:** `FakeAnswerGeneration` kept its old name after the port became
  `GenerationPort`.

## What the review confirmed clean

- **security (0 findings):** auth on all 7 surviving routes, limiter on all mutating
  routes, CSRF + same-origin on every new browser call, parameterized pagination,
  provider SDK still contained, id-only localStorage. Judged the PR to *improve*
  log-privacy versus `main`.
- **architecture:** the backend convergence is "clean and the positive highlight" —
  one port with explicit mode, no branching pushed to callers, `app/domain/` with zero
  non-domain imports, `app/application/` free of infrastructure/FastAPI/SQLAlchemy/SDK.
- **regression:** no phantom imports of any deleted symbol repo-wide; no
  wrong-signature callers; request validation *tightened*, not weakened; no throttle
  lost; retired knobs genuinely unread.
- **requirements:** resolved ~55 of `validation.md`'s references against real files and
  found **no case of it crediting a deleted test or non-existent file** — the failure
  mode that would have been fatal for a deletion cycle.

## Correction to my own brief (recorded so the record is accurate)

I told the tests lane five backend suites were deleted. `test_web_rate_limit_validation.py`
was **not** — it was partially edited to drop only the two legacy-limiter tests. The
verification's round-1 table had this right; my restatement of it did not.
