"""A gate — backup stack topology + script safety (unit, OPS-01..09).

Two layers, both pure text/YAML (no Docker required, deterministic):

* Compose topology — the prod overlay's ``backup`` sidecar (GHCR image, restart,
  the three required secret files, the ``backup_data`` volume, db+minio health
  gating, and NO host port) and the dev override's profile-gated build service.
* Script safety — the safety-critical flags of ``deploy/backup/*`` are pinned as
  text so a regression that silently drops (say) ``--clean --if-exists`` or the
  ``--yes`` restore guard fails here, not in production. The end-to-end behaviour
  is proven by the CI roundtrip (OPS-10); these asserts pin the exact flags CI
  cannot easily distinguish from a weakened variant.

Mirrors the merge semantics + helper shapes of ``test_deploy_topology.py``.
"""

from __future__ import annotations

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

_CI = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

_IMAGE_TAG = "${LEARNY_IMAGE_TAG:-latest}"


def _executed_lines(text: str) -> list[str]:
    """The script's executed lines (blank lines and full-line comments dropped).

    Guards against the L-010 anti-pattern: a safety flag named only in a doc comment
    must not satisfy an assertion — pin it on the line the shell actually runs.
    """
    return [
        line
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


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
    # pg_restore line fails here, not in production.
    command_at = _RESTORE_SH.rindex("pg_restore")
    command_line = _RESTORE_SH[command_at:].splitlines()[0]
    assert "--clean --if-exists" in command_line


def test_restore_lists_archives_for_an_unknown_name() -> None:
    assert "archive not found" in _RESTORE_SH
    assert "available archives" in _RESTORE_SH


# --- image + entrypoint pins ----------------------------------------------------


def test_backup_image_pins_alpine_and_verifies_mc_checksum() -> None:
    assert "FROM alpine:3.22" in _DOCKERFILE
    # mc is pinned to a specific release and its checksum enforced at build.
    assert "MC_RELEASE=RELEASE." in _DOCKERFILE
    assert "sha256sum -c" in _DOCKERFILE
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
    assert scripts.index("DROP TABLE backup_marker") < scripts.index(
        "restore.sh --latest --yes"
    )


def test_ci_restores_from_the_latest_dump_with_yes() -> None:
    # Matches the shipped restore invocation (deploy/backup/restore.sh, run directly
    # through the image entrypoint — there is no bare `restore` binary).
    assert "restore.sh --latest --yes" in _compose_smoke_scripts()


def test_ci_asserts_the_seeded_row_returns_after_restore() -> None:
    scripts = _compose_smoke_scripts()
    restore_at = scripts.index("restore.sh --latest --yes")
    assert_at = scripts.index("SELECT note FROM backup_marker")
    assert restore_at < assert_at, "the marker assertion must run after the restore"
