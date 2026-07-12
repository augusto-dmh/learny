# cited-qa — PR #13 Review Triage

Stage-4 record of every review comment on PR #13 (comments are deleted at
Stage 6; this file is the surviving record of the review reasoning). Verdicts
judged against the code as it exists, not reviewer authority.

| # | Source comment | File:line | Finding | Verdict | Action | Rationale |
|---|---|---|---|---|---|---|
| F-1 | inline `3565375454` (performance) | `backend/app/application/qa.py:116` | `set(generated.cited_chunk_ids)` sits inside the comprehension's `if` clause, so it is rebuilt once per evidence item (O(N·M)) | **Real** — verified: the `set()` call is inside the comprehension | **Fix** | Free one-line hoist; stops the cost silently scaling with `qa_evidence_top_k`; also reads clearer |
| F-2 | inline `3565375921` (tests) | `backend/tests/test_application_qa.py:375` | QA-12 completion-log assertion covers only `outcome=answered`; the spec says "answered or not found", and no test asserts the not-found completion logs exactly once, content-free | **Real** — verified: only the answered-path test asserts on caplog | **Fix** | Spec-anchored gap (QA-12 explicitly covers both outcomes); one caplog test on the empty-evidence path closes it |
| F-3a | issue `4949430864` note 1 (requirements) | `backend/app/application/errors.py` | 409 message names the not-ready condition, not the concrete status value (`uploaded`/`processing`) | Real observation, not a defect | **Won't-fix** | QA-08's outcome (409 + not-ready messaging + no retrieval/generation) is fully met; the spec text "naming the not-ready state" is satisfied by naming the condition. Same conclusion as the Verifier's note 2 in `validation.md`. Echoing the raw status value adds no user value |
| F-3b | issue `4949430864` note 2 (requirements) | `backend/tests/test_web_questions.py` | A fully missing `question` key is enforced structurally (`Field` required) but not separately test-asserted; QA-09 lists "missing" explicitly | **Real** (minor coverage gap vs the AC text) | **Fix** | QA-09 names the missing-key case; one request-without-body test makes the AC's own enumeration fully asserted rather than structurally assumed |
| F-3c | issue `4949430864` note 3 (requirements) | `frontend/app/lib/questions.ts:72` | `toQuestionError` returns `new Error(body.detail ?? fallback)`; FastAPI 422 `detail` is a **list** of error objects, so an over-long/blank question submitted to the API would render a stringified object list, violating QA-20's "readable error message" for the 422 path | **Real** — verified: `detail` is used unguarded; 422 bodies are list-shaped | **Fix** | QA-20 requires readable errors for 422 among the listed states; guard `typeof body.detail === "string"` and fall back otherwise. Client-side `maxLength` deliberately not added — the server bound is authoritative and a silent client cap would hide the limit |
| F-4 | issue `4949439700` (summary) | — | Consolidated review summary; no findings beyond F-1/F-2 | Not a finding | **No action** | Informational; deleted with the rest at Stage 6 |

## Totals

- Findings: 5 substantive (F-1, F-2, F-3a, F-3b, F-3c) + 1 informational (F-4)
- Real: 5 (F-3a is a real observation but names no defect) · False: 0
- Fix: 4 (F-1, F-2, F-3b, F-3c) · Won't-fix: 1 (F-3a) · No action: 1 (F-4)

## Planned fix commits (Stage 5)

1. `perf(qa): hoist the cited-id set out of the grounding filter` — F-1
2. `test(qa): assert the content-free completion log on the not-found path` — F-2
3. `test(qa): assert a missing question field is rejected` — F-3b
4. `fix(qa): fall back to a readable message for non-string error details` — F-3c
