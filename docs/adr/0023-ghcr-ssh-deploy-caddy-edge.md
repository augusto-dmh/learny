# ADR-023: GHCR Images, SSH Deploy, And A Caddy TLS Edge

- **Date**: 2026-07-17
- **Status**: Accepted
- **Deciders**: Augusto, Claude
- **Tags**: architecture, deployment, ci, ghcr, ssh, caddy, tls, operations

## Context and Problem Statement

Learny ships a production-like Docker Compose stack (ADR-0008, hardened as a
base/override/prod overlay triad in the production-readiness cycle), but nothing
shipped it: no images were published, no deploy path existed, and TLS plus a
reverse proxy were explicitly deferred (TDD open question #10). Every prior cycle
built the runtime; none delivered it to a running host.

RFC-002 Cycle G closes that loop. The stack now includes six-plus services — API,
Celery worker, an isolated PDF worker (ADR-0022), the Next.js web app, PostgreSQL,
Redis, and MinIO — and needs a repeatable, credential-light way to build, publish,
and roll those services onto a single VPS with automatic HTTPS, without exposing
any application or infrastructure port directly to the internet.

The decisions to make are: what image set to publish and where; how a deploy is
triggered and gated so only validated commits reach the VPS; how the production
compose files consume published images while local development still builds from
source; what the public network edge looks like now that browser traffic (including
SSE) already flows through the Next.js same-origin proxy (ADR-0017); how the deploy
transport reaches the VPS without turning it into a second source-of-truth that can
drift; and how nightly evaluation results outlive artifact retention.

This ADR resolves the TLS / reverse-proxy portion of TDD open question #10. The
backup and monitoring/metrics portions remain deferred by prior decision
(observability defers a metrics scrape endpoint; ops runbooks document backup and
restore rather than automating them).

## Decision Drivers

- Every green build of `main` should publish immutable, versioned artifacts and
  (when a VPS exists) deploy them, so shipping is `git merge` and nothing more.
- The VPS should pull images without registry credentials or a personal access
  token lifecycle — the repository is Apache-2.0 open source.
- Only 80 and 443 should be reachable from the internet; API and infrastructure
  ports stay on the internal compose network.
- Deploys should be reproducible and rollback should be a one-variable operation.
- The deploy pipeline should run green before any VPS exists, so the pipeline can
  merge and be validated ahead of provisioning (the secret-gate precedent set by
  the nightly evaluation workflow).
- The VPS should stay a dumb host: no git checkout to maintain, no secret material
  transferred by CI, no chance of silently building stale images locally.
- Nightly evaluation JSONL should survive as diffable git history without polluting
  `main`.
- Keep local development and CI compose-smoke unchanged; the production overlay adds
  the edge, it does not fork the topology (the base/override/prod triad is the
  deliberate design and must be preserved).

## Considered Options

### Image set, naming, and registry visibility

- **Three GHCR images (`learny-backend` shared by api+worker, `learny-pdf-worker`,
  `learny-web`), public.** ✅ Chosen.
- Four images, splitting `api` and `worker` into separate refs.
- `learny-api` naming for the shared backend image.
- Private GHCR packages pulled with a PAT stored on the VPS.

### Deploy workflow shape and gating

- **A separate `deploy.yml` gated on green CI via `workflow_run` (+ ref-guarded
  `workflow_dispatch`).** ✅ Chosen.
- Extending `ci.yml` with build and deploy jobs.
- A `push: main` trigger on a standalone deploy workflow.

### Deploy transport to the VPS

- **scp the compose files + Caddyfile to a fixed `/opt/learny`, then ssh
  `docker compose pull && up -d --no-build --wait`.** ✅ Chosen.
- `git pull` on the VPS from a checked-out repository.
- A Docker context over SSH driving compose from the CI runner.

### Public network edge

- **Caddy as the sole public service, reverse-proxying only to `web:3000`.**
  ✅ Chosen.
- Caddy routing `/api/*` directly to `api:8000` alongside the web upstream.

## Decision Outcome

Chosen option: **three public GHCR images tagged `latest` + commit SHA, published
by a separate `deploy.yml` gated on green CI at `main` via `workflow_run`; the
production compose overlay consumes those images through
`${LEARNY_IMAGE_TAG:-latest}` while the base keeps `build:`; the VPS receives the
compose files over scp+ssh and runs `pull && up -d --no-build --wait`; a Caddy
service in the prod overlay only is the single public surface, terminating TLS on
80/443 and reverse-proxying solely to `web:3000`; and nightly evaluation JSONL is
committed to a dedicated `eval-results` branch.**

The implementation model is:

1. **Three GHCR images, public, tagged `latest` + SHA.**
   `ghcr.io/augusto-dmh/learny-backend` (backend Dockerfile `runtime` target,
   serving both `api` and `worker`), `learny-pdf-worker` (`pdf-worker` target),
   and `learny-web` (frontend `prod` target). `api` and `worker` already share one
   build target, so a fourth image would duplicate near-identical layers and double
   build time for no isolation gain; `learny-api` naming would mislead because the
   worker uses the same image. The commit SHA tag is the immutable rollback handle;
   `latest` tracks the tip. Push authentication uses the job-scoped `GITHUB_TOKEN`
   with `packages: write` — no PAT secret. Packages are flipped public once,
   manually, after the first push (a one-time runbook step), so the VPS pulls with
   zero registry credentials.

2. **A separate `deploy.yml`, gated on green CI.** The workflow triggers on
   `workflow_run` for the `CI` workflow (`types: [completed]`), guarded to
   `conclusion == 'success' && head_branch == 'main'`, plus a `workflow_dispatch`
   that is ref-guarded to `main` — nothing else (no `push`, no `pull_request`).
   `workflow_run` is the native "gated on green CI" mechanism without duplicating CI
   jobs; extending `ci.yml` would bloat the PR-path workflow and entangle its
   `contents: read`-only permissions with `packages: write`. A `push: main` trigger
   would race CI instead of gating on it. Three build jobs run in parallel, then a
   deploy job runs via `needs`. A workflow-level concurrency group `deploy` with
   `cancel-in-progress: false` queues overlapping deploys rather than killing an
   in-flight VPS update.

3. **The prod overlay consumes GHCR images.** `docker-compose.prod.yml` adds
   `image: ghcr.io/augusto-dmh/…:${LEARNY_IMAGE_TAG:-latest}` for `api`, `worker`,
   `worker-pdf`, and `web`, while the base keeps `build:` for local development and
   compose-smoke. The overlay merge means the prod `image:` wins where used and the
   base `build:` stays available locally; `${VAR:-latest}` keeps a manual `up`
   usable; deploys pin `LEARNY_IMAGE_TAG=<sha>` so a deploy is reproducible and
   rollback is a single environment variable (redeploy an older SHA — the rollback
   runbook gains this path). A separate VPS-only compose file set was rejected: it
   would duplicate topology and drift, defeating the triad's purpose.

4. **Caddy is the sole public surface.** A `caddy` service exists in the prod
   overlay only, pinned to a minor-pinned Caddy alpine tag, publishing only
   `80:80`, `443:443`, and `443:443/udp` (HTTP/3 is a free win). Its `deploy/Caddyfile`
   uses the site address `{$LEARNY_DOMAIN}` and `reverse_proxy web:3000` — a single
   upstream. Because ADR-0017 routes all browser traffic, including SSE, through the
   Next.js same-origin proxy, Caddy needs exactly one upstream and the API never
   needs public exposure. Routing `/api/*` at Caddy directly to `api:8000` would
   bypass the same-origin proxy boundary ADR-0017 makes authoritative and reopen
   CSRF and cookie-domain questions. To make "only 80/443" achievable — compose
   overlays can add ports but cannot remove them — the `api` and `web` host-port
   publishing moves out of the base compose into the dev override, exactly the
   pattern already used for the `db`/`redis`/`minio` ports. Named volumes
   `caddy_data` and `caddy_config` persist issued certificates across restarts, so a
   Caddy restart reuses existing certs rather than triggering a re-issuance storm.

5. **scp + ssh transport to a fixed `/opt/learny`.** The deploy job scps
   `docker-compose.yml`, `docker-compose.prod.yml`, and `deploy/Caddyfile` to the
   fixed path `/opt/learny`, then over ssh runs
   `docker compose -f docker-compose.yml -f docker-compose.prod.yml pull` followed by
   `up -d --no-build --wait`, with `LEARNY_IMAGE_TAG=<sha>` inline on the remote
   command. `--no-build` guarantees the VPS never silently builds stale images (a
   failed pull fails the job visibly); `--wait` turns an unhealthy service into a red
   workflow run. Runtime secrets stay VPS-local (`secrets/*.env` and an `.env`
   holding `LEARNY_DOMAIN`), created once per the runbook and never transferred by
   CI — the deploy job writes only the image tag. `git pull` on the VPS was rejected
   because it needs repository credentials and a checkout that can drift; a Docker
   context over SSH was rejected because VPS-local env-file resolution becomes
   confusing. worker-pdf deploys alongside the rest (the VPS is sized ~8 GB for it,
   with `mem_limit: 4g` containing it).

6. **The deploy job is secret-gated.** When any of `VPS_HOST`, `VPS_USER`, or
   `VPS_SSH_KEY` is absent, the deploy job exits green with an explanatory notice
   while the image builds still run — the same fork-safe pattern the nightly
   evaluation workflow established. This lets the whole pipeline merge and run green
   before a VPS is provisioned. Host-key trust uses `StrictHostKeyChecking=accept-new`
   (trust-on-first-use, acceptable at author scale, avoids a `known_hosts` secret).

7. **Nightly evaluation JSONL committed to a dedicated branch.** The evaluation
   workflow gains a publish step (job-scoped `contents: write`) that commits produced
   `evals/results/*.jsonl` to the dedicated `eval-results` branch, retaining the
   existing artifact upload; an absent API key or no produced results skips green. A
   dedicated branch gives permanent, diffable quality history while keeping `main`'s
   history human and free of ~30 bot commits a month; the publish step rebases and
   retries once on a rejected push and never force-pushes over history.

This makes shipping a merge to `main`: CI validates, three images publish to GHCR,
and (when the VPS secrets exist) the exact validated commit rolls onto the VPS
behind an automatic-TLS Caddy edge, with nightly quality history accumulating on its
own branch.

### Positive Consequences

- Deploying is `git merge`: green CI on `main` publishes immutable SHA-tagged images
  and rolls them onto the VPS with no human step.
- The VPS pulls public images with zero registry credentials and holds all runtime
  secrets locally — CI transfers no secret material.
- Only 80/443 are reachable from the internet; API and infrastructure ports stay on
  the internal compose network, and the Next.js same-origin proxy remains the single
  browser-facing surface (ADR-0017 preserved).
- Rollback is one environment variable: redeploy an older SHA-tagged image, no
  rebuild.
- The pipeline runs green before a VPS exists (secret gate), so it merges and is
  validated ahead of provisioning.
- Certificates persist across restarts (`caddy_data`), avoiding re-issuance storms
  and Let's Encrypt rate-limit exposure.
- Local development and CI compose-smoke are unchanged — the edge lives only in the
  prod overlay, and app host ports simply relocated to the dev override.
- Nightly evaluation JSONL survives artifact retention as diffable git history
  without polluting `main`.

### Negative Consequences

- The `runtime` backend image still installs the `dev` dependency extra, so the
  production image carries development dependencies. This is not a new regression
  (the prod overlay already built this target), and it is kept as-is this cycle
  because changing the installed extras risks breaking in-container tooling
  assumptions; it is an accepted follow-up.
- The `learny-pdf-worker` image is multi-gigabyte (Docling models baked in at build
  per ADR-0022). GitHub Actions cache eviction makes some deploy runs rebuild it
  slowly; per-image cache scoping mitigates but does not eliminate the cost. Accepted
  follow-up.
- `workflow_run` couples the deploy to the CI workflow's `name: CI`; renaming CI
  would silently detach deploys (a workflow test pins the referenced name).
- The `eval-results` branch grows unbounded (~1 text-JSONL commit per day),
  acceptable at this scale but not pruned.
- The first GHCR push is private by default; the one-time manual visibility flip is a
  runbook step, and skipping it surfaces as a visible red pull on the first deploy.
- Host-key trust is trust-on-first-use (`accept-new`) rather than a pinned
  `known_hosts`, an accepted trade-off at author scale.

## References

- [ADR-008: Use Docker Compose On A VPS For The First Production-Like Deploy](0008-use-docker-compose-vps-for-first-production-like-deploy.md)
- [ADR-017: Use A Thin Next.js Same-Origin API Proxy To FastAPI](0017-use-thin-nextjs-same-origin-api-proxy-to-fastapi.md)
- [ADR-022: PDF Ingestion Via Docling And Corpus Normalization](0022-pdf-ingestion-via-docling-and-corpus-normalization.md)
- [RFC-002: Learny v2 Roadmap](../rfc/0002-learny-v2-roadmap.md)
- Deploy runbook: [../ops/deploy.md](../ops/deploy.md)
- Rollback runbook: [../ops/rollback.md](../ops/rollback.md)
- VPS sizing and deploy-transport research (2026-07-12): `../research/2026-07-12/followup-vps-sizing.md`
- Caddy documentation: https://caddyserver.com/docs/
