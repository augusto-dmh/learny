# v5-worker-recovery-hardening Specification (RFC-005 Cycle E)

## Problem Statement

Two recovery gaps are on record. **Workers**: when a worker process dies abruptly (OOM kill, SIGKILL, container stop mid-task) Celery raises `WorkerLostError` in the parent — the task body's `except` blocks never run, so the ingestion job row stays `running` forever with no worker behind it and no signal that anything is wrong. `task_reject_on_worker_lost` is not set (`backend/app/worker/celery_app.py:29-41`), and nothing pins the reliability config that is set, so the whole block can regress silently (`backend/tests/test_worker_logging.py:19` pins exactly one key). **Recovery**: ADR-0024 shipped nightly logical dumps and explicitly deferred WAL archiving ("PITR/WAL archiving remains a recorded future upgrade if the RPO ever tightens", ADR-0024:96-97; `docs/ops/backups.md:186`). The RFC-004 dogfood window is accumulating the study log and notes that are its *own* evidence artifact, and a mid-window loss today costs up to a full day of it.

## Goals

- [ ] A worker lost mid-task surfaces and terminates: the job is redelivered rather than abandoned, and a job that keeps killing its worker reaches a terminal `failed` state instead of looping forever.
- [ ] The worker's reliability configuration is pinned by tests, so the durability contract cannot regress unobserved.
- [ ] Point-in-time recovery to an arbitrary moment within the retention window, proven end-to-end by CI on scratch services — not by trust.
- [ ] The `torchvision`/`+cpu` blockage recorded in AD-102 is re-probed against current pins and the outcome recorded.

## Out of Scope

| Feature | Reason |
|---|---|
| Replacing the nightly logical dump | Physical base + WAL and logical dumps are complementary; the dump stays as the version-portable path (ADR-0024) |
| Celery beat / a periodic reaper task | New scheduled infrastructure; the redelivery + attempts cap closes the observed failure without it |
| Streaming replication / a standby server | Availability, not recovery; ADR-0008 keeps the deploy single-host |
| pgBackRest / wal-g / any backup vendor | Provider neutrality (ADR-0024); stock `archive_command` + `pg_basebackup` need no new dependency |
| Flower / an external Celery monitor | New public surface + third-party image; ADR-0017/0023 single-public-surface holds |
| A slim pdf-worker image | RFC-005 Cycle E scopes this as "re-probe and record only" |
| Redis persistence/backup | Transport only by decision (ADR-0014, ADR-0024) |
| Broker-level heartbeat tuning (`broker_heartbeat`) | AMQP-only in Celery; inert on the Redis transport this project uses — see assumption below |

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
|---|---|---|---|
| WAL archiving alone is not a recovery chain | Ship a **physical base backup** (`pg_basebackup`) alongside WAL archiving | WAL replay needs a physical base with a known WAL position; a `pg_dump` archive has none, so "WAL on top of the nightly dump" (RFC wording) would be an unusable promise | auto (ship-cycle) |
| `broker_heartbeat` is the Celery-native liveness knob | **Not set** — it is AMQP-only and inert on Redis; liveness comes from the existing `celery inspect ping` healthchecks plus worker-lost rejection | Setting an inert knob would be verification theatre; the honest detection layer is redelivery + a durable attempts cap | auto (ship-cycle) |
| `task_reject_on_worker_lost=True` is safe on its own | **No** — it is paired with a durable attempts cap | A requeued message keeps its `retries` header, so `self.request.retries` never advances across worker-lost redeliveries; only the PostgreSQL `attempts` column survives, making it the sole viable poison-pill guard (ADR-0014: PostgreSQL is source of truth) | auto (ship-cycle) |
| A fresh named volume is writable by the postgres user | **No** — the WAL archive directory must exist in the image so Docker propagates ownership | Docker creates a named volume root-owned when the mount path is absent from the image; `archive_command` runs as `postgres` and would fail | auto (ship-cycle); verified in-phase |
| The stock image accepts remote replication connections for `pg_basebackup` | Verify empirically in-phase; if `pg_hba` rejects it, extend the db `command` rather than baking credentials | Unverified upstream default — must not be assumed (knowledge chain step 5) | **verify in-phase** |
| Default WAL retention | `LEARNY_WAL_KEEP_DAYS` default 14, matching `LEARNY_BACKUP_KEEP_DAYS` | One retention story for the operator; WAL is pruned only against a *retained base backup*, never by age alone | auto |
| Base backup cadence | Weekly, `LEARNY_BASEBACKUP_CRON` default `0 2 * * 0` | A base per retention window bounds replay time; nightly physical backups would multiply volume for no RPO gain | auto |

**Open questions:** none — all resolved or logged above.

## User Stories

### P1: A lost worker surfaces instead of hanging ⭐ MVP

**User Story**: As the operator, I want a job whose worker died to be retried and, if it keeps killing workers, to fail terminally — so a stalled phase never sits in `running` forever waiting for a manual nudge.

**Acceptance Criteria**:

1. (WRK-01) WHEN the Celery app configuration is read THEN it SHALL set `task_reject_on_worker_lost=True`, so a task whose worker died abruptly is redelivered rather than left with its job row in a non-terminal state.
2. (WRK-02) WHEN an ingestion job is claimed and its `attempts` have already reached `LEARNY_INGESTION_MAX_ATTEMPTS` THEN the claim SHALL NOT start another run; the job SHALL be transitioned to terminal `failed` with the fixed non-secret error text, a `failed` event SHALL be appended, and the source status SHALL be synced — so a task that deterministically kills its worker terminates instead of redelivering forever.
3. (WRK-03) WHEN an ingestion job is claimed with `attempts` below the cap THEN it SHALL run exactly as today (`queued`/`running` → `running`, `attempts+1`), and a missing or already-terminal job SHALL remain an idempotent no-op.
4. (WRK-04) WHEN a job is claimed for an attempt after its first THEN the worker SHALL emit one WARNING-level structured record naming the job, source, and attempt number — so a silently restarting phase is visible in the logs the monitoring stack already collects.
5. (WRK-05) WHEN `LEARNY_INGESTION_MAX_ATTEMPTS` is unset THEN it SHALL default to 5, and a value below 1 SHALL be rejected at settings validation.
6. (WRK-06) WHEN the worker's reliability configuration is read THEN a test SHALL pin `task_acks_late`, `worker_prefetch_multiplier`, `task_time_limit`, `task_soft_time_limit`, `task_reject_on_worker_lost`, and the broker `visibility_timeout`, asserting the invariant that `visibility_timeout` exceeds `task_time_limit` (a shorter timeout would redeliver a healthy long-running job mid-run).

**Independent Test**: drive `begin_run` at, below, and above the cap against the real DB and assert the resulting job status, event trail, and log record; assert the config keys directly.

### P1: Point-in-time recovery

**User Story**: As the operator, I want to restore the database to an arbitrary moment inside the retention window, so a mid-window mistake or corruption costs minutes of data rather than up to a day.

**Acceptance Criteria**:

7. (PITR-01) WHEN the `db` service starts THEN it SHALL run with `archive_mode=on` and an `archive_command` that copies each completed WAL segment into the WAL-archive volume, refusing to overwrite an existing segment, and SHALL set a bounded `archive_timeout` so an idle database still closes segments.
8. (PITR-02) WHEN the WAL-archive volume is mounted THEN its directory SHALL be writable by the database's runtime user without any host-side chown, and a test SHALL assert the mechanism that guarantees it.
9. (PITR-03) WHEN the base-backup job runs THEN it SHALL write a `pg_basebackup` archive to the backup volume under a timestamped name, writing to a temp name and renaming only on success, leaving prior base backups untouched on failure.
10. (PITR-04) WHEN offsite is configured (the same four `LEARNY_BACKUP_REMOTE_*` variables) THEN new base backups and newly archived WAL segments SHALL be copied offsite; WHEN it is not configured THEN both SHALL complete locally and log the existing explicit "offsite not configured" notice and exit 0.
11. (PITR-05) WHEN WAL segments are pruned THEN pruning SHALL never remove a segment required to replay from the oldest **retained** base backup — age alone SHALL NOT be sufficient grounds to delete a segment.
12. (PITR-06) WHEN base backups are pruned THEN the newest base backup SHALL always be exempt, and pruning SHALL NOT run if the current base backup failed.
13. (PITR-07) WHEN the operator runs the shipped point-in-time restore with a target timestamp and `--yes` THEN it SHALL restore the chosen base backup, configure WAL replay to that target, and bring the database up recovered to that point; WHEN `--yes` is absent THEN it SHALL print what it would do and exit non-zero without touching any data directory.
14. (PITR-08) WHEN a point-in-time restore is requested with a target older than every retained base backup THEN it SHALL exit non-zero naming the earliest recoverable time, without modifying any data directory.
15. (PITR-09) WHEN CI runs THEN it SHALL prove point-in-time recovery end-to-end on scratch services: take a base backup, write a row, record a timestamp, write a second row, force a WAL switch, then restore to the recorded timestamp and assert the first row is present and the second is absent — a drill that a whole-archive restore cannot pass.
16. (PITR-10) WHEN backup credentials and settings are inspected THEN every new value SHALL come from the existing secrets files and `.env.production.example` SHALL document each new variable; no credential SHALL appear in compose files, workflows, or any image.

**Independent Test**: the CI drill in AC 15 is the proof; the discriminating assertion is that the second row is absent, which distinguishes true PITR from a plain restore.

### P1: Runbook and decision record

17. (PITR-11) WHEN `docs/ops/backups.md` is read THEN it SHALL document WAL archiving, base-backup cadence, the combined retention rule, the point-in-time restore procedure, and SHALL replace the "Point-in-time recovery (WAL archiving) is out of scope" statement; `test_ops_docs` SHALL assert the section's key strings.
18. (PITR-12) WHEN the cycle completes THEN an ADR SHALL record the PITR topology (physical base + archived WAL, stock-image constraint and how it was resolved, retention coupling, provider-neutral offsite) and the worker-lost policy including why the durable attempts cap is what makes rejection safe; it SHALL state that it supersedes ADR-0024's deferral of PITR.

### P2: pdf-worker re-probe

19. (PROBE-01) WHEN the `torchvision`/`torch` resolution is re-probed against current pins THEN the outcome SHALL be recorded with evidence (the resolved versions and the exact constraint that admits or excludes a `+cpu` local version); if still blocked, the record SHALL state so and **no** lockfile or pin change SHALL be made.

## Edge Cases

- WHEN the WAL archive volume is full or unwritable THEN `archive_command` fails, PostgreSQL retains the segment and retries — WAL SHALL NOT be silently discarded (documented as the disk-pressure failure mode the monitoring stack surfaces).
- WHEN a base backup runs while a scheduled dump holds the backup lock THEN the second job SHALL exit without corrupting either artifact.
- WHEN the offsite endpoint is configured but unreachable THEN local artifacts are kept and the job exits non-zero (configured-but-failing ≠ not configured — the existing convention).
- WHEN a job reaches the attempts cap THEN the durable failure text SHALL remain the fixed non-secret summary; no exception detail SHALL reach the owner-readable field.
- WHEN `attempts` is already above the cap (cap lowered between runs) THEN the claim SHALL still terminate the job rather than run it.

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
|---|---|---|---|
| WRK-01..06 | P1 worker liveness | A | Pending |
| PITR-01..02 | P1 recovery (archiving substrate) | B | Pending |
| PITR-03..06, PITR-10 | P1 recovery (base backup + retention) | B | Pending |
| PITR-07..09 | P1 recovery (restore + CI proof) | C | Pending |
| PITR-11..12 | P1 runbook + decision record | D | Pending |
| PROBE-01 | P2 pdf-worker re-probe | D | Pending |

**Coverage:** 19 total, all mapped to phases A–D.

## Success Criteria

- [ ] CI proves recovery to a point in time, with the discriminating assertion that post-target data is absent.
- [ ] A job that repeatedly loses its worker reaches terminal `failed` rather than redelivering indefinitely.
- [ ] Full backend suite green from the 2077-test baseline plus the new tests; `make lint` clean.
- [ ] No new Python runtime dependency, no new backup vendor, no new public listener.
