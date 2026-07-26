# ADR-029: Unified Grounded Conversations (Scope × Mode)

- **Date**: 2026-07-25
- **Status**: Accepted (2026-07-25, rides the implementing cycle's merge gate; content decisions made by the driver in RFC-006, 2026-07-24)
- **Deciders**: Augusto, Claude
- **Tags**: domain, schema, conversations, teaching, qa, retrieval, api

## Context and Problem Statement

The 2026-07-24 dogfood session (RFC-006, findings 7 and 8) showed that Ask and
Teach are two points in one product space that the schema forbids expressing.
Ask is stateless: `ask-panel.tsx` holds turns in client state, nothing is
persisted, and every reload evaporates the conversation. Teach is persisted but
unmanageable: `teaching_sessions` has only a per-source list endpoint — no
global list, no rename, no delete. Yet both surfaces are the same product idea:
**a grounded conversation about a book**, distinguished only by *scope* (which
part of the book the retrieval may see) and *mode* (how the reply behaves).

The turn shape is already generic. `teaching_turns` stores message, answer
status, answer text, model, and evidence count; `teaching_turn_citations`
snapshots citations without a corpus FK so they survive corpus replace
(AD-033). Only the session's three NOT NULL target columns
(`target_anchor`, `target_section_path`, `target_title`) block generalization.
The retrieval layer needs no work: `RetrievalPort.search` already accepts an
`anchors` list (`None` = whole source), and `CorpusRepository.expand_anchors`
(AD-085) already expands chapter subtrees to canonical + alias anchors.

RFC-006 Cycle D (the reader-as-workspace) must be built against the final
conversation model, not against the Ask/Teach split it would then unlearn.
This ADR precedes and governs the implementing cycle (RFC-006 Cycle C).

## Decision

### The model

One conversation model per source, defined by two axes:

- **Scope** — a conversation-level list of section anchors. Empty list means
  the whole book; a non-empty list restricts book retrieval to those sections,
  with chapter subtrees and merged-away aliases expanded per turn via
  `expand_anchors` (AD-085), so scopes survive corpus replace. Scope is fixed
  at creation; page-range scoping is deferred (see below).
- **Mode** — a per-turn choice, `answer` or `teach`. `answer` replies as cited
  Q&A; `teach` replies as structured teaching against a target section. One
  conversation may interleave modes.

Notes inclusion becomes **one explicit per-conversation choice** stored on the
conversation, superseding AD-147's per-surface defaults for the unified
surface. (Compatibility endpoints keep AD-147's defaults for the old panels
until those panels retire.)

### The migration shape

A rename plus generalization, not a rewrite: `teaching_sessions` →
`conversations`, `teaching_turns` → `conversation_turns`,
`teaching_turn_citations` → `conversation_turn_citations`.

- `conversations` gains `title` (NOT NULL, for rename/list UX),
  `scope_anchors` (JSONB list, `[]` = whole book), and `include_notes`
  (BOOLEAN NOT NULL). The three `target_*` columns become **nullable** and are
  kept as the denormalized snapshot of the primary teach target (the head of a
  non-empty scope, resolved at creation).
- `conversation_turns` gains `mode` (TEXT NOT NULL, `answer` | `teach`,
  following the schema's string-constant convention — no enums).
- Backfill: existing teaching sessions get `scope_anchors =
  [target_anchor]`, `title = target_title`, `include_notes = false` (their
  AD-147 default); existing turns get `mode = 'teach'`.
- Everything else is preserved: UUID PKs, `sources` CASCADE, the
  `UNIQUE(conversation_id, turn_index)` turn-order arbiter, and the FK-less
  citation snapshot (AD-033).

### The scope-is-a-promise rule

A scoped conversation must never silently search the whole book. When
retrieval or grounding fails inside a non-empty scope, the turn's status is
**`not_found_in_scope`** — a distinct wire value beside `answered` and
`not_found_in_source` — so the UI can say "not found in your selection" and
offer to widen. `not_found_in_source` remains the whole-book verdict.
Compatibility presenters for the legacy panels collapse `not_found_in_scope`
to `not_found_in_source`, because the shipped panels only understand the old
vocabulary; the collapse dies with those endpoints.

### The teaching-anchor invariant

Teach-mode turns still require a resolvable target section. A teach turn is
valid only when the conversation's scope is non-empty and its primary target
resolves (alias-aware) to a live section; teaching against the whole book is
rejected. Answer-mode turns carry no such requirement.

### The unified API

One resource, `/api/conversations`: global list (newest activity first, with
an optional source filter), start (source, scope, explicit notes choice),
read, rename, delete, turn, and turn stream (same UI Message Stream framing as
today). Q&A turns are persisted from the first release: the legacy one-shot
questions endpoints create a whole-book conversation per question, so nothing
evaporates even before the workspace UI exists.

### Endpoint retirement and redirects

The legacy surface — `POST/GET /api/teaching-sessions*`,
`GET /api/sources/{id}/teaching-sessions`, and
`POST /api/sources/{id}/questions[/stream]` — is **compatibility-only** from
Cycle C: same paths, same statuses, same view shapes, same SSE frames, wired
to the unified model underneath. It retires in Cycle D when the workspace
re-points the panels; the frontend routes `/sources/[id]/ask` and
`/sources/[id]/teach` become redirects into the reader with the dock open
(RFC-006 Cycle D). Until retirement, the legacy per-source teaching list shows
only conversations with a teach target (`target_anchor` non-null), keeping
ask-created conversations out of the old Teach panel.

Retirement also converges the two generation ports. `AnswerGenerationPort` and
`TeachingGenerationPort` describe the same capability with a differently named
message parameter, a different argument order, and `history` optional on one and
required on the other. The unified turn service pays for that gap three times: both
generate paths branch on mode purely to rename an argument, reading the model
identity forces a union return type, and the composition root hands the ask path a
teaching generator it can never reach. Converging them is deliberately *not* done
while both wires are frozen — these are contracts the compatibility adapters depend
on. When the panels move, they become one `GenerationPort` whose target section path
is optional and whose message parameter has one name, and both mode branches go.

### One rate-limit policy

The unified mutating endpoints share a single conversations rate-limit policy
(the established fixed-window limiter, one policy instead of the separate
questions/teaching pair). The legacy endpoints keep their existing limiter
dependencies until they retire with the rest of the compatibility surface.

## Considered Alternatives

- **Two models, shared components** (keep `teaching_sessions`, add a parallel
  `qa_conversations`): rejected — it doubles every management endpoint,
  forbids interleaving modes, and Cycle D would build the dock against a split
  this ADR exists to remove.
- **New tables + copy + drop** instead of rename: rejected — the rename
  preserves data, FKs, and the turn-order arbiter in place; a copy adds a
  failure surface for zero benefit at this data size.
- **Mode on the conversation, not the turn**: rejected — the driver's model
  is explicitly scope × per-turn mode (RFC-006); a conversation-level mode
  recreates the Ask/Teach split one level down.
- **Nullable scope column** (`NULL` = whole book): rejected in favor of a
  single representation — `[]` means whole book; two spellings of "no scope"
  invite drift.

## Consequences

- Cycle D can build the four-tab dock, conversation list, rename, and delete
  against one stable resource.
- Chapter-scoped chat becomes expressible immediately; the retrieval engine
  needs no changes (Assumption 3 of RFC-006 held).
- The `answered | not_found_in_source | not_found_in_scope` status vocabulary
  becomes a wire contract; goldens must pin it.
- Legacy panels keep working bit-for-bit during Cycle C; their removal is a
  Cycle D deletion, not a migration.
- Deferred, recorded here per RFC-006: **page-range scoping** waits until the
  page unit has a stable mapping to sections (a page range rounds outward to
  whole sections, and the UI must show the resolved scope); **PDF true-page
  preference** stays deferred with it. Scope editing after creation is out
  until a real UI needs it.
