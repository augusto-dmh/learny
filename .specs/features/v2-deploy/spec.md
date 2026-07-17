# v2-deploy Specification (RFC-002 Cycle G — deploy + presentation)

## Problem Statement

Learny's production-like compose stack exists but nothing ships it: no images are published, no deploy path exists, and TLS/reverse-proxy is explicitly deferred (docker-compose.prod.yml:7-9, TDD open question #10). Cycle G closes the loop: CI-built GHCR images, a green-CI-gated SSH deploy to a VPS, a Caddy TLS edge exposing only 80/443, nightly eval results persisted as JSONL, and the presentation finale (README, runbook, retrospective, v0.2.0 release).

## Goals

- [ ] Every merge to main with green CI automatically publishes versioned images and (when VPS secrets exist) deploys them.
- [ ] The production stack is reachable only through Caddy on 80/443 with persisted certs; all app/infra ports are internal.
- [ ] Nightly eval results survive as committed JSONL history, not just expiring artifacts.
- [ ] A newcomer can deploy Learny to any fresh VPS following docs/ops/deploy.md alone.
- [ ] README and docs present the finished v2 system (architecture, decisions, demo scaffolding, retrospective) at v0.2.0.

## Out of Scope

| Feature | Reason |
| --- | --- |
| Choosing/locking a specific VPS provider or domain registrar | RFC-002 sets size/cost envelope only; machinery stays provider-neutral (ADR-0008 spirit) |
| Recording the demo GIF and screenshots | Manual author artifacts needing real books + live keys + a browser; cycle ships the capture guide + asset slots (AD-096) |
| Monitoring/metrics stack, log shipping | AD-041 deferral stands; correlated structured logs remain the hook |
| Blue-green/zero-downtime deploys, k8s | Author-scale single VPS; compose pull && up -d is the accepted RFC-002 mechanism |
| Multi-arch image builds (arm64) | Target VPS is x86_64; add later if a VPS choice requires it |
| Staging environment | Single prod VPS per RFC-002 cost envelope |
| Creating the actual GitHub release | `gh release create v0.2.0 --generate-notes` runs at ship-cycle wrap after merge; this cycle ships the version bump + checklist |

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| GHCR packages visibility | Public (one-time manual flip after first push, documented in runbook) | Repo is Apache-2.0 OSS; lets the VPS pull without registry credentials or PAT lifecycle | auto (AD-090) |
| api needs public exposure through Caddy | No — Caddy proxies only web:3000 | ADR-0017: all browser traffic (incl. SSE) goes through the Next.js same-origin proxy | auto (AD-093) |
| "Results committed as JSONL" target | Dedicated `eval-results` branch, not main | Nightly bot commits would pollute main history/branch protection; branch keeps a clean queryable history | auto (AD-095) |
| Deploy directory on VPS | Fixed `/opt/learny` | One less secret/variable; documented in runbook | auto (AD-094) |
| Retrospective location | `docs/retrospectives/2026-07-learny-v2.md` | Durable docs live under docs/; matches docs/research convention | auto (AD-096) |
| worker-pdf ships to the VPS | Yes | 8 GB VPS sized for it (followup-vps-sizing); mem_limit 4g contains it | auto (AD-094) |

**Open questions:** none — all resolved or logged above.

## User Stories

### P1: GHCR image publishing ⭐ MVP

**User Story**: As the maintainer, I want CI to publish versioned images to GHCR on every green main build so that deploys pull immutable artifacts instead of building on the VPS.

**Acceptance Criteria**:

1. (DEP-01) WHEN the deploy workflow runs THEN it SHALL build and push exactly three images — `ghcr.io/augusto-dmh/learny-backend` (backend/Dockerfile target `runtime`), `ghcr.io/augusto-dmh/learny-pdf-worker` (target `pdf-worker`), `ghcr.io/augusto-dmh/learny-web` (frontend/Dockerfile target `prod`) — each tagged both `latest` and the commit SHA.
2. (DEP-02) WHEN CI completes on main with conclusion success THEN the deploy workflow SHALL trigger via `workflow_run`; WHEN CI fails or ran on a non-main branch THEN the workflow SHALL exit without building; `workflow_dispatch` SHALL be the only other trigger (no `push`/`pull_request`).
3. (DEP-03) WHEN images are pushed THEN auth SHALL use the job-scoped `GITHUB_TOKEN` with `packages: write` permission — no PAT secret.
4. (DEP-04) WHEN two deploy runs overlap THEN a workflow-level concurrency group SHALL queue them without cancelling an in-flight run (`cancel-in-progress: false`).

**Independent Test**: Workflow YAML asserts triggers/permissions/image matrix; post-merge, Actions run shows three pushed packages.

### P1: Caddy production edge ⭐ MVP

**User Story**: As the operator, I want the prod stack fronted by Caddy with automatic TLS so that only 80/443 are exposed and certs persist across restarts.

**Acceptance Criteria**:

1. (DEP-05) WHEN base+prod compose configs are merged THEN api, worker, worker-pdf, and web SHALL resolve to their GHCR image refs parameterized as `${LEARNY_IMAGE_TAG:-latest}`.
2. (DEP-06) WHEN base+prod configs are merged THEN the only host-published ports SHALL be 80 and 443, both on the `caddy` service.
3. (DEP-07) WHEN the prod overlay is used THEN a `caddy` service SHALL exist (prod overlay only) with named volumes `caddy_data` and `caddy_config` persisted, `deploy/Caddyfile` mounted read-only, `restart: unless-stopped`, and the site address driven by `{$LEARNY_DOMAIN}` reverse-proxying to `web:3000`.
4. (DEP-08) WHEN base+override (dev) configs are merged THEN today's dev ports (api 8000, web 3000, db 5432, redis 6379, minio 9000/9001) SHALL still be published and compose-smoke SHALL still pass — api/web port publishing moves from base to the override.
5. (DEP-09) WHEN the prod stack runs THEN api and web SHALL be reachable only on the internal compose network (no host ports in base or prod).

**Independent Test**: Compose topology tests (existing pattern) assert merged-config port sets, image refs, caddy volumes/mounts for prod, and unchanged dev topology.

### P1: SSH deploy job ⭐ MVP

**User Story**: As the maintainer, I want merges to main to deploy themselves over SSH so that shipping is `git merge`, nothing more.

**Acceptance Criteria**:

1. (DEP-10) WHEN all three image pushes succeed and VPS secrets are present THEN the deploy job SHALL copy `docker-compose.yml`, `docker-compose.prod.yml`, and `deploy/Caddyfile` to `/opt/learny` on the VPS and run `docker compose -f docker-compose.yml -f docker-compose.prod.yml pull` then `up -d --no-build --wait` with `LEARNY_IMAGE_TAG=<commit sha>`.
2. (DEP-11) WHEN any of the VPS secrets (`VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`) are absent THEN the deploy job SHALL exit green with an explanatory notice (eval.yml secret-gate precedent) while image builds still run.
3. (DEP-12) WHEN a deploy runs THEN it SHALL transfer no secret material — runtime env stays VPS-local (`secrets/*.env` + `/opt/learny/.env` holding `LEARNY_DOMAIN`); the deploy job writes only the image tag.
4. (DEP-13) WHEN `up -d --wait` reports an unhealthy service THEN the workflow run SHALL fail visibly.

**Independent Test**: Workflow YAML asserts job ordering (`needs` on all builds), secret gate, scp file set, remote command shape, and sha tag injection.

### P2: Eval results committed as JSONL

**User Story**: As the maintainer, I want nightly eval JSONL persisted in git so that quality history outlives 90-day artifact retention.

**Acceptance Criteria**:

1. (DEP-14) WHEN the nightly eval produces `evals/results/*.jsonl` THEN the workflow SHALL commit them to the dedicated `eval-results` branch (job-scoped `contents: write`), retaining the existing artifact upload.
2. (DEP-15) WHEN the API key secret is absent or no results were produced THEN the publish step SHALL skip green (fork-safe behavior unchanged).

**Independent Test**: eval.yml YAML asserts the publish step's branch, permission scope, and gating conditions.

### P2: Deploy runbook

**User Story**: As a future operator (or the author in six months), I want a single runbook that takes a fresh VPS to a running Learny.

**Acceptance Criteria**:

1. (DEP-16) WHEN following `docs/ops/deploy.md` THEN it SHALL cover, provider-neutrally: VPS prerequisites (x86_64, 8 GB, Docker Engine + compose plugin), DNS A record, `/opt/learny` layout, creating `secrets/*.env` + `.env` (`LEARNY_DOMAIN`), GitHub secrets to set, the one-time GHCR package-visibility flip, first deploy, verifying health, and rollback by re-dispatching with an older `LEARNY_IMAGE_TAG` (cross-linked with docs/ops/rollback.md, which gains the image-tag rollback path).

**Independent Test**: Runbook review against a checklist of those sections; rollback.md cross-link present.

### P2: Presentation finale (README, retrospective, v0.2.0)

**User Story**: As a visitor, I want the README and docs to present the finished v2 system so the project reads as shipped, not in-progress.

**Acceptance Criteria**:

1. (DEP-17) WHEN reading README THEN the deployment section SHALL document the GHCR→VPS pipeline and Caddy edge, and the Mermaid architecture diagram SHALL include the edge/deploy path.
2. (DEP-18) WHEN reading README THEN the decisions/tech-stack tables SHALL be current through ADR-0022 and the Roadmap section SHALL reflect v2 completion.
3. (DEP-19) WHEN preparing demo media THEN `docs/media/README.md` SHALL contain the <90s money-path capture script (upload → cited answer → quiz → review) and named asset slots; README SHALL contain a demo section referencing those slots without broken images.
4. (DEP-20) WHEN the cycle merges THEN versions SHALL read 0.2.0 in both `backend/pyproject.toml` and `frontend/package.json`, a retrospective SHALL exist at `docs/retrospectives/2026-07-learny-v2.md` covering cycles A–G, and the release checklist (tag v0.2.0, generated notes) SHALL be documented.

**Independent Test**: Version-consistency test (pyproject == package.json == 0.2.0); docs present with required sections.

## Edge Cases

- WHEN `workflow_dispatch` fires the deploy workflow on a non-main ref THEN build/deploy jobs SHALL be skipped by a ref guard.
- WHEN the VPS pull fails (e.g., package still private) THEN `--no-build` SHALL ensure the job fails rather than silently building stale images on the VPS.
- WHEN a deploy re-runs with the same SHA THEN `pull` + `up -d` SHALL be idempotent (no-op restart at most).
- WHEN Caddy restarts THEN previously issued certs SHALL be reused from `caddy_data` (no re-issuance storm).
- WHEN the eval publish step races a concurrent push to `eval-results` THEN the job SHALL rebase-retry or fail visibly — never force-push over history.

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| --- | --- | --- | --- |
| DEP-01..04 | P1: GHCR publishing | Design | Pending |
| DEP-05..09 | P1: Caddy edge | Design | Pending |
| DEP-10..13 | P1: SSH deploy | Design | Pending |
| DEP-14..15 | P2: Eval JSONL | Design | Pending |
| DEP-16 | P2: Runbook | Design | Pending |
| DEP-17..20 | P2: Presentation | Design | Pending |

**Coverage:** 20 total, 0 mapped to tasks (pending), 0 unmapped.

## Success Criteria

- [ ] Merge to main → three GHCR packages updated with sha+latest tags, deploy job green (gated or live).
- [ ] `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` shows only 80/443 published, images from GHCR.
- [ ] Dev workflow and CI compose-smoke unchanged.
- [ ] Backend suite + topology/workflow tests green; ruff clean; frontend suite green.
- [ ] README/runbook/retrospective land; versions read 0.2.0.
