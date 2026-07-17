# Backup and Restore Runbook

Operator procedures for backing up and restoring Learny's durable state in the
production-like Docker Compose deployment (ADR-0008, AD-042/AD-043). Commands are
**provider-neutral**: they use the tools shipped in the service images and the
standard S3 API, so they work against self-hosted MinIO or a managed
S3-compatible provider without change.

> Production invocation used throughout this doc:
> `docker compose -f docker-compose.yml -f docker-compose.prod.yml <cmd>`.
> (The local override is not loaded in production — see AD-042.)

## What to back up

| Item | Where it lives | Why |
|---|---|---|
| PostgreSQL database `learny` | `db` service volume `db_data` | Source of truth for users, sources, ingestion jobs/events, corpus, retrieval columns, teaching sessions/turns |
| Object storage bucket `learny-sources` | `minio` service volume `minio_data` (or the managed provider) | Uploaded EPUB source files (ADR-0013) |
| Secret env files | `./secrets/*.env` (git-ignored) | Credentials needed to bring the stack back up |
| Compose files | repo (`docker-compose*.yml`) | Topology needed to redeploy |

PostgreSQL is the source of truth; Redis is transport only and is **not** backed
up (its state is reconstructable).

## Automated backups (the `backup` service)

The prod stack ships a dedicated `backup` sidecar (image `learny-backup`, RFC-003
Cycle A) that runs the nightly job on a schedule — you do not run `pg_dump` by hand
in normal operation. It reads its DB credentials from `./secrets/db.env`, its MinIO
credentials from `./secrets/minio.env`, and its own tunables from
`./secrets/backup.env` (see the backup section of `backend/.env.production.example`
for the full list; every value is optional and shown at its default).

Each nightly run:

1. Writes a timestamped `pg_dump -Fc` archive to the `backup_data` volume under
   `/backups/db/` (temp name, renamed onto the final name only on success — a failed
   dump never leaves a partial archive nor touches prior ones).
2. If offsite is configured, copies that dump offsite and mirrors the source object
   bucket offsite (see below).
3. Prunes old dumps by the retention policy.
4. Pings the heartbeat URL, only if every step above succeeded.

### Schedule (`LEARNY_BACKUP_CRON`)

The job runs on the crond schedule in `LEARNY_BACKUP_CRON`, default `30 3 * * *`
(03:30 UTC nightly). Change it in `secrets/backup.env` and recreate the service to
reschedule. The container logs the effective schedule at startup
(`docker compose ... logs backup`).

Run one on demand (no waiting for the schedule):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm backup backup-now
```

### Retention (`LEARNY_BACKUP_KEEP_DAYS`)

After a successful dump, local dumps older than `LEARNY_BACKUP_KEEP_DAYS` (default
`14`) are pruned; when offsite is configured, the offsite dump copies are pruned by
the same window. The newest archive is always exempt, so retention never deletes the
dump just written. Pruning never runs if the dump failed.

### Offsite (`LEARNY_BACKUP_REMOTE_*`)

Offsite copy is opt-in and provider-neutral — any S3-compatible endpoint. It engages
only when **all four** of these are set in `secrets/backup.env`:

- `LEARNY_BACKUP_REMOTE_ENDPOINT`
- `LEARNY_BACKUP_REMOTE_ACCESS_KEY`
- `LEARNY_BACKUP_REMOTE_SECRET_KEY`
- `LEARNY_BACKUP_REMOTE_BUCKET`

With all four set, the job copies each new dump to `<bucket>/db/` and mirrors the
source object bucket (`LEARNY_BACKUP_SOURCE_BUCKET`, default `learny-sources`) to
`<bucket>/objects/`. Leave any of them blank to keep backups **local-only**: the job
completes the local dump, logs `offsite not configured`, and exits 0.

Object mirroring uses `mc mirror` **without `--remove`**: objects deleted in the app
bucket are *not* deleted from the offsite copy, so an accidental deletion in the app
remains recoverable offsite. The trade-off is that the offsite object copy grows
monotonically and is not a byte-for-byte mirror of live state.

### Heartbeat (`LEARNY_BACKUP_HEARTBEAT_URL`)

If `LEARNY_BACKUP_HEARTBEAT_URL` is set, the job issues a single `curl` to it as its
last step — reached only on a fully successful run (any earlier failure aborts before
it). Point it at a dead-man's-switch monitor to get alerted when a nightly run stops
succeeding. Leave it unset to disable the ping entirely.

## PostgreSQL: logical backup and restore

Take a compressed logical dump (custom format, best for selective restore):

```bash
mkdir -p backups
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T db \
  pg_dump -U learny -Fc learny > "backups/learny-$(date +%F-%H%M).dump"
```

Restore into a running (empty or existing) database:

```bash
cat backups/learny-YYYY-MM-DD-HHMM.dump | \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T db \
  pg_restore -U learny -d learny --clean --if-exists --no-owner
```

`--clean --if-exists` drops and recreates objects so the restore is idempotent.
The database schema is managed by Alembic; a restored dump already carries the
schema at its captured revision (see `alembic_version`). After a restore, confirm
the app's expected head with `alembic upgrade head` (a no-op when already at head).

## Object storage: bucket backup and restore

Using the MinIO client `mc` (works against any S3-compatible endpoint). Configure
an alias to the running endpoint, then mirror the bucket in each direction.

```bash
# Point mc at the deployment's storage endpoint (creds from ./secrets/minio.env).
mc alias set learny "$STORAGE_ENDPOINT" "$STORAGE_ACCESS_KEY" "$STORAGE_SECRET_KEY"

# Backup: pull every object down to a local (or offsite) directory.
mc mirror --overwrite learny/learny-sources ./backups/objects/

# Restore: push the objects back into the bucket.
mc mirror --overwrite ./backups/objects/ learny/learny-sources
```

Any S3 tool works here (`aws s3 sync s3://learny-sources ./backups/objects/` is an
equivalent restore/backup with the AWS CLI) — the bucket is plain S3.

## Restore with the shipped script

The `backup` service ships a `restore.sh` that restores a `pg_dump -Fc` archive from
the `backup_data` volume with `pg_restore --clean --if-exists` (idempotent). It is a
deliberate, manual operation — it is never triggered automatically.

```bash
# Restore the most recent dump. --yes is mandatory to touch the database.
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm backup restore.sh --latest --yes

# Restore a specific archive by name (list them: run --rm backup restore.sh --latest
# with no --yes, or `ls` the volume under /backups/db/).
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm backup restore.sh learny-2026-07-17-033000.dump --yes
```

Run it **without `--yes`** first to dry-run: it prints the `pg_restore` plan it would
execute and exits non-zero **without touching the database**. An unknown archive name
also exits non-zero and lists the available archives, so a typo never silently does
nothing dangerous.

The CI compose-smoke job exercises this exact path end-to-end on scratch services
(seed a row → `backup-now` → drop it → `restore.sh --latest --yes` → assert the row is
back), so the mechanism is proven on every change.

Object storage is not restored by this script; restore the bucket with `mc mirror`
(above) from the offsite copy.

## Restore drill

Rehearse full recovery regularly so a real incident is routine:

1. Stand up a throwaway stack (or a separate compose project name).
2. Restore the latest PostgreSQL dump into its `db` with `restore.sh --latest --yes`
   (above), or the manual `pg_restore` path if restoring outside the backup image.
3. Restore the object bucket (above) into its `minio` from the offsite mirror.
4. Bring up `api` + `worker`; confirm `GET /readyz` returns ready.
5. Log in as a known user and open a previously-ingested source; confirm cited
   Q&A and a teaching session return grounded answers (the corpus + objects are
   consistent).
6. Tear the throwaway stack down.

## Encryption at rest

Dump archives are written unencrypted to the `backup_data` volume and, when offsite
is configured, uploaded as-is. If your threat model requires encryption at rest,
enable it at the storage layer: server-side encryption on the offsite S3 bucket, and
an encrypted filesystem/volume on the VPS host. Point-in-time recovery (WAL
archiving) is out of scope — logical nightly dumps fit the author-scale one-day RPO
(see ADR-0024).
