# v2-foundation — Tasks

Branch: `feat/v2-foundation`. One atomic commit per task. Gate per task noted; cycle gates = backend pytest + ruff, frontend vitest + tsc + build.

## Phase A — Land artifacts

- [x] **A1** Commit README.md (root) — `docs(readme): introduce the project readme` — gate: file present, relative links resolve. (FND-01)
- [x] **A2** Commit QA runbook + report — `docs(ops): add the end-to-end qa runbook and first qa report` — gate: files present. (FND-01)
- [x] **A3** Commit research + RFC-002 — `docs(planning): record the v2 research evidence and accepted roadmap rfc` — gate: 13 research files + RFC present, RFC status Accepted. (FND-01)
- [x] **A4** Commit compose F1 fix + regression test in `backend/tests/test_compose_prod.py` — `fix(compose): give the worker the object-storage endpoint configuration` — gate: new test fails on pre-fix compose (assert by reverting in-memory), passes now; backend suite green. (FND-02)

## Phase B — Defect fixes

- [x] **B1** F2: classify `BotoCoreError`/`ClientError` across `_ensure_bucket`/`get_object`/`put_object` → `StorageUnavailable` (keep `ObjectNotFound`); tests with fake client raising `EndpointConnectionError` per path — `fix(storage): classify unreachable object storage as retryable` — gate: new tests + existing storage/worker tests green. (FND-03..06)
- [x] **B2** F3: strip `expect` + hop-by-hop request headers in `buildProxyRequest`; strip `content-encoding`/`content-length` in `relayResponse`; vitest cases incl. preserved cookie/csrf/set-cookie — `fix(proxy): drop hop-by-hop headers the upstream fetch cannot forward` — gate: frontend vitest + tsc green. (FND-07..10)
- [x] **B3** F4: reproduce (drop/create fresh test DB + full pytest), diagnose in `backend/tests/conftest.py`, fix root cause, document mechanism in context.md D-5 + STATE AD-049 — `fix(tests): make the suite deterministic on a freshly created database` — gate: scripted fresh-DB full-suite run passes on first attempt, twice in a row. (FND-11..12)

## Phase C — CI + hygiene + docs refresh

- [x] **C1** `.github/workflows/ci.yml` (4 jobs per design; Learny env names; `/healthz`) — `ci: add the github actions pipeline` — gate: YAML parses; each job's commands pass locally (pytest already green from B3 gate; ruff; vitest+tsc+build; compose build + healthz poll). (FND-13..15)
- [x] **C2** LICENSE (Apache-2.0) + license fields in `backend/pyproject.toml` / `frontend/package.json` — `chore(license): adopt the apache-2.0 license` — gate: full text present; pyproject still valid (`uv lock --check` or pytest collect), package.json valid. (FND-16)
- [x] **C3** SECURITY.md + CONTRIBUTING.md + `.github/dependabot.yml` — `docs(community): add security policy and contribution guide` — gate: files present; dependabot YAML parses. (FND-17)
- [x] **C4** Refresh CLAUDE.md Current Status/direction; add v2 table to `.specs/project/ROADMAP.md`; STATE.md AD-045..AD-050 + Handoff — `docs(planning): align project docs with the shipped mvp and v2 roadmap` — gate: no stale "no scaffold" claims (grep); ROADMAP has v2 rows. (FND-18..19)

## Verifier

After C4: fresh Verifier sub-agent (spec-anchored outcome check + discrimination sensor) → `validation.md`.
