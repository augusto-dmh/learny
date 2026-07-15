# v2 Foundation Specification

## Problem Statement

The MVP is complete and QA'd end-to-end, but the repository carries uncommitted planning/QA artifacts, three verified defects from the 2026-07-12 QA run (F2 storage-retry, F3 proxy header, F4 first-run test flake), no CI, no license, and a stale `CLAUDE.md` that still claims no runtime scaffold exists. RFC-002 (Accepted) defines Cycle A as the foundation everything in v2 builds on: land the artifacts, fix the known defects, and put CI + OSS hygiene in place before any provider or feature work.

## Goals

- [ ] Land the QA/research/RFC artifacts and the compose worker-storage fix (F1) on `main` via this cycle's PR.
- [ ] Storage faults from an unreachable object store classify as retryable (`StorageUnavailable`) across the whole S3 adapter surface (F2).
- [ ] The Next.js proxy survives non-browser clients (`Expect` header) and future response compression (F3).
- [ ] The backend test suite passes on its **first** run against a freshly created database (F4) — the property CI depends on.
- [ ] GitHub Actions CI gates every PR: backend tests (pgvector+redis services), ruff, frontend tests+build, compose build smoke.
- [ ] The repo reads as maintained OSS: Apache-2.0 LICENSE, SECURITY.md, CONTRIBUTING.md, Dependabot security updates.
- [ ] `CLAUDE.md` and `.specs/project/ROADMAP.md` reflect reality (MVP shipped; v2 driven by RFC-002).

## Out of Scope

| Feature | Reason |
| ------- | ------ |
| Anything from RFC-002 cycles B–G (providers, embeddings, frontend styling, quizzes, PDF, deploy) | Each is its own cycle; this cycle is the foundation only. |
| `v0.1.0` tag | Applied to the merge commit on `main` after Stage 7, not inside the PR. |
| Issue templates, CODE_OF_CONDUCT, changelog automation | Deliberately skipped per oss-maturity-ci research (solo-maintainer noise). |
| CI deploy/publish jobs (GHCR images, VPS) | RFC-002 Cycle G. |
| Fixing the QA report's F5–F8 findings | F5 (relevance refusal) = Cycle C; F6 (UI) = Cycle D; F7 (EPUB structure) = Cycle F; F8 (FTS language) = Cycle B. |

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --------------------- | -------------- | --------- | ---------- |
| Roadmap driver for v2 | RFC-002 replaces TDD-001 as the roadmap source; ROADMAP.md gains a v2 cycle table | TDD-001's 10 phases are all Done; RFC-002 is Accepted by the user | y (AD-045) |
| Already-authored artifacts (README, QA docs, research, RFC) land as-is | Commit unmodified as the cycle's opening docs commits | They were produced and user-approved this session; re-editing them inside tlc re-litigates approved content | y (AD-046) |
| CI design | Per `docs/research/2026-07-12/oss-maturity-ci.md` sketch, adapted to Learny env names (`LEARNY_TEST_DATABASE_URL`) and endpoints (`/healthz`) | Research verified current actions/pitfalls against official docs on 2026-07-12 | y (AD-047) |
| License | Apache-2.0 | Patent grant + enterprise-readable + relicensable later; research-adjudicated | y (AD-048) |
| F4 fix approach | Diagnose first; fix root cause, not symptoms; record as AD-049 once known | Root cause is unconfirmed (SQLAlchemy inactive-transaction on first DB test, fresh DB + full suite only) | y (AD-049 pending diagnosis) |
| Slice shape | Docs/infra/fix cycle, no frontend product feature — deliberate departure from AD-010 | Precedent AD-023/AD-039/AD-044; foundation work has no user-facing surface | y (AD-050) |
| CI proof | Local gates prove each job's commands; the workflow's first live run happens on the PR itself | GitHub-hosted execution cannot be run locally; the PR run is the acceptance evidence | y |

**Open questions:** none.

## User Stories

### P1: Land the approved artifacts ⭐

**User Story**: As the maintainer, I want the QA/research/RFC artifacts and the F1 compose fix committed so that `main` records what was learned and decided.

**Acceptance Criteria**:

1. **FND-01** WHEN the cycle branch is inspected THEN `README.md`, `docs/ops/e2e-qa.md`, `docs/ops/e2e-qa-report-2026-07-12.md`, `docs/research/2026-07-12/` (13 files), and `docs/rfc/0002-learny-v2-roadmap.md` SHALL be committed with RFC-002 status `Accepted`.
2. **FND-02** WHEN the base compose file is parsed THEN the `worker` service SHALL define `LEARNY_STORAGE_ENDPOINT`, `LEARNY_STORAGE_BUCKET`, and `LEARNY_STORAGE_REGION` (F1), and a test SHALL assert this so the regression cannot silently return.

### P2: Retryable storage faults (F2)

**User Story**: As the operator, I want transient object-storage outages to retry with backoff instead of terminally failing ingestion jobs.

**Acceptance Criteria**:

1. **FND-03** WHEN `get_object` is called while the storage endpoint is unreachable (a `BotoCoreError` such as `EndpointConnectionError`, raised from bucket ensure or the get itself) THEN the adapter SHALL raise `StorageUnavailable`.
2. **FND-04** WHEN `put_object` encounters a `BotoCoreError` or non-not-found `ClientError` (from bucket ensure or the put itself) THEN the adapter SHALL raise `StorageUnavailable`.
3. **FND-05** WHEN `get_object` receives a not-found `ClientError` THEN it SHALL still raise `ObjectNotFound` (existing semantics preserved).
4. **FND-06** WHEN the ingestion task encounters `StorageUnavailable` THEN it SHALL retry with backoff (existing behavior — regression-guarded by existing tests remaining green).

### P3: Proxy header hygiene (F3)

**User Story**: As an API client (curl, scripts), I want multipart uploads through the proxy to reach FastAPI instead of dying in undici.

**Acceptance Criteria**:

1. **FND-07** WHEN an incoming request carries `Expect: 100-continue` (any casing) THEN the proxied upstream request SHALL NOT include an `Expect` header.
2. **FND-08** WHEN an incoming request carries hop-by-hop headers (`connection`, `keep-alive`, `transfer-encoding`, `upgrade`, `te`, `trailer`, `proxy-authorization`, `proxy-authenticate`) THEN none of them SHALL be forwarded upstream.
3. **FND-09** WHEN the upstream response carries `content-encoding` or `content-length` THEN the relayed response SHALL NOT include those headers (undici has already decompressed the body).
4. **FND-10** WHEN a request carries `cookie`, `x-csrf-token`, and `content-type` THEN those SHALL still be forwarded, and `set-cookie` SHALL still be relayed verbatim (existing behavior preserved).

### P4: First-run test determinism (F4)

**User Story**: As CI, I want the full backend suite green on the first run against a fresh database, because every CI run is a first run.

**Acceptance Criteria**:

1. **FND-11** WHEN the root cause is identified THEN it SHALL be recorded (context.md + AD-049) with the failing mechanism named — not just a symptomatic retry/ordering workaround.
2. **FND-12** WHEN the full suite runs against a freshly created database (`DROP DATABASE; CREATE DATABASE; pytest tests/`) THEN it SHALL pass on the first run (verified locally as the gate; CI service containers re-verify on every PR).

### P5: CI pipeline

**User Story**: As the maintainer, I want every PR gated by the same checks I run locally.

**Acceptance Criteria**:

1. **FND-13** WHEN `.github/workflows/ci.yml` is inspected THEN it SHALL define 4 jobs — `backend-test` (services: `pgvector/pgvector:pg16` with `pg_isready` healthcheck + `redis:7-alpine` with ping healthcheck; steps: setup-uv with cache, `uv sync --locked`, pytest with `LEARNY_TEST_DATABASE_URL` pointing at the service), `lint` (ruff check only — format enforcement deliberately excluded: 38 files are not ruff-format-clean and reformatting is out of this cycle's scope), `frontend` (npm ci with cache, vitest run, tsc, next build), `compose-smoke` (buildx bake with GHA cache, compose up, `/healthz` poll, teardown) — with a `concurrency` group cancelling in-progress runs.
2. **FND-14** WHEN the workflow file is parsed THEN it SHALL be valid YAML and reference only env var names the codebase actually reads (`LEARNY_*`).
3. **FND-15** WHEN each job's commands are executed locally (pytest, ruff, vitest+tsc+build, compose build+healthz) THEN each SHALL pass — the local equivalence gate for what CI will run.

### P6: OSS hygiene + docs refresh

**User Story**: As a repo visitor (or future contributor), I want license, security, and contribution basics present and the project docs truthful.

**Acceptance Criteria**:

1. **FND-16** WHEN the repo root is listed THEN `LICENSE` SHALL contain the full Apache-2.0 text, and `backend/pyproject.toml` + `frontend/package.json` SHALL declare `Apache-2.0`.
2. **FND-17** WHEN `.github/` is listed THEN `SECURITY.md` (private vulnerability reporting) — root or `.github/` — `CONTRIBUTING.md` (setup, tests, conventional commits, ≤1 page), and `dependabot.yml` (pip + npm + github-actions, security updates only) SHALL exist.
3. **FND-18** WHEN `CLAUDE.md` is read THEN the Current Status section SHALL describe the shipped MVP and RFC-002-driven v2 (no "research artifacts only / no runtime scaffold" claims), and constraints/directions SHALL not contradict RFC-002's accepted decisions.
4. **FND-19** WHEN `.specs/project/ROADMAP.md` is read THEN it SHALL contain a v2 section mapping RFC-002 cycles A–G to tlc cycles with status, marking `v2-foundation` in progress.
