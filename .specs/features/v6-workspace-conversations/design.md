# Design — v6-workspace-conversations

Architecture for the spec's 15 requirements. Seams are given as signatures and
`file:line` refs; implementation shape is left to the phase workers.

## Shape of the change

Nothing new is built at the data layer — migration 0017 already carries every column.
This cycle is a **re-pointing plus a deletion**: the product moves onto the surface
Cycle C built, and the surface it left behind is removed. Four phases, ordered so the
deletion happens only after nothing depends on what is deleted.

```
A  port convergence      domain protocol + adapters + composition root
B  unified surface       pagination; list/rename/delete edges the dock needs
C  frontend re-point     panels onto /api/conversations; dock management; copy
D  legacy retirement     delete modules/knobs/method; re-anchor wire coverage
```

---

## A — Generation port convergence (WSC-10)

### Today

Two protocols in `app/domain/ports.py` describe one capability:

- `AnswerGenerationPort` (L554): `model: str`; `generate(*, question, evidence, history=())`; `generate_stream(...)`
- `TeachingGenerationPort` (L696): `model: str`; `generate(*, message, target_section_path, history, evidence)` — `history` **required**, argument order differs, message parameter differently named.

Four adapters implement them: `DeterministicAnswerAdapter` / `DeterministicTeachingAdapter`
(`app/infrastructure/answering/local.py:73,109`) and `AnthropicAnswerAdapter` /
`AnthropicTeachingAdapter` (`app/infrastructure/answering/anthropic.py:233,307`, sharing
`AnthropicAdapterBase` L165).

`PostConversationTurn` branches on mode in three places —
`_port` (`app/application/conversations.py:723`), `_generate` (L727), `_generate_stream` (L742) —
and `_port`'s union return type is what forces the union at every read of `model`.

### After

One `GenerationPort`. Per **AD-205**, `mode` is an explicit parameter; the optional
`target_section_path` carries the teach target. What disappears is the *port-selection*
branch and the union return type — not the mode concept.

```
class GenerationPort(Protocol):
    model: str
    def generate(*, message, mode, evidence, history=(), target_section_path=None) -> GeneratedAnswer
    def generate_stream(*, message, mode, evidence, history=(), target_section_path=None) -> Iterator[AnswerStreamEvent]
```

One adapter per provider family — `DeterministicGenerationAdapter`,
`AnthropicGenerationAdapter` — each dispatching prompt construction on `mode`
internally. The composition root (`app/infrastructure/web/dependencies.py`,
`app/infrastructure/answering/__init__.py`) wires **one** generator, which removes the
live defect where the ask path is handed a teaching generator it can never reach.

### The trap this phase must not fall into

**Target-presence is not the mode discriminator.** AD-194 sets the target trio from the
*scope head* at creation, so a chapter-scoped **answer** conversation carries a non-null
`target_anchor`. An adapter (or service) that infers "teach" from a present target will
silently route chapter-scoped ask turns through the teaching prompt — a fault no
existing test reaches, because today the port selection happens upstream on `mode`.
A sensor must pin this case directly.

### Invariants

- **I-A1** For the deterministic adapters, generated answer text and citations are
  byte-identical before and after convergence, for both modes. The merged adapter
  reuses the existing per-mode construction rather than a rewritten common path.
- **I-A2** A chapter-scoped conversation with `mode=answer` and a non-null target
  snapshot generates through the answer path.
- **I-A3** Reading the model identity for a turn yields a single non-union type.
- **I-A4** Anthropic failure and timeout behavior is preserved verbatim.

---

## B — Unified surface completion (WSC-12, and the edges the dock consumes)

### Pagination (AD-206)

`GET /api/conversations` (`app/infrastructure/web/conversations.py:359`) gains bounded
`limit`/`offset`, matching the shipped convention on `GET /api/reviews/due`
(`app/infrastructure/web/quiz.py:365`: `limit: int = 20, ge=1, le=100`). It threads
through `ListConversations.__call__` (`app/application/conversations.py:293`) to
`ConversationRepository.list_for_user` (port `app/domain/ports.py:623`, impl
`app/infrastructure/db/repositories.py:910`), which today applies no `LIMIT`/`OFFSET`.

Offset paging is safe here specifically because migration 0017's
`ix_conversations_updated_at_id (updated_at DESC, id DESC)` makes the sort order
**total** — the id tiebreaker is already in the ORDER BY at `repositories.py:919`. The
usual objection to offset paging (rows shifting under equal sort keys) does not apply.

### Invariants

- **I-B1** Paging the full list in windows yields every conversation exactly once,
  including when several share an `updated_at`.
- **I-B2** `limit` outside its bounds is rejected with 422; an `offset` past the end is
  an empty page, not an error.
- **I-B3** The default response is bounded — an unparameterized call does not return
  unbounded history.

---

## C — Frontend re-point (WSC-01..06, WSC-11)

### Today

- `ask-panel.tsx:80` — `useChat` + `createQuestionTransport(sourceId, csrf, includeNotes)`
  → `POST /api/sources/{id}/questions/stream` (`app/lib/streaming.ts:153`). Turns live
  only in client state; a reload loses them.
- `teach-panel.tsx:76` / `TeachChat` (L251) — `startTeachingSession` + `listTeachingSessions`
  (`app/lib/teaching.ts`) + `createTurnTransport(sessionId, csrf, includeNotes)`
  → `POST /api/teaching-sessions/{id}/turns/stream` (`streaming.ts:183`).
- `ReaderPanel` (`reader-panel.tsx`) owns `PanelMode = "ask" | "teach"` (L25).
- No Next.js route-handler work is needed: `frontend/app/api/[...path]/route.ts` is a
  catch-all proxy, so `/api/conversations*` is already reachable from the browser.

### After

Both panels drive `/api/conversations`. The asymmetry to resolve: **start and turn are
separate calls**. `POST /api/conversations` creates the conversation; the first turn is
then posted to `/api/conversations/{id}/turns/stream`. So the transport must resolve a
conversation id lazily — create-then-stream on the first message of a thread, stream
directly on every subsequent one. Ask sends `mode=answer`, Teach sends `mode=teach`;
scope is `[]` for whole-book ask and `[target_anchor]` for teach.

Conversation management (WSC-05, WSC-06) is a per-book list in the dock — one
mode-agnostic list per **AD-208** — backed by `GET /api/conversations?source_id=`,
with rename (`PATCH`) and delete (`DELETE`) in place.

`not_found_in_scope` now arrives on the wire (**AD-207**) and needs its own message,
distinct from the whole-book miss. Today `assistantView()` (`streaming.ts:49`) reads
the `data-answer-status` part; the panel's rendering of that status is where the third
value lands.

Copy (WSC-11): `include-notes-toggle.tsx:27` — `Include my notes` → `Search my notes too`,
plus a description; the start request carries an explicit boolean rather than a
per-surface implicit default.

### Invariants

- **I-C1** A thread's turns survive a reload because they are restored from the server.
- **I-C2** For an identical grounded request, rendered answer, citations, and status
  match the pre-re-point behavior.
- **I-C3** A failed or aborted first message leaves no conversation the dock will list
  — the persist-only-after-grounding parity Cycle C established must survive.
- **I-C4** Deleting the open conversation returns the panel to its empty state with no
  stale thread rendered.

---

## D — Legacy retirement (WSC-07, WSC-08, WSC-09)

### Deleted

| Item | Ref |
| --- | --- |
| `POST/GET /api/teaching-sessions*`, `GET /api/sources/{id}/teaching-sessions` | `app/infrastructure/web/teaching.py` |
| `POST /api/sources/{id}/questions[/stream]` | `app/infrastructure/web/questions.py` |
| status-collapse presenter | `app/infrastructure/web/legacy_status.py` |
| legacy application adapters + legacy wording contextmanagers | `app/application/teaching.py`, `app/application/qa.py` |
| `ConversationRepository.list_for_source_with_target` | port `ports.py:636`, impl `repositories.py:923` |
| `qa_evidence_top_k`, `teaching_evidence_top_k`, `teaching_history_turns` | `app/core/config.py:178,187,188` |

`teaching_message_max_chars` is **actively read** and is not part of this deletion.

### The retired-knob warning survives, re-based on environment names

Settings are `extra="ignore"` (`config.py:45`), so deleting the three fields already
satisfies WSC-08 AC-4 — a deployment that still sets `LEARNY_TEACHING_HISTORY_TURNS`
boots fine. But `_warn_about_retired_knobs` (L293) iterates `model_fields_set`, so with
the fields gone it would silently stop firing, and the operator's dead tuning becomes
*less* visible than it is today, not more.

The warning is therefore kept and re-based on environment-variable names rather than
model fields. This resolves context.md **D-7** in favor of keeping the diagnostic: the
failure it prevents (a tuning that validates, boots, and does nothing) is unchanged by
the field's removal, and it costs a handful of lines. Recorded as **AD-210**.

### Coverage must be re-anchored, not deleted (WSC-09)

The legacy wire-freeze tests are the risk in this phase. `tests/test_web_teaching.py`
and `tests/test_web_questions.py` exist to freeze a wire that is being deleted, so they
go — but several assert behavior that still exists and would otherwise lose its only
sensor. Named explicitly:

- `test_web_teaching.py:654` and `:974` — scope-miss verdict stored as
  `not_found_in_scope`. The *collapse* is what dies; the stored verdict and its
  appearance on the wire must be asserted on `/api/conversations` (now uncollapsed).
- `test_web_teaching.py:1109` — legacy stream endpoints stay synchronous handlers. The
  equivalent sensor for `/api/conversations/{id}/turns/stream` already exists from
  Cycle C; confirm it does before deleting this one.
- `test_web_questions.py` (~L241, L264-280, L756-780, L927) — SSE `data-citations` and
  answer-status framing. Equivalent framing assertions must exist for the unified
  stream.

The rule for this phase: **delete a test only after naming where its behavior is
asserted on the unified surface** — or writing that assertion.

### Invariants

- **I-D1** Every legacy path returns 404; no legacy module remains in the tree.
- **I-D2** The app boots with all three retired environment variables set.
- **I-D3** Every surviving mutating conversation route still carries a rate limiter —
  deleting the legacy limiter dependencies must leave no route unthrottled (WSC-15).
- **I-D4** Teach-target staleness → 409 and unresolvable scope → 422 still hold
  (AD-201), asserted on the unified surface.
- **I-D5** Deleting a conversation removes its turns and citations (WSC-06).

---

## Verification

`make check` — backend `pytest`, frontend `vitest`, `ruff check` + `ruff format --check`,
`tsc --noEmit`, architecture boundaries. DB tests need `make infra` first.

Two known-local conditions, neither caused by this cycle and neither to be chased
inside it: `test_eval_retrieval_metrics.py::…::test_metrics_meet_thresholds` fails
locally on HNSW approximate-recall variance (passes in CI), and
`test_worker_tasks.py::test_run_ingestion_builds_corpus_from_valid_epub` is an
order-dependent flake in untouched ingestion code.
