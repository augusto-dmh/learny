# Design — `v6-conversation-model`

Binding decisions: ADR-0029 (model, migration shape, statuses, invariants,
retirement plan), AD-192..AD-202 (`context.md`). Survey seams below are from
the 2026-07-25 Explore pass; line numbers are pre-cycle.

## Shape of the change

```
backend/migrations/versions/0017_conversations.py        (new; head after 0016_reading_volume)
backend/app/infrastructure/db/metadata.py                (rename 3 tables + new columns)
backend/app/domain/entities.py                           (Conversation, ConversationTurn, ConversationSummary, modes/statuses)
backend/app/domain/ports.py                              (ConversationRepository, ConversationTurnRepository, AnswerGenerationPort.history)
backend/app/infrastructure/db/repositories.py            (renamed impls + list_for_user/rename/delete/touch)
backend/app/application/conversations.py                 (new; unified services — generalizes app/application/teaching.py)
backend/app/application/teaching.py                      (folds into conversations.py; legacy services become thin delegates or are absorbed)
backend/app/application/qa.py                            (AskQuestion delegates to the unified turn path, persisting)
backend/app/infrastructure/answering/anthropic.py        (answer adapter accepts history; teaching untouched)
backend/app/infrastructure/answering/local.py            (signature only; output unchanged)
backend/app/infrastructure/web/conversations.py          (new router)
backend/app/infrastructure/web/teaching.py               (legacy presenter over unified services; wire frozen)
backend/app/infrastructure/web/questions.py              (legacy presenter over unified services; wire frozen)
backend/app/infrastructure/web/rate_limit.py             (+ rate_limit_conversations)
backend/app/infrastructure/web/dependencies.py           (DI for unified services)
backend/app/core/config.py                               (+ conversation_* settings; deprecate 3 legacy fields in place)
backend/app/main.py                                      (mount conversations router)
docs/adr/0029-unified-grounded-conversations.md          (already authored)
```

Frontend: **zero changes**. Its suite must pass unedited (I-CM-4).

## Schema (Phase A)

Migration `0017_conversations`, `down_revision="0016_reading_volume"`
(`backend/migrations/versions/0016_reading_volume.py:38-40` is head).
Current shape: sessions `metadata.py:316-334`, turns `:336-359` (arbiter
`UniqueConstraint("session_id","turn_index")` :358), citations `:361-382`
(FK-less `chunk_id`, AD-033 comment :374-375).

- Renames: `teaching_sessions→conversations`,
  `teaching_turns→conversation_turns` (col `session_id→conversation_id`),
  `teaching_turn_citations→conversation_turn_citations`. Rename dependent
  indexes/constraints so `metadata.py` and DB agree (CONV-02); the migration
  test compares reflected DDL.
- Adds on `conversations`: `title TEXT NOT NULL` (backfill `target_title`),
  `scope_anchors JSONB NOT NULL` (backfill `[target_anchor]` as a JSON
  list), `include_notes BOOLEAN NOT NULL` (backfill `false`); `target_anchor`,
  `target_section_path`, `target_title` → nullable.
- Adds on `conversation_turns`: `mode TEXT NOT NULL` (backfill `'teach'`).
  String-constant convention, no enums (matches `answer_status`).
- Downgrade restores the exact 0016 shape (drops adds, re-tightens NOT NULLs,
  reverses renames).

## Domain (Phase A)

Entities beside the current ones (`entities.py:487-545`): `Conversation`
(id, source_id, title, scope_anchors `tuple[str, ...]`, include_notes,
nullable target trio, created_at, updated_at), `ConversationTurn` (adds
`mode`), `ConversationSummary` (conversation + `turn_count` +
`source_title`). `HistoryTurn` (:527) unchanged. Mode constants
`MODE_ANSWER = "answer"` / `MODE_TEACH = "teach"` and status
`NOT_FOUND_IN_SCOPE = "not_found_in_scope"` live with the existing status
constants — the wire strings are a domain contract like `entities.py:431`.

Repository ports replace `TeachingSessionRepository`/`TeachingTurnRepository`
(`ports.py:594-640`):

```python
class ConversationRepository(Protocol):
    def add(self, conversation) -> Conversation
    def get_by_id(self, conversation_id) -> Conversation | None
    def list_for_user(self, user_id, source_id: UUID | None = None) -> list[ConversationSummary]   # updated_at desc
    def list_for_source_with_target(self, source_id) -> list[ConversationSummary]                  # legacy panel; target_anchor IS NOT NULL
    def rename(self, conversation_id, title, now) -> Conversation | None
    def delete(self, conversation_id) -> bool
    def touch(self, conversation_id, now) -> None                                                  # updated_at bump on turn persist

class ConversationTurnRepository(Protocol):   # add / list_for_conversation / recent_history — as today (:619-:632), renamed
```

Ownership stays source-mediated (no `user_id` on the aggregate, AD-014):
`list_for_user` joins through `sources` (pattern: `most_recent_for_user`).
`TeachingTurnConflict` → `ConversationTurnConflict` (rename, same semantics).

`AnswerGenerationPort` (`ports.py:554-591`) gains
`history: Sequence[HistoryTurn] = ()` on `generate`/`generate_stream`
(AD-197). `TeachingGenerationPort` (:643) unchanged.

## Application (Phase B)

`app/application/conversations.py` generalizes `teaching.py` — reuse its
proven mechanics rather than reinvent: shared `authorized_conversation`
(pattern `teaching.py:64`), preflight (pattern `:269`: subtree anchors
`:308-310`, `expand_anchors` `:314`, `recent_history` `:320`, scoped retrieve
`:322-329`), persist-only-after-grounding (`:481` — stream and non-stream
identical, I-CM-5), `_not_found` construction, and `ground(...)`
(`grounding.py:18`) untouched.

Services: `StartConversation`, `ListConversations`, `ReadConversation`,
`RenameConversation`, `DeleteConversation`, `PostConversationTurn`
(`__call__` + `stream`, mode-dispatched generation; signature carries
`include_notes_override: bool | None = None` used only by legacy presenters
per AD-147). Turn flow decides status by scope: empty scope → today's
statuses; non-empty scope → `not_found_in_scope` on grounding/retrieval
failure (I-CM-3). Teach dispatch requires resolvable target (409 via a
dedicated error type; I-CM-7). Answer dispatch passes history (AD-197);
retrieval query = the raw message, as both paths do today.

Legacy service layer: `qa.py`'s `AskQuestion` and `teaching.py`'s five
services become delegates over the unified services (or are absorbed into
the web layer's legacy presenters — worker's call; the contract is the wire,
not the module layout). `NOT_FOUND` collapse happens at presentation, not in
the domain (AD-196).

Anthropic answer adapter: `_run_stream` base (`anthropic.py:200`) and
teaching's history assembly (`:300-322`) already exist — the answer adapter
gains the alternating-history `messages` shape while keeping
`ANSWER_SYSTEM_PROMPT` and citation mechanics byte-identical (CONV-26 AC2
pins the request shape offline). `local.py` signatures widen; output
unchanged (I-CM-8).

## Web (Phase C) — unified surface

`app/infrastructure/web/conversations.py`, mounted in `main.py:95-96`
neighborhood. Views mirror the established style (`teaching.py:109-198`):

| Method/path | Status | Notes |
|---|---|---|
| POST `/api/conversations` | 201 | `{source_id, scope_anchors: list[str] = [], include_notes: bool (required), title?: str}` → `ConversationView` |
| GET `/api/conversations[?source_id=]` | 200 | `list[ConversationSummaryView]` (id, source_id, source_title, title, scope_anchors, include_notes, turn_count, created_at, updated_at) |
| GET `/api/conversations/{id}` | 200 | detail + turns (each with `mode`, citations `EvidenceView`) |
| PATCH `/api/conversations/{id}` | 200 | `{title: str}` 1–200 trimmed |
| DELETE `/api/conversations/{id}` | 204 | |
| POST `/api/conversations/{id}/turns` | 201 | `{message: str (≤ conversation_message_max_chars), mode: Literal["answer","teach"]}` → `ConversationTurnView` |
| POST `/api/conversations/{id}/turns/stream` | 200 | UI Message Stream via `to_sse_response` (`ui_message_stream.py:115` — return the instance, threadpool contract :115-128); frames incl. `data-answer-status` may carry `not_found_in_scope` |

Mutating routes: `dependencies=[rate_limit_conversations, enforce_origin,
enforce_csrf]` (limiter sibling pattern `rate_limit.py:128-193`). 404 for
unowned/unknown (I-CM-6). 422/409 per AD-201. 502 mapping as today.

## Web (Phase D) — legacy wire, frozen

The compatibility contract (survey §6): five teaching paths
(`teaching.py:219-328`), two questions paths (`questions.py:105-165`), view
field sets `TargetView`/`SessionView`/`TurnView`/`SessionDetailView`/
`SessionSummaryView`/`AnswerResponse` (incl. `retrieval.strategy ==
"hybrid"`), statuses (201s, 200s), SSE frame order (`ui_message_stream.py:
60-95`), and limiter deps unchanged. Underneath: unified services.

- Legacy start → `StartConversation(scope=[target_anchor],
  include_notes=false, title=target_title)`; `SessionView.target` from the
  snapshot (non-null by the list filter).
- Legacy turn → `PostConversationTurn(mode='teach',
  include_notes_override=request value if provided)`.
- Legacy list → `list_for_source_with_target`.
- Legacy ask → create conversation (whole book, title = question[:80],
  include_notes = request value else true) + `PostConversationTurn
  (mode='answer')`; present `AnswerResponse`; stream variant identical.
- Presenters collapse `not_found_in_scope → not_found_in_source` (AD-196) in
  both JSON and the `data-answer-status` frame.

## Test derivation notes (all phases)

Existing suites are the parity oracle: `test_application_teaching.py` (40),
`test_web_teaching.py` (34), `test_web_questions.py` (27) largely **survive
with mechanical renames only where they touch internal names** — their wire
assertions must not weaken (I-CM-4). New coverage: migration round-trip w/
seeded backfill, unified service + web suites, scope-promise sensor (evidence
outside scope only → `not_found_in_scope`), concurrency conflict, history
plumb-through (recorded-request shape), byte-stability of first-turn local
answers (I-CM-8), golden citations green (`test_golden_citations.py`).
DB-gated tests use `requires_db`/`db_conn` (`conftest.py:23`;
`test_migrations.py:33-45` restores head).

## Environment facts

- `uv` off PATH → `backend/.venv/bin/python -m pytest` from `backend/`.
- DB tests need `make infra` up; `LEARNY_TEST_DATABASE_URL` from
  `.claude/settings.json`.
- Known pre-existing failure on `main`:
  `test_eval_retrieval_metrics.py::TestDeterministicRetrievalMetrics::test_metrics_meet_thresholds`
  (green in CI; eval-stack ground excluded by RFC-006) — carry, don't fix.
- Baseline counts at branch start: to be recorded by Phase A from a full run.
- Bash cwd resets between tool calls: absolute paths or one `cd … && …`.
