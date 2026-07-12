# cited-qa Validation

**Date**: 2026-07-11
**Spec**: `.specs/features/cited-qa/spec.md`
**Diff range**: `main...HEAD` (feat/cited-qa), commits `ddf67a2..97285e1`
**Verifier**: independent sub-agent (author ≠ verifier, evidence-or-zero)

**Verdict**: ✅ PASS

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| A1 GeneratedAnswer + QuestionAnswer DTOs | ✅ Done | `backend/app/domain/entities.py:346,363` |
| A2 AnswerGenerationPort | ✅ Done | `backend/app/domain/ports.py:388` (`model: str` per SPEC_DEVIATION) |
| A3 QA errors + settings | ✅ Done | `errors.py:111,120`; `config.py:108-109` |
| B1 DeterministicAnswerAdapter | ✅ Done | `backend/app/infrastructure/answering/local.py` |
| B2 AskQuestion service | ✅ Done | `backend/app/application/qa.py` |
| C1 rate limit + error mappings | ✅ Done | `rate_limit.py:128`; `error_handlers.py:96` |
| C2 questions router + wiring | ✅ Done | `web/questions.py`; `dependencies.py:319` |
| D1 questions client | ✅ Done | `frontend/app/lib/questions.ts` |
| D2 AskPanel + page + link | ✅ Done | `AskPanel.tsx`, `ask/page.tsx`, `SourcesPanel.tsx:236` |

---

## Spec-Anchored Acceptance Criteria

### P1-A: Ask a cited question

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| QA-01 ready source w/ evidence → answered | 200, `answer_status=="answered"`, non-empty `answer` | `test_web_questions.py:170-171` — `body["answer_status"]=="answered"` & `body["answer"]==_PHOTO` | ✅ PASS |
| QA-02 citations carry anchor fields, non-empty, no dup chunk_id | 6 anchor fields present; non-empty; deduped | `test_web_questions.py:177-195` — `set(citation)=={7 fields}`, `len==1`, dup-check; service dedupe `test_application_qa.py:165-167` | ✅ PASS |
| QA-03 every citation chunk_id ∈ retrieved evidence | grounding | `test_application_qa.py:165,168` — `result.citations==(e0,e2)`, `all(c in {e0,e1,e2})`; unretrieved id dropped | ✅ PASS |
| QA-04 200 carries `retrieval={strategy:hybrid,evidence_count:N}` + `model` | exact diagnostics both outcomes | `test_web_questions.py:172-173,255-256` — `body["retrieval"]=={"strategy":"hybrid","evidence_count":1/0}`, `body["model"]==_MODEL`; service `test_application_qa.py:194-195` | ✅ PASS |
| QA-05 generation only via port, trimmed q + Evidence; no SDK in domain/application | port-only; no provider import | `test_application_qa.py:219` — `generation.calls==[{"question":"photosynthesis","evidence":evidence}]`; `:383-394` import sweep of qa module | ✅ PASS (see note 1) |
| QA-06 adapter deterministic, evidence-only, no network | identical twice; cited ⊆ evidence | `test_answering_local.py:44` (`first==second`), `:55-56`, `:104-115` (no SDK), `:118-123` (no client) | ✅ PASS |
| QA-07 missing/non-owned → 404, identical body | no existence disclosure | `test_web_questions.py:313-315` — both 404, `non_owned.json()==missing.json()`; service `test_application_qa.py:95,112` | ✅ PASS |
| QA-08 owned but not ready → 409, no retrieval/generation | 409; neither runs | `test_web_questions.py:329-330` — 409 + body; `test_application_qa.py:132-133` — `retrieve.calls==[]`, `generation.calls==[]` | ✅ PASS (see note 2) |
| QA-09 missing/empty/whitespace question → 422 before service | 422 pre-service | `test_web_questions.py:340-341` (empty, `"answer_status" not in`), `:350` (whitespace) | ✅ PASS (see note 3) |
| QA-10 trimmed > max chars → 422 pre-service | 422 | `test_web_questions.py:362` (over-long), `:375` (exactly-max accepted 200) | ✅ PASS |
| QA-11 no session → 401; bad CSRF/Origin → 403 | 401/403 | `test_web_questions.py:267` (401), `:274` (no CSRF 403), `:281` (bad CSRF 403), `:294` (bad Origin 403) | ✅ PASS |
| QA-12 one content-free completion log (source_id, outcome, evidence_count, model; no q/answer text) | single redacted log | `test_application_qa.py:373-380` — `len(records)==1`, contains outcome/source_id/evidence_count/model, excludes question & answer text | ✅ PASS |

### P1-B: Explicit not-found

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| QA-13 zero evidence → not_found, empty citations, port NOT invoked | 200 not_found; port uninvoked | `test_application_qa.py:235-240` — `generation.calls==[]`, status/text/citations/count; web `test_web_questions.py:252-256` | ✅ PASS |
| QA-14 found==false → not_found, empty citations | not_found | `test_application_qa.py:261-265` — status `not_found_in_source`, `citations==()` | ✅ PASS |
| QA-15 out-of-evidence citations discarded; none remain → not_found | discard + not_found | `test_application_qa.py:292-293` — status not_found, `citations==()` | ✅ PASS |
| QA-16 found==true + blank text → not_found | not_found | `test_application_qa.py:320-321` — status not_found, `citations==()` | ✅ PASS |
| QA-17 port raises → 502 generic body, no internal detail, no persistent state | 502 generic | `test_web_questions.py:402-404` — 502, `{"detail":"Answer generation failed. Please try again."}`, secret absent; service `test_application_qa.py:342` — `__cause__ is boom` | ✅ PASS |

### P1-C: Browser ask panel

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| QA-18 answered → renders answer + each citation section path + snippet | render answer + citations | `ask-screen.test.tsx:125-131` — answer text, `"Chapter 1 › Core Idea"`, snippets; link `:228` | ✅ PASS |
| QA-19 not_found → explicit message, no citation list | explicit message | `ask-screen.test.tsx:149-152` — `"not found in this source"`, no `answer`/listitem | ✅ PASS |
| QA-20 error states → readable message, form usable | readable error + usable | `ask-screen.test.tsx:177-187` — alert text, re-submit succeeds; client detail mapping `questions-client.test.ts:123,133,143,153` | ✅ PASS |
| QA-21 request via same-origin proxy w/ credentials + CSRF | proxy path, same-origin, CSRF | `questions-client.test.ts:68-73` — `/api/sources/s1/questions`, `credentials==same-origin`, `X-CSRF-Token==csrf-xyz` | ✅ PASS |

### P2-D: Abuse protection

| Criterion | Spec-defined outcome | `file:line` + assertion | Result |
| --------- | -------------------- | ----------------------- | ------ |
| QA-22 exceed rate limit → 429 + Retry-After | 429 + header | `test_web_questions.py:467-468` (endpoint 429 + Retry-After), `test_web_rate_limit_validation.py:143-146` (dependency 429 + Retry-After) | ✅ PASS |

### Edge Cases

| Edge case | Evidence | Result |
| --------- | -------- | ------ |
| Exactly max chars accepted (inclusive) | `test_web_questions.py:375` — 200 | ✅ |
| Zero-chunk corpus → not_found | `test_web_questions.py:250-256` (corpus present, not embedded → 0 evidence); `test_application_qa.py:222-240` | ✅ |
| Adapter cites same chunk twice → deduped | `test_application_qa.py:152,165` (e0 cited twice → once) | ✅ |
| Fewer evidence than top_k → proceed | `test_answering_local.py:73-83` (1 item); web single-chunk answered | ✅ |

**Status**: ✅ 22/22 ACs matched spec outcome; 3 minor precision notes (below), none blocking.

**Notes:**
1. QA-05 no-SDK check asserts against the `qa` module (`test_application_qa.py:383`) and the adapter module (`test_answering_local.py:104`), not a repo-wide `grep` of all `app/domain`/`app/application`. Independently confirmed: no `openai`/`anthropic`/provider import exists anywhere under those trees for this diff. Adequate.
2. QA-08 message is `"Source is not ready for questions."` — it names the not-ready *condition* but not the concrete status value (e.g. `uploaded`/`processing`). Outcome (409 + not-ready messaging + no retrieval/generation) is fully met; wording is a stylistic reading of "naming the not-ready state".
3. QA-09 tests cover empty and whitespace-only; a fully *missing* `question` key is enforced structurally by `Field(min_length=1)` (required) but is not separately asserted by a test. Substantive cases covered.

---

## Discrimination Sensor

Mutations injected in scratch state (Edit → run covering test → confirm FAIL → `git checkout` revert). Real tree never persistently modified.

| # | File:line | Description | Covering test | Killed? |
| - | --------- | ----------- | ------------- | ------- |
| 1 | `qa.py:73` | Invert readiness guard `!=` → `==` | `test_application_qa.py` + `test_web_questions.py` (16 failed) | ✅ Killed |
| 2 | `qa.py:116` | Skip grounding filter → `grounded = list(evidence)` | `test_ask_all_citations_out_of_evidence_is_not_found`, `..._grounds_orders_and_dedupes...` | ✅ Killed |
| 3 | `qa.py:116` | Iterate cited ids (breaks dedupe + rank order) | `test_ask_answered_grounds_orders_and_dedupes_citations` | ✅ Killed |
| 4 | `qa.py:117` | Weaken blank-text guard `not text.strip()` → `not text` | `test_ask_blank_answer_text_is_not_found` | ✅ Killed |
| 5 | `error_handlers.py:96` | 502 handler leaks `str(cause)` in body | `test_ask_generation_failure_returns_502_generic` | ✅ Killed |
| 6 | `web/questions.py:60` | Off-by-one max-chars `>` → `>=` | `test_ask_exactly_max_chars_is_accepted` | ✅ Killed |

**Sensor depth**: lightweight+ (6 mutations, covering readiness/QA-08, grounding/QA-03/15, dedupe+order/QA-02, blank-text/QA-16, no-leak/QA-17, inclusive-bound/QA-10).
**Result**: 6/6 killed — ✅ PASS

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code / no scope creep | ✅ (stateless per D-2; no persistence, no provider adapter) |
| Surgical changes, matches patterns | ✅ (mirrors retrieval router, embedding adapter, rate_limit_upload) |
| Spec-anchored outcome check (asserted values match spec) | ✅ |
| Per-layer coverage (domain 1:1 ACs; routes happy+edge+error) | ✅ |
| Every test maps to a spec AC / edge / Done-when | ✅ (no unclaimed tests) |
| Documented guidelines followed | ✅ `CLAUDE.md` (ports/adapters, citations core), `context.md` decisions |

Layering held: `qa.py` imports no fastapi/sqlalchemy/celery/openai/anthropic (asserted). Provider-independence preserved (AD-024 deterministic default; provider ADR flagged as merge-gate follow-up per D-1).

---

## Gate Check

- **Backend**: `uv run pytest -q` → **351 passed**, 1 warning (Starlette httpx deprecation, pre-existing). `ruff check .` → **All checks passed**.
- **Frontend**: `npm test` → **60 passed** (10 files). `npx tsc --noEmit` → exit 0.
- **Test count**: baseline `main` 314 backend → 351 (+37). No decreases, no unjustified skips, no weakened assertions.

---

## Requirement Traceability Update

| Requirement | New Status |
| ----------- | ---------- |
| QA-01..QA-22 | ✅ Verified |

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 22/22 ACs matched spec outcome (3 minor, non-blocking precision notes).
**Sensor**: 6/6 mutations killed.
**Gate**: backend 351 passed + ruff clean; frontend 60 passed + tsc clean.

**What works**: Owner-scoped cited-answer endpoint with grounding enforced in the application service (grounding, dedupe, rank order, empty-evidence short-circuit, blank/found guards), explicit `not_found_in_source` product outcome, generic 502 on port failure with no leak, content-free lifecycle log, full auth/CSRF/404-collapse/readiness/validation/rate-limit surface, and the browser ask panel through the same-origin proxy.

**Issues found**: none blocking. Three minor spec-precision observations recorded above (QA-05 module-scoped vs repo-wide no-SDK assertion; QA-08 message names the condition not the concrete state; QA-09 missing-key enforced structurally, not test-asserted).

**Lessons**: clean PASS — no surviving mutants, no failed/uncovered ACs. The single `SPEC_DEVIATION` (QA-04 `model` read off the port) is additive and pre-accepted in `context.md`; no new lesson warranted.

**Next steps**: none for this cycle. Provider-adapter ADR remains the flagged merge-gate follow-up (D-1) for LLM-generated prose.
