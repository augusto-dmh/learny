"""A gate — backup stack topology + script safety (unit, OPS-01..09, PITR-03..06/10).

Three layers, all pure text/YAML (no Docker required, deterministic):

* Compose topology — the prod overlay's ``backup`` sidecar (GHCR image, restart,
  the three required secret files, the ``backup_data`` volume, db+minio health
  gating, and NO host port) and the dev override's profile-gated build service.
* Script safety — the safety-critical flags of ``deploy/backup/*`` are pinned as
  text so a regression that silently drops (say) ``--clean --if-exists`` or the
  ``--yes`` restore guard fails here, not in production. The end-to-end behaviour
  is proven by the CI roundtrip (OPS-10); these asserts pin the exact flags CI
  cannot easily distinguish from a weakened variant.
* Recovery chain — the physical base backup and the WAL retention predicate. The
  predicate is the highest-value assertion in the module: deleting a segment a
  retained base still needs severs the replay chain invisibly, and the severance
  only surfaces when someone actually attempts a restore. Its behaviour was
  additionally exercised against a live archive during development; what is pinned
  here is the shape a text diff can silently weaken.

Mirrors the merge semantics + helper shapes of ``test_deploy_topology.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BASE = _REPO_ROOT / "docker-compose.yml"
_OVERRIDE = _REPO_ROOT / "docker-compose.override.yml"
_PROD = _REPO_ROOT / "docker-compose.prod.yml"

_BACKUP_DIR = _REPO_ROOT / "deploy" / "backup"
_BACKUP_SH = (_BACKUP_DIR / "backup.sh").read_text()
_RESTORE_SH = (_BACKUP_DIR / "restore.sh").read_text()
_ENTRYPOINT_SH = (_BACKUP_DIR / "entrypoint.sh").read_text()
_DOCKERFILE = (_BACKUP_DIR / "Dockerfile").read_text()
_BASE_BACKUP_SH = (_BACKUP_DIR / "base-backup.sh").read_text()
_WAL_SH = (_BACKUP_DIR / "wal-archive.sh").read_text()

_CI = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

_IMAGE_TAG = "${LEARNY_IMAGE_TAG:-latest}"


def _executed_lines(text: str) -> list[str]:
    """The script's executed lines (blank lines and full-line comments dropped).

    Guards against the L-010 anti-pattern: a safety flag named only in a doc comment
    must not satisfy an assertion — pin it on the line the shell actually runs.
    """
    return [
        line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")
    ]


def _logical_lines(text: str) -> list[str]:
    """Executed lines, with backslash continuations rejoined into one line each.

    A safety-critical flag pushed onto a continuation line is still part of the same
    command, so assertions about a command must see it whole.
    """
    joined: list[str] = []
    for line in _executed_lines(text):
        if joined and joined[-1].rstrip().endswith("\\"):
            joined[-1] = joined[-1].rstrip()[:-1].rstrip() + " " + line.strip()
        else:
            joined.append(line)
    return joined


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _deep_merge(a: dict, b: dict) -> dict:
    """Merge ``b`` over ``a`` the way an added compose `-f` file overrides keys."""
    out = dict(a)
    for key, b_val in b.items():
        a_val = out.get(key)
        if isinstance(a_val, dict) and isinstance(b_val, dict):
            out[key] = _deep_merge(a_val, b_val)
        else:
            out[key] = b_val
    return out


def _services(*paths: Path) -> dict:
    merged: dict = {}
    for path in paths:
        merged = _deep_merge(merged, _load(path)["services"])
    return merged


@pytest.fixture
def prod() -> dict:
    return _services(_BASE, _PROD)


@pytest.fixture
def override() -> dict:
    return _load(_OVERRIDE)["services"]


# --- prod overlay backup service (OPS-01) ---------------------------------------


def test_prod_backup_uses_the_pinned_ghcr_image(prod: dict) -> None:
    assert prod["backup"]["image"] == f"ghcr.io/augusto-dmh/learny-backup:{_IMAGE_TAG}"


def test_prod_backup_restarts_unless_stopped(prod: dict) -> None:
    assert prod["backup"]["restart"] == "unless-stopped"


def test_prod_backup_sources_the_three_required_secret_files(prod: dict) -> None:
    env_file = prod["backup"]["env_file"]
    # Long-form entries only, each required so a missing secrets file aborts startup
    # instead of silently falling back to unset credentials.
    for entry in env_file:
        assert isinstance(entry, dict), "backup env_file must use long-form entries"
        assert entry.get("required") is True, f"{entry} must be required"
    paths = {entry["path"] for entry in env_file}
    assert paths == {
        "./secrets/db.env",
        "./secrets/minio.env",
        "./secrets/backup.env",
    }


def test_prod_backup_persists_dumps_in_the_named_volume(prod: dict) -> None:
    assert "backup_data:/backups" in prod["backup"]["volumes"]


def test_prod_backup_waits_for_db_and_minio_healthy(prod: dict) -> None:
    depends = prod["backup"]["depends_on"]
    assert depends["db"]["condition"] == "service_healthy"
    assert depends["minio"]["condition"] == "service_healthy"


def test_prod_backup_publishes_no_host_ports(prod: dict) -> None:
    # The backup sidecar reaches db/minio over the compose network only; a host
    # port would widen the public surface past caddy (ADR-0017/0023).
    assert not prod["backup"].get("ports")


def test_prod_declares_the_backup_data_volume() -> None:
    volumes = {}
    for path in (_BASE, _PROD):
        volumes = _deep_merge(volumes, _load(path).get("volumes") or {})
    assert "backup_data" in volumes


def test_backup_service_is_absent_from_the_base_file() -> None:
    assert "backup" not in _load(_BASE)["services"]


# --- dev override backup service (profile-gated build) --------------------------


def test_dev_backup_is_gated_behind_the_backup_profile(override: dict) -> None:
    # `profiles: ["backup"]` keeps it out of a plain `docker compose up`; CI/dev
    # opt in with `docker compose --profile backup run --rm backup ...`.
    assert override["backup"]["profiles"] == ["backup"]


def test_dev_backup_builds_from_the_backup_context(override: dict) -> None:
    assert override["backup"]["build"] == "./deploy/backup"


def test_dev_backup_mounts_the_volume_with_local_credentials(override: dict) -> None:
    backup = override["backup"]
    assert "backup_data:/backups" in backup["volumes"]
    env = backup["environment"]
    # Dev creds must match the local db/minio override values so it can authenticate.
    assert env["POSTGRES_PASSWORD"] == "learny"
    assert env["MINIO_ROOT_USER"] == "learny"
    assert env["MINIO_ROOT_PASSWORD"] == "learny-dev-secret"


# --- backup.sh safety-critical flags (OPS-04..08) -------------------------------


def test_backup_runs_in_strict_mode_with_pipefail() -> None:
    assert "set -euo pipefail" in _BACKUP_SH


def test_backup_guards_against_a_concurrent_run() -> None:
    # `flock -n` fails immediately if a run is in progress (OPS-07); the guard must
    # not block-and-wait (which would queue a duplicate dump). Pin `-n` on the
    # executed guard line, so dropping it from the real `if !` check fails here even
    # while a doc comment still names `flock -n`.
    guard = [line for line in _executed_lines(_BACKUP_SH) if "flock" in line]
    assert guard, "backup.sh must run a flock guard"
    guard_line = guard[0]
    assert guard_line.lstrip().startswith("if !"), (
        "the flock guard must be a non-blocking `if !` check"
    )
    assert "-n" in guard_line, (
        "the flock guard must use -n (non-blocking); a blocking flock queues a duplicate dump"
    )


def test_backup_writes_a_compressed_custom_format_dump() -> None:
    assert "pg_dump" in _BACKUP_SH
    assert "-Fc" in _BACKUP_SH


def test_backup_dumps_to_a_temp_name_and_renames_only_on_success() -> None:
    # Temp-then-rename (OPS-04): a failed dump leaves no partial under the final
    # name. Assert both the temp target and the rename onto the final archive.
    assert 'tmp="$archive.tmp"' in _BACKUP_SH
    assert 'mv "$tmp" "$archive"' in _BACKUP_SH


def test_backup_gates_offsite_on_all_four_remote_vars() -> None:
    # OPS-05: offsite runs only when ALL four remote vars are set. Extract the executed
    # `if [ -n ... ]` conditional and assert the four `-n` checks are AND-joined, so a
    # regression flipping any `&&` to `||` (offsite on a single var) fails here.
    lines = _executed_lines(_BACKUP_SH)
    start = next(i for i, ln in enumerate(lines) if ln.lstrip().startswith("if [ -n"))
    end = next(i for i in range(start, len(lines)) if lines[i].rstrip().endswith("; then"))
    # Rejoin the backslash-continued conditional into one logical line.
    conditional = " ".join(ln.rstrip().rstrip("\\").strip() for ln in lines[start : end + 1])
    for var in (
        "LEARNY_BACKUP_REMOTE_ENDPOINT",
        "LEARNY_BACKUP_REMOTE_ACCESS_KEY",
        "LEARNY_BACKUP_REMOTE_SECRET_KEY",
        "LEARNY_BACKUP_REMOTE_BUCKET",
    ):
        assert f'[ -n "${{{var}:-}}" ]' in conditional, (
            f"offsite gate must check {var} with -n on the executed conditional"
        )
    # All four checks are AND-joined (three &&, no ||): a single set var must not enable offsite.
    assert conditional.count("&&") == 3, "the four remote-var checks must be joined by &&"
    assert "||" not in conditional, "offsite gating must not OR the remote-var checks"
    # The exact local-only notice CI asserts (OPS-05, OPS-10).
    assert "offsite not configured" in _BACKUP_SH


def test_backup_mirrors_objects_without_remove() -> None:
    # `mc mirror` WITHOUT `--remove`: objects deleted in the app persist offsite
    # (recoverability-favoring default). Check the invocation itself, not the whole
    # file — an explanatory comment naming the flag is legitimate.
    assert "mc mirror" in _BACKUP_SH
    mirror_cmd = _BACKUP_SH[_BACKUP_SH.index("mc mirror") :]
    mirror_cmd = mirror_cmd[: mirror_cmd.index("\n\n")]
    assert "--remove" not in mirror_cmd


def test_backup_prunes_by_keep_days_and_exempts_the_newest() -> None:
    assert "LEARNY_BACKUP_KEEP_DAYS" in _BACKUP_SH
    assert '-mtime "+$LEARNY_BACKUP_KEEP_DAYS"' in _BACKUP_SH
    # The just-written dump must survive: prune excludes the newest archive.
    assert 'newest="$(ls -1t' in _BACKUP_SH
    assert '! -path "$newest"' in _BACKUP_SH


def test_backup_pings_heartbeat_last_and_only_on_success() -> None:
    # Heartbeat must come after the dump and prune, so it is reached only on a fully
    # successful run (set -e aborts earlier on any failure, skipping it — OPS-08).
    dump_at = _BACKUP_SH.rindex("pg_dump")  # the command, not the header comment
    prune_at = _BACKUP_SH.index("-mtime")
    heartbeat_at = _BACKUP_SH.index("LEARNY_BACKUP_HEARTBEAT_URL")
    assert dump_at < prune_at < heartbeat_at
    assert "curl -fsS" in _BACKUP_SH


# --- base-backup.sh: the physical base every replay starts from (PITR-03/04/06) --
#
# WAL segments are not a recovery chain on their own — replay needs a physical base
# with a known WAL position, which a logical dump does not have. These pin the
# properties that make the base usable and its failure modes safe.


def test_base_backup_runs_in_strict_mode_with_pipefail() -> None:
    assert "set -euo pipefail" in _BASE_BACKUP_SH


def test_base_backup_takes_a_physical_backup_not_a_logical_dump() -> None:
    executed = "\n".join(_executed_lines(_BASE_BACKUP_SH))
    assert "pg_basebackup" in executed
    assert "pg_dump" not in executed, "the base must be physical; the dump is a separate job"


def test_base_backup_shares_the_nightly_dump_lock() -> None:
    # A base backup and a dump are both heavy full-database reads over the same disk
    # and the same /backups volume. Sharing backup.sh's lock file is what makes the
    # second arrival exit instead of running concurrently; a private lock here would
    # silently allow the overlap. Pin the SAME variable and default backup.sh uses.
    assert "LEARNY_BACKUP_LOCK:=/tmp/learny-backup.lock" in _BASE_BACKUP_SH
    assert "LEARNY_BACKUP_LOCK:=/tmp/learny-backup.lock" in _BACKUP_SH
    guard = [line for line in _executed_lines(_BASE_BACKUP_SH) if "flock" in line]
    assert guard and guard[0].lstrip().startswith("if !")
    assert "-n" in guard[0], "the guard must be non-blocking; blocking would queue a duplicate"


def test_base_backup_writes_to_a_temp_name_and_renames_only_on_success() -> None:
    # PITR-03: a failed run must leave no partial artifact under the final name and
    # must not touch prior bases.
    assert 'tmp="$base.tmp"' in _BASE_BACKUP_SH
    assert 'mv "$tmp" "$base"' in _BASE_BACKUP_SH
    assert "trap 'rm -rf \"$tmp\"' EXIT" in _BASE_BACKUP_SH


def test_base_backup_records_the_wal_segment_its_replay_starts_from() -> None:
    # This file is the sole input to WAL retention. Without it, pruning would have
    # nothing to derive from and would fall back to age — the exact silent
    # chain-breaking the retention rule exists to prevent.
    assert "backup_label" in _BASE_BACKUP_SH
    assert "START WAL LOCATION" in _BASE_BACKUP_SH
    assert 'printf \'%s\\n\' "$start_wal" > "$tmp/START_WAL"' in _BASE_BACKUP_SH
    # The record is written INSIDE the temp directory, so the rename publishes the
    # base and its replay floor atomically — a base can never appear without one.
    label_at = _BASE_BACKUP_SH.index('> "$tmp/START_WAL"')
    rename_at = _BASE_BACKUP_SH.index('mv "$tmp" "$base"')
    assert label_at < rename_at


def test_base_backup_fails_when_the_replay_floor_cannot_be_read() -> None:
    # A base whose START WAL is unknown cannot pin any segment, so publishing one
    # would quietly leave every retained segment prunable. Fail the run instead.
    assert 'if [ -z "$start_wal" ]; then' in _BASE_BACKUP_SH
    guard_at = _BASE_BACKUP_SH.index('if [ -z "$start_wal" ]')
    rename_at = _BASE_BACKUP_SH.index('mv "$tmp" "$base"')
    assert guard_at < rename_at, "the floor must be verified before the base is published"


def test_base_backup_gates_offsite_on_all_four_remote_vars() -> None:
    # PITR-04: identical gate to the dump's — all four set means ship, anything else
    # completes locally with the existing explicit notice and exits 0.
    lines = _executed_lines(_BASE_BACKUP_SH)
    start = next(i for i, ln in enumerate(lines) if ln.lstrip().startswith("if [ -n"))
    end = next(i for i in range(start, len(lines)) if lines[i].rstrip().endswith("; then"))
    conditional = " ".join(ln.rstrip().rstrip("\\").strip() for ln in lines[start : end + 1])
    for var in (
        "LEARNY_BACKUP_REMOTE_ENDPOINT",
        "LEARNY_BACKUP_REMOTE_ACCESS_KEY",
        "LEARNY_BACKUP_REMOTE_SECRET_KEY",
        "LEARNY_BACKUP_REMOTE_BUCKET",
    ):
        assert f'[ -n "${{{var}:-}}" ]' in conditional, f"offsite gate must check {var}"
    assert conditional.count("&&") == 3, "the four remote-var checks must be joined by &&"
    assert "||" not in conditional, "offsite gating must not OR the remote-var checks"
    # The same notice the dump logs, which CI asserts on.
    assert "offsite not configured" in _BASE_BACKUP_SH


def test_base_backup_prunes_only_after_success_and_exempts_the_newest() -> None:
    # PITR-06. `set -e` means a failed backup never reaches the prune, so a failure
    # can never shrink the retention window; the newest base is exempt regardless.
    assert '-mtime "+$LEARNY_BACKUP_KEEP_DAYS"' in _BASE_BACKUP_SH
    assert 'newest="$(ls -1dt' in _BASE_BACKUP_SH
    assert '! -path "$newest"' in _BASE_BACKUP_SH
    backup_at = _BASE_BACKUP_SH.rindex("pg_basebackup -h")
    prune_at = _BASE_BACKUP_SH.index("-mtime")
    assert backup_at < prune_at, "pruning must follow the backup, never precede it"


def test_base_backup_prune_targets_directories_not_the_whole_backup_tree() -> None:
    # The artifact is a directory, so the prune uses -type d. Bounding it with
    # -mindepth/-maxdepth 1 keeps it from matching the backup root itself or
    # descending into a base's contents.
    prune = next(ln for ln in _executed_lines(_BASE_BACKUP_SH) if ln.startswith("find "))
    assert "-mindepth 1 -maxdepth 1" in prune
    assert "-type d" in prune
    assert "-name 'learny-base-*'" in prune


def test_entrypoint_schedules_the_base_backup_weekly_clear_of_the_dump() -> None:
    # Sharing the dump's lock means an overlapping base backup is skipped, so the
    # defaults must not overlap: 02:00 Sunday against the dump's 03:30 nightly.
    assert "LEARNY_BASEBACKUP_CRON:=0 2 * * 0" in _ENTRYPOINT_SH
    executed = "\n".join(_executed_lines(_ENTRYPOINT_SH))
    assert "/usr/local/bin/base-backup.sh" in executed
    assert "> /etc/crontabs/root" in executed


def test_image_ships_the_base_backup_job_executable() -> None:
    assert "base-backup.sh" in _DOCKERFILE
    assert "base-backup-now" in _DOCKERFILE
    chmod = _DOCKERFILE[_DOCKERFILE.index("RUN chmod +x") :]
    assert "/usr/local/bin/base-backup.sh" in chmod
    assert "/usr/local/bin/base-backup-now" in chmod


# --- wal-archive.sh: shipping + base-derived retention (PITR-04/05) -------------
#
# The retention predicate is the highest-value assertion in this module: deleting a
# segment a retained base still needs breaks the replay chain invisibly, and the
# break only surfaces when someone actually attempts a restore.


def test_wal_archive_runs_in_strict_mode_with_pipefail() -> None:
    assert "set -euo pipefail" in _WAL_SH


def test_wal_pruning_derives_its_floor_from_the_oldest_retained_base() -> None:
    # PITR-05. The floor is read from the base's recorded start segment, not from a
    # clock, a constant, or the archive's own contents.
    assert "START_WAL" in _WAL_SH
    assert 'floor="$(cat "$oldest_base/START_WAL")"' in _WAL_SH
    assert 'oldest_base="$(ls -1d "$LEARNY_BASEBACKUP_DIR"/learny-base-*' in _WAL_SH


def test_age_alone_never_deletes_a_segment() -> None:
    """PITR-05's discriminating assertion.

    An age sweep would pass a naive "old segments are pruned" check while silently
    destroying recoverability. So the deletion must sit inside the floor comparison,
    and the age filter must only ever narrow the candidate set feeding it.
    """
    executed = _logical_lines(_WAL_SH)
    deletions = [i for i, line in enumerate(executed) if line.strip().startswith('rm -f "$path"')]
    assert len(deletions) == 1, "there must be exactly one segment deletion site"
    # The nearest enclosing condition above the deletion is the floor comparison.
    guards = [line for line in executed[: deletions[0]] if line.strip().startswith("if [ ")]
    assert guards[-1].strip() == 'if [ "$segment" \\< "$floor" ]; then', (
        f"the segment deletion must be guarded by the floor comparison, got {guards[-1]!r}"
    )
    # `find -mtime` produces candidates only; it must never delete.
    find_line = next(line for line in executed if line.startswith("find "))
    assert "-delete" not in find_line and "-exec rm" not in find_line, (
        "the age filter must only list candidates, never delete them"
    )
    assert '-print > "$candidates"' in find_line


def test_the_floor_comparison_is_strict_so_the_base_start_segment_survives() -> None:
    # The segment a base replays FROM is required by it. `<=` would delete exactly
    # the segment the oldest base needs first — an off-by-one that destroys the chain.
    assert '[ "$segment" \\< "$floor" ]' in _WAL_SH
    assert "\\<=" not in _WAL_SH


def test_no_base_backup_means_no_segment_is_pruned() -> None:
    # With no base there is no floor to derive from, and the fail-safe direction is
    # to keep everything rather than fall back to age.
    assert 'if [ -z "$oldest_base" ] || [ ! -f "$oldest_base/START_WAL" ]; then' in _WAL_SH
    bail_at = _WAL_SH.index("no retained base backup with a recorded start segment")
    delete_at = _WAL_SH.index('rm -f "$path"')
    assert bail_at < delete_at
    # The bail must actually leave the script, not merely log.
    tail = _WAL_SH[bail_at : bail_at + 400]
    assert "exit 0" in tail, "the no-base branch must exit before reaching the prune"
    # The branch is only reachable if looking for a base cannot itself abort the run.
    # Under `set -e` with `pipefail`, the glob matching nothing makes `ls` exit
    # non-zero and kills the script before the branch — observed, not theorised — so
    # the lookup must tolerate the empty case.
    lookup = next(line for line in _logical_lines(_WAL_SH) if line.startswith("oldest_base="))
    assert "|| true" in lookup, (
        "the oldest-base lookup must tolerate finding nothing, or the no-base "
        "fail-safe becomes an aborted run"
    )


def test_timeline_history_files_are_never_pruned() -> None:
    # A few bytes each, and what lets a restore resolve which timeline to follow.
    assert "*.history) continue ;;" in _WAL_SH


def test_segments_are_shipped_before_they_can_be_pruned() -> None:
    # PITR-04 + PITR-05 together: a segment deleted locally before it reached the
    # offsite bucket exists nowhere.
    ship_at = _WAL_SH.index("mc mirror")
    prune_at = _WAL_SH.index('rm -f "$path"')
    assert ship_at < prune_at


def test_wal_shipping_never_overwrites_an_archived_segment() -> None:
    # An archived segment is immutable; a local file differing from the object of the
    # same name means something is wrong, and overwriting would destroy the good copy.
    mirror = next(line for line in _executed_lines(_WAL_SH) if "mc mirror" in line)
    assert "--overwrite" not in mirror
    assert "--remove" not in mirror


def test_offsite_pruning_removes_only_what_was_pruned_locally() -> None:
    # Never a bulk age sweep and never `mirror --remove`: either would let an emptied
    # or lost local archive wipe the offsite copy that exists for exactly that case.
    assert "while IFS= read -r name; do" in _WAL_SH
    assert 'done < "$pruned"' in _WAL_SH
    assert "--older-than" not in _WAL_SH, "offsite WAL retention must not be age-driven"
    # Removal is guarded by an existence check, so a segment archived before offsite
    # was configured does not abort the run.
    assert 'if mc stat "$object" >/dev/null 2>&1; then' in _WAL_SH


def test_wal_archive_gates_offsite_on_all_four_remote_vars() -> None:
    lines = _executed_lines(_WAL_SH)
    start = next(i for i, ln in enumerate(lines) if ln.lstrip().startswith("if [ -n"))
    end = next(i for i in range(start, len(lines)) if lines[i].rstrip().endswith("; then"))
    conditional = " ".join(ln.rstrip().rstrip("\\").strip() for ln in lines[start : end + 1])
    for var in (
        "LEARNY_BACKUP_REMOTE_ENDPOINT",
        "LEARNY_BACKUP_REMOTE_ACCESS_KEY",
        "LEARNY_BACKUP_REMOTE_SECRET_KEY",
        "LEARNY_BACKUP_REMOTE_BUCKET",
    ):
        assert f'[ -n "${{{var}:-}}" ]' in conditional, f"offsite gate must check {var}"
    assert conditional.count("&&") == 3, "the four remote-var checks must be joined by &&"
    assert "||" not in conditional, "offsite gating must not OR the remote-var checks"
    assert "offsite not configured" in _WAL_SH


def test_wal_shipping_takes_its_own_lock_not_the_dump_lock() -> None:
    # It runs every few minutes and competes with nothing; sharing the dump's lock
    # would let one nightly dump silently stretch the offsite recovery point.
    assert "LEARNY_WAL_LOCK:=/tmp/learny-wal.lock" in _WAL_SH
    assert "LEARNY_BACKUP_LOCK" not in _WAL_SH
    guard = [line for line in _executed_lines(_WAL_SH) if "flock" in line]
    assert guard and "-n" in guard[0]


def test_entrypoint_schedules_wal_shipping_frequently() -> None:
    # This interval is the offsite recovery point for WAL, so it must be far shorter
    # than the nightly dump's — a daily schedule would make archiving pointless.
    assert "LEARNY_WAL_SHIP_CRON:=*/15 * * * *" in _ENTRYPOINT_SH
    executed = "\n".join(_executed_lines(_ENTRYPOINT_SH))
    assert "/usr/local/bin/wal-archive.sh" in executed


def test_entrypoint_schedules_all_three_jobs() -> None:
    # The crontab is written in one redirect; a job left out of the block is a
    # schedule that silently never runs.
    executed = "\n".join(_executed_lines(_ENTRYPOINT_SH))
    for job in ("backup.sh", "base-backup.sh", "wal-archive.sh"):
        assert f"/usr/local/bin/{job}" in executed, f"{job} must be scheduled"
    assert executed.count("> /etc/crontabs/root") == 1


def test_image_ships_the_wal_archive_job_executable() -> None:
    assert "wal-archive.sh" in _DOCKERFILE
    chmod = _DOCKERFILE[_DOCKERFILE.index("RUN chmod +x") :]
    assert "/usr/local/bin/wal-archive.sh" in chmod


# --- restore.sh safety-critical flags (OPS-09) ----------------------------------


def test_restore_requires_explicit_yes_before_touching_the_db() -> None:
    # Without --yes it must print the plan and exit non-zero (never restore).
    assert "--yes" in _RESTORE_SH
    assert 'if [ "$confirm" -ne 1 ]; then' in _RESTORE_SH
    # The plan branch exits before PGPASSWORD/pg_restore are ever reached. Use the
    # last pg_restore occurrence (the command; earlier ones are in the doc header).
    plan_at = _RESTORE_SH.index('"$confirm" -ne 1')
    restore_at = _RESTORE_SH.rindex("pg_restore")
    assert plan_at < restore_at


def test_restore_uses_clean_if_exists() -> None:
    # Assert on the actual command (last occurrence — earlier ones are the doc
    # header and the dry-run PLAN echo), so dropping the flags from the executed
    # pg_restore line fails here, not in production. --single-transaction makes a
    # partial restore roll back (implies --exit-on-error) instead of exiting 0 on a
    # half-restored db; --clean --if-exists keeps it idempotent.
    command_at = _RESTORE_SH.rindex("pg_restore")
    command_line = _RESTORE_SH[command_at:].splitlines()[0]
    assert "--single-transaction" in command_line
    assert "--clean --if-exists" in command_line


def test_restore_lists_archives_for_an_unknown_name() -> None:
    assert "archive not found" in _RESTORE_SH
    assert "available archives" in _RESTORE_SH


# --- image + entrypoint pins ----------------------------------------------------


def test_backup_image_pins_alpine_and_verifies_mc_checksum() -> None:
    assert "FROM alpine:3.22" in _DOCKERFILE
    # mc is pinned to a specific release and verified against a hardcoded digest ARG at
    # build — never a checksum fetched same-origin as the binary (trust-on-first-use).
    assert "MC_RELEASE=RELEASE." in _DOCKERFILE
    assert "ARG MC_SHA256=" in _DOCKERFILE
    assert "sha256sum -c" in _DOCKERFILE
    assert ".sha256sum" not in _DOCKERFILE, "the mc digest must be a pinned constant, not fetched"
    assert "postgresql16-client" in _DOCKERFILE


def test_entrypoint_defaults_the_schedule_and_runs_crond() -> None:
    assert "LEARNY_BACKUP_CRON:=30 3 * * *" in _ENTRYPOINT_SH
    assert "crond -f" in _ENTRYPOINT_SH


def test_entrypoint_renders_the_schedule_into_the_crontab() -> None:
    # The crond branch writes the schedule (running backup.sh) into /etc/crontabs/root;
    # pin the target on the executed line so a redirect to the wrong path — a silently
    # dead schedule — fails here, not in production.
    executed = "\n".join(_executed_lines(_ENTRYPOINT_SH))
    assert "/usr/local/bin/backup.sh" in executed
    assert "> /etc/crontabs/root" in executed


def test_entrypoint_persists_the_backup_env_filtered_by_prefix() -> None:
    # Cron runs jobs with a bare environment; the branch snapshots only the
    # POSTGRES_/MINIO_/LEARNY_ vars into /etc/backup.env. Pin the filter case and the
    # target on the executed lines, not a whole-file substring.
    executed = "\n".join(_executed_lines(_ENTRYPOINT_SH))
    assert "POSTGRES_*|MINIO_*|LEARNY_*)" in executed
    assert "> /etc/backup.env" in executed


def test_entrypoint_writes_the_backup_env_owner_only() -> None:
    # /etc/backup.env snapshots DB/MinIO/offsite credentials, so it must be created
    # owner-only. Pin the umask on the executed line (a doc comment must not satisfy it).
    assert any("umask 077" in line for line in _executed_lines(_ENTRYPOINT_SH))


# --- configuration is documented, credentials are not committed (PITR-10) -------

_ENV_EXAMPLE = (_REPO_ROOT / "backend" / ".env.production.example").read_text()

# Every name that would be a credential if it appeared with a literal value.
_SECRET_NAMES = (
    "POSTGRES_PASSWORD",
    "PGPASSWORD",
    "MINIO_ROOT_USER",
    "MINIO_ROOT_PASSWORD",
    "LEARNY_BACKUP_REMOTE_ACCESS_KEY",
    "LEARNY_BACKUP_REMOTE_SECRET_KEY",
)


def _shell_defaults(text: str) -> set[str]:
    """The ``LEARNY_*`` variables a script declares with ``: "${VAR:=default}"``."""
    return set(re.findall(r':\s*"\$\{(LEARNY_[A-Z0-9_]+):=', text))


def test_every_new_backup_variable_is_documented_for_operators() -> None:
    """PITR-10 — derived from the scripts, not from a hand-kept list.

    A variable a job reads but no template mentions is a setting the operator can
    only discover by reading the source, which is where undocumented retention
    knobs come from.
    """
    existing = _shell_defaults(_BACKUP_SH) | _shell_defaults(_RESTORE_SH)
    added = (
        _shell_defaults(_BASE_BACKUP_SH)
        | _shell_defaults(_WAL_SH)
        | _shell_defaults(_ENTRYPOINT_SH)
    ) - existing
    assert added, "expected the recovery jobs to introduce configuration"
    undocumented = {name for name in added if name not in _ENV_EXAMPLE}
    assert not undocumented, f"undocumented in .env.production.example: {sorted(undocumented)}"


def test_the_compose_level_archive_setting_is_documented() -> None:
    # The db's archive settings are compose interpolation rather than a secrets file,
    # so they are documented under their own heading; an operator tuning the recovery
    # point must be able to find the knob.
    base_text = _BASE.read_text()
    for name in set(re.findall(r"\$\{(LEARNY_[A-Z0-9_]+)(?::-[^}]*)?\}", base_text)):
        if name == "LEARNY_IMAGE_TAG":
            continue  # set by the deploy workflow, not an operator setting
        assert name in _ENV_EXAMPLE, f"{name} is interpolated into compose but undocumented"


def test_the_coupled_retention_rule_is_stated_where_operators_configure_it() -> None:
    # The one rule an operator can break by hand: the two artifact families cannot be
    # retained independently. Stating the knob without the coupling invites exactly
    # the age-based pruning that severs the chain.
    section = _ENV_EXAMPLE[_ENV_EXAMPLE.index("LEARNY_WAL_KEEP_DAYS") - 2000 :]
    assert "oldest retained base backup" in section
    assert "Never prune the archive by age by hand" in section


# The throwaway values used by local dev and by CI's scratch services. They exist
# only inside a developer's machine or a runner, and the dev/CI stacks must share
# them to boot at all. Anything else appearing as a literal is a real credential.
_THROWAWAY = {"learny", "learny-dev-secret"}


def test_no_credential_is_committed_in_compose_workflows_or_images() -> None:
    """PITR-10 — a production credential reaches a container only via a secrets file.

    Allow-listing the two documented throwaway values rather than excluding whole
    files keeps this able to catch a real secret pasted into any of them.
    """
    scanned = [
        _BASE,
        _PROD,
        _OVERRIDE,
        *sorted((_REPO_ROOT / ".github" / "workflows").glob("*.yml")),
        *sorted((_REPO_ROOT / "deploy" / "backup").iterdir()),
        *sorted((_REPO_ROOT / "deploy" / "postgres").iterdir()),
    ]
    offenders: list[str] = []
    for path in scanned:
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue  # prose naming a variable is not a credential
            for name in _SECRET_NAMES:
                # A literal value begins with an alphanumeric; every legitimate use is
                # a reference (`${VAR}`, `${VAR:?...}`, `${VAR:-...}`) or a bare name.
                for value in re.findall(rf"\b{name}\s*[:=]\s*['\"]?([A-Za-z0-9][^\s'\"]*)", line):
                    if value not in _THROWAWAY:
                        offenders.append(f"{path.relative_to(_REPO_ROOT)}:{number}: {name}={value}")
    assert not offenders, "committed credential(s):\n" + "\n".join(offenders)


def test_the_production_overlay_carries_no_credential_literal_at_all() -> None:
    # Even a throwaway value would be wrong in the production overlay: every service
    # there takes its credentials from a required secrets file.
    for number, line in enumerate(_PROD.read_text().splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        for name in _SECRET_NAMES:
            assert not re.search(rf"\b{name}\s*[:=]\s*['\"]?[A-Za-z0-9]", line), (
                f"docker-compose.prod.yml:{number} sets {name} inline"
            )


def test_the_database_image_carries_no_backup_credential() -> None:
    # The db archives to a shared volume precisely so the sidecar can own every
    # offsite decision; an object-store client or credential here would widen the
    # secret blast radius to the database container.
    postgres_dir = (_REPO_ROOT / "deploy" / "postgres").iterdir()
    text = "\n".join(p.read_text() for p in sorted(postgres_dir) if p.is_file())
    for marker in ("mc alias", "ACCESS_KEY", "SECRET_KEY", "aws", "s3"):
        assert marker not in text, f"the database image must not carry {marker!r}"


# --- CI restore roundtrip (OPS-10) ----------------------------------------------
#
# The end-to-end proof lives in ci.yml's compose-smoke job; these asserts pin the
# step sequence and the safety-critical strings so a reorder that would silently
# skip the proof (e.g. restoring before dropping, or dropping the offsite-notice
# assertion) fails here rather than passing a hollow CI run.


def _compose_smoke_scripts() -> str:
    """The compose-smoke job's ``run:`` bodies, concatenated in step order."""
    workflow = yaml.safe_load(_CI.read_text())
    steps = workflow["jobs"]["compose-smoke"]["steps"]
    return "\n".join(step.get("run", "") for step in steps)


def test_ci_seeds_the_marker_before_backing_up() -> None:
    scripts = _compose_smoke_scripts()
    assert scripts.index("CREATE TABLE backup_marker") < scripts.index("backup-now")


def test_ci_backup_run_asserts_the_offsite_notice() -> None:
    # The local-only run (no LEARNY_BACKUP_REMOTE_* set) must be asserted to emit the
    # exact notice backup.sh logs (OPS-05, OPS-10).
    scripts = _compose_smoke_scripts()
    assert "backup-now" in scripts
    assert "offsite not configured" in scripts


def test_ci_drops_the_marker_before_restoring() -> None:
    scripts = _compose_smoke_scripts()
    assert scripts.index("DROP TABLE backup_marker") < scripts.index("restore.sh --latest --yes")


def test_ci_restores_from_the_latest_dump_with_yes() -> None:
    # Matches the shipped restore invocation (deploy/backup/restore.sh, run directly
    # through the image entrypoint — there is no bare `restore` binary).
    assert "restore.sh --latest --yes" in _compose_smoke_scripts()


def test_ci_asserts_the_seeded_row_returns_after_restore() -> None:
    scripts = _compose_smoke_scripts()
    restore_at = scripts.index("restore.sh --latest --yes")
    assert_at = scripts.index("SELECT note FROM backup_marker")
    assert restore_at < assert_at, "the marker assertion must run after the restore"


def test_ci_proves_the_offsite_branch_after_the_local_roundtrip() -> None:
    # F9: the offsite branch was text-pinned only. CI now executes it against a scratch
    # bucket on the same MinIO — after the local-only roundtrip, so both paths run.
    scripts = _compose_smoke_scripts()
    assert scripts.index("offsite not configured") < scripts.index(
        "LEARNY_BACKUP_REMOTE_ENDPOINT=http://minio:9000"
    ), "the offsite proof must follow the local-only roundtrip"
    for var in (
        "LEARNY_BACKUP_REMOTE_ENDPOINT",
        "LEARNY_BACKUP_REMOTE_ACCESS_KEY",
        "LEARNY_BACKUP_REMOTE_SECRET_KEY",
        "LEARNY_BACKUP_REMOTE_BUCKET",
    ):
        assert f"{var}=" in scripts, f"the offsite CI run must set {var}"


def test_ci_asserts_offsite_dump_and_mirror_landed() -> None:
    # A follow-up mc listing proves the branch executed: the dump copy lands under db/
    # and the seeded source object is mirrored under objects/ in the offsite bucket.
    scripts = _compose_smoke_scripts()
    assert "mc ls --recursive m/learny-offsite-ci/db/" in scripts
    assert "mc ls --recursive m/learny-offsite-ci/objects/" in scripts
