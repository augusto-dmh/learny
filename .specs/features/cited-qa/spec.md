# Cited Q&A Specification (`cited-qa`, TDD Phase 7)

## Problem Statement

Processed sources can already return citation-ready evidence (Phase 6), but
users still cannot ask a question and get a grounded, cited answer. This cycle
adds the answer path: a Learny-owned answer-generation port, a default
deterministic adapter, an owner-scoped cited-answer endpoint with explicit
"not found in source" behavior, and the browser surface to ask and inspect
citations.

## Goals

- [ ] An authenticated owner can POST a question against a ready source and
      receive an answer whose every citation resolves to retrieved evidence.
- [ ] Questions the source cannot support return an explicit
      `not_found_in_source` result — never an uncited or fabricated answer.
- [ ] Answer generation runs behind a Learny-owned port; no provider SDK type,
      model name, or citation format crosses into application/domain code.
- [ ] A user can ask and inspect citations in the browser via the same-origin
      proxy.

## Out of Scope

| Feature | Reason |
|---|---|
| Cloud LLM provider adapter (OpenAI/Anthropic) | Needs its own ADR (CLAUDE.md, ADR-0007); deferred per D-1/AD-024 — follow-up flagged at merge gate |
| Answer persistence (`qa_answers`, `answer_citations`) | TDD-001 marks it optional; no MVP consumer (D-2/AD-025) |
| Teaching sessions, follow-up turns, conversation state | TDD Phase 8 |
| Long-context fallback routing | ADR-0001 fallback path; needs provider + its own design |
| Golden fixture evaluation harness | TDD Phase 9 |
| Streaming answers (SSE) | Deterministic adapter returns instantly; revisit with the provider ADR |
| Reranking / retrieval changes | Phase-6 layer is consumed as-is (ADR-0006) |
| `top_k` / retrieval knobs in the questions API | Server-side settings only (D-3) |

## Assumptions & Open Questions

All gray areas were auto-decided per the ship-cycle contract and recorded with
options + rationale in `context.md` (D-1..D-6, mirrored as AD-024..AD-029).

| Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|
| Default answer adapter | Deterministic, evidence-grounded local adapter; provider ADR follow-up | D-1: AD-019 precedent; no provider lock-in without ADR | auto (D-1) |
| Persistence | None this cycle | D-2: optional in TDD, no consumer | auto (D-2) |
| Not-found representation | 200 + `answer_status: "not_found_in_source"` | D-3: product outcome, not transport error | auto (D-3) |
| Grounding enforcement | Application service discards non-evidence citations; empty ⇒ not found | D-4: Learny invariant, adapter-independent | auto (D-4) |
| Frontend | Full slice (ask panel) per AD-010 | D-5: Phase 7 is the user surface AD-023 deferred to | auto (D-5) |
| Rate limit / bounds | Existing in-process limiter; `LEARNY_QA_QUESTION_MAX_CHARS=2000`, `LEARNY_QA_EVIDENCE_TOP_K=8` | D-6: TDD requires the hook; reuse over new infra | auto (D-6) |
| Question normalization | The **trimmed** question is validated (1..max chars) and used downstream | Single interpretation for bounds + matches retrieve's non-blank rule | auto |

**Open questions:** none — all resolved or logged above.

## User Stories

### P1-A: Ask a cited question ⭐ MVP

**User Story**: As a signed-in user, I want to ask a question against one of my
processed sources and get an answer with citations so that I can trust and
verify what the answer is based on.

**Why P1**: This is the phase outcome — the first user-facing grounded answer
path; everything else in the cycle serves it.

**Acceptance Criteria**:

1. (QA-01) WHEN an authenticated owner POSTs `{"question": q}` (trimmed q,
   1..`LEARNY_QA_QUESTION_MAX_CHARS` chars) to
   `POST /api/sources/{source_id}/questions` for a source with
   `status == "ready"` whose corpus yields ≥1 evidence item for `q` THEN the
   system SHALL respond 200 with `answer_status == "answered"` and non-empty
   `answer` text.
2. (QA-02) WHEN an answer is returned THEN each item in `citations` SHALL carry
   `chunk_id`, `source_id`, `section_path`, `anchor`, `page_span`, `snippet`
   (the Evidence anchor fields), and `citations` SHALL be non-empty and free of
   duplicate `chunk_id`s.
3. (QA-03) WHEN an answer is returned THEN every `citations[].chunk_id` SHALL
   be a member of the evidence set retrieved for this request (grounding).
4. (QA-04) WHEN a 200 response is returned (answered or not found) THEN it
   SHALL include `retrieval == {"strategy": "hybrid", "evidence_count": N}`
   where N is the number of evidence items retrieved, and `model` naming the
   generation adapter's model identity.
5. (QA-05) WHEN the application service invokes answer generation THEN it SHALL
   do so only through the Learny `AnswerGenerationPort`, passing the trimmed
   question and the retrieved `Evidence` list, and receive a Learny-owned
   result (answer text, cited chunk ids, model identity, found flag); no
   provider SDK/module import SHALL exist in `app/domain` or `app/application`.
6. (QA-06) WHEN the default deterministic adapter generates twice for the same
   question and evidence THEN it SHALL return identical results, composed only
   from the provided evidence (cited chunk ids ⊆ evidence chunk ids), with no
   network access.
7. (QA-07) WHEN the source id does not exist or belongs to another user THEN
   the system SHALL respond 404 with no existence disclosure (identical body
   for both cases).
8. (QA-08) WHEN the source exists and is owned but `status != "ready"` THEN the
   system SHALL respond 409 naming the not-ready state, and neither retrieval
   nor generation SHALL run.
9. (QA-09) WHEN `question` is missing, empty, or whitespace-only THEN the
   system SHALL respond 422 before retrieval or generation runs.
10. (QA-10) WHEN the trimmed `question` exceeds `LEARNY_QA_QUESTION_MAX_CHARS`
    THEN the system SHALL respond 422 before retrieval or generation runs.
11. (QA-11) WHEN the request lacks a valid session THEN 401; WHEN the CSRF
    token or Origin check fails THEN 403 — matching the existing
    state-changing endpoints.
12. (QA-12) WHEN a question completes (answered or not found) THEN the system
    SHALL emit one structured log event carrying `source_id`, outcome,
    `evidence_count`, and model identity — and never the question or answer
    text.

**Independent Test**: Register, upload + ingest a fixture EPUB, POST a question
whose words appear in the book, and assert 200 answered with citations whose
chunk ids exist in the corpus.

---

### P1-B: Explicit "not found in source" ⭐ MVP

**User Story**: As a signed-in user, I want Learny to tell me plainly when my
source does not answer my question so that I never receive fabricated or
uncited answers.

**Why P1**: ADR-0003 makes citation integrity a core requirement; TDD-001
security list requires the explicit not-found response.

**Acceptance Criteria**:

1. (QA-13) WHEN retrieval returns zero evidence THEN the system SHALL respond
   200 with `answer_status == "not_found_in_source"`, empty `citations`, and
   the `AnswerGenerationPort` SHALL NOT be invoked.
2. (QA-14) WHEN the generation port returns found == false THEN the system
   SHALL respond 200 `not_found_in_source` with empty `citations`.
3. (QA-15) WHEN the generation result cites chunk ids outside the retrieved
   evidence set THEN those citations SHALL be discarded; WHEN no valid
   citations remain THEN the response SHALL be `not_found_in_source`.
4. (QA-16) WHEN the generation result has found == true but empty/whitespace
   answer text THEN the response SHALL be `not_found_in_source`.
5. (QA-17) WHEN the generation port raises THEN the system SHALL respond 502
   with a generic error body (no provider/internal detail), and the request
   SHALL leave no persistent state behind.

**Independent Test**: Ask a nonsense-token question against a ready fixture
source and assert 200 `not_found_in_source` with `citations == []`.

---

### P1-C: Ask and inspect citations in the browser ⭐ MVP

**User Story**: As a signed-in user, I want an Ask panel for my ready sources
so that I can ask questions and inspect the cited passages without tooling.

**Why P1**: AD-010 full-slice cadence (restored after AD-023's deliberate
deferral); the phase outcome is explicitly user-facing.

**Acceptance Criteria**:

1. (QA-18) WHEN the owner opens the ask view for a ready source, submits a
   question, and the API answers THEN the answer text SHALL render together
   with each citation's section path and snippet.
2. (QA-19) WHEN the API returns `not_found_in_source` THEN the UI SHALL render
   an explicit "not found in this source" message and no citation list.
3. (QA-20) WHEN the API returns 401/404/409/422/429/502 THEN the UI SHALL
   render a readable error message for that state (not a raw failure), and the
   form SHALL remain usable.
4. (QA-21) WHEN the browser asks a question THEN the request SHALL go through
   the same-origin Next.js proxy with credentials and the CSRF header,
   matching the existing sources/ingestion clients.

**Independent Test**: With a ready source, type a question in the ask panel and
see the answer with citations; type nonsense and see the not-found message.

---

### P2-D: Abuse protection on questions

**User Story**: As the operator, I want the questions endpoint throttled so
that a single client cannot flood retrieval/generation.

**Why P2**: TDD-001 requires rate-limit hooks on Q&A "even if initial
thresholds are conservative"; not required to demo the feature.

**Acceptance Criteria**:

1. (QA-22) WHEN a client exceeds the questions rate limit within the window
   THEN the system SHALL respond 429 with a `Retry-After` header, via the
   existing swappable limiter keyed by client IP + route.

**Independent Test**: Hammer the endpoint past the window limit in a test and
assert 429 + `Retry-After`.

---

## Edge Cases

- WHEN the trimmed question is exactly `LEARNY_QA_QUESTION_MAX_CHARS` chars
  THEN it SHALL be accepted (bound is inclusive).
- WHEN a ready source has a corpus with zero chunks THEN retrieval yields no
  evidence and the response is `not_found_in_source` (QA-13 path).
- WHEN the adapter cites the same chunk id more than once THEN citations SHALL
  be deduplicated to one entry per chunk (QA-02).
- WHEN fewer evidence items exist than `LEARNY_QA_EVIDENCE_TOP_K` THEN the
  service SHALL proceed with what was retrieved (no padding, no error).

## Implicit-Requirement Dimensions (sweep)

| Dimension | Resolution |
|---|---|
| Input validation & bounds | QA-09/QA-10 + edge cases; question trimmed, 1..max chars |
| Failure / partial-failure | QA-17 (502, generic body); stateless so nothing to roll back |
| Idempotency / retry / duplicates | N/A because the endpoint is stateless (D-2) — retries are safe by construction; citation dedup covered by QA-02 |
| Auth boundaries & rate limits | QA-07/QA-11 (auth, CSRF, 404 collapse), QA-22 (throttle) |
| Concurrency / ordering | N/A because requests share no mutable state (stateless reads + pure generation) |
| Data lifecycle / expiry | N/A because nothing is persisted this cycle (D-2/AD-025) |
| Observability | QA-12 (structured lifecycle log, content-free) |
| External-dependency failure | QA-17 (port failure contract); deterministic default adapter is dependency-free (QA-06) |
| State-transition integrity | QA-08 (readiness guard); no transitions are written |

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
|---|---|---|---|
| QA-01..QA-12 | P1-A: Ask a cited question | Done | Verified |
| QA-13..QA-17 | P1-B: Not found in source | Done | Verified |
| QA-18..QA-21 | P1-C: Browser ask panel | Done | Verified |
| QA-22 | P2-D: Abuse protection | Done | Verified |

**Coverage:** 22 total, 22 mapped to tasks (A1..D2), 0 unmapped. Verifier: 22/22 matched spec outcome (`validation.md`).

## Success Criteria

- [ ] A fixture-book question returns an answer whose every citation resolves
      to a real corpus chunk of that source (demoable end-to-end in the browser).
- [ ] A nonsense question returns an explicit not-found result — zero uncited
      answers in the test suite.
- [ ] `grep` finds no provider SDK import in `app/domain` or `app/application`.
- [ ] All backend/frontend gates pass (pytest, vitest, ruff, tsc).
