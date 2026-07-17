# Monitoring Runbook

Operator procedures for watching the production Learny stack's host and
per-container health (RFC-003 Cycle A, ADR-0024). The prod overlay ships a
`monitoring` service running [Netdata](https://www.netdata.cloud/) — a
self-hosted, provider-neutral agent that reads host metrics from read-only bind
mounts and per-container metrics from the docker socket. No external SaaS, no
data leaves the VPS.

> Production invocation used throughout this doc:
> `docker compose -f docker-compose.yml -f docker-compose.prod.yml <cmd>`.
> (The local override is not loaded in production — see AD-042.)

## Why the UI is not publicly exposed

Caddy is the **single public surface** of the deployment (ADR-0017/0023): it is
the only service that publishes a non-loopback host port. Netdata's UI would be a
second public listener, so the `monitoring` service publishes its port **only on
loopback** (`127.0.0.1:19999:19999`) and Caddy has no route to it. You reach the
UI over an SSH tunnel instead — authenticated by the same key that gets you onto
the box, never exposed to the internet.

This is a deliberate change from Netdata's stock compose recipe, which uses
`network_mode: host` (binding 19999 on every interface). We publish a single
loopback port instead to keep the public surface to Caddy alone.

## Trust boundary

Treat the netdata container as fully host-privileged and its dashboard as
unauthenticated. This is an accepted, deliberate design (ADR-0024), and the
security of the whole arrangement rests on a single invariant:

- **The dashboard has no authentication.** Anyone who can reach port 19999 sees
  every host and per-container metric. There is no login in front of it.
- **The container can read the entire host.** To collect host metrics it mounts
  the root filesystem read-only at `/host/root` (which includes this repo's
  `secrets/` directory) and mounts the Docker socket (`/var/run/docker.sock`),
  i.e. it can enumerate and inspect every container via the Docker API. These
  mounts follow netdata's official recipe and are required for host metrics; they
  are not scoped down.
- **The loopback bind + SSH tunnel is the sole boundary.** The only thing keeping
  this unauthenticated, host-reading agent off the internet is that it publishes
  `127.0.0.1:19999:19999` and Caddy has no route to it. You reach it exclusively
  over `ssh -L` (below), authenticated by the same key that gets you onto the box.

**Invariant:** the monitoring port must never be published on a non-loopback
interface, and any future exposure (e.g. a real UI URL) must put authentication in
front of it first. `test_deploy_topology.py` enforces the topology half of this —
across the base+prod merge, Caddy is the only service publishing a non-loopback
port — so a regression that widens the surface fails CI, not production.

## Access the UI over an SSH tunnel

Forward the loopback UI port from the VPS to your workstation, then open it
locally:

```bash
# Forward the VPS's loopback 19999 to your machine's localhost:19999.
ssh -L 19999:127.0.0.1:19999 user@vps-host

# With that session open, browse to:
#   http://localhost:19999
```

Close the SSH session to close the tunnel. Nothing is persisted client-side; the
dashboards are served live from the agent.

## What to check routinely

Netdata's default dashboard covers host + containers out of the box. The panels
that matter for this stack:

| Panel | What to watch for | Why it matters |
|---|---|---|
| Per-container memory (cgroup) | `worker-pdf` approaching its `mem_limit: 4g` cap; `monitoring` near its own `512m` cap | Docling PDF parsing is memory-heavy (ING-18); a container at its cap gets OOM-killed |
| Per-container CPU (cgroup) | sustained pegging on `api`/`worker` | saturation shows up here before users report slowness |
| System memory / OOM | `oom_kill` events on any cgroup | a killed worker silently drops jobs; correlate with `docker compose ... ps` showing a restart |
| Disk space (`/`) | steady growth from the `backup_data`, `db_data`, and `minio_data` volumes | nightly dumps and object mirrors accumulate; a full disk stops backups *and* Postgres writes |
| Docker containers | any container not `healthy` / restarting | maps to the healthchecks in the compose files |

When a container looks wrong in a panel, confirm state and read its logs:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=100 <service>
```

## Inspect the backup job

The nightly `backup` service (see [backups.md](backups.md)) logs every run to
stdout, so its history is in the container logs:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs backup
```

What the tail should look like:

- **Successful run** — a `pg_dump` line, the prune step, and (if configured) the
  offsite copy/mirror, ending cleanly. If `LEARNY_BACKUP_HEARTBEAT_URL` is set, the
  heartbeat `curl` is the last line — it is only reached on a fully successful run.
- **Local-only mode** — the exact notice `offsite not configured` and a clean exit
  0. This is expected when the four `LEARNY_BACKUP_REMOTE_*` values are blank; the
  local dump still succeeded.
- **Failure** — a non-zero exit with no heartbeat. Prior archives are left intact
  (a failed dump never overwrites them). Common causes: `db`/`minio` unreachable, or
  offsite configured but its endpoint down.

To force a run instead of waiting for the schedule:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm backup backup-now
```

## Where alerting could attach later

Alert **delivery** is deliberately not configured in this cycle (out of scope —
no provider-locked integrations). The hook exists when you want it: Netdata ships
a built-in health engine (`health.d` alarm definitions) and `alarm-notify`
supports many transports (email, Slack, Discord, ntfy, generic webhooks). To wire
it up later, drop notification config into the `netdata_config` volume
(mounted at `/etc/netdata`) and restart the service — no image change needed.

For a dead-man's-switch that is independent of the monitoring UI, prefer the
backup job's `LEARNY_BACKUP_HEARTBEAT_URL` (see [backups.md](backups.md)): it
alerts you when a nightly run *stops succeeding*, which is the failure that
actually costs data.
