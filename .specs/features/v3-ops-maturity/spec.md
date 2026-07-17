# v3-ops-maturity Specification (RFC-003 Cycle A)

## Problem Statement

The deployed stack has no automated backups (docs/ops/backups.md is a manual runbook that explicitly defers scheduling/retention/offsite to TDD open question #10), no monitoring beyond structured logs, and two recorded image-hygiene debts from ADR-0023 (the `runtime` backend image installs the `dev` extra; the `pdf-worker` image is multi-gigabyte). A VPS failure today loses everything since the last manual dump nobody is running.

## Goals

- [ ] Nightly automated backups (PostgreSQL dumps + MinIO object mirror) with retention, optional off-VPS offsite, and a restore path proven by CI — closing the backup half of TDD OQ #10.
- [ ] Self-hosted, provider-neutral monitoring of host + containers on the VPS, without widening the public surface (Caddy stays the only non-loopback listener).
- [ ] `runtime` image ships without the `dev` extra; `pdf-worker` size reduction investigated and either implemented or recorded with evidence.

## Out of Scope

| Feature | Reason |
|---|---|
| PITR / WAL archiving (pgBackRest, wal-g) | Logical dumps fit author-scale RPO; ADR records as future upgrade path |
| Redis backup | Transport-only by decision (backups.md); PostgreSQL is source of truth |
| Prometheus/Grafana stack, external uptime SaaS, alert delivery integrations | Heavyweight or provider-locked; monitoring runbook documents hooks |
| Public exposure of the monitoring UI (via Caddy) | Violates single-public-surface (ADR-0017/0023); SSH tunnel instead |
| Scanned-PDF OCR-related image changes | RFC-003 Cycle C |
| Restore automation triggered from CI/deploy against the real VPS | Restore is a deliberate manual operation; CI proves the mechanism on scratch services |

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|
| Scheduling mechanism | Dedicated `backup` sidecar container running crond (D-1) | See context.md | auto (ship-cycle) |
| Backup tooling | Repo-owned image: alpine + postgresql16-client + minio `mc` (D-2) | See context.md | auto (ship-cycle) |
| Offsite topology | DB dumps local + offsite; bucket objects mirrored offsite-only (D-3) | See context.md | auto (ship-cycle) |
| Monitoring stack | Netdata, pinned tag, loopback-only publish + SSH tunnel (D-4) | See context.md | auto (ship-cycle) |
| Runtime extras fix | Plain `uv sync --frozen` (main deps only); import-chain audit in-phase (D-5) | See context.md | auto (ship-cycle) |
| pdf-worker slimming | CPU-only torch investigation, do-if-clean else record in ADR (D-6) | See context.md | auto (ship-cycle) |
| Offsite provider | Any S3-compatible endpoint via env (no vendor pinned) | Provider-neutral per project constraint | auto |
| Backup cadence default | Nightly `30 3 * * *`, `LEARNY_BACKUP_KEEP_DAYS=14` | Author-scale RPO of one day; two weeks of dumps is small (logical dumps of a personal corpus) | auto |

**Open questions:** none — all resolved or logged above.

## User Stories

### P1: Automated, restorable backups ⭐ MVP

**User Story**: As the operator, I want scheduled DB dumps and object mirrors with retention and a proven restore path, so a VPS loss costs at most one day of data.

**Acceptance Criteria**:

1. (OPS-01) WHEN the prod overlay is merged with the base compose file THEN it SHALL define a `backup` service using image `ghcr.io/augusto-dmh/learny-backup:${LEARNY_IMAGE_TAG:-latest}`, `restart: unless-stopped`, a `backup_data` volume mounted at `/backups`, `env_file` entries (`required: true`) for `./secrets/db.env`, `./secrets/minio.env`, `./secrets/backup.env`, and NO published ports.
2. (OPS-02) WHEN deploy.yml runs its build job THEN the matrix SHALL include a 4th image `learny-backup` built from context `./deploy/backup`, pushed with the same sha + latest tags as the other images.
3. (OPS-03) WHEN the backup container starts THEN it SHALL run crond with a schedule from `LEARNY_BACKUP_CRON` (default `30 3 * * *`) invoking the backup job; an on-demand run SHALL be possible via `backup-now`.
4. (OPS-04) WHEN a backup job runs THEN it SHALL write a timestamped `pg_dump -Fc` archive of the configured database to `/backups/db/`, writing to a temp name and renaming only on success (a failed dump SHALL leave no partial archive under the final name and SHALL NOT touch prior archives).
5. (OPS-05) WHEN offsite is configured (`LEARNY_BACKUP_REMOTE_ENDPOINT`/`_ACCESS_KEY`/`_SECRET_KEY`/`_BUCKET` all set) THEN the job SHALL copy the new dump to the offsite bucket and mirror the source MinIO bucket (`LEARNY_BACKUP_SOURCE_BUCKET`, default `learny-sources`) to the offsite bucket; WHEN offsite is not configured THEN the job SHALL complete the local dump, log an explicit "offsite not configured" notice, and exit 0.
6. (OPS-06) WHEN a backup job completes THEN local dumps older than `LEARNY_BACKUP_KEEP_DAYS` (default 14) SHALL be pruned, and WHEN offsite is configured the offsite dump copies SHALL be pruned by the same policy; pruning SHALL never run if the current dump failed.
7. (OPS-07) WHEN a backup job is already running THEN a second invocation SHALL exit without dumping (lock); WHEN any step fails THEN the job SHALL exit non-zero and skip the heartbeat.
8. (OPS-08) WHEN `LEARNY_BACKUP_HEARTBEAT_URL` is set THEN the job SHALL request it only after a fully successful run; WHEN unset THEN no request is attempted.
9. (OPS-09) WHEN the operator runs the shipped `restore` script with a dump name and `--yes` THEN it SHALL `pg_restore --clean --if-exists` that archive into the configured database; WHEN `--yes` is absent THEN it SHALL print what it would do and exit non-zero without touching the database.
10. (OPS-10) WHEN CI runs THEN it SHALL exercise the real backup image end-to-end on scratch services: seed data → `backup-now` → destroy the seeded data → `restore --yes` → assert the seeded data is back, and assert the "offsite not configured" notice appears in local-only mode.
11. (OPS-11) WHEN secrets are inspected THEN backup/offsite credentials SHALL come only from `secrets/backup.env` (+ reused `db.env`/`minio.env`); no backup credential SHALL appear in compose files, workflows, or the image; `backend/.env.production.example` SHALL gain a documented backup section and `docs/ops/deploy.md` SHALL list `backup.env` among the secrets files.
12. (OPS-12) WHEN docs/ops/backups.md is read THEN it SHALL document the automated schedule, retention, offsite configuration, heartbeat, and a restore drill using the shipped scripts (replacing "deliberately not fixed here"), and test_ops_docs SHALL assert the section's key strings.

**Independent Test**: compose-smoke CI job proves seed→backup→destroy→restore roundtrip with the shipped image.

### P1: Self-hosted monitoring

**User Story**: As the operator, I want host + per-container metrics on the VPS so I can see memory/CPU/disk pressure and unhealthy containers without SSH archaeology.

**Acceptance Criteria**:

13. (OPS-13) WHEN the prod overlay is merged THEN it SHALL define a `monitoring` service running Netdata with a pinned, registry-verified version tag, `restart: unless-stopped`, a memory limit, and the mounts required for host + Docker container metrics (`/proc`, `/sys`, `/etc/os-release` read-only, docker socket read-only, named volumes for netdata config/lib/cache).
14. (OPS-14) WHEN the prod overlay is merged THEN the monitoring UI port SHALL be published ONLY on loopback (`127.0.0.1:19999:19999`) and a topology test SHALL assert that caddy remains the only service publishing non-loopback host ports.
15. (OPS-15) WHEN docs/ops/monitoring.md is read THEN it SHALL document: SSH-tunnel access to the UI, the key panels to check (per-container memory/CPU, disk, OOM), how backup-job logs are inspected, and where alert hooks could attach — and test_ops_docs SHALL assert its key strings.

**Independent Test**: yaml-merge topology tests + monitoring.md content assertions; compose config validation in CI.

### P2: Image hygiene

**User Story**: As the operator, I want production images to carry only what they run, so pulls are faster and the surface smaller.

**Acceptance Criteria**:

16. (OPS-16) WHEN the `runtime` stage of backend/Dockerfile is built THEN it SHALL install only main dependencies (`uv sync --frozen`, no `--extra dev`), the app modules imported by api/worker startup SHALL not require dev-extra packages, and a test SHALL assert the runtime stage contains no `--extra dev`.
17. (OPS-17) WHEN the `runtime` image runs THEN it SHALL run as a non-root user, and compose-smoke SHALL still pass (api/worker healthy, migrations apply).
18. (OPS-18) WHEN the pdf-worker torch dependency is investigated THEN either (a) CPU-only torch wheels are pinned via uv configuration with the lockfile consistent and CI green, or (b) the blocker is recorded in the cycle ADR with evidence (measured sizes / resolver conflict); one of the two outcomes SHALL be present.

### P1: Decision record

19. (OPS-19) WHEN the cycle completes THEN ADR-0024 SHALL record the backup + monitoring stack decisions (tooling, topology, retention, offsite neutrality, netdata choice, tunnel-only access) and state that it closes the backup/monitoring half of TDD open question #10; the ADR SHALL also record the OPS-18 outcome.

## Edge Cases

- WHEN the db or minio service is unreachable during a backup THEN the job exits non-zero, prior archives remain intact, no heartbeat is sent.
- WHEN the offsite endpoint is unreachable THEN the local dump is kept, job exits non-zero (offsite was configured but failed ≠ not configured).
- WHEN restore is invoked with a non-existent dump name THEN it exits non-zero listing available archives.
- WHEN `LEARNY_BACKUP_KEEP_DAYS` prunes everything older THEN the just-written dump always survives (prune runs only after a successful dump, never deletes the newest archive).

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
|---|---|---|---|
| OPS-01..08 | P1 backups (engine) | A | Pending |
| OPS-09..12 | P1 backups (restore + docs + CI proof) | B | Pending |
| OPS-13..15 | P1 monitoring | C | Pending |
| OPS-16..18 | P2 image hygiene | D | Pending |
| OPS-19 | P1 decision record | E | Pending |

**Coverage:** 19 total, mapped to phases A–E.

## Success Criteria

- [ ] CI proves the restore roundtrip with the shipped image and scripts.
- [ ] `docker compose config` of base+prod merge is valid with backup + monitoring services; caddy remains the only non-loopback listener.
- [ ] Full backend suite + ruff green; no new runtime Python dependencies.
