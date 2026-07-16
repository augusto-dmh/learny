# v2-generation — PR #23 Review Triage

Review executed by a fresh-context subagent running the project `pr-review` skill (6 dimension agents). Comments are deleted after fixes land (ship-cycle Stage 6); this file is the surviving record. Triage standard: each finding judged against the code as it exists, not reviewer authority.

## Inventory

4 review artifacts: 1 PR-level dimension summary (requirements, id 4988428792), 3 inline findings. Security, Architecture, Regression, and Performance-positive checks reported no further findings (Security/Architecture/Regression: zero ≥confidence-bar findings each, with full second-pass coverage notes).

## Findings

| # | Source comment | Location | Finding | Verdict | Action | Rationale |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | inline 3592788450 (test coverage) | `backend/app/application/streaming.py:90` | `hold_back_deltas`' contract-violation branch (`if answer is None: raise AnswerGenerationFailed`) — a port stream ending without a terminal `AnswerCompleted` — has no test; all fakes always emit a completed event. | **Real** | **Fix** — add a fake-driven unit test (stream yields deltas then ends) asserting the raise. | Verified: branch exists at `streaming.py:90-92`; grep of `tests/test_application_qa.py` finds no test driving a completed-less stream. Strengthens the sensor over a defensive invariant the Verifier's mutations didn't target. |
| 2 | inline 3598527425 (performance) | `backend/app/infrastructure/web/questions.py:157` | `ask_question_stream`'s handler body — `AskQuestion.stream(...)` eager preflight (ownership/readiness queries + query embedding + hybrid retrieval) — executes on the event loop: FastAPI's SSE dispatch (`is_sse_stream` branch, `routing.py:512-514` in the locked 0.138.1) calls `gen = dependant.call(...)` directly, unlike the normal sync-endpoint `run_in_threadpool` path; only the returned generator is `iterate_in_threadpool`'d. Blocks every concurrent request while preflight runs. | **Real** (verified in installed FastAPI source) | **Fix** — run the preflight off the event loop while preserving the two proven contracts: pre-stream failures surface as plain HTTP (404/409/422/429) and the frame sequence/header stay byte-identical (existing integration tests are the safety net). | The claim's mechanism was independently confirmed against `fastapi/routing.py` in the locked version. Interactive streaming endpoints are Cycle D's primary surface; an event-loop stall per stream is a genuine scalability defect, not a nit. |
| 3 | inline 3598527537 (performance) | `backend/app/infrastructure/web/teaching.py:313` | Same mechanism for `post_teaching_turn_stream`, heavier prefix: `_preflight` runs 4 sequential DB queries + the embedding round-trip on the loop. | **Real** | **Fix** — same treatment as #2. | Same verification as #2. |
| 4a | PR-level 4988428792, note 1 (requirements) | `docs/adr/0020-use-anthropic-claude-for-generation.md:1` | H1 reads `ADR-020` but "the 4-digit convention" allegedly requires `ADR-0020`. | **False** | **Won't fix** | The repo convention is 4-digit filenames with 3-digit H1s: `docs/adr/0019-*.md` → `# ADR-019: …`, `0016-*.md` → `# ADR-016: …`. The new ADR matches its siblings exactly; "fixing" it would break the actual convention. |
| 4b | PR-level 4988428792, note 2 | judge thresholds | Judge thresholds are report-only (calibration-first), not yet gating. | **Real observation, by design** | **Won't fix (accepted design)** | Recorded decision AD-063: thresholds calibrate on first live baselines, then gate via `LEARNY_EVAL_GATE`. The reviewer itself marked this non-blocking-by-design. |
| 4c | PR-level 4988428792, note 3 | disconnect-before-first-token | True mid-stream client disconnect is not drivable via `TestClient`; verified one layer down. | **Real observation, accepted** | **Won't fix (layered coverage)** | Same conclusion as the independent Verifier: generator-close semantics are asserted at application and adapter layers (`finally` close + `with messages.stream` closure). No practical in-process test exists at the HTTP layer. |

## Totals

- Findings: 6 (3 inline + 3 notes inside the requirements summary)
- Real: 5 (of which 2 are accepted-by-design observations with no action)
- False: 1 (4a — misread convention)
- Fix: 3 (#1 test addition; #2/#3 SSE preflight off-loop)
- Won't fix: 3 (4a false; 4b/4c accepted design)

## Positive signals recorded by dimensions (no action)

Security: SSE endpoints at full auth/CSRF/origin/rate-limit parity; content-free logging; no key leakage; disconnect closes the paid provider stream. Architecture: SENTINEL/domain placement endorsed as least-coupled; single grounding enforcement point; protocol vocabulary confined to the presenter. Regression: `fastapi.sse` and Anthropic SDK usages verified real against locked deps; all deletions intentional; no weakened assertions. Test coverage: streaming state machine coverage called out as exemplary. One out-of-band note (Security, not posted): confirm `backend/.env.example` documents the new `LEARNY_GENERATION_*`/`LEARNY_ANTHROPIC_API_KEY` variables — folded into fix #2/#3's commit if the file exists and lacks them.
