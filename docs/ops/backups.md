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

## Restore drill

Rehearse recovery regularly so a real incident is routine:

1. Stand up a throwaway stack (or a separate compose project name).
2. Restore the latest PostgreSQL dump (above) into its `db`.
3. Restore the object bucket (above) into its `minio`.
4. Bring up `api` + `worker`; confirm `GET /readyz` returns ready.
5. Log in as a known user and open a previously-ingested source; confirm cited
   Q&A and a teaching session return grounded answers (the corpus + objects are
   consistent).
6. Tear the throwaway stack down.

## Retention and offsite (operator TODO)

Retention schedule, encryption at rest, and the offsite/second-region copy depend
on the chosen VPS/provider and are deliberately **not fixed here** — they are part
of TDD open question #10 (backup/TLS/reverse-proxy/monitoring stack), the tracked
follow-up. Until it is decided, at minimum: keep dumps off the app host, encrypt
them, and test a restore (above) on a schedule.
