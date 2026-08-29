# v5-worker-recovery-hardening Tasks

**Spec**: `spec.md` · **Design**: `design.md` · **Context**: `context.md`

Four phases, one Opus worker each (AD-257), then a fresh Verifier. Every task:
tests derive from the acceptance criteria, the gate passes before the task is done,
one atomic Conventional Commit per task, no internal IDs and no attribution in
commit messages.

Baseline at branch start: **2077 tests collected**; Alembic head `0017_conversations`.
Gate commands — scoped module per intermediate commit, full suite at each phase
boundary: `cd backend && uv run pytest <module>` then `uv run pytest`, plus
`make lint` at the phase boundary. DB-backed tests need `make infra` and
`LEARNY_TEST_DATABASE_URL`.

---

## Phase A — Worker liveness (WRK-01..06)

| # | Task | Covers | Verification |
|---|---|---|---|
| T1 | Add `LEARNY_INGESTION_MAX_ATTEMPTS` (default 5, rejected below 1) to settings | WRK-05 | `tests/test_config.py` |
| T2 | Enforce the attempts cap in the claim seam: at or above the cap, terminate the job (`failed` + event + source status synced) and return `None`; below the cap, behave exactly as today | WRK-02, WRK-03 | `tests/test_application_ingestion.py`, `tests/test_worker_tasks.py` |
| T3 | Emit one WARNING structured record when a job is claimed for an attempt after its first | WRK-04 | worker logging/lifecycle tests |
| T4 | Set `task_reject_on_worker_lost=True` and pin the reliability config block, asserting `visibility_timeout > task_time_limit` | WRK-01, WRK-06 | `tests/test_worker_logging.py` or a sibling config test |

**Phase boundary**: full backend suite + `make lint` green.

---

## Phase B — WAL archiving substrate and base backups (PITR-01..06, PITR-10)

| # | Task | Covers | Verification |
|---|---|---|---|
| T5 | **Verify first**, then build: confirm empirically whether the stock image accepts a remote replication connection for `pg_basebackup`; record the finding in `context.md` before depending on it | assumption closure | Recorded evidence; blocks T7 |
| T6 | Repo-owned postgres image creating the archive directory owned by the database user; wire `archive_mode`/`archive_command`/`archive_timeout` and the archive volume into base + prod compose; add the image to the deploy matrix | PITR-01, PITR-02 | `tests/test_compose_topology.py`, `tests/test_compose_prod.py`, `tests/test_deploy_workflow.py` |
| T7 | Base-backup job in the backup image: temp-then-rename, lock-shared with the nightly dump, offsite under the existing four-variable gate, newest-exempt pruning | PITR-03, PITR-04, PITR-06 | `tests/test_backup_stack.py` |
| T8 | WAL shipping + retention derived from the oldest retained base backup, never age alone | PITR-05 | `tests/test_backup_stack.py` |
| T9 | Document every new variable in `.env.production.example`; assert no credential appears in compose, workflows, or images | PITR-10 | `tests/test_backup_stack.py` / config tests |

**Phase boundary**: full backend suite + `make lint` green; `docker compose config` valid for base and base+prod.

---

## Phase C — Point-in-time restore and its CI proof (PITR-07..09)

| # | Task | Covers | Verification |
|---|---|---|---|
| T10 | Point-in-time restore script: `--yes` required, target timestamp, replay onto the chosen base; dry run prints and exits non-zero without touching a data directory | PITR-07 | `tests/test_backup_stack.py` |
| T11 | Target older than every retained base exits non-zero naming the earliest recoverable time | PITR-08 | `tests/test_backup_stack.py` |
| T12 | CI drill in `compose-smoke`: base backup → row A → record timestamp → row B → WAL switch → restore to timestamp → assert A present **and B absent** | PITR-09 | Green CI run; structural pins in `tests/test_backup_stack.py` |

> The B-absent assertion is the discriminating one: a plain whole-archive restore passes an A-present check and fails this.

**Phase boundary**: full backend suite + `make lint` green; the drill green in CI.

---

## Phase D — Record and re-probe (PITR-11, PITR-12, PROBE-01)

| # | Task | Covers | Verification |
|---|---|---|---|
| T13 | Rewrite the recovery sections of `docs/ops/backups.md`: WAL archiving, base cadence, the coupled retention rule, the restore procedure, the one-time restart; remove the "out of scope" statement | PITR-11 | `tests/test_ops_docs.py` |
| T14 | ADR recording the PITR topology and the worker-lost policy, superseding ADR-0024's PITR deferral | PITR-12 | `tests/test_versions.py` / ADR presence tests |
| T15 | Re-probe `torch`/`torchvision` resolution against current pins; record versions and the exact excluding constraint; make **no** pin or lockfile change if still blocked | PROBE-01 | Recorded evidence in the ADR |

**Phase boundary**: full backend suite + `make lint` green.

---

## Verifier

Fresh agent (Fable), author ≠ verifier: spec-anchored outcome check across all 19
acceptance criteria plus a discrimination sensor. Highest-value mutation targets:
the cap boundary (at, below, above), the WAL-retention predicate, and the drill's
B-absent assertion.
