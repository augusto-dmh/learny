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

**Phase A: DONE** — commits `8766b212` (A1, migration+metadata together so every commit stays green), `f2b54f72` (A2), `2e1b59b0` (A3), `b3354237` (A4), `97e1990d` (follow-up: qa.py reads status constants from the domain). Baseline 1789/1/11 → 1808/1/11 (+19); ruff + `make lint` clean. Sensors: I-CM-1 `test_migrations.py:2129`, I-CM-2 `:2143` + `test_repositories.py:1868`, backfill round-trip `:2056`. Deviations recorded in the Phase A report (notable: **downgrade drops whole-book conversations** — unrepresentable in the 0016 shape; documented in the migration docstring and pinned by test).

## Phase B — Unified services and generation history · Opus

| # | Task | Requirements | Gate |
|---|---|---|---|
| B1 | `StartConversation` (scope validation 422, target snapshot, title default) + `Read`/`List`/`Rename`/`Delete` | CONV-05..09, I-CM-6 | `pytest tests/test_application_conversations.py` |
| B2 | `PostConversationTurn` + `stream`: per-turn expansion, scoped retrieval, mode dispatch, `not_found_in_scope`, teach invariant 409, persist-after-grounding, `updated_at` bump, conflict | CONV-10..13, I-CM-2/3/5/7 | same file + concurrency test |
| B3 | `AnswerGenerationPort.history` + Anthropic answer history assembly + local signature widening; byte-stability pin | CONV-14, CONV-26, I-CM-8 | `pytest tests/test_answering_anthropic.py tests/test_answering_local.py tests/test_generation_invariants.py` |

Phase gate: full backend suite + ruff.

**Phase B: DONE** — commits `0a6f5d40` (B1), `a3daf2ff` (B2), `c1c7afaa` (B3). 1808/1/11 → 1866/1/11 (+58); ruff + `make lint` clean; carried failure unchanged. Sensors: I-CM-3 `test_application_conversations.py:1130` (vanished scope keeps its anchor, never `None`) + `:1199` (`not_found_in_scope`) + `:1061` (only an empty scope gets `anchors=None`); I-CM-5 `:1652` (cancel persists nothing) + `:1606` (stream == buffered turn); I-CM-2 `:1520`/`:1540`; I-CM-6 `:834`/`:897`/`:931`/`:1703`; I-CM-7 `:1375`/`:1398`; I-CM-8 `test_answering_local.py:54`/`:76`; history request shape `test_answering_anthropic.py:169`/`:188`/`:220`/`:234`. Five implementation mutations run against the new suite: four caught, the fifth (dropping the whole-book teach guard) is redundant with the target re-resolution and yields the same error. Decisions: `InvalidTeachingTarget`→`InvalidConversationScope`, `TeachingTargetGone`→`ConversationTargetUnavailable` (renamed, same status mapping), new `InvalidConversationTitle`→422; legacy `teaching.py`/`qa.py` left as-is this phase (Phase D folds them into the legacy presenters and removes the duplication).

## Phase C — Unified web surface · Opus

| # | Task | Requirements | Gate |
|---|---|---|---|
| C1 | Router: start/list/read/rename/delete (+DI, mount) with 404-as-absence, 422 explicit `include_notes` | CONV-15..19, I-CM-6 | `pytest tests/test_web_conversations.py` |
| C2 | Turn + stream endpoints: SSE frame parity, 409/422/429/502 mappings | CONV-20, CONV-21 | same file |
| C3 | `rate_limit_conversations` on all mutating routes + validation limits | CONV-22 | same file + `tests/test_web_rate_limit_validation.py` |

Phase gate: full backend suite + ruff.

**Phase C: DONE** — commits `ce356581` (C1), `aeb0c55b` (C2), C3 (this commit). 1866/1/11 → 1920/1/11 (+54); `ruff check` + `ruff format --check` + `make lint` (incl. architecture boundaries) clean; carried failure unchanged. Sensors: I-CM-6 `test_web_conversations.py:379`/`:601`/`:687`/`:751`/`:1032` (missing and unowned compared body-for-body on every route); explicit-notes 422 `:345` (mutation `include_notes: bool = False` → caught); SSE frame order `:1173` (exact frame-type list) + `:1246` (error then `[DONE]`, no `finish`) + `:1219` (`not_found_in_scope` on the status frame); 429 policy `:1474` (route inventory — every mutating route declares exactly `[rate_limit_conversations, enforce_origin, enforce_csrf]`, reads declare none; mutation dropping the limiter from DELETE → caught) + `:1410` (429 + `Retry-After`) + `:1455` (throttled before any SSE byte) + `test_web_rate_limit_validation.py:199` (dependency-level, house pattern); I-CM-2 `:1067` (a taken turn index → 409 through the real DB arbiter); I-CM-3 `:894`/`:1009` (scoped not-found says `not_found_in_scope`; a vanished scope anchor never widens to the book); I-CM-5 `:1097`/`:1246` (502 and mid-stream failure persist nothing) + `:1173` (stream persists on completion); I-CM-7 `:976`/`:993`. Three mutations run: all three caught. Decisions: `rate_limit_conversations` landed in C1 with the first mutating routes (C2's row already expects 429s) and C3 owns its verification; a new `:1352` sensor pins both turn handlers as synchronous — the `to_sse_response` threadpool contract is invisible to functional tests. `test_worker_tasks.py::test_run_ingestion_builds_corpus_from_valid_epub` failed once under the full suite and passed alone and on re-run — an order-dependent flake in untouched ingestion code, not carried by this phase.

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
