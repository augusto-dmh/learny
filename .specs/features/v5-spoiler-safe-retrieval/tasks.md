# Spoiler-Safe Retrieval Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and report back — do not proceed without it.**

---

**Design**: `.specs/features/v5-spoiler-safe-retrieval/design.md`
**Context / ADs**: `.specs/features/v5-spoiler-safe-retrieval/context.md`, STATE.md AD-346..AD-349
**Spec**: `.specs/features/v5-spoiler-safe-retrieval/spec.md` (SPOILER-01..15)
**Status**: T1, T2, T3 done (all phases complete).

---

## Test Coverage Matrix

> Generated from the seam survey + repo conventions. Backend-only cycle: no frontend change.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| --- | --- | --- | --- | --- |
| SQL adapter (hybrid statements, all variants) | db-gated integration (`requires_db`) | 1:1 to SPOILER-01/02/03/04/12/14/15 at the SQL layer: section-granularity boundary, every statement variant's book arms, note arms bound-free, `None`-bound parity, stale-anchor fail-closed + warning, scores stable | `backend/tests/test_retrieval.py`, `backend/tests/test_retrieval_notes.py` | `cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test uv run pytest tests/test_retrieval.py tests/test_retrieval_notes.py -q` |
| Retrieval service | unit (fakes) | SPOILER-05/06/13: flag reads own position, absent → `None`, flag false never touches the repo, anchor propagates to the port | `backend/tests/test_application_retrieval.py` | `cd backend && uv run pytest tests/test_application_retrieval.py -q` |
| Web endpoint + conversation turns | integration (fakes) | SPOILER-07/08/09/10: endpoint bound, scoped-teach AND-intersection, empty intersection honest turn, opening-turn bound | existing conversation + `/retrieve` endpoint test modules | `cd backend && uv run pytest tests/ -q -k "conversation or retrieve" ` |
| Fakes | correctness of doubles | Fakes reproduce section-order semantics incl. fail-closed (exercised via the suites above) | `backend/tests/fakes.py` | via the suites above |

**Baselines (must grow, never shrink):** backend 2890 passed / 12 skipped; frontend 902 passed (untouched).

## Gate Check Commands

| Level | Command (from repo root) |
| --- | --- |
| Quick (adapter) | `cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test uv run pytest tests/test_retrieval.py tests/test_retrieval_notes.py -q` && `cd backend && uv run ruff check app tests` |
| Quick (service) | `cd backend && uv run pytest tests/test_application_retrieval.py -q` && `cd backend && uv run ruff check app tests` |
| Build (phase boundary / last task) | `make lint` && `cd backend && LEARNY_TEST_DATABASE_URL=postgresql+psycopg://learny:learny@localhost:5432/learny_test uv run pytest -q` |

**Environment facts (verified this session):** the db must be up first —
`docker.exe compose -f docker-compose.yml -f docker-compose.override.yml up -d db minio redis`
(both `-f` flags required; plain `docker` is not on PATH in this WSL distro). Without the DSN,
db-gated tests silently skip — a green run with skips where SQL tests should run is NOT a pass.

---

## Phase 1 — The bound at the retrieval seam (port + SQL adapter)

### T1: Position bound in `RetrievalPort` + hybrid SQL, all variants, fail-closed warning

**Done when**: `RetrievalPort.search` accepts `not_past_anchor: str | None = None` (appended
last, contract documented on the protocol); `SqlAlchemyRetrievalRepository.search` enforces the
section-order bound (AD-347) inside the shared `scoped` CTE of **every statement variant's book
arms**, composes with the `anchors` filter (AND, SPOILER-07), leaves note arms and all knobs
untouched (SPOILER-11/12), keeps admissible scores/order semantics unchanged (SPOILER-04), and
logs a warning naming source + anchor when a supplied bound matches no section of the source
(book arms empty, notes unaffected — SPOILER-14/15). Db-gated tests derive from the spec ACs —
including the PDF-source parity case (SPOILER-03, same section-order predicate) and the
boundary cases from the spec's Edge Cases list (first/last/single-section).

**Files**: `backend/app/domain/ports.py`, `backend/app/infrastructure/db/retrieval.py`,
`backend/tests/test_retrieval.py`, `backend/tests/test_retrieval_notes.py`
**Tests**: db-gated integration per the coverage matrix
**Gate**: Quick (adapter)
**Depends on**: nothing

---

## Phase 2 — Service resolution, call sites, honest fakes

### T2: `RetrieveEvidence` resolves the position; fakes mirror the semantics

**Done when**: `RetrieveEvidence.__call__` accepts `respect_reading_position: bool = False`;
when true it reads the calling user's own position row for the source via the injected
`ReadingPositionRepository` and passes the canonical anchor down (missing row → `None`,
SPOILER-05/06); when false the repository is never touched (SPOILER-13 — prove with a
spy/recording fake); composition root wires the dependency; `FakeRetrieveEvidence` /
`FakeRetrievalPort` reproduce the section-order semantics (incl. fail-closed) so upper-layer
tests exercise the real contract. Service tests derive from the spec ACs.

**Files**: `backend/app/application/retrieval.py`, `backend/app/infrastructure/web/dependencies.py`, `backend/tests/fakes.py`, `backend/tests/test_application_retrieval.py`
**Tests**: unit (fakes) per the coverage matrix
**Gate**: Quick (service)
**Depends on**: T1

### T3: Wire ask turns, teach turns, and the citation endpoint to the bound

**Done when**: `PostConversationTurn._retrieve_evidence` (both buffered and streaming paths, and
the teach-opening turn — they share this seam) and the `POST /api/sources/{source_id}/retrieve`
handler request position-respecting retrieval (SPOILER-01/09/10); scoped teach composes with the
bound (SPOILER-07) and an empty intersection takes the existing zero-evidence turn outcome with
no bypass (SPOILER-08 — **verify and report the actual observed behavior** of that path; no new
envelope/status code); every other caller unchanged. Conversation- and endpoint-level tests
derive from the spec ACs.

**Files**: `backend/app/application/conversations.py`, `backend/app/infrastructure/web/retrieval.py`, plus the conversation/endpoint test modules they exercise
**Tests**: integration (fakes) per the coverage matrix
**Gate**: Build (phase boundary — full backend suite with DSN + `make lint`)
**Depends on**: T2

---

## Execution Plan

Sequential: T1 → T2 → T3 → Verifier (fresh sub-agent, always runs after T3). One atomic commit
per task; conventional commits; no AI attribution; no internal IDs (SPOILER/AD/T-numbers) in
commit messages — code docstrings may cite the SPOILER ACs per repo convention.

## Parallelism Assessment

Backend-only; tasks are strictly sequential by dependency (adapter → service → call sites).
No frontend work; no migrations; no worker changes.
