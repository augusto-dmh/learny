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

**Phase D: DONE** — commits `2854a453` (D1), `449505bb` (D2), D3 (this commit). 1920/1/11 → 1937/1/11 (+17); `ruff check` + `ruff format --check` + `make lint` (incl. architecture boundaries) clean; carried failure unchanged (`test_eval_retrieval_metrics.py::…::test_metrics_meet_thresholds`), worker flake did not reappear. Frontend **untouched** (`git diff` shows zero files under `frontend/`): `npm test` 633 passed in 63 files, `tsc --noEmit` clean — the I-CM-4 sensor. Duplication removed: `app/application/teaching.py`'s four services and `qa.py`'s `AskQuestion` are now thin adapters over the unified services (no retrieval/generation/grounding/persistence logic left in either); `app/infrastructure/web/legacy_status.py` is the one home of the AD-196 collapse. Sensors: I-CM-4 wire freeze `test_web_teaching.py` (34 pre-existing tests pass with **zero** assertion edits) + `test_web_questions.py` (27 pass; only four generation doubles gained the port's `history` argument — no assertion touched), field-set pins `test_web_teaching.py:561`/`:1071` and `test_web_questions.py:184`/`:224`/`:884`, legacy detail wording `test_web_questions.py:473`, stream-handler synchronicity `test_web_teaching.py:1068` (both legacy stream handlers, mirroring Phase C's); status collapse (JSON) `test_web_teaching.py:649` (wire says `not_found_in_source`, the same turn read on `/api/conversations` says `not_found_in_scope`) + (SSE) `:933`, plus `:624`/`:913` which now pass only because of the collapse — mutation making `legacy_answer_status` the identity → 4 tests caught; no failure litter `test_web_questions.py:334` (502 → `GET /api/conversations` empty) + `:365` (mid-stream error frame → empty) + `test_application_qa.py:566`/`:592`/`:617` (buffered, mid-stream, consumer disconnect) — mutation removing the discard → 5 tests caught; ask persisted + visible `test_web_questions.py:290` (list shows it, title = question, `turn_count` 1, turn 0 `mode == "answer"`) + `test_application_qa.py:499`/`:544` (whole-book scope, stored notes choice, 80-char title cut); ask stays out of the old panel `test_web_questions.py:321` + `test_application_teaching.py:739`; legacy start mapping `test_application_teaching.py:537` (scope `[target]`, notes off, title = target title); AD-147 override `test_application_teaching.py:874` (both paths forward the request value; the stored choice is never rewritten); I-CM-3 end-to-end `test_web_conversations.py:917` (same question, same embedded corpus: the whole-book conversation cites the sibling section, the scoped one never does) — mutation dropping scope expansion → caught; I-CM-8 end-to-end `test_golden_citations.py:66` (a golden ask's text and citation order equal the deterministic adapter's own composition of the evidence retrieved, recomputed rather than pinned to a literal) + `test_web_questions.py:184` (byte-exact extractive answer through the full legacy path, unchanged from pre-cycle). Coverage retargeted, never dropped: `test_application_teaching.py` (40 → 43) and `test_application_qa.py` (27 → 32) keep every assertion, with their builders now composing the unified services behind the legacy seam, so both suites are end-to-end over the real mechanics; the only rewrites were the completion-log tests (logger `app.application.{qa,teaching}` → `app.application.conversations`, `source_id`/`session_id` → `conversation_id` + `mode`, every content-free assertion kept) and the teaching turn's not-found expectations (`not_found_in_source` → `not_found_in_scope`, which is the spec's truth at that layer; the wire value is asserted in `test_web_teaching.py`). Deviations: (1) legacy errors are re-worded in the adapters (`_teaching_wording`, `_questions_wording`) so the 409/404/422 `detail` strings stay byte-identical — a message map, not a status map; (2) `ReadTeachingSession` reports a target-less conversation as absent (404) — otherwise a question's conversation read through the teaching endpoint would 500 in `TargetView`; the legacy turn endpoint leaves the unified 409 for that case; (3) legacy budgets now come from `conversation_evidence_top_k`/`conversation_history_turns` per AD-198 — same values (8/6) as the deprecated fields, so no behaviour moved; (4) `tests/eval_runner.answer()` wires the unified services (its asks now persist a conversation + turn inside the rolled-back test transaction); (5) `dependencies.py` drops the `conversation_services` module alias now that the legacy names no longer collide.

## Close

After D: fresh Verifier (Opus) — spec-anchored outcome check over CONV-01..26 +
discrimination sensor over I-CM-1..8; `validation.md`; fix loop ≤3.
