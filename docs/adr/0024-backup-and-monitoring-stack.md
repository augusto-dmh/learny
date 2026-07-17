# ADR-024: Sidecar Backups, Netdata Monitoring, And Production Image Hygiene

- **Date**: 2026-07-17
- **Status**: Accepted
- **Deciders**: Augusto, Claude
- **Tags**: operations, backups, monitoring, docker, images, postgres, minio

## Context and Problem Statement

The deployed stack (ADR-0023) ran with no automated backups — `docs/ops/backups.md`
was a manual runbook that explicitly deferred scheduling, retention, and offsite
copies — and no monitoring beyond structured JSON logs. A VPS disk failure would
have lost everything since the last manual dump. Two image-hygiene debts were also
on record from ADR-0023: the `runtime` backend image installed the `dev` extra
(pytest, ruff, httpx, docling-core) it never uses, and the `pdf-worker` image is
multi-gigabyte.

This ADR records how RFC-003 Cycle A closes the backup and monitoring half of TDD
open question #10 (the TLS/reverse-proxy half was resolved by ADR-0023), and the
outcome of both image-hygiene follow-ups.

## Decision Drivers

- A VPS loss should cost at most one day of data, without any human remembering to
  run anything.
- Provider neutrality: no backup destination vendor, no monitoring SaaS, no new
  third-party images beyond what can be pinned and verified.
- The single-public-surface invariant stands: Caddy remains the only non-loopback
  listener (ADR-0017, ADR-0023).
- Everything must be testable in the repo's house style (YAML/text assertions in
  `backend/tests/`) and, where behavior matters, proven by CI — not by trust.
- Restore is the product; a backup that has never been restored is a hope, not a
  backup.

## Considered Options

### Backup scheduling

1. **Dedicated sidecar container running crond** — chosen.
2. Host cron on the VPS — config outside the repo; drift; undone by VPS rebuild.
3. Celery beat + a backup task — puts `pg_dump`/`mc` into the app image (the
   opposite of the hygiene goal) and couples backups to app deploys and worker
   health.
4. Ofelia (cron-for-Docker) — a third-party scheduler image and label DSL for one
   nightly job.

### Backup tooling

1. **Repo-owned image (`deploy/backup/`): pinned Alpine + `postgresql16-client` +
   pinned, checksum-verified MinIO `mc`, with shell scripts** — chosen; published
   as the fourth GHCR image `learny-backup` by the existing deploy matrix.
2. `prodrigestivill/postgres-backup-local` — Postgres-only (objects still need a
   second mechanism) and a third-party image to vet.
3. restic/rclone — encryption and dedup, but two more tools plus repository-format
   state; `mc` already speaks every S3-compatible target and matches the runbook.

### Monitoring

1. **Netdata, one pinned container, loopback-only publish + SSH tunnel** — chosen.
2. Prometheus + Grafana + cAdvisor + node_exporter — four containers and a config
   surface for a one-operator VPS.
3. Uptime Kuma — uptime only; cannot answer "which container is eating memory".
4. Dozzle — logs only; logs are already structured and queryable.

## Decision Outcome

### Backups

A `backup` service in the production overlay runs busybox crond in the repo-owned
`learny-backup` image. On `LEARNY_BACKUP_CRON` (default `30 3 * * *`) it:

1. dumps the database with `pg_dump -Fc` to the `backup_data` volume, writing a
   temp file and renaming only on success (a failed dump can never clobber or
   truncate a prior archive);
2. if all four `LEARNY_BACKUP_REMOTE_*` variables are set (any S3-compatible
   endpoint — no vendor pinned), copies the dump offsite and mirrors the source
   MinIO bucket offsite with `mc mirror` **without** `--remove` (objects deleted
   in the app persist offsite until pruned deliberately);
3. prunes local and offsite dumps older than `LEARNY_BACKUP_KEEP_DAYS` (default
   14), only after a successful dump, never touching the newest archive;
4. optionally pings `LEARNY_BACKUP_HEARTBEAT_URL` — success only, so a missed
   heartbeat is the alert.

Overlapping runs are excluded with `flock`; any failure exits non-zero and is
visible in `docker compose logs backup` and in netdata. Without offsite
configuration the job logs `offsite not configured` and stays local-only —
deliberately secret-gated like the deploy itself. Credentials reach the container
only via `secrets/db.env`, `secrets/minio.env`, and `secrets/backup.env`
(documented in `backend/.env.production.example`); nothing sensitive lives in
compose files or workflows.

Restore ships as `restore.sh <archive|--latest> --yes` (`pg_restore --clean
--if-exists`); without `--yes` it prints the plan and refuses. CI's compose-smoke
job proves the whole mechanism on every run: seed a marker row → `backup-now` →
drop → `restore.sh --latest --yes` → assert the row returned, plus the local-only
notice. Redis remains explicitly un-backed-up (transport only); PITR/WAL archiving
remains a recorded future upgrade if the RPO ever tightens.

### Monitoring

A `monitoring` service runs `netdata/netdata:v2.10.4` (tag verified against the
Docker Hub API) following netdata's official Docker recipe (pid host, SYS_PTRACE +
SYS_ADMIN, read-only host mounts including the Docker socket) with one deliberate
divergence: instead of the recipe's host networking, the UI is published only on
loopback (`127.0.0.1:19999`), reached via `ssh -L 19999:127.0.0.1:19999` — host
networking would have bound every interface and broken the single-public-surface
invariant. A topology test enforces the stronger contract: across the base+prod
merge, caddy is the only service publishing non-loopback ports. Access, routine
checks, and future alert hooks are documented in `docs/ops/monitoring.md`.

The trust assumption is explicit and accepted: the netdata container is
host-privileged (read-only mount of the whole host filesystem — `secrets/`
included — plus the Docker socket) and its dashboard is unauthenticated, so the
loopback bind and SSH tunnel are the *sole* boundary keeping it off the internet.
The port must never be published non-loopback, and any future exposure requires
authentication in front of it (documented as an invariant in
`docs/ops/monitoring.md`, enforced by the topology test). Netdata's anonymous
telemetry is disabled (`DISABLE_TELEMETRY=1`) so the agent phones home to no one —
consistent with the no-monitoring-SaaS driver above.

### Image hygiene

The `runtime` image now installs only main dependencies (`uv sync --frozen`, no
extras) and runs as a dedicated non-root user (uid 10001). An import audit
confirmed no dev-extra package is reachable from api or worker startup: the only
docling path is the parser factory's PDF branch, which lazy-imports behind an
availability probe. Verified by building the image, importing `app.main` and
`app.worker.celery_app` inside it, and asserting the non-root uid.

**pdf-worker slimming is blocked upstream, recorded with evidence.** torch 2.13.0
arrives only through the `pdf` extra (docling → torchvision/accelerate) and drags
~2.6 GB of CUDA-13 wheels the CPU-only worker never uses. The documented uv
CPU-index recipe (`[tool.uv.sources]` → `download.pytorch.org/whl/cpu`) is
silently not honored by uv 0.11.8 here because torchvision 0.28.0 pins
`torch>=2.13.0,<2.13.0+`, whose upper bound excludes the local-version
`2.13.0+cpu` wheel — the only self-consistent resolution is the PyPI CUDA build.
`uv lock --upgrade` additionally churned ~15 unrelated packages without adopting
CPU torch. No lockfile change was made. Revisit when torchvision's torch pin
admits local versions, when the pdf extra can drop torchvision, or with an
explicit mutually-consistent `+cpu` pair; meanwhile the image stays large but is
never part of the default `up` and CI never resolves the `pdf` extra.

## Consequences

- Positive: unattended nightly backups with a CI-proven restore path; disaster
  recovery documented against shipped scripts instead of prose; per-container
  metrics one SSH tunnel away; a smaller, non-root runtime image; TDD open
  question #10 is now fully closed.
- Negative: one more always-on container per concern (backup ~idle, netdata
  ~512 MB limit); offsite protection requires the operator to provision an
  S3-compatible bucket and fill `secrets/backup.env`; the netdata UI needs a
  tunnel rather than a URL.
- Follow-ups: none required by this cycle; the pdf-worker size and PITR remain
  recorded upgrade paths.
