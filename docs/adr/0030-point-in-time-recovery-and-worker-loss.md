# ADR-030: Point-In-Time Recovery Topology And Worker-Loss Policy

- **Date**: 2026-08-02
- **Status**: Accepted (2026-08-02, rides the implementing cycle's merge gate)
- **Deciders**: Augusto, Claude
- **Tags**: operations, backups, recovery, postgres, docker, celery, workers

## Context and Problem Statement

Two recovery gaps were on record, one at each end of the stack.

**Recovery.** ADR-0024 shipped nightly logical dumps and explicitly deferred the
rest: "PITR/WAL archiving remains a recorded future upgrade if the RPO ever
tightens". It tightened. The deployment is now accumulating a study log and notes
that are themselves the artifact the current phase exists to produce, and a
mid-afternoon mistake or corruption costs up to a full day of it — the exact case a
nightly dump cannot answer.

**Workers.** When a worker process dies abruptly — an OOM kill, a SIGKILL, a
container stopped mid-task — Celery raises `WorkerLostError` in the parent process.
No `except` in the task body ever runs, so nothing writes a terminal state. Without
rejection the message is simply dropped, and the ingestion job row says `running`
forever with no worker behind it and no signal that anything is wrong.
`task_reject_on_worker_lost` was unset, and a single key of the reliability block
was asserted anywhere, so the whole durability contract could have regressed
silently.

This ADR records the topology and the policy that close both, including the
constraints that were discovered empirically during the build and forced the shape
they took.

## Decision Drivers

- Recovery to an arbitrary moment inside the retention window, **proven by CI**, not
  asserted. A backup mechanism nobody has watched fail is not yet evidence.
- Provider neutrality (ADR-0024): stock PostgreSQL facilities, no backup vendor.
- The database container must gain no object-store client and no backup credential.
- A recovery path that works only for tables without embeddings is not a recovery
  path.
- The single-public-surface invariant holds (ADR-0017, ADR-0023): no new listener.
- A job whose worker keeps dying must reach a terminal state without a human.
- PostgreSQL is the source of truth for durable job state (ADR-0014).

## Decision Outcome

### Two artifact families, not one

Point-in-time recovery ships as a **weekly physical base backup**
(`pg_basebackup -Ft -z -X stream --checkpoint=fast`) plus **continuous WAL
archiving**, *complementing* the nightly logical dump rather than replacing it.

This is forced, not preferred. WAL replay needs a physical base carrying a known WAL
position to replay onto; a `pg_dump -Fc` archive is a logical export and has none.
"WAL archiving on top of the nightly logical dump" — the shape the proposal
described — is therefore not implementable as written: the archived segments would
have nothing to attach to. Shipping the base is what makes the deliverable real
instead of a promise that fails on first use. The logical dump stays because it is
the version-portable, selectively restorable path, which the physical base (locked
to its PostgreSQL major version) is not.

Each base records the first WAL segment a replay from it needs, beside the archive
itself. That file is the input to the retention rule below.

### The archive is written to a shared volume, and the sidecar owns everything past it

`archive_command` copies each completed segment into a volume shared by `db` and the
backup sidecar. All offsite shipping and all pruning happen in the sidecar.

The boundary is the reason: `archive_command` runs inside the database container,
which has no object-store client and no offsite credential. Archiving straight to S3
would require putting both there, moving backup secrets into the database service
for a marginal gain. The accepted cost is that WAL reaches the offsite bucket on the
sidecar's schedule (default every 15 minutes) rather than continuously, so the
offsite recovery point is that interval, not zero. It is stated in
`docs/ops/backups.md` rather than left to be discovered.

### A thin repo-owned PostgreSQL image, for two reasons both found by probing

`FROM pgvector/pgvector:pg16`, adding exactly two things. Neither was in the plan;
both are load-bearing.

**Volume ownership.** Docker creates a fresh named volume root-owned when the mount
path is *absent* from the image, and copies the image path's ownership when it is
*present*. `archive_command` runs as the unprivileged database user, so an archive
volume mounted at a path the image never declared fails at runtime with a permission
error far from its cause — on a clean deploy, which is exactly when nobody is
looking. Creating the directory in the image is what makes the volume writable, with
no entrypoint wrapper and no host-side `chown`. Verified on a fresh empty volume
(`owner=postgres:postgres mode=700`), then by archiving for real.

**Replication authentication.** The stock image **refuses remote replication
connections.** Every replication rule its entrypoint generates is local-socket or
loopback, and PostgreSQL's `all` database keyword deliberately does not match
physical replication connections — so `pg_basebackup` from the sidecar matches no
rule whatsoever and fails with `no pg_hba.conf entry for replication connection`.
This was assumed to be fine going in and is not; it was verified empirically before
anything was built on it.

The resolution is a `pg_hba.conf` shipped in the image and selected with
`-c hba_file=`, reproducing the stock file and adding one rule —
`host replication all all scram-sha-256` — i.e. remote replication under the *same*
authentication the existing remote rule already used. Authentication is weakened
nowhere: `trust` stays confined to the in-container local socket and loopback,
exactly as the stock image had it, and no credential is baked into the image.

`hba_file` was chosen over an entrypoint init script that appends to the generated
file because that hook runs only on a **first** initialisation. Every
already-deployed data directory — including the live one — would otherwise have
remained silently unable to serve a base backup, which is a failure that surfaces
only when a backup is first attempted. `hba_file` points outside the data directory
and applies on restart, so it covers both cases.

`archive_mode` itself is supplied via the compose `command`, keeping the image free
of policy.

### Retention is coupled across the two families

A WAL segment is pruned only when it is **both** past its retention window **and** no
longer required to replay from the oldest *retained* base backup. **Age alone is
never sufficient grounds to delete a segment.**

Pruning by age alone silently breaks the replay chain of a base that is still inside
its own retention window. Nothing reports the break; it surfaces the first time
someone attempts a restore, which is the worst available moment — and it is precisely
the class of defect this work exists to remove. With no retained base at all, nothing
is pruned: with no floor to derive from, the fail-safe direction is to keep segments.

The cost is that the operator cannot reason about WAL retention in isolation, so the
coupling is stated explicitly in the runbook rather than implied by the code.

### The restore is split, and it is two commands

The sidecar **prepares** the recovery — choosing the base that precedes the target,
unpacking it, writing the recovery configuration — and a profile-gated `db-restore`
service, built from the **same image as `db`**, performs the replay.

The obvious reading of the archive-boundary decision above was that the sidecar would
also run the recovering server. It cannot, and the assumption that its PostgreSQL
client package supplies a server was wrong: `postgres`, `pg_ctl`, and `initdb` are all
absent from it (verified). Adding Alpine's server package would have built, and would
have been a trap — that server carries no `vector.so`, so a recovered Learny cluster
would start, replay, report success, and then fail on the first read of an embedding
column, including any `pg_dump` of it, since dumping calls the type's output function.

The split keeps the archive-reading half where the credentials already are and the
replay where the right binaries and extensions are. The database image still gains no
object-store client and no credential, and `db-restore` mounts the archive
**read-only** and runs with `archive_mode=off`, so a promoted restore cannot write its
new timeline back into the archive the live database owns.

Two consequences are stated rather than left to be discovered. The restore is a
**two-command procedure** — prepare, then bring up — which is also how a real
point-in-time recovery is performed; the prepare step prints the second command. And
the staging area is its own volume, never the live data volume: a sidecar running
cron jobs around the clock must not be able to overwrite the database it exists to
protect, and a rehearsal then costs only disk. Recovery promotes to a writable
database rather than pausing at the target, so "it accepts writes" is a real signal
instead of an ambiguous one, and the restore server's healthcheck demands a server
*out of* recovery — one still replaying answers reads and refuses writes, which is a
failed restore that otherwise looks like a healthy one.

### The proof: three writes and two targets

CI drills the whole chain on scratch services: base backup, write, record a moment,
write again, force a WAL switch, restore to the moment, assert the first row is
present **and the second is absent**. The second assertion is the one that carries the
claim — a plain whole-archive restore passes the first and fails the second.

The drill uses three writes and two targets rather than the obvious two and one,
because the control run that proves the discriminating assertion *can* fail did not
merely fail — it crashed the server. PostgreSQL confirms it reached a time target only
by seeing a committed record past it, so a target after the last archived commit is
unreachable and recovery refuses to finish (`recovery ended before configured recovery
target was reached`) rather than quietly stopping at the end of the archive. That is
the right behaviour, and it is why a target beyond the window fails loudly instead of
silently under-restoring — but it also means the control needs a third write after the
control target, or the control cannot run at all. Restoring the same base and the same
archive to the two targets yields different row sets, which is what makes the
assertion evidence.

Independently confirmed by mutation: deleting the emitted `recovery_target_time`
degrades the implementation into a whole-archive restore, and the discriminating
assertion then fails.

### Worker-loss policy: rejection, made safe by a durable cap

`task_reject_on_worker_lost=True`, so a task whose worker died is requeued instead of
dropped — **paired** with a durable attempts cap enforced where an ingestion job is
claimed, defaulting to 5 and rejected below 1 at settings validation.

The pairing is the whole decision. Rejection alone converts a hang into an infinite
loop: a job that deterministically kills its worker (an OOM on one pathological
document) would redeliver forever, which is strictly worse than the failure it
replaces. And the cap cannot be Celery's own retry counter: a message requeued after
`WorkerLostError` keeps its original delivery headers, so that counter never advances
across worker-lost redeliveries. The job row's `attempts` column, incremented when the
job is claimed, is the only counter that survives one — which also puts the guard
where ADR-0014 already puts job state. A job at or above the cap is not started again;
it is transitioned to terminal `failed` with the same fixed, non-secret error text the
task's own failure path writes, its `failed` event appended and the source status
synced, so a job that died with its worker still ends in a state its owner can read.

The guard lives in the application service, so a future task that claims work without
going through that seam would bypass the cap. Accepted: every ingestion path claims
through it today.

Rejected alternatives: rejection with no cap (above); a periodic reaper task, which
needs new scheduled infrastructure and only marks jobs dead after the fact instead of
recovering them.

### Liveness detection, and one setting deliberately not set

Container liveness stays with the `celery inspect ping` healthchecks both worker
services already carried — that was not the gap. `broker_heartbeat` is **deliberately
not set**: it is an AMQP setting and is inert on the Redis transport this deployment
uses, so setting it would look like coverage while detecting nothing.

The genuinely missing signal was that a silently restarting job left no trace at all
beyond a row that kept saying `running`. One WARNING record on every re-claimed
attempt, naming the job, source, and attempt number, puts it in the log stream the
monitoring stack already collects.

### The durability configuration is pinned

Every reliability-relevant Celery key is now asserted by test — including the broker
visibility timeout against the task time limit as a **relationship**, not two
independent literals. If the visibility timeout were the shorter of the two, a
*healthy* long-running ingestion would be redelivered while still running and two
workers would process the same job. That ordering, not either number alone, is the
invariant; before this, only the logging key was pinned, and every setting the
redelivery story rests on could be changed with nothing failing until the day a worker
died.

## Relationship to ADR-0024

ADR-0024 stands, with one sentence superseded: "PITR/WAL archiving remains a recorded
future upgrade if the RPO ever tightens" is replaced by this ADR. Everything else it
decided is unchanged and still in force — the nightly logical dump and its
temp-then-rename write, the retention window and newest-archive exemption, the
four-variable offsite gate, the heartbeat, the logical restore script and its CI
roundtrip, the netdata monitoring stack and its loopback-only boundary, and Redis
remaining explicitly un-backed-up. The base backup shares the nightly dump's lock, so
the two never contend; WAL shipping takes its own, because it runs every few minutes
and sharing would let one long dump stretch the offsite recovery point.

## Consequences

- Positive: recovery to an arbitrary moment inside the retention window, proven on
  every CI run by an assertion a whole-archive restore cannot pass; a rehearsal that
  is safe to run against the live host because it writes only to its own volume; a
  lost worker that ends in a readable terminal state instead of a permanent `running`;
  a durability contract that can no longer regress unobserved.
- Negative: two artifact families to retain and reason about, with coupled retention
  the operator must understand before changing either number; a fifth repo-owned image
  in the deploy matrix, whose base tag is one more thing to track; one more volume, and
  a staged restore that costs disk; adopting archiving on an existing deployment
  requires one database restart, because `archive_mode` is postmaster-level.
- The physical base is locked to its PostgreSQL major version. A major-version upgrade
  invalidates existing bases for replay; the logical dump remains the path across one,
  which is part of why it stays.
- Offsite WAL protection is bounded by the shipping interval, not by the archive
  interval. An operator who needs a tighter offsite recovery point tightens that cron,
  and pays in requests rather than in correctness.
