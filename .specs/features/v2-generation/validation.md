# v2-generation Validation

**Date**: 2026-07-16
**Spec**: `.specs/features/v2-generation/spec.md`
**Diff range**: `8e38bd4..HEAD` (15 implementation commits; planning commit 8e38bd4 excluded)
**Verifier**: independent sub-agent (author ≠ verifier; evidence-or-zero; re-derived from spec + diff)

---

## Verdict: PASS ✅

All 23 requirements (GEN-01..GEN-23) and every listed edge case trace to a located `file:line` + assertion whose asserted value matches the spec-defined outcome. Gate green at the expected baseline (645 passed, 10 skipped; ruff clean). Expanded 6-mutation discrimination sensor: 6 injected, 6 killed, 0 survived.

---

## Spec-Anchored Acceptance Criteria

Line numbers are into the named test file. All paths under `backend/`.

### P1: Claude-generated cited answers (GEN-04..08)

| Criterion (WHEN X THEN Y) | Spec outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| provider=anthropic → one plain-text citations-enabled doc per chunk, evidence order, frozen system prompt, question last | doc-per-chunk in order, `citations:{enabled:True}`, `system==ANSWER_SYSTEM_PROMPT` | `tests/test_answering_anthropic.py:117` — asserts `doc["citations"]=={"enabled":True}`, `doc["source"]["data"]==item.snippet`, `content[-1]=={"type":"text","text":"What is X?"}` | ✅ |
| cited_chunk_ids via document_index, first-citation order, dedup, never document_title | maps index→chunk_id, title ignored | `:163` `result.cited_chunk_ids==(evidence[1].chunk_id,)` with `document_title="MISLEADING"`; `:178` dedup `==(e[1],e[0])` | ✅ |
| whole-reply sentinel → found=False | `text=""`, `cited=()`, `found=False` | `:197` `result.found is False and result.text=="" and result.cited_chunk_ids==()` | ✅ |
| endpoint 200 + answer_status=not_found_in_source | 200 not-found body | `tests/test_web_questions.py:237` `body["answer_status"]=="not_found_in_source"`; service `test_application_qa.py:244` found=False→not_found | ✅ |
| provider error → 502 generic, no leak | 502, detail generic, secret absent | `test_web_questions.py:396` `resp.status_code==502` + `"provider-secret-internal-detail" not in resp.text`; `test_application_qa.py:325` wraps `AnswerGenerationFailed` | ✅ |
| provider unset/local → byte-identical | deterministic path unchanged | `test_answering_factory.py:27` local→`DeterministicAnswerAdapter`; `test_config.py:39` defaults; full suite green under default | ✅ |
| citation index outside evidence → grounding discards, none→not_found | out-of-range dropped, ground→None | `test_answering_anthropic.py:281` `cited==()` and `ground(result,ev) is None`; `test_application_qa.py:269` all-out-of-set→not_found | ✅ |

### P1: Claude teaching turns with prompt caching (GEN-10, GEN-11)

| Criterion | Spec outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| frozen teaching prompt + alternating history + this turn's evidence docs → cited grounded prose | layout as specified | `test_answering_anthropic.py:316` asserts `system==[{...TEACHING_SYSTEM_PROMPT,cache_control:1h}]`, alternating user/assistant, final user turn = docs+text | ✅ |
| system prompt no interpolation + cache_control ttl:"1h" (system + latest history block); volatile after prefix | byte-stable system, 1h breakpoints, latest-only 2nd bp | `:359` `first_system==second_system`; `:386` only `messages[3]` block carries `cache_control==_CACHE_1H`, `messages[1]` none; `:409` empty history → system bp only | ✅ |
| irrelevant evidence → sentinel → not-found turn | found=False turn | `:446` teaching sentinel `found is False`; `test_application_teaching.py:872` found=False→not_found persisted | ✅ |
| provider error → 502, persist no turn | 502 + `add_calls==0` | `test_application_teaching.py:923` `add_calls==0`; `test_web_teaching.py:754` 502 + turns read back `[]` | ✅ |

### P2: SSE streaming endpoints (GEN-12..17)

| Criterion | Spec outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| /questions/stream → SSE + header, ordered parts start→text-start→delta→text-end→data-citations→(status)→finish→[DONE] | exact frame list + `x-vercel-ai-ui-message-stream: v1` | `test_web_questions.py:532` `_part_types(parts)==[...]`, header `=="v1"`, `delta["delta"]==_PHOTO`, `status["data"]=={"status":"answered"}` | ✅ |
| /turns/stream completes → turn persisted same fields + same parts | persisted + read-back | `test_web_teaching.py:871` full frame list + read-back one answered turn | ✅ |
| pre-stream guard fails → plain 404/409/422/429 before SSE | plain HTTP | `test_web_questions.py:611` 404 identical, `:628` 409, `:642` 422 (`"start" not in text`), `:662` 429, `:652` 403 CSRF | ✅ |
| mid-stream failure → protocol error part, terminate, no persist | `error` part, no finish, no leak | `test_web_questions.py:681` `"error" in types`, `"finish" not in types`, secret absent; `test_web_teaching.py:996` + turns `[]` | ✅ |
| not-found → data-answer-status not_found_in_source, no text | status part, no delta | `test_web_questions.py:580` no `text-delta`, `status.data=={"status":"not_found_in_source"}`; `test_web_teaching.py:915` + persisted not_found | ✅ |
| client disconnect mid-stream → cancel provider stream, persist nothing | close→port closed, no persist | `test_application_teaching.py:1278` `stream_closed True`, `add_calls==0`; `test_application_qa.py:631` port stream closed; adapter `test_answering_anthropic.py:606` SDK stream closed | ✅ (endpoint-level HTTP disconnect covered at adapter+app layers; see note) |
| deterministic provider streams (trivially chunked) | provider-independent | all web SSE tests run offline under deterministic provider; `test_answering_local.py:230` one delta + completed | ✅ |

### P2: Evaluation harness (GEN-18..22)

| Criterion | Spec outcome | `file:line` + assertion | Result |
| --- | --- | --- | --- |
| PR suite offline → 3 exact citation invariants over deterministic adapter on golden book | cited⊆retrieved; anchors resolve; answered⇒≥1 citation | `test_generation_invariants.py:81` asserts all three per case; seeded-violation checks `:55,:63,:70` prove each can fail | ✅ |
| snapshots exist → same invariants; none → explicit skip | parametrized + skip reason | `:111` parametrized over `load_snapshots()`, `:125` explicit skip; `test_replay_harness.py:165` roundtrip-or-skip | ✅ |
| pytest --record + key → live adapter rewrites snapshots | record path writes reviewable JSON | `test_replay_harness.py:122` fake-adapter record → `a.json/b.json`; `:190` live (skipped); `conftest.py:35` `--record-generation` option | ✅ |
| key set → live smoke, text + ≥1 valid citation per adapter; unset → skip | real call asserts prose+citation | `test_answering_anthropic.py:692,709,731` (@live+skipif); F5 sentinel `:731` found=False | ✅ (skip-by-design, body targets spec outcome) |
| judge: faithfulness ratio (structured outputs) + relevancy 1-5 + versioned prompts + JSONL line (scores, model ids, prompt hash, sha) | ratio math, integer parse, full schema | `test_eval_judge.py:83` `supported_ratio==2/3` + `output_config.format.type=="json_schema"`; `:115` relevancy enum; `:143` JSONL schema set + values | ✅ |
| nightly (cron+dispatch), secret present → run capped + upload; absent → skip | workflow structure + cap + skip | `.github/workflows/eval.yml` cron+workflow_dispatch, secret→`present=false` notice+skip, `LEARNY_EVAL_MAX_CASES:20`, upload-artifact; cap enforced `test_eval_judge.py:190` `caps_at_max_cases` | ✅ (config validated by inspection per spec's "dispatch dry-run structure") |

### Cross-cutting (GEN-01, 02, 03, 09, 23)

| Req | Evidence | Result |
| --- | --- | --- |
| GEN-01 settings fields + offline defaults | `test_config.py:39` defaults; `:51` env overrides | ✅ |
| GEN-02 factory switch, unknown→ValueError, empty-key fail-fast | `test_answering_factory.py:27,35,51,60` (answer) + `:70..107` (teaching) | ✅ |
| GEN-03 SDK imported lazily only | `test_answering_anthropic.py:265` + `test_eval_judge.py:240` AST assert `"anthropic" not in top_level` | ✅ |
| GEN-09 ADR-0020 Accepted | `docs/adr/0020-use-anthropic-claude-for-generation.md` present | ✅ |
| GEN-23 suite green offline, no schema change, frontend untouched | 645 passed / 10 skipped offline; diff has no migration; no frontend files | ✅ |

**Status**: ✅ All 23 requirements + all edge cases covered; 0 spec-precision gaps.

---

## Edge Cases

| Edge case | `file:line` | Verdict |
| --- | --- | --- |
| empty evidence → port NOT invoked (streaming too) | `test_application_qa.py:223,482`; teaching `:814,1194` `generation.calls==[]` | ✅ |
| zero citations, no sentinel → grounding not_found | `test_application_qa.py:586` streamed prose → not_found | ✅ |
| embedded sentinel in longer answer → stays prose (only whole-reply not-found) | `test_answering_anthropic.py:219` | ✅ |
| repeated document_index → dedup keeps first | `test_answering_anthropic.py:178` | ✅ |
| anthropic + empty key → fail fast (config error, not 502) | `test_answering_factory.py:51,94` `ValueError match "required"` | ✅ |
| unknown provider → ValueError | `test_answering_factory.py:60,103` | ✅ |
| stop_reason==max_tokens → partial text + citations, never raise | `test_answering_anthropic.py:236` | ✅ |
| SSE disconnect before first token → no provider leak | generator laziness + close path (`test_answering_anthropic.py:606`, `test_application_*` close tests) | ✅ (note) |

**Note (AC P2-SSE #6 / disconnect-before-first-token):** true HTTP mid-stream disconnect is not directly drivable through FastAPI's `TestClient` (it consumes the whole body). The cancellation contract is verified one layer down — `generate_stream` is a lazy generator (no provider call until first iteration), `hold_back_deltas` closes the port stream in `finally`, and the adapter's `with messages.stream(...)` closes on `GeneratorExit` — each asserted (`test_answer_stream_close_closes_the_sdk_stream`, `test_stream_consumer_close_*`). This is adequate layered coverage, not a gap.

---

## Discrimination Sensor

Scratch-state mutations (Edit → run target file → `git checkout` revert; `git status` clean confirmed after each).

| # | File:line | Mutation | Target file | Killed? |
| --- | --- | --- | --- | --- |
| 1 | `answering/anthropic.py:122` | sentinel whole-reply `text.strip()==SENTINEL` → substring `SENTINEL in text.strip()` | `test_answering_anthropic.py` | ✅ Killed (`test_embedded_sentinel_stays_prose`) |
| 2 | `answering/anthropic.py:45` | cache TTL `"1h"` → `"5m"` | `test_answering_anthropic.py` | ✅ Killed (5 teaching-layout tests) |
| 3 | `answering/anthropic.py:120` | citation order `cited.append` → `cited.insert(0,...)` (reverse first-occurrence) | `test_answering_anthropic.py` | ✅ Killed (`test_citations_dedup_keeping_first_occurrence_order`) |
| 4 | `application/streaming.py:84` | hold-back prefix `SENTINEL.startswith(accumulated)` → `accumulated.startswith(SENTINEL)` | `test_application_qa.py`, `test_application_teaching.py` | ✅ Killed (3 sentinel-suppression tests) |
| 5 | `web/questions.py:135` | drop `Depends(rate_limit_questions)` from `/questions/stream` deps | `test_web_questions.py` | ✅ Killed (`test_ask_stream_rate_limit_returns_429`) |
| 6 | `web/ui_message_stream.py:96` | answer-status payload `{"status":status}` → `{"status":"answered"}` (hardcode) | `test_web_questions.py`, `test_web_teaching.py` | ✅ Killed (2 not-found status-part tests) |

**Sensor depth**: P0-full (expanded, correctness-critical paths) — 6 behavior-level mutations across parser, cache config, citation ordering, streaming hold-back, SSE dependency wiring, and SSE payload value.
**Result**: 6/6 killed — PASS ✅

---

## Payload / Conjunction Rule

Payload-bearing criteria assert field VALUES, not merely that a call occurred:
- SSE frames: `delta["delta"]==_PHOTO`, `citation["anchor"]==_ANCHOR`, `status["data"]=={"status": "not_found_in_source"}`, `error_part["errorText"]=="Answer generation failed. Please try again."` (`test_web_questions.py:558-577,717`).
- JSONL line: `faithfulness==1.0`, `relevancy==5`, `citation_valid is True`, `prompt_hash()==...`, full key-set equality (`test_eval_judge.py:165-183`).
- GeneratedAnswer: `cited_chunk_ids`, `text`, `found`, `model` asserted on both outcomes (`test_answering_anthropic.py`, `test_application_*`).
- Request shape: `system`, per-doc `source.data`/`citations`, `cache_control` value asserted verbatim.

All ✅ — no "call happened" shallow assertions found on payload criteria.

---

## Code Quality

| Principle | Status |
| --- | --- |
| Minimum code / no scope creep | ✅ (adapters behind existing ports; no schema/frontend change) |
| Surgical changes, matches patterns | ✅ (mirrors embeddings factory / OpenAI adapter conventions) |
| Spec-anchored outcome check (asserted values match spec) | ✅ |
| Per-layer coverage (domain 1:1 ACs; routes happy+edge+error) | ✅ (404/409/422/429/403/502 all covered for both stream + JSON) |
| Every test maps to a spec req / edge case / Done-when | ✅ (no unclaimed tests found) |
| Layering (no FastAPI/SQLAlchemy/SDK in domain/app) | ✅ (`test_application_qa.py:659`, `test_application_teaching.py:1338` AST guards) |
| Documented guidelines followed | ✅ (CLAUDE.md: citations/golden-fixtures core; ADR-0007/0009 ports; pyproject markers) |

---

## Gate Check

- **Full suite**: `LEARNY_TEST_DATABASE_URL=... uv run pytest -q` → **645 passed, 10 skipped**, 1 warning (33.12s). Matches expected baseline.
- **Lint**: `uv run ruff check .` → All checks passed.
- **Skips (all justified, skip-by-design)**: 3 live Anthropic smoke + 1 live judge (`LEARNY_ANTHROPIC_API_KEY` unset), 2 live OpenAI (pre-existing), 2 replay-harness (no committed snapshots + `--record-generation` absent), 2 generation-invariants snapshot skips (empty param set / explicit no-snapshot reason). Each skip's body targets the spec outcome behind its gate.
- **Test integrity**: test count increased (new suites `test_answering_anthropic.py`, `test_answering_factory.py`, `test_eval_judge.py`, `test_generation_invariants.py`, `tests/eval/`, `test_web_*` stream sections); no assertions weakened; no tests deleted.

---

## Requirement Traceability Update

GEN-01 .. GEN-23: all **✅ Verified** (see Spec-Anchored table). 0 Needs-Fix.

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 23/23 requirements + all edge cases matched spec outcome; 0 spec-precision gaps.
**Sensor**: 6/6 mutations killed (P0-full).
**Gate**: 645 passed, 10 skipped; ruff clean.

**What works**: Anthropic answer + teaching adapters behind existing ports with document_index citation mapping, whole-reply sentinel F5 fix, prompt caching (1h, system + latest history block); provider factory + DI switch with fail-fast; domain streaming contract + application hold-back + SSE UI-Message-Stream presenter with full guard parity; deterministic citation invariants, replay harness with `--record-generation`, LLM judge with calibration-gate, live smokes, secret-gated nightly workflow.

**Issues found**: none.

**Next steps**: none — feature is verification-clean.
