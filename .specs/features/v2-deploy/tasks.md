# v2-deploy Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. If the skill cannot be activated, STOP.

**Design**: `.specs/features/v2-deploy/design.md`
**Status**: Done — all 12 tasks A1–E3 shipped; Verifier PASS (20/20 ACs, 4/4 mutants killed). See `validation.md`.

**Phase A pinned caddy image**: `caddy:2.10-alpine`. No existing test needed port-relocation updates (base never asserted app ports); new coverage in `test_deploy_topology.py`.

---

## Test Coverage Matrix

> Guidelines found: `CLAUDE.md` (citations/eval are core; golden-fixture philosophy), `CONTRIBUTING.md`, existing config-artifact test precedent (`backend/tests/test_compose_topology.py`, `test_compose_prod.py` — this repo tests infra config as YAML/text, overriding the "config → none" default).

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| --- | --- | --- | --- | --- |
| Compose files + Caddyfile (deploy topology) | unit (pure YAML/text) | 1:1 to DEP-05..09 + port/volume edge cases | `backend/tests/test_deploy_topology.py` (+ updates to `test_compose_prod.py`, `test_compose_topology.py`) | `cd backend && uv run pytest tests/test_deploy_topology.py tests/test_compose_prod.py tests/test_compose_topology.py` |
| GitHub workflow files | unit (pure YAML) | 1:1 to DEP-01..04, 10..15 + trigger/guard edge cases | `backend/tests/test_deploy_workflow.py`, `tests/test_eval_workflow.py` | `cd backend && uv run pytest tests/test_deploy_workflow.py tests/test_eval_workflow.py` |
| Version metadata | unit | pyproject == package.json == 0.2.0 | `backend/tests/test_versions.py` | `cd backend && uv run pytest tests/test_versions.py` |
| Docs (runbook, ADR, README, retrospective, media guide) | none | content review at PR review stage | — | build gate only |

## Parallelism Assessment

| Test Type | Parallel-Safe? | Isolation Model | Evidence |
| --- | --- | --- | --- |
| unit (YAML/text parsing) | Yes | Read-only file parsing, no shared state | `test_compose_topology.py` — pure `yaml.safe_load`, no fixtures/DB |

(Execution is sequential per phase anyway — `[P]` marks order-freedom only.)

## Gate Check Commands

> `uv` lives at `/home/augusto/myenv/bin/uv` (not on default PATH). Backend baseline before this cycle: **941 passed, 11 skipped** locally; counts only grow.

| Gate Level | When to Use | Command |
| --- | --- | --- |
| Quick | After each task | `cd backend && uv run pytest tests/test_deploy_topology.py tests/test_deploy_workflow.py tests/test_eval_workflow.py tests/test_compose_prod.py tests/test_compose_topology.py tests/test_versions.py --ignore-glob='*missing*' -q` (subset that exists at that point) |
| Full backend | Phase boundary | `cd backend && uv run pytest -q` + `uv run ruff check` |
| Frontend | Phase D boundary only (package.json touched) | `cd frontend && npm test -- --run && npx tsc --noEmit` |

---

## Execution Plan

```
Phase A (compose edge)   : A1 → A2 → A3
Phase B (deploy workflow): B1 → B2          (needs A: scp file set + image refs exist)
Phase C (eval publish)   : C1               (independent; runs after B for clean sequencing)
Phase D (ops docs+version): D1 [P] → D2 [P] → D3   (facts from A–C)
Phase E (presentation)   : E1 → E2 → E3     (facts from A–D)
```

5 phases → one sub-agent worker per phase, sequential (ship-cycle mode; precedent cycles C–F). Models per ship-cycle cost discipline: **A, B, C, E = Opus** (topology/CI correctness invariants; ADR/README carry architecture judgment), **D = Haiku** (doc chores + fully-specified version bump; slips caught by quick gate + Verifier).

## Task Breakdown

### A1: Move app host ports from base compose to the dev override

**What**: Delete `ports:` from `api` and `web` in `docker-compose.yml`; add `8000:8000` (api) and `3000:3000` (web) to `docker-compose.override.yml`. Start `backend/tests/test_deploy_topology.py`: base file publishes zero host ports on every service; override carries exactly today's dev port set. Update any existing topology/prod test that asserted base ports.
**Where**: `docker-compose.yml`, `docker-compose.override.yml`, `backend/tests/test_deploy_topology.py`, existing compose tests
**Depends on**: None · **Requirement**: DEP-08, DEP-09 · **Reuses**: `test_compose_topology.py` `_load`/`_deep_merge` pattern
**Done when**: base portless; merged base+override port set unchanged vs. today (8000, 3000, 5432, 6379, 9000, 9001); quick gate passes; no test weakened (only relocated assertions).
**Tests**: unit · **Gate**: quick
**Commit**: `refactor(compose): move app host ports into the dev override`

### A2: Prod overlay consumes GHCR images

**What**: Add `image: ghcr.io/augusto-dmh/learny-backend:${LEARNY_IMAGE_TAG:-latest}` to `api`+`worker`, `learny-pdf-worker:...` to `worker-pdf`, `learny-web:...` to `web` in `docker-compose.prod.yml`. Tests: exact refs incl. the `${LEARNY_IMAGE_TAG:-latest}` interpolation; base services keep `build:`.
**Where**: `docker-compose.prod.yml`, `backend/tests/test_deploy_topology.py`
**Depends on**: A1 · **Requirement**: DEP-05 · **Reuses**: AD-042 overlay conventions
**Done when**: all four app services carry the ghcr ref in prod; quick gate passes.
**Tests**: unit · **Gate**: quick
**Commit**: `feat(deploy): consume ghcr images in the prod overlay`

### A3: Caddy TLS edge in the prod overlay

**What**: Add `caddy` service to `docker-compose.prod.yml` (pinned caddy alpine image, ports `80:80`/`443:443`/`443:443/udp`, `restart: unless-stopped`, `LEARNY_DOMAIN` env with `:?` guard, `./deploy/Caddyfile:/etc/caddy/Caddyfile:ro`, `caddy_data:/data`, `caddy_config:/config`, `depends_on: [web]`); add top-level volumes; create `deploy/Caddyfile` (`{$LEARNY_DOMAIN}`, `encode`, `reverse_proxy web:3000`). Tests: merged base+prod publishes ports only on caddy and only 80/443(+udp); volumes persisted; Caddyfile proxies only `web:3000` and contains no api upstream; caddy absent from base/override.
**Where**: `docker-compose.prod.yml`, `deploy/Caddyfile`, `backend/tests/test_deploy_topology.py`
**Depends on**: A2 · **Requirement**: DEP-06, DEP-07 · **Reuses**: AD-042 pinning style
**Done when**: assertions above green; full backend + ruff green at phase boundary (941+ passed).
**Tests**: unit · **Gate**: full backend (phase boundary)
**Commit**: `feat(deploy): add the caddy tls edge to the prod overlay`

### B1: deploy.yml — GHCR build/push pipeline

**What**: Create `.github/workflows/deploy.yml`: triggers `workflow_run` (workflow `CI`, `types: [completed]`) + `workflow_dispatch`, nothing else; guard `conclusion == 'success' && head_branch == 'main'` (dispatch: ref must be main); `concurrency {group: deploy, cancel-in-progress: false}`; 3-entry build matrix (learny-backend/runtime/backend, learny-pdf-worker/pdf-worker/backend, learny-web/prod/frontend) with checkout @ `workflow_run.head_sha || github.sha`, buildx, ghcr login via `GITHUB_TOKEN`, build-push tagging `:latest` + `:<sha>`, per-image gha cache scope; job permissions `packages: write, contents: read`. Real action versions only (mirror ci.yml's checkout; docker actions at current majors). New `backend/tests/test_deploy_workflow.py` asserting all of the above from YAML.
**Where**: `.github/workflows/deploy.yml`, `backend/tests/test_deploy_workflow.py`
**Depends on**: A3 · **Requirement**: DEP-01..04 · **Reuses**: ci.yml conventions
**Done when**: trigger set exact (no push/pull_request); matrix names/targets/contexts/tags exact; concurrency non-cancelling; quick gate passes.
**Tests**: unit · **Gate**: quick
**Commit**: `feat(ci): build and publish images to ghcr after green ci`

### B2: deploy.yml — SSH deploy job

**What**: Add `deploy` job: `needs` all builds; eval.yml-style secret gate on `VPS_HOST`/`VPS_USER`/`VPS_SSH_KEY` (absent → `::notice` + green exit); checkout @ same sha; write key 0600; scp `docker-compose.yml docker-compose.prod.yml deploy/Caddyfile` → `/opt/learny` (Caddyfile under `deploy/`); ssh remote: `cd /opt/learny && LEARNY_IMAGE_TAG=<sha> docker compose -f docker-compose.yml -f docker-compose.prod.yml pull && ... up -d --no-build --wait`; `StrictHostKeyChecking=accept-new`. Tests: needs-ordering, gate shape, scp file set, remote command contains `pull`, `up -d --no-build --wait`, sha injection, no secret material in scp list.
**Where**: `.github/workflows/deploy.yml`, `backend/tests/test_deploy_workflow.py`
**Depends on**: B1 · **Requirement**: DEP-10..13 · **Reuses**: eval.yml:41 secret gate
**Done when**: assertions green; full backend + ruff green at phase boundary.
**Tests**: unit · **Gate**: full backend (phase boundary)
**Commit**: `feat(ci): deploy to the vps over ssh after image publish`

### C1: eval.yml — persist nightly results to the eval-results branch

**What**: Give `generation-eval` job `permissions: {contents: write}`; add publish step after artifact upload, gated on key presence AND produced `evals/results/*.jsonl` (else green skip): bot git identity, fetch/switch (or `--orphan`) `eval-results`, copy results to `results/<utc-date>-<run_id>/`, commit, push with one rebase retry, never `--force`. New `backend/tests/test_eval_workflow.py`: permission scope, branch name, gating conditions, retry-not-force. Existing artifact upload untouched.
**Where**: `.github/workflows/eval.yml`, `backend/tests/test_eval_workflow.py`
**Depends on**: B2 (sequencing only) · **Requirement**: DEP-14, DEP-15
**Done when**: assertions green; fork-safety (absent key → green) preserved; full backend + ruff green.
**Tests**: unit · **Gate**: full backend (phase boundary)
**Commit**: `feat(ci): persist nightly eval results to a dedicated branch`

### D1: VPS deploy runbook [P]

**What**: `docs/ops/deploy.md` covering, provider-neutrally: prerequisites (x86_64 VPS 8 GB, Docker Engine + compose plugin), DNS A record, `/opt/learny` layout, creating `secrets/{db,minio,api,worker}.env` + `.env` (`LEARNY_DOMAIN`), GitHub secrets table (`VPS_HOST`/`VPS_USER`/`VPS_SSH_KEY`), one-time GHCR package-visibility flip, first deploy (dispatch), health verification, rollback via older `LEARNY_IMAGE_TAG` (cross-link rollback.md). Update `docs/ops/rollback.md` with the image-tag rollback path.
**Where**: `docs/ops/deploy.md`, `docs/ops/rollback.md`
**Depends on**: C1 · **Requirement**: DEP-16 · **Reuses**: backups.md/rollback.md style (AD-043)
**Done when**: every DEP-16 section present; commands match deploy.yml/compose exactly (no drift).
**Tests**: none · **Gate**: build (ruff no-op; docs only)
**Commit**: `docs(ops): add the vps deploy runbook`

### D2: Demo media capture guide [P]

**What**: `docs/media/README.md`: <90s money-path script (upload → cited answer → quiz → review) with per-scene timing, tool suggestions, and named asset slots (`docs/media/demo.gif`, `docs/media/screenshot-library.png`, `-ask.png`, `-review.png`). No binaries committed.
**Where**: `docs/media/README.md`
**Depends on**: C1 · **Requirement**: DEP-19 (guide half)
**Done when**: script + slots present; referenced names match what E2 will embed.
**Tests**: none · **Gate**: build
**Commit**: `docs(media): add the demo capture guide`

### D3: Version bump to 0.2.0 + consistency test

**What**: `backend/pyproject.toml` and `frontend/package.json` → `0.2.0`; new `backend/tests/test_versions.py` asserting both files agree and equal `0.2.0` (parse TOML + JSON).
**Where**: `backend/pyproject.toml`, `frontend/package.json`, `backend/tests/test_versions.py`
**Depends on**: D1, D2 · **Requirement**: DEP-20 (version half)
**Done when**: version test green; full backend + ruff green; frontend gate green (`npm test -- --run`, `tsc --noEmit`).
**Tests**: unit · **Gate**: full backend + frontend (phase boundary)
**Commit**: `chore(release): bump the project version to 0.2.0`

### E1: ADR-0023 — GHCR images, SSH deploy, Caddy edge

**What**: `docs/adr/0023-ghcr-ssh-deploy-caddy-edge.md`: context (TDD OQ #10 TLS/proxy part, RFC-002 Cycle G), decision (3 GHCR images sha+latest, workflow_run gating, scp+ssh compose deploy, Caddy sole public surface via web:3000, secret-gated bootstrap), consequences (incl. dev-deps-in-runtime-image follow-up, pdf-worker image size note). Status Accepted.
**Where**: `docs/adr/0023-ghcr-ssh-deploy-caddy-edge.md`
**Depends on**: D3 · **Requirement**: DEP-17 (decision record grounding) · **Reuses**: ADR house style (0020/0022)
**Done when**: ADR complete and consistent with shipped artifacts.
**Tests**: none · **Gate**: build
**Commit**: `docs(adr): record the ghcr, ssh deploy, and caddy edge decision`

### E2: README finale

**What**: README: new/updated deployment section (GHCR→VPS pipeline, Caddy edge, link to deploy.md); Mermaid architecture diagram gains the edge/deploy path; decisions + tech-stack tables current through ADR-0023; Roadmap section reflects v2 completion; demo section referencing `docs/media/` slots without broken embeds.
**Where**: `README.md`
**Depends on**: E1 · **Requirement**: DEP-17, DEP-18, DEP-19 (README half)
**Done when**: sections present; Mermaid renders (no syntax errors — `npx -y @mermaid-js/mermaid-cli` not required, reviewer-checked); no dead relative links.
**Tests**: none · **Gate**: build
**Commit**: `docs(readme): present the deployed v2 system`

### E3: v2 retrospective

**What**: `docs/retrospectives/2026-07-learny-v2.md`: cycles A–G narrative (what shipped, verifier/review stats where recorded in STATE.md, what worked — spec-driven cycles, deterministic-first adapters; what to change), forward look (post-v2 candidates from RFC-002 out-of-scope list). Plus the release checklist (tag `v0.2.0`, `gh release create --generate-notes` post-merge).
**Where**: `docs/retrospectives/2026-07-learny-v2.md`
**Depends on**: E2 · **Requirement**: DEP-20 (retrospective half)
**Done when**: A–G each covered; checklist present; full backend + ruff final pass green.
**Tests**: none · **Gate**: full backend (final)
**Commit**: `docs(retrospectives): add the v2 retrospective`

---

## Diagram-Definition Cross-Check

| Task | Depends On (body) | Diagram | Status |
| --- | --- | --- | --- |
| A1 | None | phase start | ✅ |
| A2 | A1 | A1→A2 | ✅ |
| A3 | A2 | A2→A3 | ✅ |
| B1 | A3 | A→B | ✅ |
| B2 | B1 | B1→B2 | ✅ |
| C1 | B2 (sequencing) | B→C | ✅ |
| D1 | C1 | C→D, [P] with D2 | ✅ |
| D2 | C1 | C→D, [P] with D1 | ✅ |
| D3 | D1, D2 | D1,D2→D3 | ✅ |
| E1 | D3 | D→E | ✅ |
| E2 | E1 | E1→E2 | ✅ |
| E3 | E2 | E2→E3 | ✅ |

## Test Co-location Validation

| Task | Layer | Matrix Requires | Task Says | Status |
| --- | --- | --- | --- | --- |
| A1–A3 | compose/Caddyfile topology | unit | unit | ✅ |
| B1–B2 | workflow files | unit | unit | ✅ |
| C1 | workflow files | unit | unit | ✅ |
| D1, D2 | docs | none | none | ✅ |
| D3 | version metadata | unit | unit | ✅ |
| E1–E3 | docs | none | none | ✅ |

## Task Granularity Check

All tasks touch 1–3 cohesive files with one deliverable each — ✅ (A3 is the largest: one service + one config file + its tests, cohesive as "the edge").
