# v3-ops-maturity Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: activate it by name and follow its Execute flow and Critical Rules. If the skill cannot be activated, STOP.

**Design**: `.specs/features/v3-ops-maturity/design.md`
**Status**: Approved (auto, ship-cycle)

## Test Coverage Matrix

> Guidelines found: `CLAUDE.md` (golden fixtures / citations-as-core), house infra-test pattern in `backend/tests/test_compose_*.py`, `test_deploy_*.py`, `test_ops_docs.py` (pure YAML/text asserts, no Docker at test time), CI as the executable gate for container behavior.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
|---|---|---|---|---|
| Compose topology (backup, monitoring, volumes, ports) | unit (yaml-merge asserts) | 1:1 to OPS-01, OPS-13, OPS-14 + edge invariants (no non-loopback ports beyond caddy) | `backend/tests/test_backup_stack.py`, edits to `test_deploy_topology.py`, `test_compose_prod.py` | `uv run pytest tests/test_backup_stack.py tests/test_deploy_topology.py tests/test_compose_prod.py -q` |
| Backup image + scripts (safety-critical flags) | unit (text asserts) | pin: flock, `-Fc`, tmp+rename, `--clean --if-exists`, `--yes` guard, `offsite not configured`, KEEP_DAYS prune guard, heartbeat-on-success | `backend/tests/test_backup_stack.py` | same |
| Backup/restore behavior end-to-end | CI integration | seed→backup→drop→restore→assert roundtrip + local-only notice (OPS-10) | `.github/workflows/ci.yml` compose-smoke steps (asserted textually in `test_backup_stack.py`) | CI |
| Workflows (deploy matrix 4th image) | unit (yaml asserts) | matrix `{name:(context,target)}` includes learny-backup | edit `backend/tests/test_deploy_workflow.py` | `uv run pytest tests/test_deploy_workflow.py -q` |
| Dockerfile runtime/pdf-worker stages | unit (text asserts) | runtime has no `--extra dev`, has USER; pdf-worker unchanged contract | edit `backend/tests/test_compose_topology.py` | `uv run pytest tests/test_compose_topology.py -q` |
| Ops docs (backups.md automation, monitoring.md, deploy.md secrets list) | unit (text asserts) | key strings per OPS-12/15/11 | edit `backend/tests/test_ops_docs.py` | `uv run pytest tests/test_ops_docs.py -q` |
| ADR-0024 | none | build gate only | — | — |

## Parallelism Assessment

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
|---|---|---|---|
| all backend pytest | No (run sequentially, single process) | shared repo-file reads only, but suite runs without xdist | CI runs `uv run pytest -q` single-process |

## Gate Check Commands

(cwd `backend/`, uv at `/home/augusto/myenv/bin/uv`; docker CLI in this WSL is `docker.exe`)

| Gate Level | When to Use | Command |
|---|---|---|
| Quick | per task | `uv run pytest <touched test files> -q` |
| Compose-valid | after any compose/Dockerfile task | `docker.exe compose -f ../docker-compose.yml -f ../docker-compose.prod.yml config -q` and base+override `config -q` |
| Full (phase boundary) | end of each phase | `uv run pytest -q` + `uv run ruff check` |

## Execution Plan (5 phases, sequential; one worker each — all Opus per ship-cycle cost rules)

Phase A: T1 → T2 → T3 → T4   (backup engine)
Phase B: T5 → T6              (CI proof + docs)
Phase C: T7 → T8              (monitoring)
Phase D: T9 → T10             (image hygiene)
Phase E: T11                  (ADR)

## Task Breakdown

### T1: Backup image + scripts (`deploy/backup/`)
**What**: Dockerfile (alpine pinned + postgresql16-client + pinned `mc` + curl) with `entrypoint.sh`, `backup.sh`, `restore.sh`, `backup-now` per design contracts (flock, tmp+rename, offsite gating, prune-with-newest-exemption, heartbeat-last, `--yes` guard).
**Where**: `deploy/backup/*`
**Depends on**: None  **Requirement**: OPS-03..09
**Done when**: files exist honoring every contract; every third-party tag verified against its registry (record how in the commit body is NOT needed — verify, then pin).
**Tests**: text asserts land in T4 (same phase; scripts+tests co-committed per task granularity below is acceptable as T1 ships scripts, T4 ships the suite asserting them — the phase gate runs both).
**Gate**: quick (T4 file once present) · **Commit**: `feat(backup): add scheduled backup and restore tooling image`

### T2: Compose wiring (prod overlay + dev override profile)
**What**: prod `backup` service + `backup_data` volume per OPS-01; override `backup` service under `profiles: ["backup"]` with dev creds + build context.
**Where**: `docker-compose.prod.yml`, `docker-compose.override.yml`
**Depends on**: T1  **Requirement**: OPS-01
**Done when**: both merges pass `docker.exe compose ... config -q`.
**Tests**: covered by T4 suite. **Gate**: compose-valid · **Commit**: `feat(backup): wire the backup service into compose`

### T3: Deploy matrix + secrets example
**What**: 4th matrix entry (`learny-backup`, context `./deploy/backup`, no target) in deploy.yml; `backend/.env.production.example` gains the backup section; `secrets/backup.env` documented (creation only — deploy.md text lands in T6).
**Where**: `.github/workflows/deploy.yml`, `backend/.env.production.example`
**Depends on**: T1  **Requirement**: OPS-02, OPS-11(part)
**Done when**: matrix test (updated in T4) green; example lists every `LEARNY_BACKUP_*` var with comments.
**Tests**: T4 + `test_deploy_workflow.py` edit. **Gate**: quick · **Commit**: `feat(deploy): publish the backup image and document its secrets`

### T4: Backup test suite
**What**: `backend/tests/test_backup_stack.py` (topology per OPS-01, script-safety text asserts per matrix row 2, deploy-matrix helper reuse) + `test_deploy_workflow.py` matrix update.
**Where**: `backend/tests/`
**Depends on**: T1–T3  **Requirement**: OPS-01..09 (test anchor)
**Done when**: suite green; phase gate full pass.
**Tests**: is the tests. **Gate**: full · **Commit**: `test(backup): pin the backup stack topology and script safety contracts`

### T5: CI restore roundtrip
**What**: compose-smoke extension per design (seed→backup-now with `offsite not configured` assert→drop→`restore --latest --yes`→assert) + text asserts on the new steps in `test_backup_stack.py`.
**Where**: `.github/workflows/ci.yml`, `backend/tests/test_backup_stack.py`
**Depends on**: T4  **Requirement**: OPS-10
**Done when**: step sequence asserted; YAML valid; (CI executes it on the PR).
**Tests**: unit + CI. **Gate**: quick · **Commit**: `test(backup): prove the backup and restore roundtrip in ci`

### T6: Backups + deploy docs
**What**: rewrite `docs/ops/backups.md` automation sections (schedule/retention/offsite/heartbeat/restore drill via shipped scripts; drop "deliberately not fixed here"); `docs/ops/deploy.md` secrets list + backup.env; `test_ops_docs.py` assertions.
**Where**: `docs/ops/`, `backend/tests/test_ops_docs.py`
**Depends on**: T5  **Requirement**: OPS-11, OPS-12
**Done when**: doc strings asserted; full phase gate green.
**Tests**: unit. **Gate**: full · **Commit**: `docs(ops): document the automated backup pipeline`

### T7: Monitoring service
**What**: netdata service in prod overlay per design (pinned verified tag, loopback-only port, ro mounts, mem limit, volumes).
**Where**: `docker-compose.prod.yml`
**Depends on**: None (within phase C)  **Requirement**: OPS-13, OPS-14(part)
**Done when**: prod merge `config -q` passes; tag verified against Docker Hub.
**Tests**: T8. **Gate**: compose-valid · **Commit**: `feat(monitoring): add a loopback-only netdata service to the prod stack`

### T8: Monitoring tests + runbook
**What**: topology asserts (mounts, loopback-only, caddy-only-non-loopback tightening in `test_deploy_topology.py`) + `docs/ops/monitoring.md` (tunnel access, key panels, backup-log inspection, alert hooks) + `test_ops_docs.py` asserts.
**Where**: `backend/tests/`, `docs/ops/monitoring.md`
**Depends on**: T7  **Requirement**: OPS-14, OPS-15
**Done when**: suite green; full phase gate green.
**Tests**: unit. **Gate**: full · **Commit**: `feat(monitoring): document tunnel access and pin the exposure contract`

### T9: Runtime image slimming
**What**: import audit (`docling` reachability from api/worker startup — guard/lazy-import if needed), runtime stage drops `--extra dev` (both uv sync lines), non-root USER; `test_compose_topology.py` asserts no `--extra dev` in runtime stage + USER present.
**Where**: `backend/Dockerfile`, `backend/app/**` (only if audit requires a guard), `backend/tests/test_compose_topology.py`
**Depends on**: None (within phase D)  **Requirement**: OPS-16, OPS-17
**Done when**: audit outcome stated in commit body; tests green; compose-valid gate passes (CI compose-smoke will boot it).
**Tests**: unit + CI. **Gate**: full · **Commit**: `feat(images): ship the runtime image without dev dependencies as a non-root user`

### T10: pdf-worker torch investigation
**What**: bounded per design — inspect uv.lock torch wheels; attempt CPU-only pin if clean; else write evidence notes (sizes, conflict) for T11.
**Where**: `backend/pyproject.toml`+`uv.lock` (only if clean) or notes for ADR
**Depends on**: T9  **Requirement**: OPS-18
**Done when**: either lock updated + full suite green, or evidence recorded for the ADR (no commit if documentation-only — evidence goes into T11's ADR).
**Tests**: full suite if lock changes. **Gate**: full · **Commit** (only if lock changes): `chore(images): pin cpu-only torch wheels for the pdf worker`

### T11: ADR-0024
**What**: `docs/adr/0024-*.md` recording backup+monitoring stack (D-1..D-4, D-7), retention/offsite neutrality, tunnel-only access, closing the backup/monitoring half of TDD OQ #10, and the OPS-18 outcome with evidence.
**Where**: `docs/adr/`
**Depends on**: T10  **Requirement**: OPS-19
**Done when**: ADR complete, statuses/links correct; full gate green.
**Tests**: none. **Gate**: build (ruff + full suite unchanged) · **Commit**: `docs(adr): record the backup and monitoring stack decision`

## Diagram-Definition Cross-Check

| Task | Depends On (body) | Diagram | Status |
|---|---|---|---|
| T1 | none | phase A head | ✅ |
| T2 | T1 | A: T1→T2 | ✅ |
| T3 | T1 | A: T2→T3 (sequential order within phase; dependency satisfied) | ✅ |
| T4 | T1–T3 | A tail | ✅ |
| T5 | T4 | B head | ✅ |
| T6 | T5 | B tail | ✅ |
| T7 | — | C head | ✅ |
| T8 | T7 | C tail | ✅ |
| T9 | — | D head | ✅ |
| T10 | T9 | D tail | ✅ |
| T11 | T10 | E | ✅ |

## Test Co-location Validation

| Task | Layer | Matrix Requires | Task Says | Status |
|---|---|---|---|---|
| T1–T3 | scripts/compose/workflow | unit (text/yaml) | suite lands in T4, same phase, phase gate runs it | ✅ (phase-cohesive; no phase ends untested) |
| T4 | tests | — | is the suite | ✅ |
| T5 | workflow | unit + CI | unit + CI | ✅ |
| T6 | docs | unit (ops-docs) | unit | ✅ |
| T7 | compose | unit | suite lands in T8, same phase | ✅ |
| T8 | tests+docs | unit | unit | ✅ |
| T9 | Dockerfile | unit + CI boot | unit + CI | ✅ |
| T10 | lockfile | full suite | full suite | ✅ |
| T11 | ADR | none | none | ✅ |
