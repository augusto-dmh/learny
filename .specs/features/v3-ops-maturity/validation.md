# v3-ops-maturity Validation

**Date**: 2026-07-17
**Spec**: `.specs/features/v3-ops-maturity/spec.md`
**Diff range**: `db5e370..157c431` (10 commits, `main...HEAD` on `feat/v3-ops-maturity`)
**Verifier**: independent sub-agent (author ≠ verifier); re-derived with evidence-or-zero
**Verdict**: ✅ PASS — all 19 ACs covered with matching outcomes, gate green, and all 6 discrimination mutants killed after the OPS-09 test-strengthening fix (157c431).

> **Re-verification note (2026-07-17)**: the sole FAIL blocker from the first pass — a surviving mutant on the OPS-09 `--if-exists` command flag — was fixed in commit **157c431**. `test_restore_uses_clean_if_exists` now isolates the executed command via `_RESTORE_SH.rindex("pg_restore")` and asserts `--clean --if-exists` on that line only. Re-running Mutant #1 (drop `--if-exists` from `restore.sh:71`) now **kills** it (`AssertionError: assert '--clean --if-exists' in 'pg_restore --clean --no-owner \\'`). 6/6 mutants killed; verdict flipped FAIL → PASS.

---

## Task Completion

All nine implementation commits are present and build to a coherent end state. The one accepted process deviation (the `set -euo pipefail` strict-mode line for `backup.sh` landing in the f2825aa test commit rather than the first feature commit) is confirmed present in the end state (`deploy/backup/backup.sh:14`). OPS-18 landed as outcome (b) — blocker recorded in ADR, no lockfile change (`git diff main...HEAD` shows no `uv.lock` change).

---

## Spec-Anchored Acceptance Criteria

Evidence paths: `T` = `backend/tests/`. Behavioral proofs cite the CI roundtrip in `.github/workflows/ci.yml` (executable) or the shipped script/compose/ADR text.

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
|---|---|---|---|
| OPS-01 backup service full shape | image `ghcr.io/…/learny-backup:${LEARNY_IMAGE_TAG:-latest}` | `T/test_backup_stack.py:77` — `prod["backup"]["image"] == f"ghcr.io/augusto-dmh/learny-backup:{_IMAGE_TAG}"` | ✅ PASS |
| " | `restart: unless-stopped` | `:81` — `== "unless-stopped"` | ✅ PASS |
| " | 3 env_file, each `required: true`, exact paths | `:84-96` — every entry `required is True`; `paths == {db.env, minio.env, backup.env}` | ✅ PASS |
| " | `backup_data:/backups` volume | `:100` — `"backup_data:/backups" in volumes` | ✅ PASS |
| " | NO published ports | `:112` — `not prod["backup"].get("ports")` | ✅ PASS |
| " | volume declared; absent from base | `:115`, `:122` | ✅ PASS |
| OPS-02 4th image `learny-backup` from `./deploy/backup`, sha+latest | matrix incl. `("./deploy/backup", None)` | `T/test_deploy_workflow.py:118-127` — `by_name == {…, "learny-backup": ("./deploy/backup", None)}`; tags `:133-141` (matrix-parameterized latest+sha) | ✅ PASS |
| OPS-03 crond from `LEARNY_BACKUP_CRON` default `30 3 * * *`; `backup-now` | default + `crond -f` | `T/test_backup_stack.py:249` — `"LEARNY_BACKUP_CRON:=30 3 * * *"` and `"crond -f"`; `backup-now` invoked `T/…:271,278` (CI) | ✅ PASS |
| OPS-04 `pg_dump -Fc` temp→rename-on-success | temp then `mv` onto final | `:162` (`pg_dump`,`-Fc`); `:167-171` (`tmp="$archive.tmp"`, `mv "$tmp" "$archive"`); CI roundtrip proves end-to-end | ✅ PASS |
| OPS-05 offsite gated on all 4 vars; else notice+exit0 | all 4 vars + `mc mirror`; `offsite not configured` | `:174-183` (4 vars + notice); `:186-193` (`mc mirror`, no `--remove`); CI `:274-279` asserts notice | ✅ PASS |
| OPS-06 prune >KEEP_DAYS (default 14), newest exempt, only after success | `-mtime +KEEP_DAYS`, newest exempt | `:196-201` (`LEARNY_BACKUP_KEEP_DAYS`, `-mtime "+$LEARNY_BACKUP_KEEP_DAYS"`, `newest="$(ls -1t`, `! -path "$newest"`); order dump<prune `:204-210` | ✅ PASS |
| OPS-07 concurrent run lock; any fail → non-zero, skip heartbeat | `flock -n`; strict mode | `:156` (`flock -n`); `:152` (`set -euo pipefail`); `:204-210` heartbeat after dump/prune | ✅ PASS |
| OPS-08 heartbeat only after full success; unset → no request | heartbeat last, `curl -fsS` | `:204-211` (`dump_at < prune_at < heartbeat_at`, `curl -fsS`); unset guarded by `if [ -n … ]` (`backup.sh:90`, structural) | ✅ PASS (unset-branch not independently asserted) |
| OPS-09 `--yes`→`pg_restore --clean --if-exists`; no `--yes`→plan+non-zero, no DB | `--clean --if-exists`; plan-before-restore | `:217-225` (`--yes`, `confirm -ne 1`, plan<restore); `:229-234` (`--clean --if-exists` on the isolated `rindex("pg_restore")` command line, post-fix 157c431); `:233-235` unknown-name lists archives | ✅ PASS (command-line-pinned; Mutant #1 now kills) |
| OPS-10 CI seed→backup→destroy→restore→assert; offsite notice | ordered steps + notice | `:269-299` five ordered asserts; `ci.yml:137-156` steps present | ✅ PASS |
| OPS-11 creds only from backup.env(+db/minio); none in compose/wf/image; env template + deploy.md | env_file only; no secret in deploy job; deploy.md lists backup.env | OPS-01 env_file asserts; `T/test_deploy_workflow.py:228` (`secrets/`, `.env` not in deploy job); `T/test_ops_docs.py:114` (`backup.env`, `backend/.env.production.example` in deploy.md); template present `.env.production.example:39-56` | ✅ PASS (template backup section present but not test-pinned) |
| OPS-12 backups.md schedule/retention/offsite/heartbeat/drill; deferral gone | key strings pinned | `T/test_ops_docs.py:67,72,78,96,100,106,57` — schedule/retention/offsite/heartbeat/restore/deferral-gone/drill | ✅ PASS |
| OPS-13 netdata pinned tag, restart, mem limit, host+docker mounts | pinned tag, 512m, ro mounts | `T/test_deploy_topology.py:245,252,256,261,266,276` | ✅ PASS (registry-verification is a process claim, ADR-recorded) |
| OPS-14 UI only on `127.0.0.1:19999:19999`; caddy sole non-loopback | exact loopback binding | `:239-242` (`== ["127.0.0.1:19999:19999"]`); `:166-177` caddy-only non-loopback | ✅ PASS |
| OPS-15 monitoring.md tunnel/panels/backup-logs/alert-hooks | key strings pinned | `T/test_ops_docs.py:130,136,142,149,155` | ✅ PASS |
| OPS-16 runtime installs no `--extra dev`; test asserts | no `--extra dev` in runtime stage | `T/test_compose_topology.py:164` — `"--extra dev" not in _dockerfile_stage("runtime")`; import audit in ADR; compose-smoke boots api/worker | ✅ PASS |
| OPS-17 runtime non-root; compose-smoke passes | USER not root/0 | `T/test_compose_topology.py:168-176`; `ci.yml:128` boots api/worker `--wait` (migrations apply) | ✅ PASS |
| OPS-18 CPU torch pinned OR blocker recorded in ADR w/ evidence | outcome (b) recorded | `docs/adr/0024-…md:120-131` — torchvision `<2.13.0+` excludes `+cpu`, ~2.6GB measured, no lockfile change (confirmed by diff) | ✅ PASS (pre-agreed outcome b) |
| OPS-19 ADR records backup+monitoring decisions, closes TDD OQ#10, records OPS-18 | full decision record | `docs/adr/0024-…md` — tooling/topology/retention/offsite-neutrality/netdata/tunnel (`:39-131`); closes OQ#10 (`:18-19,138`); OPS-18 (`:120-131`) | ✅ PASS (doc deliverable, read-verified) |

**Status**: ✅ 19/19 ACs covered with matching spec outcomes; OPS-09 discrimination-strength gap resolved in 157c431.

---

## Edge Cases

- [x] db/minio unreachable → non-zero, priors intact, no heartbeat — **structural** (`backup.sh:14` `set -euo pipefail` aborts on `pg_dump` failure; `:48` `trap 'rm -f "$tmp"'` removes the partial; final name never created; heartbeat is last so it is skipped). Not exercised by a dedicated failure-injection test; CI proves only the happy path.
- [x] offsite endpoint unreachable → local dump kept, non-zero — **structural** (local dump written/renamed before the offsite block; `mc` failure aborts under `set -e`). Not independently tested.
- [x] restore unknown archive → non-zero, lists archives — `T/test_backup_stack.py:233` + `restore.sh:55-59`.
- [x] KEEP_DAYS prunes everything → newest survives — `T/test_backup_stack.py:196-201` (`! -path "$newest"`) + `backup.sh:79-81`.

---

## Discrimination Sensor

Scratch method: Edit the artifact → run the covering test file from `backend/` with `uv run pytest <file> -q` → `git checkout -- <file>` to restore. Tree confirmed pristine after each (only `.specs/project/STATE.md` modified + `.specs/features/v3-ops-maturity/` untracked, both pre-existing).

| # | File:line | Mutation | Covering test(s) | Killed? |
|---|---|---|---|---|
| 1 | `deploy/backup/restore.sh:71` | Drop `--if-exists` from the `pg_restore` **command** (`--clean --if-exists --no-owner` → `--clean --no-owner`) | `test_backup_stack.py::test_restore_uses_clean_if_exists` | ✅ Killed (post-fix 157c431; ❌ survived pre-fix) |
| 2 | `docker-compose.prod.yml:86` | `backup.env` `required: true` → `false` | `test_backup_stack.py::test_prod_backup_sources_the_three_required_secret_files` | ✅ Killed |
| 3 | `docker-compose.prod.yml:116` | Monitoring port `127.0.0.1:19999:19999` → `19999:19999` (public) | `test_deploy_topology.py::test_prod_publishes_non_loopback_ports_only_on_caddy` + `::test_monitoring_publishes_only_the_loopback_ui_port` | ✅ Killed (2) |
| 4 | `.github/workflows/deploy.yml:51-53` | Remove `learny-backup` from the build matrix | `test_deploy_workflow.py::test_build_matrix_covers_the_four_images` | ✅ Killed |
| 5 | `.github/workflows/ci.yml:146` | Remove the `grep -qF "offsite not configured"` roundtrip assertion | `test_backup_stack.py::test_ci_backup_run_asserts_the_offsite_notice` | ✅ Killed |
| 6 | `backend/Dockerfile:48` | Re-add `--extra dev` to the `runtime` stage sync | `test_compose_topology.py::test_runtime_stage_installs_no_dev_extra` | ✅ Killed |

**Sensor depth**: lightweight infra fault-injection (6 mutations across scripts, compose, workflows, Dockerfile).
**Result**: 6/6 killed — ✅ (Mutant #1 killed after fix 157c431; the other 5 killed on the first pass).

### Resolved: Mutant #1 (first-pass survivor)

**First pass**: `test_restore_uses_clean_if_exists` asserted `"--clean --if-exists" in _RESTORE_SH` — a **whole-file** substring. The string also appears in the doc-comment header (`restore.sh:7`) and the dry-run PLAN echo (`restore.sh:64`), so removing `--if-exists` from the actual `pg_restore` command (line 71) left the assertion satisfied and the mutant survived. CI's OPS-10 roundtrip was blind to it too (`--clean` without `--if-exists` emits non-fatal DROP errors on absent objects and still restores).

**Fix (157c431)**: the test now extracts the executed command via `command_at = _RESTORE_SH.rindex("pg_restore")`, takes that single line, and asserts `"--clean --if-exists" in command_line` — the same isolation pattern `test_restore_requires_explicit_yes…` already used. Re-running Mutant #1 now fails the test (`assert '--clean --if-exists' in 'pg_restore --clean --no-owner \\'`), confirming the kill. The three legitimate occurrences of the string (header, PLAN echo, command) remain intact on pristine.

---

## Code Quality

| Principle | Status |
|---|---|
| Minimum code / no scope creep | ✅ artifacts match the six D-decisions; no extra services/flags |
| Surgical changes; only required files | ✅ diff is backup/monitoring/image/docs + their tests |
| Matches existing patterns/style | ✅ mirrors `test_deploy_topology.py` merge/helpers; compose overlay idioms |
| Spec-anchored outcome check (asserted values match spec) | ✅ (OPS-09 flag-pinning fixed in 157c431) |
| Per-layer coverage (infra: topology + happy/edge + CI proof) | ✅ happy-path roundtrip + text pins; failure edges structural |
| Every test maps to an AC/edge/Done-when | ✅ no unclaimed tests in scope |
| Documented guidelines followed | tlc-spec-driven house style (YAML/text asserts) — followed |

---

## Gate Check

- **Command**: `uv run pytest -q` and `uv run ruff check` (from `backend/`)
- **Result**: **704 passed, 350 skipped, 2 warnings** — 0 failed. Ruff: **All checks passed!**
- **Baseline**: matches the expected 704/350. Skips are the standard `LEARNY_TEST_DATABASE_URL not set` integration guards (network-free local run), justified and pre-existing.
- **Test integrity**: no test count decrease; new tests add coverage for OPS-01..19; no weakened prior assertions observed.

---

## Requirement Traceability Update

| Requirement | Previous | New |
|---|---|---|
| OPS-01..08 | Pending | ✅ Verified |
| OPS-09 | Pending | ✅ Verified (test-strength gap fixed in 157c431) |
| OPS-10..19 | Pending | ✅ Verified |

---

## Fix Plans

### Fix 1: Pin `--clean --if-exists` on the restore command, not the whole file — ✅ RESOLVED (157c431)

- **Root cause**: `test_restore_uses_clean_if_exists` matched `"--clean --if-exists"` anywhere in `restore.sh`; the header comment and PLAN echo satisfied it independently of the executed `pg_restore` command.
- **Fix applied**: `backend/tests/test_backup_stack.py:229-234` now extracts the executed command via `_RESTORE_SH.rindex("pg_restore")`, takes that line, and asserts `"--clean --if-exists" in command_line`.
- **Verified**: re-ran Mutant #1 (drop `--if-exists` from `restore.sh:71`) — the strengthened test now FAILS (kills the mutant); full suite still 704 passed / ruff clean on pristine.
- **Priority**: Minor (test hardening; shipped production command was already correct).

---

## Summary

**Overall**: ✅ Ready.

**Spec-anchored check**: 19/19 ACs covered with matching outcomes; the OPS-09 whole-file-substring weakness is fixed in 157c431.
**Sensor**: 6 injected, 6 killed, 0 survived (Mutant #1 killed after the fix; the other 5 killed on the first pass).
**Gate**: 704 passed, 0 failed, 350 skipped; ruff clean.

**What works**: the full backup service topology (image/restart/required secrets/volume/no-ports), the 4-image deploy matrix, crond scheduling + `backup-now`, temp→rename dump safety, four-var offsite gating with the local-only notice, keep-days pruning with newest-exemption, the `--yes`-guarded restore now command-line-pinned, the CI seed→backup→destroy→restore roundtrip, loopback-only netdata with caddy-sole-public-surface, non-root dev-extra-free runtime image, and the OPS-18 blocker + full ADR record.

**Issues found**: none open. The single first-pass gap (OPS-09 test discrimination) is resolved and re-verified.

**Next steps**: none — ready to proceed to publish/review.
