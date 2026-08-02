# v5-worker-recovery-hardening Context (RFC-005 Cycle E)

Decisions taken under the ship-cycle auto-decision rule: each option set carries a
why-recommend and a why-not, the recommended option was taken, and the choice is
mirrored into `.specs/project/STATE.md` as an `AD-NNN` row. None met the escalation
rule (no product-direction change, no new external dependency, no undefendable pick).

## D-1 — Slice shape → AD-249

**Chosen: backend worker config + application guard, plus ops/infra (compose, backup image, CI, docs). No frontend.**

- *Chosen — worker + ops slice.* Why: the cycle's whole subject is process death and database recovery; neither has a user-visible surface, and RFC-005 §Sequencing requires Cycles A–E to stay invisible to the dogfooding author. Why not: a sixth consecutive backend-only slice further departs from AD-010's full-vertical-slice cadence — flagged at the merge gate, as the prior departures were.
- *Rejected — add an operator-facing job-health page.* Why it was tempting: it would make stalls visible in the product. Why not: it is a new studied surface inside the open dogfood window, which RFC-005 explicitly forbids for Cycles A–E.

## D-2 — Worker-lost policy → AD-250

**Chosen: `task_reject_on_worker_lost=True`, made safe by a durable attempts cap enforced in `RunIngestion.begin_run`.**

- *Chosen — reject + durable cap.* Why: rejection is what turns an abandoned `running` row into a redelivery, and the cap is what stops a deterministic worker-killer (an OOM on one pathological PDF) from redelivering forever. Critically, `self.request.retries` cannot serve as that cap: a message requeued after `WorkerLostError` keeps its original delivery headers, so the Celery-side counter never advances across worker-lost redeliveries. The `attempts` column incremented in `begin_run` (`backend/app/application/ingestion.py:185`) is the only counter that survives, and putting the guard there matches ADR-0014 (PostgreSQL is source of truth for job state). Why not: the guard lives in the application service, so a task that bypasses `begin_run` would bypass the cap — accepted because every ingestion path already claims through it.
- *Rejected — enable rejection alone.* Why not: converts a hang into an infinite loop; strictly worse for the exact failure the cycle exists to fix.
- *Rejected — leave rejection off and add a reaper.* Why not: a reaper needs celery-beat (new scheduled infrastructure) and only marks jobs dead after the fact instead of recovering them.

## D-3 — Liveness detection layer → AD-251

**Chosen: rely on the existing `celery inspect ping` container healthchecks; add no `broker_heartbeat`; add a WARNING record on every re-claimed attempt.**

- *Chosen.* Why: the survey found both `worker` and `worker-pdf` already carry `inspect ping` healthchecks (`docker-compose.yml:98-104`, `:131-137`), so container liveness is not the gap the RFC assumed. `broker_heartbeat` is documented as AMQP-only and is inert on the Redis transport, so setting it would be verification theatre. The genuine missing signal is that a job silently restarting leaves no trace, which one WARNING record fixes at near-zero cost using the structured-logging substrate AD-041 already established. Why not: log-based surfacing depends on the operator reading logs or the monitoring stack alerting on them; no active notification is added.
- *Rejected — set `broker_heartbeat` anyway "for completeness".* Why not: an inert setting that appears to satisfy the RFC bullet is exactly the kind of false coverage this project's verification discipline exists to prevent.

## D-4 — Reliability-config regression pin → AD-252

**Chosen: one test pinning the durability-relevant Celery keys, including the `visibility_timeout > task_time_limit` relationship as an asserted invariant.**

- *Chosen.* Why: today only `worker_hijack_root_logger` is pinned (`backend/tests/test_worker_logging.py:19`); the settings the whole redelivery story rests on can be changed with no test failing, and the timeout ordering is a silent-corruption hazard (a shorter visibility timeout redelivers a healthy long-running ingestion mid-run, duplicating work). Why not: pinning configuration values makes deliberate future tuning a two-file change — accepted, since that is the point.

## D-5 — PITR chain shape → AD-253

**Chosen: physical base backup (`pg_basebackup`) on a weekly cadence + continuous WAL archiving, complementing (not replacing) the nightly logical dump.**

- *Chosen.* Why: WAL replay requires a physical base with a known WAL position. The RFC's phrasing ("WAL archiving on top of ADR-0024's nightly logical dump") is not implementable as written — a `pg_dump -Fc` archive carries no WAL position, so archived segments would have nothing to replay onto. Shipping the base backup is what makes the deliverable real rather than a promise that fails on first use. Keeping the logical dump preserves the version-portable, selective restore path ADR-0024 chose. Why not: two artifact families to retain and reason about, and the physical base is PostgreSQL-major-version-locked.
- *Rejected — WAL archiving alone.* Why not: unusable; would ship an untestable recovery claim (and PITR-09's drill would have been impossible to write, which is how the gap surfaced).
- *Rejected — replace logical dumps with physical only.* Why not: discards version portability and per-object restore for no recovery gain.

## D-6 — Where `archive_command` writes → AD-254

**Chosen: archive to a dedicated volume shared by `db` and the `backup` sidecar; the sidecar owns all offsite shipping and pruning.**

- *Chosen.* Why: `archive_command` runs inside the db container, which has no `mc` client and no offsite credentials; giving it any would put backup secrets in the database service. Writing to a shared volume keeps the db container credential-free and leaves every offsite decision in the sidecar that already owns them (AD-098/AD-099). Why not: WAL reaches the offsite bucket on the sidecar's schedule rather than continuously, so the offsite RPO is the sidecar interval, not zero — documented in the runbook.
- *Rejected — archive directly to S3 from `archive_command`.* Why not: requires a client and credentials inside the database container, widening the secret blast radius for a marginal RPO gain.

## D-7 — Postgres image and the volume-ownership trap → AD-255

**Chosen: a thin repo-owned Postgres image (`FROM pgvector/pgvector:pg16`) that creates the archive directory owned by the database user; `archive_mode` supplied via the compose `command`.**

- *Chosen.* Why: Docker creates a fresh named volume root-owned when the mount path is absent from the image, and `archive_command` runs as the unprivileged database user — so archiving would fail at runtime on a clean deploy with a permissions error far from its cause. Creating the directory in the image makes Docker propagate its ownership to the volume. It also matches the precedent already set by the repo-owned `learny-backup` image (AD-098) rather than inventing a new pattern. Why not: a fifth image in the deploy matrix, and the base image tag must now be tracked in one more place.
- *Rejected — chown in a wrapper command before the entrypoint drops privileges.* Why not: overrides the upstream entrypoint's contract and re-runs on every boot; a subtle wrapper is harder to verify than a one-line image.
- *Rejected — archive inside the existing data volume.* Why not: the archive would be lost with the very data directory it exists to recover.

## D-8 — WAL retention rule → AD-256

**Chosen: WAL segments are pruned only when no longer required by the oldest retained base backup; age is never sufficient grounds on its own.**

- *Chosen.* Why: pruning WAL by age alone silently breaks the replay chain of a base backup that is still inside its retention window — the failure is invisible until a restore is attempted, which is the exact class of defect this cycle exists to eliminate. Why not: retention is coupled across two artifact families, so the operator cannot reason about WAL retention in isolation — stated explicitly in the runbook.

## T5 — replication connectivity finding

**The stock `pgvector/pgvector:pg16` image REFUSES a remote replication connection.**
Verified empirically, not assumed. The assumption in `spec.md` ("verify in-phase") is
now closed: the negative branch is the real one, and Phase B had to resolve it.

**Evidence 1 — the generated `pg_hba.conf`.** Ran the stock image with the project's
`POSTGRES_USER/DB` and dumped its rules:

```
$ docker exec t5probe-db cat /var/lib/postgresql/data/pg_hba.conf   # comments stripped
local   all             all                                     trust
host    all             all             127.0.0.1/32            trust
host    all             all             ::1/128                 trust
local   replication     all                                     trust
host    replication     all             127.0.0.1/32            trust
host    replication     all             ::1/128                 trust
host all all all scram-sha-256
```

Every `replication` rule is local-socket or loopback. The only remote rule uses the
`all` database keyword, and PostgreSQL's `all` deliberately **does not match physical
replication connections** — so a `pg_basebackup` from another container matches no
rule whatsoever.

**Evidence 2 — the connection itself.** From a second container on a shared network:

```
$ docker run --rm --network t5probe-net -e PGPASSWORD=learny pgvector/pgvector:pg16 \
    pg_basebackup -h t5probe-db -U learny -D /tmp/bb -Ft -X fetch
pg_basebackup: error: connection to server at "t5probe-db" (172.23.0.2), port 5432 failed:
FATAL:  no pg_hba.conf entry for replication connection from host "172.23.0.3", user "learny",
no encryption
```

**Resolution taken.** `deploy/postgres/pg_hba.conf`, shipped in the repo-owned image
(AD-255) and selected with `-c hba_file=` from the compose `command`. It reproduces the
stock file verbatim and adds exactly one rule —
`host replication all all scram-sha-256` — i.e. remote replication under the *same*
authentication the remote rule already used. No credential is baked into the image; the
password still arrives via `POSTGRES_PASSWORD` from the env_file. Authentication is not
weakened anywhere: `trust` remains confined to the in-container local socket and
loopback, exactly as the stock image already had it.

`hba_file` was chosen over a `/docker-entrypoint-initdb.d` script that appends to
`$PGDATA/pg_hba.conf` because that hook only ever runs on a **first** initialisation:
every already-deployed data directory — including the live VPS one — would silently
remain unable to serve a base backup. `hba_file` points outside `PGDATA` and takes
effect on restart, so it covers both cases.

**Evidence 3 — the resolution works, on a fresh AND a pre-existing data directory.**

```
# fresh volume, repo-owned image:
$ pg_basebackup -h t5probe-db2 -U learny -D /tmp/bb -Ft -z -Xfetch -P   →  rc=0
$ pg_basebackup -h t5probe-db2 -U learny -D /tmp/bb3 -Ft -z -X stream   →  rc=0
# data dir initialised by the STOCK image, then started by the repo-owned image:
$ pg_basebackup -h t5probe-upg -U learny -D /tmp/bb2 -Ft -z -Xfetch     →  rc=0
```

`-X stream` opens a *second* replication connection and also succeeds, so the shipped
job can use it (it bundles the WAL the base needs into `pg_wal.tar.gz`).

**Evidence 4 — AD-255's ownership mechanism, proven rather than trusted.** With
`/wal_archive` created in the image and a *fresh, empty* named volume mounted over it:

```
$ docker exec t5probe-db2 stat -c '%n owner=%U:%G mode=%a' /wal_archive
/wal_archive owner=postgres:postgres mode=700
```

Docker propagated the image path's ownership into the empty volume, so the
unprivileged `postgres` user can archive with no host-side chown. Archiving then ran
for real — `pg_stat_archiver` reported `archived_count=6, failed_count=0` with the
segments present in the volume — and the no-overwrite guard was confirmed to fail
closed (`test ! -f … && cp …` returns 1 on an existing segment, leaving it byte-identical,
which makes PostgreSQL retain and retry rather than silently corrupt the chain).

**Evidence 5 — no new package in the backup image.** Alpine's already-installed
`postgresql16-client` ships `pg_basebackup` (16.14), and busybox `tar` can extract
`backup_label` out of `base.tar.gz` to read `START WAL LOCATION` — so the retention
predicate needs no new dependency:

```
$ docker run --rm alpine:3.22 sh -c 'apk add postgresql16-client && which pg_basebackup'
/usr/bin/pg_basebackup
$ busybox tar -xzOf base.tar.gz backup_label
START WAL LOCATION: 0/C000028 (file 00000001000000000000000C)
```

All probe containers, volumes, networks, and the probe image were removed afterwards;
the `learny` compose project's `db`/`redis`/`minio` were never touched.

## D-10 — Lock sharing for the base backup (in-phase)

**Chosen: `base-backup.sh` shares `LEARNY_BACKUP_LOCK` with the nightly dump;
`wal-archive.sh` takes its own separate lock.**

- *Base backup shares the dump's lock.* Why: `spec.md`'s edge case is explicit — "WHEN a
  base backup runs while a scheduled dump holds the backup lock THEN the second job SHALL
  exit without corrupting either artifact" — and both jobs are heavy full-database reads
  competing for the same disk and the same `/backups` volume. Why not: a base backup that
  collides with a dump is skipped, leaving that week without a new base. Mitigated by
  non-overlapping defaults (`0 2 * * 0` vs `30 3 * * *`, 90 minutes apart) and by the
  skip being logged rather than silent.
- *WAL shipping takes its own lock.* Why: it runs every 15 minutes, so sharing the dump's
  lock would let one nightly dump silently blow the offsite RPO, and its work (copying
  and pruning finished segments) conflicts with neither `pg_dump` nor `pg_basebackup`. Its
  own lock still prevents it from overlapping *itself* when a mirror runs long. Why not:
  two lock files instead of one for the operator to know about — documented in the runbook.

## D-9 — Execution shape → AD-257

**Chosen: four phases, one worker per phase, all Opus; fresh Verifier on Fable.**

- *Chosen.* Why: every phase carries a correctness invariant — A the idempotency and terminal-state guard, B retention ordering and volume permissions, C a restore path whose only real proof is the drill, D a code-fact record (and project memory records Haiku fabricating env-var names in exactly this kind of runbook). No unit passes the four-condition Haiku-safe test. Fable for the Verifier follows the ship-cycle candidate-upshift rule and the precedent set in `v6-answer-experience`. Why not: all-Opus is the more expensive configuration; justified because a weak worker's slip here is a recovery path that appears to work and fails when actually needed.
- *Phase order*: A is independent; B must precede C (nothing to restore without an archiving substrate); D is last because the ADR records what B and C actually did, and the probe is independent.
