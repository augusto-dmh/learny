# v5-worker-recovery-hardening — Independent Validation

- **Verdict: PASS**
- **Diff range reviewed:** `main..HEAD` (`141d55ca..0aedf934`, 15 commits, 38 files)
- **Verifier:** independent of the implementation; evidence-or-zero standard
- **Date:** 2026-08-02
- **Baseline at HEAD:** full backend suite green except the pre-existing
  `test_eval_retrieval_metrics::test_metrics_meet_thresholds` HNSW-variance failure
  (recorded across four prior cycles as pre-existing on clean `main`; nothing in this
  diff touches retrieval, and the failure reproduced identically before any mutation
  work began). `make lint` clean at HEAD.

## 1. Per-criterion evidence

### Worker liveness (WRK-01..06)

| ID | Verdict | Evidence |
|---|---|---|
| WRK-01 | PASS | `task_reject_on_worker_lost=True` set at `backend/app/worker/celery_app.py:44`; pinned by `test_worker_config.py::test_a_task_whose_worker_died_is_redelivered` (kill confirmed by mutation M7). |
| WRK-02 | PASS | Cap enforced at the claim seam (`RunIngestion.begin_run` → `_exhaust`, `backend/app/application/ingestion.py:210-254`): terminal `failed`, fixed non-secret error text, `failed` event, source synced. Proven at unit level (`test_application_ingestion.py`, five tests) and through the real Celery task against the real DB (`test_worker_tasks.py::test_run_ingestion_stops_a_job_that_has_used_up_its_attempts`, which also asserts the step is never invoked). Terminal-transition equivalence with the ordinary failure path verified by inspection and by mutations M2–M4: `_exhaust` performs the same three writes as `fail` (job.failed + source failed + failed event) with the same durable text. |
| WRK-03 | PASS | Below-cap claims behave exactly as before, including a redelivered `running` row (`test_begin_run_below_the_cap_keeps_claiming_the_job`); boundary's other side proven through the task (`test_run_ingestion_still_runs_a_job_with_one_attempt_left`); missing/terminal no-op retained (pre-existing tests plus `test_a_redelivery_after_the_cap_terminated_the_job_is_an_idempotent_no_op`). |
| WRK-04 | PASS | One WARNING with `job_id`, `source_id`, `attempt` on every claim after the first, asserted at unit level and through the real task log stream; the discriminating halves (first claim silent, ordinary terminal redelivery silent) are separately asserted. Mutations M5/M6 killed. |
| WRK-05 | PASS | Default 5 (`config.py:144`, `Field(default=5, ge=1)`); `test_config.py` covers default, override, and `0`/`-1` rejection at settings validation (mutation M9 killed). Documented in both `.env.example` and `.env.production.example`. |
| WRK-06 | PASS | `test_worker_config.py` pins all six values. The `visibility_timeout > task_time_limit` assertion is a genuine relationship, not two literals: mutation M8 (raise `task_time_limit` to 7200) was killed by the ordering test independently of the literal pin. |

### PITR (PITR-01..12)

| ID | Verdict | Evidence |
|---|---|---|
| PITR-01 | PASS | Compose `db` command sets `archive_mode=on`, no-overwrite `archive_command` (`test ! -f … && cp …`), bounded `archive_timeout` (default 900, test-bounded ≤3600 and >0). Pinned structurally in `test_compose_topology.py` (mutation S9 killed); archiving proven live — segments landed in the archive volume during the verifier's drill. |
| PITR-02 | PASS | Image creates `/wal_archive` owned by `postgres` (`deploy/postgres/Dockerfile`); test asserts the mechanism (image path = compose mount point, `install -d -o postgres`). Proven live: the verifier's throwaway project used a fresh named volume and archiving + `pg_basebackup` succeeded with no host-side chown. |
| PITR-03 | PASS | `base-backup.sh`: timestamped name, temp-dir + rename-on-success, EXIT trap, START_WAL written inside the temp dir so base and floor publish atomically (mutation S6 killed). Ran successfully in the live drill. |
| PITR-04 | PASS | Four-variable gate identical to the dump's, in both scripts (text-pinned, AND-joined). WAL half proven live by the verifier against a scratch MinIO: all segments shipped before pruning; unconfigured path logs "offsite not configured" and exits 0 (observed in the drill). Base-backup offsite half is text-pinned only — see §4. |
| PITR-05 | PASS | Retention predicate proven live: with floor `…10`, an aged below-floor segment (and its `.backup` label) was pruned; the floor segment itself, an above-floor segment, a *fresh* below-floor segment (age withholds), and a `.history` file all survived. No-base and missing-START_WAL branches prune nothing and exit 0 (proven live, incl. the `|| true` glob-abort hazard — mutation S1 killed). Offsite pruning mirrors only the locally pruned names (proven live: the offsite copy of the pruned segment was removed, retained ones kept; bulk-age-sweep mutation S4 killed). |
| PITR-06 | PASS | Prune after success only (`set -e` ordering, text-pinned), newest exempt (`! -path "$newest"` — mutation S5 killed), offsite `--older-than` window never removes the just-uploaded base. |
| PITR-07 | PASS | Live: `--yes` restored the chosen base, configured replay, and `db-restore` came up recovered to the recorded moment, promoted and writable. Dry run proven inert live (exit 1, `/pitr/data` never created); ordering of the gate before every write also text-pinned (mutation S8 killed). Base selection excludes bases after the target (behavioral scratch run chose the 07-01 base over an 08-01 base for a 07-15 target; incomplete base directories invisible to both selection and floor; mutation S7 killed). |
| PITR-08 | PASS | Live: a 2000-01-01 target exited 1 naming "earliest recoverable time: <floor of oldest retained base>", with no data directory created. Also proven in scratch behavioral runs. |
| PITR-09 | PASS (locally; CI run pending) | The verifier replicated the full drill end-to-end in a throwaway compose project using the shipped compose files and the CI steps verbatim: base → three writes/two targets → forced WAL switch with archive-landing wait → restore to target ⇒ row 1 present, row 2 absent, `pg_is_in_recovery()=f`, writable; control restore to the later target ⇒ rows 1–2 present, row 3 absent. The author's mutation claim was verified independently: with `recovery_target_time` stripped from `restore-pitr.sh`, the same restore returned rows 2 and 3 (whole-archive restore) — the drill's discriminating assertion catches exactly that. The drill's order and two-sided shape are pinned in `test_backup_stack.py` (mutations C1–C3 killed). |
| PITR-10 | PASS | All new variables documented in `.env.production.example` — and the test derives the variable set from the scripts themselves rather than a hand-kept list. Credential scan covers compose files, workflows, and both deploy image directories with a throwaway-value allowlist; prod overlay allows no literal at all; the postgres image directory is asserted free of any object-store client or credential marker. |
| PITR-11 | PASS | `docs/ops/backups.md` gains the full PITR section (archiving, cadence, coupled retention rule stated as an invariant, two-command restore, restore-state properties); the deferral text is gone and `test_ops_docs.py` asserts both directions with strings that are code facts pinned elsewhere in the suite. |
| PITR-12 | PASS | ADR-0030 records the two-family topology, the stock-image refusal (pg_hba `all` ≠ replication) and the `hba_file` resolution, the coupled retention rule, provider-neutral offsite, and the worker-lost policy with the durable-cap rationale; it names the exact ADR-0024 sentence it supersedes, and ADR-0024 carries the reciprocal "Superseded in part by ADR-0030" stamp (both test-pinned). |

### PROBE-01

PASS. The re-probe record in ADR-0024 carries the resolved versions (docling 2.117.0, torch 2.13.0/torchvision 0.28.0, the 2.52 GB CUDA stack), the exact constraint finding (torchvision's `==2.13.0` admits `+cpu`; the real blocker was `[tool.uv.sources]` applying only to direct dependencies), and the explicit "Still no lockfile or pin change". The diff touches neither `pyproject.toml` nor `uv.lock`, and `test_ops_docs.py::test_the_reprobe_left_the_dependency_pins_alone` makes the record-only scope checkable.

## 2. Mutation table

All mutants killed; every mutation was reverted and the tree verified clean afterwards.

| # | Mutation | Where | Result | Killed by |
|---|---|---|---|---|
| M1 | cap check `>=` → `>` | `ingestion.py::begin_run` | KILLED | at-cap, lowered-cap, not-silent unit tests + task-level DB test (5 failures) |
| M2 | `_exhaust` skips source-status sync | `ingestion.py` | KILLED | at-cap unit + lowered-cap + task-level DB test |
| M3 | `_exhaust` skips the `failed` event | `ingestion.py` | KILLED | at-cap unit + readable-failure + task-level DB test |
| M4 | `_exhaust` writes leaky error text | `ingestion.py` | KILLED | readable-failure unit + task-level DB test |
| M5 | `_exhaust` warning removed | `ingestion.py` | KILLED | `test_the_cap_terminating_a_job_is_not_silent` |
| M6 | re-claim warning threshold `>1` → `>2` | `ingestion.py` | KILLED | repeat-claim unit + task-level log-stream test |
| M7 | `task_reject_on_worker_lost=False` | `celery_app.py` | KILLED | `test_a_task_whose_worker_died_is_redelivered` |
| M8 | `task_time_limit` 1800 → 7200 | `celery_app.py` | KILLED | ordering test (independently of the literal pin) — the invariant is a real relationship |
| M9 | `ge=1` → `ge=0` on the cap setting | `config.py` | KILLED | below-one-rejected test |
| M10 | task composition root hardcodes `max_attempts=999` | `tasks.py` | KILLED | task-level DB cap test |
| S1 | `\|\| true` removed from oldest-base lookup | `wal-archive.sh` | KILLED | no-base fail-safe test |
| S2 | floor guard removed (age alone deletes) | `wal-archive.sh` | KILLED | `test_age_alone_never_deletes_a_segment` + strict-floor test |
| S3 | `.history` exemption removed | `wal-archive.sh` | KILLED | timeline-history test |
| S4 | offsite prune → bulk `--older-than` sweep | `wal-archive.sh` | KILLED | offsite-mirrors-local test |
| S5 | newest-base prune exemption removed | `base-backup.sh` | KILLED | prune-after-success test |
| S6 | START_WAL written outside the atomic rename | `base-backup.sh` | KILLED | replay-floor test |
| S7 | base selection flips to admit bases after the target | `restore-pitr.sh` | KILLED | base-precedes-target test |
| S8 | staging writes moved before the `--yes` gate | `restore-pitr.sh` | KILLED | dry-run-inert + plan tests |
| S9 | `archive_command` overwrites silently | `docker-compose.yml` | KILLED | no-overwrite topology test |
| S10 | `db-restore` healthcheck weakened to `pg_isready` | `docker-compose.yml` | KILLED | out-of-recovery healthcheck test |
| C1 | drill's row-2-absent assertion deleted | `ci.yml` | KILLED | two dedicated CI-shape tests |
| C2 | base backup moved after the boundary writes | `ci.yml` | KILLED | base-before-rows test |
| C3 | archive-landing wait removed | `ci.yml` | KILLED | wait-before-restore test |
| L1 | `recovery_target_time` emission stripped (live) | `restore-pitr.sh` in the verifier's running drill | KILLED | the drill itself: restore returned rows 2 and 3 — the `id=2` assertion fails exactly this mutant |

**Score: 24/24 killed.**

Behavioral runs beyond mutations: `wal-archive.sh` executed against scratch state (floor/age/no-base/history/label semantics, and the offsite branch against a scratch MinIO with ship-before-prune order observed); `restore-pitr.sh` executed against scratch bases (selection, dry run, out-of-window, no-offset rejection, staged config content); the full drill executed end-to-end in an isolated compose project built from the shipped files.

## 3. What remains unproven until CI runs

- **The drill on GitHub Actions itself.** It passed verbatim in the verifier's local replication (same compose files, same steps, same assertions, fresh volumes), so the remaining exposure is runner-environmental only (network to dl.min.io for the backup image build — already exercised by the existing CI roundtrip — plus disk/time, both trivially within ubuntu-latest budgets). No internally inconsistent step was found; the teardown was correctly extended to the new profiles.
- **The `learny-postgres` GHCR publish** (`deploy.yml` matrix row) first runs on merge; `test_deploy_workflow.py` pins the matrix and cross-checks that every GHCR image the prod overlay references is built.

## 4. Notes and residual risks (none blocking)

1. **`base-backup.sh` offsite branch is never executed anywhere** (CI runs it without offsite vars; the verifier live-proved the WAL script's offsite branch but not the base script's). It is text-pinned and uses the same `mc alias/mb/cp` pattern the dump's CI-proven offsite path uses. Low risk; a future CI extension could point one base backup at the scratch MinIO.
2. **Ongoing regression protection for the retention predicate is text-level.** The verifier's behavioral runs prove the shipped code, but they are not repeatable gates; a semantics-changing rewrite that preserved the pinned strings would only be caught by review. Accepted trade-off (stated in the test module), noted for the record.
3. **Base-selection edge inside a backup window:** a target that falls after a base's start stamp but before that base's end-of-copy consistency point selects that base, and recovery then fails loudly ("recovery stop point is before consistent recovery point") rather than choosing the previous base. Spec-conformant (PITR-08 covers only targets older than every base) and fail-loud, but the script offers no `--base` override; the operator's recourse is moving the newest base directory aside. Worth a runbook sentence someday.
4. **WRK-02 scope:** the cap guards the claim seam; a task that bypassed `begin_run` would bypass the cap. Recorded and accepted in `context.md` D-2 — every ingestion path claims through it today.
5. The pre-existing HNSW-variance eval failure reproduced identically before any change was made in this session; nothing in this diff touches retrieval. No evidence it is anything but pre-existing.
