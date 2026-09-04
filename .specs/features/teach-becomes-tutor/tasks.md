# teach-becomes-tutor Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user — do not proceed without it.**

---

**Design**: `.specs/features/teach-becomes-tutor/design.md`
**Status**: Approved

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec. Guidelines: `CLAUDE.md` (`make infra`, `make test-backend`, `make test-frontend`, `make lint`), pytest under `backend/tests/`, vitest + Testing Library under `frontend/tests/`.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Frozen prompt / Anthropic request | unit | Byte-stable teach prompt; TUTOR-02 constraints present; answer prompt unchanged; phase/hint in user text not system; citations shape unchanged | `backend/tests/test_answering_anthropic.py` | `cd backend && uv run pytest tests/test_answering_anthropic.py` |
| Grounding carve-out | unit | Teach zero-citation non-sentinel → answered; sentinel → not-found; answer zero-citation → not-found | `backend/tests/test_application_conversations.py` | `cd backend && uv run pytest tests/test_application_conversations.py` |
| TeachingPolicy | unit | Every transition in TUTOR-16..22 plus check-phase chips are not a pass | `backend/tests/test_application_teaching_policy.py` | `cd backend && uv run pytest tests/test_application_teaching_policy.py` |
| Turn path | unit | Opening retrieve query; 422 non-opening first teach; retry after failed opening; close 409; answer-mode 422; ordinary retrieve still message | `backend/tests/test_application_conversations.py` | `cd backend && uv run pytest tests/test_application_conversations.py` |
| HTTP | integration | Opening stream; 409 closed; tutor-card 201/200/409/404; views expose phase | `backend/tests/test_web_conversations.py` | `cd backend && uv run pytest tests/test_web_conversations.py` |
| Quiz origin / reconcile | unit/integration | Idempotent accept; delete conversation leaves card; tutor keep-if-anchor / orphan-if-gone; scheduling untouched | `backend/tests/test_application_cards.py` `test_application_quiz.py` `test_web_cards.py` | `cd backend && uv run pytest tests/test_application_cards.py tests/test_application_quiz.py tests/test_web_conversations.py` |
| Settings | unit | `LEARNY_TUTOR_CHECK_AFTER_TURNS` default 3 | `backend/tests/test_config.py` | `cd backend && uv run pytest tests/test_config.py` |
| Chat dock | unit (jsdom) | Strip Chat/Notes/Review; aliases; empty names both modes; resume last_turn_mode; Explain pending-request | `frontend/tests/reader-panel.test.tsx` `chapter-reader.test.tsx` | `cd frontend && npm test -- reader-panel chapter-reader` |
| Tutor Start / chips / close / card | unit (jsdom) | Create+opening stream; hide sentinel bubble; composer after persist; chips; close hides composer; one card offer | `frontend/tests/teach-panel.test.tsx` `chat-panel.test.tsx` | `cd frontend && npm test -- teach-panel chat-panel reader-panel` |

## Parallelism Assessment

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
| --------- | -------------- | --------------- | -------- |
| backend unit (no DB) | Yes | in-process fakes | `tests/fakes.py` |
| backend DB-gated | No across workers sharing `learny_test` | one pytest process per gate | `conftest.py` |
| frontend vitest | Yes within one `npm test` | jsdom per file | `frontend/tests/` |

## Gate Check Commands

> `uv` may be off PATH: `backend/.venv/bin/python -m pytest` / `backend/.venv/bin/ruff`. Prefix `LEARNY_GENERATION_PROVIDER=local LEARNY_EMBEDDING_PROVIDER=local` if the local `.env` leaks real providers. `jq` is not installed.

| Gate Level | When to Use | Command |
| ---------- | ----------- | ------- |
| Quick | After a backend unit task | `cd /home/augusto/projects/learny/backend && uv run pytest <touched module>` |
| Full | After HTTP or frontend tasks | touched backend module and/or `cd /home/augusto/projects/learny/frontend && npm test -- <file>` |
| Build | Phase boundary | `cd /home/augusto/projects/learny && make lint` plus the cycle's backend + frontend suites |

---

## Execution Plan

Four phases, sequential. One Opus worker per phase (grounding carve-out, opening retrieve, close 409, and tutor origin/reconcile are quiet-failure invariants). No Haiku-safe unit. Verifier after T15.

### Phase 1 — Playbook and retrieve fork

```
T1 → T2 → T3 → T4
```

### Phase 2 — Ladder on the conversation

```
T4 → T5 → T6 → T7 → T8
```

### Phase 3 — Tutor card

```
T8 → T9 → T10 → T11
```

### Phase 4 — Chat dock

```
T11 → T12 → T13 → T14 → T15
```

---

## Task Breakdown

### T1: Frozen playbook prompt and sentinel strings

**What**: Replace `TEACHING_SYSTEM_PROMPT` with the TUTOR-02 playbook as a byte-stable constant. Add `TUTOR_OPENING_MESSAGE`, `TUTOR_JUST_EXPLAIN_MESSAGE`, `TUTOR_DONT_KNOW_MESSAGE`, and `TUTOR_CARD_QUESTION` next to `SENTINEL`. Leave `ANSWER_SYSTEM_PROMPT` byte-identical.
**Where**: `backend/app/infrastructure/answering/prompts.py`
**Depends on**: None
**Reuses**: Existing `SENTINEL` import; cache breakpoint stays on the teach system string
**Requirement**: TUTOR-01, TUTOR-02, TUTOR-04

**Tools**: Skill `ruff`

**Done when**:

- [x] Two reads of `TEACHING_SYSTEM_PROMPT` are identical bytes and the playbook constraints are present as text
- [x] Answer prompt test still asserts the pre-cycle string
- [x] Gate: `uv run pytest tests/test_answering_anthropic.py -k prompt`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(generation): freeze the teach playbook prompt`

---

### T2: Phase and hint on the generation port

**What**: Add optional `tutor_phase` and `hint_level` to `GenerationPort.generate` / `generate_stream`. Anthropic teach user text includes `Phase:` and `HintLevel:` beside the section line. Fakes and the local adapter accept the kwargs (default `None`) and ignore them.
**Where**: `backend/app/domain/ports.py`
**Depends on**: T1
**Reuses**: `AnthropicGenerationAdapter._build_request` teach branch; do not interpolate into the system prompt
**Requirement**: TUTOR-03

**Tools**: Skill `ruff`

**Done when**:

- [x] A teach request with phase `open` and hint `pump` puts those tokens in the user turn and not in the system block
- [x] Answer requests still omit them
- [x] Gate: `uv run pytest tests/test_answering_anthropic.py tests/test_answering_local.py tests/test_application_conversations.py`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(generation): put tutor phase on the user turn`

---

### T3: Teach grounding allows citation-free replies

**What**: WHERE mode is teach, a non-sentinel generated reply with no surviving citations persists as `answered` with empty citations. Sentinel and blank text still not-found. Answer mode keeps the empty-citation collapse.
**Where**: `backend/app/application/conversations.py`
**Depends on**: T2
**Reuses**: `ground()` — do not delete it; branch in the teach caller
**Requirement**: TUTOR-05, TUTOR-06, TUTOR-07

**Tools**: Skill `ruff`

**Done when**:

- [x] Application test: teach `found=True`, text, zero cited ids → persisted `answered`
- [x] Application test: teach whole-reply sentinel → not-found
- [x] Application test: answer zero citations → not-found
- [x] Gate: `uv run pytest tests/test_application_conversations.py tests/test_application_grounding.py`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(conversations): keep socratic teach turns without citations`

---

### T4: Opening retrieval uses the section title

**What**: WHEN the teach message is `TUTOR_OPENING_MESSAGE`, `_retrieve_evidence` queries `target_title` or `target_anchor`. Other turns still query the learner message. Subtree `anchors` unchanged.
**Where**: `backend/app/application/conversations.py`
**Depends on**: T3
**Reuses**: `_retrieve_evidence` / `RetrieveEvidence`; do not pin path-matched chunks
**Requirement**: TUTOR-09, TUTOR-10

**Tools**: Skill `ruff`

**Done when**:

- [x] Opening retrieve assertion uses `query=target_title`
- [x] A follow-up teach turn still retrieves with the learner text
- [x] Gate: `uv run pytest tests/test_application_conversations.py`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(conversations): retrieve the opening tutor turn by section title`

---

### T5: Tutor state columns

**What**: Migration `0019_tutor_state` (down_revision `0018_citation_spans`) adds `tutor_phase`, `hint_level`, `tutor_ordinary_turns`, `tutor_scaffold_misses`, `tutor_check_text` to `conversations` with the all-or-nothing phase/hint CHECK. Map them on the Conversation entity, metadata, and repository.
**Where**: `backend/migrations/versions/0019_tutor_state.py`
**Depends on**: T4
**Reuses**: `target_all_or_nothing` CHECK style; existing conversation repository
**Requirement**: TUTOR-16, TUTOR-24

**Tools**: Skill `ruff`

**Done when**:

- [x] Upgrade then downgrade on the test DB; pre-cycle rows read as null phase
- [x] Gate: `uv run pytest tests/test_migrations.py tests/test_repositories_conversations.py`

**Tests**: integration
**Gate**: full
**Commit**: `feat(conversations): persist tutor phase on the conversation`

---

### T6: Pure teaching policy

**What**: `TeachingPolicy.advance` / `after_tutor_turn` covering opening, ordinary, chips, check-after-N, two misses → assert, check restatement → close, chips in check are not a pass. Setting `LEARNY_TUTOR_CHECK_AFTER_TURNS` default 3.
**Where**: `backend/app/application/teaching_policy.py`
**Depends on**: T5
**Reuses**: Frozen message constants from T1
**Requirement**: TUTOR-16, TUTOR-17, TUTOR-18, TUTOR-19, TUTOR-20, TUTOR-21, TUTOR-22

**Tools**: Skill `ruff`

**Done when**:

- [x] Table-driven tests kill a skipped transition (at least: just-explain in check does not close; third ordinary moves to check)
- [x] Gate: `uv run pytest tests/test_application_teaching_policy.py tests/test_config.py`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(conversations): own the tutor hint ladder in application code`

---

### T7: Enforce opening, close, and mode lock on turns

**What**: Wire policy into `PostConversationTurn` / `.stream`. First teach turn must be the opening sentinel (422 otherwise) unless retrying a failed opening. Pass phase/hint into the port. Persist new tutor columns. Close → 409 persist-nothing. Tutor thread + `mode=answer` → 422. Null phase (Answer / pre-cycle teach with turns) unchanged.
**Where**: `backend/app/application/conversations.py`
**Depends on**: T6
**Reuses**: AD-262 failed persist; existing 409 conflict
**Requirement**: TUTOR-08, TUTOR-11, TUTOR-12, TUTOR-23, TUTOR-25, TUTOR-26

**Tools**: Skill `ruff`

**Done when**:

- [x] Tests for 422 / retry / 409 close / 422 mixed mode / null-phase teach still accepts a normal first message when turns already exist
- [x] Gate: `uv run pytest tests/test_application_conversations.py`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(conversations): open tutor sessions and refuse turns after the check`

---

### T8: Expose tutor state and map the new errors

**What**: Conversation list/detail views include `tutor_phase` and `hint_level` (and target title if the client needs it for the card question). Map `ConversationClosed` to 409. HTTP tests for opening stream + closed turn.
**Where**: `backend/app/infrastructure/web/conversations.py`
**Depends on**: T7
**Reuses**: `error_handlers.py` status map; `ConversationView`
**Requirement**: TUTOR-08, TUTOR-24, TUTOR-23

**Tools**: Skill `fastapi`

**Done when**:

- [x] GET conversation after opening shows `tutor_phase=open`
- [x] POST turn on close is 409 with no new row
- [x] Gate: `uv run pytest tests/test_web_conversations.py`

**Tests**: integration
**Gate**: full
**Commit**: `feat(api): show tutor phase on conversation reads`

---

### T9: Tutor origin and conversation link on quiz items

**What**: Add `QuizItemOrigin.TUTOR`, nullable `quiz_items.conversation_id` FK ON DELETE SET NULL, partial unique on `(conversation_id) WHERE origin='tutor' AND conversation_id IS NOT NULL`. Same migration as a new revision `0020_tutor_cards` if T5 already shipped, or fold into 0019 only if T5 is not yet committed — **do not rewrite T5's revision**. Prefer `0020_tutor_cards` down_revision `0019_tutor_state`.
**Where**: `backend/migrations/versions/0020_tutor_cards.py`
**Depends on**: T8
**Reuses**: 0012/0014 partial-unique pattern; source CHECK unchanged
**Requirement**: TUTOR-35, TUTOR-36, TUTOR-39

**Tools**: Skill `ruff`

**Done when**:

- [x] Unique rejects two tutor rows for one conversation_id
- [x] Deleting the conversation nulls `conversation_id` and leaves the row
- [x] Gate: `uv run pytest tests/test_migrations.py tests/test_repositories_quiz.py`

**Tests**: integration
**Gate**: full
**Commit**: `feat(quiz): link a tutor card to its conversation`

---

### T10: Accept the restatement as one FSRS card

**What**: `AcceptTutorCard` builds one `free_recall` item from the closed conversation (question template, answer=`tutor_check_text`, excerpt=opening first snippet or `target_title`, due-now). `POST /api/conversations/{id}/tutor-card` 201/200/409/404. No `suggest_cards`. Idempotent via the partial unique.
**Where**: `backend/app/application/cards.py`
**Depends on**: T9
**Reuses**: `AcceptCard` validate/embed/schedule; `rate_limit_quiz` + origin + CSRF
**Requirement**: TUTOR-35, TUTOR-36, TUTOR-37, TUTOR-38, TUTOR-42

**Tools**: Skill `fastapi`

**Done when**:

- [x] Accept on close inserts one due card; second accept returns the same id without rescheduling
- [x] Accept before close is 409; stranger is 404
- [x] Gate: `uv run pytest tests/test_application_cards.py tests/test_web_conversations.py`

**Tests**: integration
**Gate**: full
**Commit**: `feat(quiz): save the tutor check as one review card`

---

### T11: Reconcile tutor cards by section anchor

**What**: `ReconcileQuizItems` keeps `origin=tutor` active while the target anchor or an alias survives, relocating onto the survivor; otherwise orphaned. Never stale-from-excerpt. Scheduling and `review_log` untouched.
**Where**: `backend/app/application/quiz.py`
**Depends on**: T10
**Reuses**: `_resolve` / `update_reconciliation`; existing byte-equal scheduling sensor
**Requirement**: TUTOR-40

**Tools**: Skill `ruff`

**Done when**:

- [x] Anchor still present → active even if excerpt is only the title
- [x] Anchor gone → orphaned; scheduling row bytes unchanged
- [x] Gate: `uv run pytest tests/test_application_quiz.py`

**Tests**: unit
**Gate**: quick
**Commit**: `feat(quiz): keep tutor cards while their section survives`

---

### T12: Merge Ask and Teach into one Chat tab

**What**: Dock strip is Chat | Notes | Review. `dockTabFromParam` maps `ask`/`teach`/`chat` to Chat. `ask` arms Answer, `teach` arms Tutor, `chat` uses last-used or Answer. Resume still follows `last_turn_mode`. Capture Explain/Ask pending-request still auto-submits in Answer. Do not change tombstone redirects off `?panel=ask`.
**Where**: `frontend/app/components/reader-panel.tsx`
**Depends on**: T11
**Reuses**: `AskPanel` / `TeachPanel` composed inside Chat; `panelFor`
**Requirement**: TUTOR-27, TUTOR-28, TUTOR-31, TUTOR-32

**Tools**: Skill `vercel-composition-patterns`

**Done when**:

- [x] Strip has no Ask/Teach tabs; `?panel=ask` still opens the conversation surface in Answer
- [x] Explain pending-request test still auto-submits
- [x] Gate: `cd frontend && npm test -- reader-panel chapter-reader`

**Tests**: unit
**Gate**: full
**Commit**: `feat(reader): put ask and teach in one chat dock`

---

### T13: Tutor Start speaks first

**What**: Tutor empty state names the mode, section picker defaults to the on-screen chapter, Start creates then streams `TUTOR_OPENING_MESSAGE`. Hide that learner bubble. Hide composer until the opening turn persists (including failed). Answer first-send stays lazy-create.
**Where**: `frontend/app/components/teach-panel.tsx`
**Depends on**: T12
**Reuses**: `useConversationThread` / `startConversation`; `include_notes: false` on Tutor Start
**Requirement**: TUTOR-08, TUTOR-13, TUTOR-14, TUTOR-15, TUTOR-29, TUTOR-30

**Tools**: Skill `vercel-react-best-practices`

**Done when**:

- [x] Start does not wait for a typed message; sentinel bubble is absent; composer appears after persist
- [x] Answer empty state still has no conversation until send
- [x] Gate: `cd frontend && npm test -- teach-panel ask-panel reader-panel`

**Tests**: unit
**Gate**: full
**Commit**: `feat(reader): start tutor sessions with the tutor speaking`

---

### T14: Chips, close, and jump to Answer

**What**: Tutor composer chips send the frozen just-explain and I-don't-know strings. WHILE close, hide composer and show a control that starts a new Answer conversation on the same source.
**Where**: `frontend/app/components/teach-panel.tsx`
**Depends on**: T13
**Reuses**: Frozen constants via a small shared module or duplicated string pinned by test
**Requirement**: TUTOR-18, TUTOR-19, TUTOR-33

**Tools**: Skill `vercel-composition-patterns`

**Done when**:

- [x] Chip click posts the exact frozen message
- [x] Close state has no composer and the Answer control does not POST onto the closed thread
- [x] Gate: `cd frontend && npm test -- teach-panel reader-panel`

**Tests**: unit
**Gate**: full
**Commit**: `feat(reader): add tutor chips and a closed-session handoff to ask`

---

### T15: Offer exactly one review card

**What**: On `tutor_phase=close`, show one card (template question + check text) with Accept / Dismiss. Accept calls the tutor-card route. Dismiss hides the offer and writes no quiz row. Do not call `suggestCards`.
**Where**: `frontend/app/components/teach-panel.tsx`
**Depends on**: T14
**Reuses**: quiz client patterns from `lib/cards.ts` or a thin `lib/tutor-card.ts`
**Requirement**: TUTOR-34, TUTOR-41

**Tools**: Skill `vercel-react-best-practices`

**Done when**:

- [x] Close UI shows one Q/A; Accept hits the new route; Dismiss does not
- [x] Gate: `cd frontend && npm test -- teach-panel` and `cd backend && uv run pytest tests/test_web_conversations.py tests/test_application_cards.py`

**Tests**: unit
**Gate**: full
**Commit**: `feat(reader): offer one review card when the tutor check passes`

---
