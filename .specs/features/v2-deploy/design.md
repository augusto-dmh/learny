# v2-deploy Design

**Spec**: `.specs/features/v2-deploy/spec.md`
**Status**: Approved (auto-approved under ship-cycle autonomy; decisions locked in context.md D-1..D-7 / AD-090..096)

## Architecture Overview

Approach chosen (vs. alternatives recorded in context.md): a **separate `deploy.yml` workflow gated on CI via `workflow_run`**, publishing three GHCR images then scp+ssh-driving the existing compose triad on the VPS, with **Caddy added only to the prod overlay** as the single public surface.

```mermaid
graph LR
    subgraph GitHub
        CI[CI workflow<br/>4 jobs] -->|workflow_run success @ main| D[deploy.yml]
        D --> B1[build learny-backend<br/>target runtime]
        D --> B2[build learny-pdf-worker<br/>target pdf-worker]
        D --> B3[build learny-web<br/>target prod]
        B1 & B2 & B3 --> GHCR[(ghcr.io<br/>:sha + :latest)]
        B1 & B2 & B3 --> DEP[deploy job<br/>secret-gated]
    end
    DEP -->|scp compose+Caddyfile<br/>ssh pull && up -d --no-build --wait| VPS
    subgraph VPS [/opt/learny on VPS/]
        Caddy[caddy :80/:443<br/>caddy_data certs] --> Web[web:3000<br/>Next proxy]
        Web --> Api[api:8000]
        Api --> Infra[(db/redis/minio)]
        W[worker + worker-pdf] --> Infra
    end
    GHCR -.->|pull public images| VPS
```

## Code Reuse Analysis

| Component | Location | How to Use |
| --- | --- | --- |
| Secret-gate pattern (absent secret → green notice) | `.github/workflows/eval.yml:41` | Copy for the deploy job's VPS-secret gate |
| Compose triad + prod hardening conventions | `docker-compose{,.override,.prod}.yml` (AD-042) | Extend prod overlay; move api/web ports to override exactly like infra ports |
| Topology test pattern (pure YAML/text, `_deep_merge`, repo-root paths) | `backend/tests/test_compose_topology.py`, `test_compose_prod.py` | New `test_deploy_topology.py` + `test_deploy_workflow.py` follow it; update `test_compose_prod.py` where prod assertions change |
| CI action version conventions | `.github/workflows/ci.yml` | Mirror `actions/checkout` version already in use; new docker actions at current majors (`docker/login-action@v3`, `docker/setup-buildx-action@v3`, `docker/build-push-action@v6`) — never invent versions (Cycle A lesson: phantom action versions) |
| Ops runbook style (provider-neutral, presence/content-tested) | `docs/ops/backups.md`, `rollback.md` (AD-043) | `deploy.md` matches; rollback.md gains the image-tag path |

### Integration Points

| System | Integration Method |
| --- | --- |
| CI workflow | `workflow_run` trigger on name `CI`, `types: [completed]`; guard `conclusion == 'success' && head_branch == 'main'`; checkout `github.event.workflow_run.head_sha` so the exact CI-validated commit is built |
| GHCR | `docker/login-action` with `github.actor`/`GITHUB_TOKEN`; job `permissions: packages: write, contents: read` |
| VPS | scp file set + ssh remote compose commands; `StrictHostKeyChecking=accept-new`; key from `VPS_SSH_KEY` written 0600 |
| Compose interpolation | `LEARNY_IMAGE_TAG` env inline on the remote command (shell env beats `.env`); `LEARNY_DOMAIN` from VPS-local `/opt/learny/.env` with `:?` guard on the caddy service |

## Components

### deploy.yml (`.github/workflows/deploy.yml`)

- **Triggers**: `workflow_run` (CI, completed) + `workflow_dispatch`; nothing else.
- **Workflow-level**: `concurrency: {group: deploy, cancel-in-progress: false}`; guard expression shared by jobs: dispatch-on-main OR run-success-on-main. `DEPLOY_SHA = github.event.workflow_run.head_sha || github.sha`.
- **`build` job (matrix, 3 entries)**: `{name: learny-backend, context: backend, target: runtime}`, `{name: learny-pdf-worker, context: backend, target: pdf-worker}`, `{name: learny-web, context: frontend, target: prod}`. Steps: checkout @ DEPLOY_SHA → setup-buildx → ghcr login → build-push with `tags: ghcr.io/augusto-dmh/<name>:latest, :<DEPLOY_SHA>`, gha cache scoped per image (`scope: <name>`; accept eviction for the large pdf-worker image).
- **`deploy` job**: `needs: build`. Step 1 secret gate (env-mapped `VPS_HOST`/`VPS_USER`/`VPS_SSH_KEY` → `present` output; absent → `::notice` + green stop). Step 2 checkout @ DEPLOY_SHA (for the compose files). Step 3 write key, scp `docker-compose.yml docker-compose.prod.yml deploy/Caddyfile` → `/opt/learny/` (Caddyfile to `/opt/learny/deploy/Caddyfile`). Step 4 ssh: `cd /opt/learny && LEARNY_IMAGE_TAG=<sha> docker compose -f docker-compose.yml -f docker-compose.prod.yml pull && LEARNY_IMAGE_TAG=<sha> docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-build --wait`.

### Compose changes

- **base**: delete `ports:` from `api` and `web` (nothing else changes).
- **override (dev)**: add `api: ports ["8000:8000"]`, `web: ports ["3000:3000"]` — dev-visible topology identical to today.
- **prod overlay**: `image:` on api+worker (`learny-backend`), worker-pdf (`learny-pdf-worker`), web (`learny-web`), all `ghcr.io/augusto-dmh/...:${LEARNY_IMAGE_TAG:-latest}`; new `caddy` service — pinned `caddy:2.10-alpine`-line image, `ports: ["80:80", "443:443", "443:443/udp"]`, `restart: unless-stopped`, `environment: LEARNY_DOMAIN: ${LEARNY_DOMAIN:?LEARNY_DOMAIN must be set}`, mounts `./deploy/Caddyfile:/etc/caddy/Caddyfile:ro`, volumes `caddy_data:/data`, `caddy_config:/config`, `depends_on: [web]`; top-level volumes gain `caddy_data`, `caddy_config`.

### deploy/Caddyfile

```
{$LEARNY_DOMAIN} {
    encode zstd gzip
    reverse_proxy web:3000
}
```

Single upstream by ADR-0017/AD-093. Agent discretion: minimal hardening headers allowed, no api route.

### eval.yml publish step

Job gains `permissions: {contents: write}` (job-level). New step after the artifact upload, `if: key present`: skip green when `evals/results/*.jsonl` empty; else configure bot identity, `git fetch origin eval-results` and `git switch` (or `git switch --orphan`), copy results into `results/<utc-date>-<run_id>/`, commit, push; on rejected push, fetch+rebase and retry once, then fail visibly. Never force-push.

### Docs & presentation

- `docs/ops/deploy.md` — sections per DEP-16 (prereqs, DNS, /opt/learny layout, secrets/*.env + .env, GitHub secrets table, GHCR visibility flip, first deploy, health verification, rollback cross-link).
- `docs/ops/rollback.md` — new image-tag rollback path (re-dispatch with older `LEARNY_IMAGE_TAG`).
- `docs/media/README.md` — <90s money-path capture script + named slots (`docs/media/demo.gif`, `screenshot-{library,ask,review}.png`).
- `README.md` — deployment section (GHCR→VPS+Caddy), Mermaid diagram gains edge/deploy path, decisions/roadmap currency, demo section referencing slots (no broken embeds).
- `docs/adr/0023-ghcr-ssh-deploy-caddy-edge.md` — records the deploy architecture (resolves TDD open question #10's TLS/reverse-proxy part; backup/monitoring stay as-is per AD-041/AD-043).
- `docs/retrospectives/2026-07-learny-v2.md` — cycles A–G retrospective.
- Version 0.2.0 in `backend/pyproject.toml` + `frontend/package.json`.

### Tests (all pure text/YAML, no Docker)

- `backend/tests/test_deploy_topology.py` — DEP-05..09: base has no host ports anywhere; override carries all dev ports; prod caddy shape (image pin, 80/443(+udp) only published ports in merged base+prod, volumes, Caddyfile mount, `LEARNY_DOMAIN` guard); ghcr image refs with `${LEARNY_IMAGE_TAG:-latest}`; Caddyfile proxies only `web:3000`.
- `backend/tests/test_deploy_workflow.py` — DEP-01..04, DEP-10..13: trigger set, guards, permissions, matrix (names/contexts/targets), sha+latest tags, concurrency, `needs`, secret gate, scp file set, remote command (`pull`, `up -d --no-build --wait`, sha injection).
- eval publish assertions appended in the same file or `test_eval_workflow.py` — DEP-14..15: job permission, branch name, gating, no `--force`.
- `backend/tests/test_versions.py` — pyproject == package.json == `0.2.0` (DEP-20).
- `test_compose_prod.py` / `test_compose_topology.py` — updated where prod/base assertions legitimately change (port relocation, image keys); never weakened otherwise.

## Error Handling Strategy

| Error Scenario | Handling | Operator sees |
| --- | --- | --- |
| CI fails / non-main | deploy.yml guard skips all jobs | No deploy run noise |
| VPS secrets absent | Gate step exits green + `::notice` | Green run, "deploy skipped" notice |
| Image pull fails on VPS (e.g. package private) | `--no-build` → command fails | Red run pointing at pull |
| Unhealthy service after up | `--wait` non-zero | Red run; VPS keeps previous containers where healthy |
| Concurrent deploys | queued via concurrency group | Sequential runs |
| eval-results push race | rebase retry once, else fail | Red nightly run, no history rewrite |
| Let's Encrypt unreachable | Caddy retries; existing certs from `caddy_data` keep serving | Transient log noise only |

## Risks & Concerns

| Concern | Location | Impact | Mitigation |
| --- | --- | --- | --- |
| `runtime` image installs `--extra dev` (dev deps in prod image) | `backend/Dockerfile:45` | Fatter prod image; not a new regression (prod compose already built this target) | Keep as-is this cycle; flagged as follow-up in ADR-0023 notes — changing extras risks breaking in-container tooling assumptions |
| Compose `ports` merge cannot remove | base compose | "only 80/443" impossible via overlay alone | Base goes portless; dev ports live in override (AD-093) — topology test pins base portlessness |
| pdf-worker image is multi-GB (baked models) — gha cache eviction, slow builds | `backend/Dockerfile:33` | Slower deploy runs after cache eviction | Per-image cache scope; accept rebuild cost; noted in ADR |
| Existing prod topology tests assert current shape | `test_compose_prod.py` | Phase A breaks them | Update assertions in the same phase, deliberately, spec-anchored |
| `workflow_run` name coupling | ci.yml `name: CI` | Renaming CI silently detaches deploys | Workflow test asserts deploy.yml references workflow name `CI` |
| First GHCR push is private | GHCR default | First VPS pull fails | Runbook one-time visibility step; failure mode is a visible red pull |

## Tech Decisions (feature-local; project-level ones are AD-090..096)

| Decision | Choice | Rationale |
| --- | --- | --- |
| Host key trust | `StrictHostKeyChecking=accept-new` | TOFU acceptable at author scale; avoids a known_hosts secret; noted in runbook |
| HTTP/3 | publish `443/udp` | Caddy serves QUIC by default; free win |
| Build checkout ref | `workflow_run.head_sha` | Build exactly the CI-validated commit |
| eval-results layout | `results/<utc-date>-<run_id>/*.jsonl` | Collision-free, chronologically sortable |
| Caddy image pin | minor-pinned alpine tag | Matches redis/minio pinning style (AD-042) |
