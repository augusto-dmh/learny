# VPS Deployment Runbook

Operator procedures for deploying Learny to a fresh VPS and keeping it updated
(RFC-002 Cycle G, AD-094). Commands are provider-neutral: they work against any x86_64 VPS
with Docker Engine and the compose plugin. No managed service dependencies or
vendor-specific tooling required.

> Production invocation used throughout:
> `docker compose -f docker-compose.yml -f docker-compose.prod.yml <cmd>`.
> The local override (`docker-compose.override.yml`) is **not** loaded in
> production; forgetting the two `-f` flags would run the dev topology.

## Prerequisites

You need:

- **VPS**: x86_64 architecture, ~8 GB RAM (sized for pdf-worker; `mem_limit: 4g`), any Linux distro
- **Docker Engine**: Install latest version (docs: https://docs.docker.com/engine/install/)
- **Docker Compose plugin**: `docker compose --version` should show v2.x+
- **Domain name**: registered and under your control
- **SSH access** to the VPS with a private key (for CI/CD deploy job)

Verify Docker + Compose:

```bash
docker --version
docker compose version
```

## DNS: Route your domain to the VPS

Point an A record from your domain to the VPS's public IPv4 address:

```bash
# Example: if your VPS IP is 203.0.113.5 and you own example.com
# Add an A record:
#   Name: @  (or your subdomain, e.g., learny.example.com)
#   Type: A
#   Value: 203.0.113.5

# Verify DNS propagation (may take a few minutes):
nslookup example.com
# or:
dig example.com
```

Use the bare domain or a chosen subdomain; the deploy will use this value for `LEARNY_DOMAIN`.

## /opt/learny layout

The deploy job provisions this directory structure on the VPS. Create it manually:

```bash
ssh user@vps-host "mkdir -p /opt/learny/secrets /opt/learny/deploy"
```

After the first deploy, the structure will be:

```
/opt/learny/
├── docker-compose.yml           (pushed by CI)
├── docker-compose.prod.yml      (pushed by CI)
├── deploy/
│   └── Caddyfile                (pushed by CI; TLS reverse proxy config)
├── secrets/
│   ├── db.env                   (you create; PostgreSQL credentials)
│   ├── minio.env                (you create; object storage credentials)
│   ├── api.env                  (you create; FastAPI secrets)
│   ├── worker.env               (you create; Celery/worker secrets)
│   └── backup.env               (you create; backup schedule/retention/offsite)
├── .env                         (you create; holds LEARNY_DOMAIN)
└── (docker volumes: db_data, minio_data, redis_data, caddy_data, caddy_config)
```

CI pushes only compose files and the Caddyfile. Secrets and domain config are VPS-local and never
transferred by the deploy job (see design rationale in ADR-0023).

## Create runtime secrets

The backend, workers, and database need credentials at startup. The single source of truth for
these is the template `backend/.env.production.example` in the Learny repo — copy the relevant
lines into each file below with real values. Application settings are read with the `LEARNY_`
prefix (see `backend/app/core/config.py`); an unprefixed name is silently ignored. Every file
lives under `/opt/learny/secrets/` (git-ignored, never transferred by CI). `docker-compose.prod.yml`
loads each one into its matching service, and `env_file` is per-service — the `api` and `worker`
services do **not** share a file, so any value both need must appear in both.

### db.env

PostgreSQL password (the user and database name are already set in the base compose file). Create
`/opt/learny/secrets/db.env`:

```bash
# Replace with a strong random string.
POSTGRES_PASSWORD=<your-db-password>
```

### minio.env

MinIO root credentials (the object-storage service's own env vars — these are not `LEARNY_`
settings). Create `/opt/learny/secrets/minio.env`:

```bash
# Replace with strong random strings.
MINIO_ROOT_USER=<your-access-key>
MINIO_ROOT_PASSWORD=<your-secret-key>
```

### api.env

FastAPI configuration. Create `/opt/learny/secrets/api.env`:

```bash
# Database URL — embeds the POSTGRES_PASSWORD from db.env above.
LEARNY_DATABASE_URL=postgresql+psycopg://learny:<your-db-password>@db:5432/learny
# Object-storage credentials — match minio.env (or your real S3 provider).
LEARNY_STORAGE_ACCESS_KEY=<same-as-MINIO_ROOT_USER>
LEARNY_STORAGE_SECRET_KEY=<same-as-MINIO_ROOT_PASSWORD>
# Public HTTPS origin(s) for the CSRF Origin/Referer check — your LEARNY_DOMAIN, comma-separated
# if several. This must match the domain you serve from or every write is rejected.
LEARNY_CSRF_TRUSTED_ORIGINS=https://<your-domain>
# Uvicorn worker processes (optional; defaults to 2).
LEARNY_API_WORKERS=2
```

### worker.env

Celery worker configuration. The worker reaches the same database and object storage as the API,
so it needs its own copy of those credentials. Create `/opt/learny/secrets/worker.env`:

```bash
LEARNY_DATABASE_URL=postgresql+psycopg://learny:<your-db-password>@db:5432/learny
LEARNY_STORAGE_ACCESS_KEY=<same-as-MINIO_ROOT_USER>
LEARNY_STORAGE_SECRET_KEY=<same-as-MINIO_ROOT_PASSWORD>
```

### Optional: enable the cloud AI providers

The stack defaults to the deterministic, network-free adapters (`LEARNY_GENERATION_PROVIDER=local`,
`LEARNY_EMBEDDING_PROVIDER=local`), so it boots with no provider keys. To serve real Claude answers
and OpenAI embeddings instead, add these to **both** `api.env` and `worker.env` (the API streams
answers/teaching; the worker runs quiz generation and ingestion embedding):

```bash
LEARNY_GENERATION_PROVIDER=anthropic
LEARNY_ANTHROPIC_API_KEY=<your-anthropic-api-key>
LEARNY_EMBEDDING_PROVIDER=openai
LEARNY_OPENAI_API_KEY=<your-openai-api-key>
```

Changing the embedding provider or model requires re-embedding existing books — see the embedding
notes in the repo before switching a populated deployment.

### backup.env

Tunables for the nightly `backup` service (RFC-003 Cycle A). It reuses `POSTGRES_PASSWORD` from
`db.env` and `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` from `minio.env` (do not duplicate them here).
Every value is optional and shown at its default in the backup section of
`backend/.env.production.example`; copy that section into `/opt/learny/secrets/backup.env`. Leave the
four `LEARNY_BACKUP_REMOTE_*` values blank to keep backups local-only. Create
`/opt/learny/secrets/backup.env`:

```bash
# Nightly dump schedule (crond format) and how many days of dumps to keep.
LEARNY_BACKUP_CRON=30 3 * * *
LEARNY_BACKUP_KEEP_DAYS=14
# Offsite S3-compatible target — set ALL FOUR to enable offsite copy + object mirror.
LEARNY_BACKUP_REMOTE_ENDPOINT=
LEARNY_BACKUP_REMOTE_ACCESS_KEY=
LEARNY_BACKUP_REMOTE_SECRET_KEY=
LEARNY_BACKUP_REMOTE_BUCKET=
# Optional dead-man's-switch URL, pinged only after a fully successful run.
LEARNY_BACKUP_HEARTBEAT_URL=
```

See [backups.md](backups.md) for the full backup/restore runbook.

## .env: Set the domain

Create `/opt/learny/.env` with the domain you configured in DNS:

```bash
LEARNY_DOMAIN=example.com
# or your subdomain:
# LEARNY_DOMAIN=learny.example.com
```

Caddy uses this value to request a TLS certificate from Let's Encrypt and to serve the site.

## GitHub repository secrets

The CI/CD deploy job needs three secrets to provision your VPS. Set these in your GitHub repo
(Settings → Secrets and variables → Actions):

| Secret Name | Value | Example |
|---|---|---|
| `VPS_HOST` | VPS's public hostname or IP | `203.0.113.5` or `vps.example.com` |
| `VPS_USER` | SSH user on the VPS | `ubuntu` (or your chosen user) |
| `VPS_SSH_KEY` | Private SSH key (PEM format) | Output of `cat ~/.ssh/id_rsa` |

**How to create the SSH key (if you don't have one):**

```bash
ssh-keygen -t ed25519 -f ~/.ssh/learny_deploy -C "learny-deploy"
# Follow prompts (leave passphrase empty for unattended CI use)

# Add the public key to your VPS's authorized_keys:
ssh-copy-id -i ~/.ssh/learny_deploy.pub user@vps-host

# Get the private key for the GitHub secret:
cat ~/.ssh/learny_deploy
```

Paste the entire private key (including `-----BEGIN OPENSSH PRIVATE KEY-----` and the closing line)
into GitHub's `VPS_SSH_KEY` secret.

## One-time: Flip GHCR packages to public

After the first successful deploy workflow run, the three container images land in your GitHub
Container Registry (GHCR) as **private by default**. The VPS needs to pull them as a public user
(no credentials), so flip their visibility once:

1. Go to your GitHub profile → **Packages**.
2. For each of these packages (in order), click → Package settings → Change visibility → **Public**:
   - `learny-backend`
   - `learny-pdf-worker`
   - `learny-web`
3. Confirm each one reads "Public" in its card.

After this, the VPS can `docker compose pull` without credentials.

## First deploy: Trigger the workflow

The CI/CD pipeline automatically deploys on every merge to `main`, but you can also manually
trigger the deploy workflow to get started:

```bash
gh workflow run deploy.yml --ref main
```

(Or use the GitHub UI: Actions → Deploy → Run workflow → main → Run workflow.)

Monitor the run:

```bash
gh run list --workflow=deploy.yml --limit=1
gh run view <run-id> --log
```

Expected output:
- Three images build and push to GHCR (learny-backend, learny-pdf-worker, learny-web), tagged `:latest` and `:<commit-sha>`.
- Deploy job runs (or skips green if VPS secrets are not yet set).
- If secrets are set, the deploy job scp's compose files to `/opt/learny`, runs `docker compose pull`, then `up -d --no-build --wait`.

## Verify health

After the deploy completes (or after you manually run `docker compose up -d` on the VPS):

```bash
# SSH into the VPS
ssh user@vps-host

# Check running containers
cd /opt/learny
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps

# You should see (all healthy or up):
# NAME                COMMAND             STATUS
# caddy               caddy run ...       Up
# web                 next start          Up
# api                 uvicorn ...         Up
# worker              celery worker       Up
# worker-pdf          celery worker       Up
# db                  postgres            Up
# redis               redis-server        Up
# minio               /usr/bin/minio ...  Up

# Check API readiness
curl -s https://example.com/api/readyz | jq .

# Check web app (should redirect to HTTPS)
curl -I http://example.com
# Expected: 308 (Permanent Redirect) to https://example.com
```

If any service is not up, inspect logs:

```bash
# Logs for a specific service
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs api
# or follow live:
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f web

# Logs for all services
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=50
```

## Rollback to a previous version

If a deployment introduces a regression, you can roll back to a prior image SHA in two ways:

### Path 1: GHCR image-tag rollback (recommended)

Each commit to main produces immutable images tagged with the commit SHA. To revert to a known-good
commit without re-building:

1. Find the previous good commit SHA (from git log or GitHub Actions runs):

   ```bash
   git log --oneline -20 | head -n 10
   # e.g., 7e3a4d5 is the known-good commit
   ```

2. Manually trigger the deploy workflow pinned to that commit's image:

   ```bash
   gh workflow run deploy.yml --ref main -F LEARNY_IMAGE_TAG=7e3a4d5
   # Note: this may fail if GitHub doesn't accept field inputs for this workflow.
   # Alternative: edit the deploy.yml locally, commit, push, then trigger — or use the SSH path below.
   ```

   Or SSH into the VPS and manually pull + redeploy the previous image:

   ```bash
   ssh user@vps-host
   cd /opt/learny
   LEARNY_IMAGE_TAG=7e3a4d5 docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
   LEARNY_IMAGE_TAG=7e3a4d5 docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-build --wait
   ```

3. Verify the rollback:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
   ```

For more information on independent service rollback and database migrations, see
[rollback.md](rollback.md).

### Path 2: Restore from backup

If ingestion or corpus state was corrupted, restore PostgreSQL and object storage from a tested
backup (see [backups.md](backups.md)).
