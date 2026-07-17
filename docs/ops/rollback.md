# Rollback and Failure Runbook

Operator procedures for reverting a bad Learny deployment and responding to
operational failures (TDD-001 §Rollback And Failure Handling, AD-043). Commands
target the production-like Docker Compose deployment (ADR-0008, AD-042).

> Production invocation used throughout:
> `docker compose -f docker-compose.yml -f docker-compose.prod.yml <cmd>`.
> The local override (`docker-compose.override.yml`) is **not** loaded in
> production; forgetting the two `-f` flags would run the dev topology.

## Independent image rollback (api / worker / web)

The three application services build from pinned images/tags and can be reverted
independently — you do not have to roll back the whole stack for a single bad
component.

1. Re-pin the affected service to the previous known-good image tag (in the
   compose overlay or your image registry reference).
2. Recreate only that service:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d api
   # or: ... up -d worker      # or: ... up -d web
   ```

3. Confirm health: `docker compose -f docker-compose.yml -f docker-compose.prod.yml ps`
   and `GET /readyz` for the API.

Because `restart: unless-stopped` is set, a reverted service stays up across host
restarts.

## GHCR image-tag rollback (all-commit rollback)

Each commit to main produces immutable container images tagged with the commit SHA (plus `:latest`).
To roll back an entire deployment to a known-good prior commit (e.g., after a regression that spans
multiple services or the worker pipeline):

1. Identify the commit SHA of the known-good version:

   ```bash
   git log --oneline -20
   # e.g., 7e3a4d5 is the working commit you want to revert to
   ```

2. SSH into the VPS and re-pull all images from that commit:

   ```bash
   ssh user@vps-host
   cd /opt/learny
   LEARNY_IMAGE_TAG=7e3a4d5 docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
   ```

3. Restart the stack with the prior images:

   ```bash
   LEARNY_IMAGE_TAG=7e3a4d5 docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-build --wait
   ```

4. Verify all services are healthy:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
   curl -s https://your-domain/api/readyz | jq .
   ```

Because images are immutable by commit SHA, the rollback is instant (no rebuild required). The VPS
always tracks the image tag you specify in `LEARNY_IMAGE_TAG`; if you do not set it, it defaults to
`:latest`.

## Database migration rollback

Schema migrations are reversible unless a migration is explicitly documented as
forward-only. To reverse the most recent migration:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec api \
  alembic downgrade -1
```

Downgrade to a specific revision with `alembic downgrade <revision>`.

**Forward-only exception:** if a migration is marked forward-only (data-lossy or
irreversible), do **not** attempt `alembic downgrade`. Instead restore the
database from the last tested backup (see `backups.md`) — this is also the
migration-failure trigger below.

## Corpus / index rollback caveat (AD-018)

Re-ingestion replaces a source's canonical corpus **atomically with no
versioning** (delete + cascade + insert in one transaction). There is therefore
**no prior corpus version to roll back to**: reverting a worker/ingestion change
means redeploying the previous worker image and **re-ingesting** affected sources,
not restoring an old corpus. Citations reference stable anchors (`anchor`,
`section_path`), so a re-ingested corpus keeps citations interpretable. If a bad
ingestion already replaced good corpus data, restore PostgreSQL + object storage
from backup (see `backups.md`).

## Operational rollback triggers

Reproduced from TDD-001 §Rollback And Failure Handling — the conditions that
should halt a rollout and the action to take:

| Trigger | Action |
|---|---|
| Auth or authorization regression | Stop rollout and revert API/frontend changes |
| Ingestion failures spike after worker deploy | Stop workers, revert worker image, inspect failed jobs |
| Retrieval returns empty or uncited answers for fixture-backed queries | Revert retrieval/indexing change and preserve the prior index state |
| Provider adapter failure rate spikes | Disable the affected adapter or route to an accepted fallback if available |
| Migration failure | Stop deployment and restore from a tested database backup or the migration rollback path |

## Diagnosing before rollback

Every request and worker task is correlated by a `request_id`/trace fields in the
structured logs (AD-041, `LEARNY_LOG_FORMAT=json` in production). When a trigger
fires, filter logs by the failing request/job id and the `http.request` access
records (status + `duration_ms`) to confirm blast radius before reverting.
Failed ingestion jobs also leave durable, inspectable state in PostgreSQL
(`ingestion_jobs` / `ingestion_events`) with a retry path.
