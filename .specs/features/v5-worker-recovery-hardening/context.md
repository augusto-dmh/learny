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

## D-9 — Execution shape → AD-257

**Chosen: four phases, one worker per phase, all Opus; fresh Verifier on Fable.**

- *Chosen.* Why: every phase carries a correctness invariant — A the idempotency and terminal-state guard, B retention ordering and volume permissions, C a restore path whose only real proof is the drill, D a code-fact record (and project memory records Haiku fabricating env-var names in exactly this kind of runbook). No unit passes the four-condition Haiku-safe test. Fable for the Verifier follows the ship-cycle candidate-upshift rule and the precedent set in `v6-answer-experience`. Why not: all-Opus is the more expensive configuration; justified because a weak worker's slip here is a recovery path that appears to work and fails when actually needed.
- *Phase order*: A is independent; B must precede C (nothing to restore without an archiving substrate); D is last because the ADR records what B and C actually did, and the probe is independent.
