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
| PostgreSQL database `learny` | `db` service volume `db_data` | Source of truth for users, sources, ingestion jobs/events, corpus, retrieval columns, conversations/turns |
| Archived WAL segments | volume `wal_archive`, mounted at `/wal_archive` | The write-ahead log the database has already committed, kept so a restore can be replayed forward to a chosen moment |
| Object storage bucket `learny-sources` | `minio` service volume `minio_data` (or the managed provider) | Uploaded EPUB source files (ADR-0013) |
| Secret env files | `./secrets/*.env` (git-ignored) | Credentials needed to bring the stack back up |
| Compose files | repo (`docker-compose*.yml`) | Topology needed to redeploy |

PostgreSQL is the source of truth; Redis is transport only and is **not** backed
up (its state is reconstructable).

## Automated backups (the `backup` service)

The prod stack ships a dedicated `backup` sidecar (image `learny-backup`, RFC-003
Cycle A) that runs its jobs on a schedule — you do not run `pg_dump` by hand in
normal operation. It reads its DB credentials from `./secrets/db.env`, its MinIO
credentials from `./secrets/minio.env`, and its own tunables from
`./secrets/backup.env` (see the backup section of `backend/.env.production.example`
for the full list; every value is optional and shown at its default).

Three jobs run on their own schedules, producing three artifacts:

| Artifact | Job | Where | Cadence | Retention |
|---|---|---|---|---|
| Logical dump `learny-<stamp>.dump` | `backup.sh` | `/backups/db/` in `backup_data` | `LEARNY_BACKUP_CRON`, default `30 3 * * *` | `LEARNY_BACKUP_KEEP_DAYS` (14), newest exempt |
| Physical base backup `learny-base-<stamp>/` | `base-backup.sh` | `/backups/base/` (`LEARNY_BASEBACKUP_DIR`) in `backup_data` | `LEARNY_BASEBACKUP_CRON`, default `0 2 * * 0` | `LEARNY_BACKUP_KEEP_DAYS` (14), newest exempt |
| Archived WAL segments | the database itself, shipped and pruned by `wal-archive.sh` | `/wal_archive` (`LEARNY_WAL_ARCHIVE_DIR`) in `wal_archive` | every completed segment, and at least every `LEARNY_WAL_ARCHIVE_TIMEOUT` seconds (900) | `LEARNY_WAL_KEEP_DAYS` (14) **and** below the oldest retained base — see the coupling below |

The dump answers "give me the database as it was last night, in a form I can restore
selectively and across major versions". The base backup plus the WAL archive answer
"give me the database as it was at 14:32 today". They are complementary and neither
replaces the other.

Each nightly dump run:

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

The same variable governs base backups (same window, same newest-exemption, same
prune-only-after-success rule) — and through them, indirectly, how far back the WAL
archive reaches. See the coupling below before changing it.

### Offsite (`LEARNY_BACKUP_REMOTE_*`)

Offsite copy is opt-in and provider-neutral — any S3-compatible endpoint. It engages
only when **all four** of these are set in `secrets/backup.env`:

- `LEARNY_BACKUP_REMOTE_ENDPOINT`
- `LEARNY_BACKUP_REMOTE_ACCESS_KEY`
- `LEARNY_BACKUP_REMOTE_SECRET_KEY`
- `LEARNY_BACKUP_REMOTE_BUCKET`

With all four set, the job creates `<bucket>` if it does not exist (idempotent),
copies each new dump to `<bucket>/db/`, and mirrors the source object bucket
(`LEARNY_BACKUP_SOURCE_BUCKET`, default `learny-sources`) to `<bucket>/objects/`. Leave any of them blank to keep backups **local-only**: the job
completes the local dump, logs `offsite not configured`, and exits 0.

Object mirroring uses `mc mirror` **without `--remove`**: objects deleted in the app
bucket are *not* deleted from the offsite copy, so an accidental deletion in the app
remains recoverable offsite. The trade-off is that the offsite object copy grows
monotonically and is not a byte-for-byte mirror of live state.

### Heartbeat (`LEARNY_BACKUP_HEARTBEAT_URL`)

If `LEARNY_BACKUP_HEARTBEAT_URL` is set, the **nightly dump** job issues a single
`curl` to it as its last step — reached only on a fully successful run (any earlier
failure aborts before it). Point it at a dead-man's-switch monitor to get alerted when
a nightly run stops succeeding. Leave it unset to disable the ping entirely.

The base-backup and WAL-shipping jobs do **not** ping it: a heartbeat on a weekly and
a quarter-hourly schedule cannot share one dead-man's-switch window with a nightly
one. Those two are watched through their container logs
(`docker compose ... logs backup`) and through `pg_stat_archiver` (below).

## Continuous WAL archiving

PostgreSQL writes every change to a write-ahead log before it touches a data file.
The `db` service is configured to copy each **completed** WAL segment out of the
database's own volume and into the shared `wal_archive` volume, from which the backup
sidecar ships and prunes it. That stream of segments is what makes recovery to an
arbitrary moment possible: replaying it forward over an older physical copy of the
database reconstructs any point in between.

The settings live in the `db` service's `command` in `docker-compose.yml`:

- `archive_mode=on` — enables archiving. This one is **postmaster-level**: it takes
  effect only when the database process restarts (see the adoption steps below).
- `archive_command=test ! -f /wal_archive/%f && cp %p /wal_archive/%f` — copies the
  segment, and refuses to overwrite one that is already there. The refusal is the
  point: an archived segment is immutable, so a same-named file that differs means
  something is wrong, and overwriting it would corrupt the replay chain silently.
- `archive_timeout=${LEARNY_WAL_ARCHIVE_TIMEOUT:-900}` — the database closes and
  archives a partially filled segment after this many seconds. On a quiet database a
  segment can otherwise stay open for hours, and everything in it is unrecoverable
  until it closes, so this value is the floor under the recovery point. It is read
  from the compose environment file on the host (`/opt/learny/.env`), not from
  `secrets/backup.env`, because compose interpolates it — and unlike `archive_mode`
  it can be changed with a plain service recreate.

The archive directory is **not** inside `db_data`: it exists to recover the very data
directory it would otherwise be lost with. It is created inside the repo-owned
`learny-postgres` image, owned by the database user, so Docker propagates that
ownership to a fresh named volume and archiving works on a clean deploy with no
host-side `chown`.

That image also ships `/etc/postgresql/pg_hba.conf` (selected with
`-c hba_file=` in the same `command`), which adds the one rule the stock image lacks:
remote physical replication, under the same `scram-sha-256` authentication the
existing remote rule already used. Without it `pg_basebackup` from the sidecar is
refused outright. Because `hba_file` points outside the data directory, it applies to
existing data directories too, not only freshly initialised ones.

### Turning it on for an existing deployment

Both the image and the `command` change, so the database container is recreated
once. `archive_mode` takes effect on exactly that restart:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull db backup
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d db backup
```

Then take the first base backup **immediately**. WAL archived before the first base
backup has nothing to replay onto and can never be used:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm backup base-backup-now
```

Confirm archiving is actually running (not just enabled):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T db \
  psql -U learny -d learny -c \
  "SELECT archived_count, failed_count, last_archived_wal, last_archived_time FROM pg_stat_archiver;"
```

`archived_count` should climb and `failed_count` should stay at 0. A rising
`failed_count` means the archive volume is full or unwritable. PostgreSQL then
**retains** the segment and keeps retrying — WAL is never silently discarded — but
`pg_wal` inside `db_data` grows until the disk fills. That is the disk-pressure
failure mode to watch for in the monitoring stack (`docs/ops/monitoring.md`).

## Physical base backups (`LEARNY_BASEBACKUP_CRON`)

A base backup is a byte-level copy of the whole data directory taken with
`pg_basebackup -Ft -z -X stream --checkpoint=fast`, recorded together with the WAL
position it was taken at. That position is what archived segments replay *onto*. A
`pg_dump` archive cannot serve this role at all — it is a logical export and carries
no WAL position — which is why point-in-time recovery needs this second artifact
family rather than riding on the nightly dump.

Each run writes `learny-base-<UTC stamp>/` under `/backups/base/` containing:

- `base.tar.gz` — the data directory.
- `pg_wal.tar.gz` — the WAL written *during* the copy (`-X stream` opens a second
  replication connection to collect it), so the base is internally consistent on its
  own; the archive supplies everything after it.
- `START_WAL` — the first archived segment a replay from this base needs. This file
  is what makes WAL retention derivable from a base instead of from age.

The job writes to a temporary name and renames onto the final name only on success,
so a failed run leaves no partial artifact and touches no prior base. Pruning runs
only after a successful backup and always exempts the newest base.

The default cadence is weekly, `0 2 * * 0` (Sunday 02:00 UTC). One base per retention
window is enough: more bases only shorten replay time, they do not improve the
recovery point, which the WAL archive already sets. Run one on demand with
`run --rm backup base-backup-now`.

The base backup **shares the nightly dump's lock** (`LEARNY_BACKUP_LOCK`, default
`/tmp/learny-backup.lock`): both are heavy full-database reads competing for the same
disk and the same `/backups` volume, so whichever arrives second exits without
corrupting either artifact. Keep `LEARNY_BASEBACKUP_CRON` clear of
`LEARNY_BACKUP_CRON` — the defaults are 90 minutes apart. A skipped base logs
`another backup run holds the lock`; it is never silent.

WAL shipping takes its **own** lock (`LEARNY_WAL_LOCK`, default
`/tmp/learny-wal.lock`) instead, because it runs every few minutes and conflicts with
neither of the other jobs. Sharing the dump's lock would let one long nightly dump
silently stretch the offsite recovery point.

### The two retentions are coupled

This is the part to read before touching either number.

WAL segments are pruned only when they are **both** older than `LEARNY_WAL_KEEP_DAYS`
(default `14`) **and** no longer required to replay from the oldest *retained* base
backup. **Age alone is never sufficient grounds to delete a segment.** Deleting by age
alone breaks the replay chain of a base that is still inside its own retention window,
and the break is invisible until someone actually attempts a restore — which is the
worst possible moment to discover it.

Concretely: `wal-archive.sh` reads `START_WAL` from the oldest retained base and
deletes only segments that sort strictly below it. Timeline history files (`*.history`)
are never pruned; they are a few bytes each and are what lets a restore resolve which
timeline to follow. If there is no retained base backup at all, **nothing** is pruned —
with no floor to derive from, the fail-safe direction is to keep segments.

Two practical consequences:

- Raising `LEARNY_BACKUP_KEEP_DAYS` (which governs base backups) also extends how far
  back WAL is kept, because the oldest retained base moves back with it.
- **Never delete files from `/wal_archive` by hand.** Retention is not something you
  can reason about one segment at a time.

### Offsite for both new artifacts

Base backups and WAL segments go offsite through the **same four**
`LEARNY_BACKUP_REMOTE_*` variables described above — there is no separate offsite
target. With all four set, base backups are copied to `<bucket>/base/` and archived
segments are mirrored to `<bucket>/wal`; with any of them blank both jobs log
`offsite not configured`, finish locally, and exit 0.

WAL is mirrored **without `--overwrite`** for the same reason `archive_command`
refuses to overwrite: an archived segment is immutable. Shipping happens before
pruning, so a segment can never be deleted locally before it has reached the bucket,
and offsite pruning deletes exactly the segments just pruned locally — never a bulk
age sweep and never `mirror --remove`, either of which would let an emptied local
archive wipe the offsite copy that exists for precisely that case.

The offsite recovery point for WAL is therefore `LEARNY_WAL_SHIP_CRON` (default
`*/15 * * * *`), not zero: segments only leave the host when that job runs. The
database container holds no object-store client and no offsite credential by
decision, so it cannot ship them itself.

## Point-in-time recovery

Restoring to a chosen moment is a **two-command procedure**, which is also how a real
point-in-time recovery is performed: one command prepares a data directory, a second
starts a server on it that replays the archive up to the target.

The `backup` sidecar owns everything that reads the archive — choosing the base,
unpacking it, writing the recovery configuration. The replay itself runs in
`db-restore`, a profile-gated service built from the **same image as `db`**, so the
replayed cluster meets the binaries and extensions it was written with. (A server
without pgvector would start, report a successful recovery, and then fail on the
first read of an embedding column — a `pg_dump` of it included.)

**Step 1 — prepare.** The target must carry an explicit UTC offset (`Z`, `+00`, or
`+00:00`); a bare timestamp is rejected, because `recovery_target_time` is read in the
server's own timezone when the value has none, which would make the boundary mean
different moments in different deployments.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  run --rm backup restore-pitr.sh --target '2026-08-02 14:32:00+00:00' --yes
```

Run it **without `--yes`** first to dry-run: it resolves the base, prints the plan,
and exits non-zero having touched nothing on disk. A target older than every retained
base backup also exits non-zero, naming the `earliest recoverable time` and the base
it came from, so an unreachable target tells you what to try instead.

**Step 2 — replay.** The prepare step prints this command (in production, prepend the
two `-f` flags as everywhere else in this runbook):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --profile restore up -d --wait db-restore
```

`--wait` holds on `db-restore`'s healthcheck, which deliberately demands a server
**out of recovery** rather than merely accepting connections: a server still replaying
— or paused at its target — answers reads and refuses writes, and that is a failed
restore that looks like a healthy one.

### What state this leaves the server in

- The recovered cluster lives on its **own** volume (`pitr_data`, at `/pitr/data`),
  never `db_data`. The live database is untouched: nothing about the running
  deployment changes, and a rehearsal costs only disk.
- It is **promoted and writable** (`recovery_target_action = 'promote'`), not paused —
  so "it accepts writes" is a real signal rather than an ambiguous one.
- `db-restore` runs with `archive_mode=off` and mounts the WAL archive **read-only**,
  so a promoted restore cannot write its new timeline back into the archive the live
  database owns.
- It publishes no host port. Reach it through compose:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec -T db-restore psql -U learny -d learny -c "SELECT count(*) FROM sources;"
```

Repeating step 1 with a different target and bringing `db-restore` up again is how you
narrow in on the right moment — same base, same archive, a different boundary.

To adopt the recovered data into the live database, dump it out of `db-restore` and
restore it into `db` with the logical path documented above:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec -T db-restore pg_dump -U learny -Fc learny > backups/recovered.dump
```

When you are done, remove the restore server. The staged directory stays in
`pitr_data` until the next prepare run replaces it:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --profile restore rm -sf db-restore
```

CI proves this path end-to-end on scratch services on every change: it takes a base
backup, writes a row, records a moment, writes a second row, forces a WAL switch, then
restores to the recorded moment and asserts the first row is present **and the second
is absent** — an assertion a plain whole-archive restore cannot pass. A control run to
a later target then brings the second row back, so the discriminating assertion is
demonstrably able to fail.

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
  pg_restore --single-transaction --clean --if-exists --no-owner -U learny -d learny
```

`--clean --if-exists` drops and recreates objects so the restore is idempotent, and
`--single-transaction` makes it all-or-nothing (it implies `--exit-on-error`): a
partial failure rolls the whole restore back instead of leaving a half-restored
database that exited 0.
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
the `backup_data` volume with `pg_restore --single-transaction --clean --if-exists`
(idempotent, and all-or-nothing — a partial failure rolls back). It is a deliberate,
manual operation — it is never triggered automatically.

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
5. Log in as a known user and open a previously-ingested source; confirm a
   conversation returns grounded answers in both modes (the corpus + objects are
   consistent).
6. Tear the throwaway stack down.

Rehearse point-in-time recovery on the live host too — it is safe by construction,
because it never writes outside `pitr_data`:

1. Pick a moment a few minutes in the past and prepare a restore to it (step 1 above).
2. Bring `db-restore` up (step 2) and confirm `--wait` returns rather than timing out.
3. Query the recovered database for a row you know was written before that moment, and
   one you know was written after it; the second must be absent.
4. `--profile restore rm -sf db-restore` when done.

Doing this after any change to the archive settings is the only way to find a broken
replay chain before an incident does.

## Encryption at rest

Dump archives, base backups, and archived WAL segments are all written unencrypted to
their volumes and, when offsite is configured, uploaded as-is. If your threat model
requires encryption at rest, enable it at the storage layer: server-side encryption on
the offsite S3 bucket, and an encrypted filesystem/volume on the VPS host.
