# Tasks — `v6-conversation-model`

Contract per task: tests derive from the spec's acceptance criteria and assert
spec outcomes; the gate is green before the task is done; one atomic commit per
task; no internal IDs and no tooling attribution in commit messages.

## Phase A — Schema and domain (backend) · Opus

| # | Task | Requirements | Gate |
|---|---|---|---|
| A1 | Migration `0017_conversations`: renames + adds + backfill + reversible downgrade | CONV-01, I-CM-1, I-CM-2 | `pytest tests/test_migrations.py` |
| A2 | `metadata.py` new shape + domain entities/constants (`Conversation`, `ConversationTurn`, modes, `not_found_in_scope`) | CONV-02, CONV-03 | `pytest tests/test_migrations.py tests/test_domain_contracts.py` (or nearest domain suite) |
| A3 | Repository ports + SqlAlchemy impls: renames + `list_for_user` + `list_for_source_with_target` + `rename`/`delete`/`touch` | CONV-04 | `pytest tests/test_repositories_teaching.py` (renamed) + new repo tests |
| A4 | Settings: `conversation_evidence_top_k/history_turns/message_max_chars`; deprecate 3 legacy fields in place | CONV-05 (partial), AD-198 | `pytest tests/test_config.py` |

Phase gate: full backend suite + `ruff check` + `ruff format --check`; record baseline counts.

## Phase B — Unified services and generation history · Opus

| # | Task | Requirements | Gate |
|---|---|---|---|
| B1 | `StartConversation` (scope validation 422, target snapshot, title default) + `Read`/`List`/`Rename`/`Delete` | CONV-05..09, I-CM-6 | `pytest tests/test_application_conversations.py` |
| B2 | `PostConversationTurn` + `stream`: per-turn expansion, scoped retrieval, mode dispatch, `not_found_in_scope`, teach invariant 409, persist-after-grounding, `updated_at` bump, conflict | CONV-10..13, I-CM-2/3/5/7 | same file + concurrency test |
| B3 | `AnswerGenerationPort.history` + Anthropic answer history assembly + local signature widening; byte-stability pin | CONV-14, CONV-26, I-CM-8 | `pytest tests/test_answering_anthropic.py tests/test_answering_local.py tests/test_generation_invariants.py` |

Phase gate: full backend suite + ruff.

## Phase C — Unified web surface · Opus

| # | Task | Requirements | Gate |
|---|---|---|---|
| C1 | Router: start/list/read/rename/delete (+DI, mount) with 404-as-absence, 422 explicit `include_notes` | CONV-15..19, I-CM-6 | `pytest tests/test_web_conversations.py` |
| C2 | Turn + stream endpoints: SSE frame parity, 409/422/429/502 mappings | CONV-20, CONV-21 | same file |
| C3 | `rate_limit_conversations` on all mutating routes + validation limits | CONV-22 | same file + `tests/test_web_rate_limit_validation.py` |

Phase gate: full backend suite + ruff.

## Phase D — Legacy compatibility and goldens · Opus

| # | Task | Requirements | Gate |
|---|---|---|---|
| D1 | Legacy teaching endpoints over unified services; wire frozen; target-filtered list; status collapse | CONV-23, I-CM-4 | `pytest tests/test_web_teaching.py tests/test_application_teaching.py` |
| D2 | Legacy questions endpoints persist conversations (AD-195); `AnswerResponse`/SSE unchanged; status collapse | CONV-24, CONV-25, I-CM-4 | `pytest tests/test_web_questions.py tests/test_application_qa.py` |
| D3 | Goldens + invariants sweep: golden citations, first-turn byte-stability, scope-promise sensor test | CONV-26, I-CM-3, I-CM-8 | `pytest tests/test_golden_citations.py tests/test_generation_invariants.py` |

Phase gate: full backend suite + ruff + **frontend `npm test` + `tsc --noEmit` with zero frontend edits** (I-CM-4).

## Close

After D: fresh Verifier (Opus) — spec-anchored outcome check over CONV-01..26 +
discrimination sensor over I-CM-1..8; `validation.md`; fix loop ≤3.
