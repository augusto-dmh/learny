"""C1 gate — operator runbooks present and complete (unit, PROD-15/16/17).

These are documentation deliverables (AD-043); the checks guard that the required
sections and provider-neutral commands/triggers stay present so the runbooks do
not silently rot. Content is asserted, not executed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_OPS = Path(__file__).resolve().parents[2] / "docs" / "ops"
_BACKUPS = _OPS / "backups.md"
_ROLLBACK = _OPS / "rollback.md"
_DEPLOY = _OPS / "deploy.md"
_MONITORING = _OPS / "monitoring.md"
_INSTRUMENTATION = _OPS / "instrumentation.md"
_ADR = Path(__file__).resolve().parents[2] / "docs" / "adr"
_BACKUP_ADR = _ADR / "0024-backup-and-monitoring-stack.md"
_RECOVERY_ADR = _ADR / "0030-point-in-time-recovery-and-worker-loss.md"


def _collapsed(text: str) -> str:
    """One-line view of a document, so a hard-wrapped sentence still matches."""
    return " ".join(text.split())


@pytest.fixture
def backups() -> str:
    return _BACKUPS.read_text()


@pytest.fixture
def rollback() -> str:
    return _ROLLBACK.read_text()


@pytest.fixture
def deploy() -> str:
    return _DEPLOY.read_text()


@pytest.fixture
def monitoring() -> str:
    return _MONITORING.read_text()


@pytest.fixture
def instrumentation() -> str:
    return _INSTRUMENTATION.read_text()


@pytest.fixture
def backup_adr() -> str:
    return _BACKUP_ADR.read_text()


@pytest.fixture
def recovery_adr() -> str:
    return _RECOVERY_ADR.read_text()


def test_runbooks_exist() -> None:
    assert _BACKUPS.is_file()
    assert _ROLLBACK.is_file()


def test_backups_documents_postgres_dump_and_restore(backups: str) -> None:
    assert "pg_dump" in backups
    assert "pg_restore" in backups


def test_backups_documents_object_storage_backup_and_restore(backups: str) -> None:
    # Provider-neutral bucket backup + restore (both directions).
    assert "mc mirror" in backups
    assert "learny-sources" in backups


def test_backups_has_a_restore_drill(backups: str) -> None:
    assert "Restore drill" in backups


# --- automated backup pipeline (OPS-12) -----------------------------------------
# The "deliberately not fixed here" deferral is replaced by the real automated
# schedule/retention/offsite/heartbeat/restore documentation; pin its key strings so
# it cannot regress back to a manual-only runbook.


def test_backups_documents_the_schedule(backups: str) -> None:
    assert "LEARNY_BACKUP_CRON" in backups
    assert "30 3 * * *" in backups


def test_backups_documents_retention(backups: str) -> None:
    assert "LEARNY_BACKUP_KEEP_DAYS" in backups
    # The newest dump is always kept — retention never deletes the dump just written.
    assert "newest archive is always exempt" in backups


def test_backups_documents_offsite_configuration(backups: str) -> None:
    for var in (
        "LEARNY_BACKUP_REMOTE_ENDPOINT",
        "LEARNY_BACKUP_REMOTE_ACCESS_KEY",
        "LEARNY_BACKUP_REMOTE_SECRET_KEY",
        "LEARNY_BACKUP_REMOTE_BUCKET",
    ):
        assert var in backups
    # Unset => local-only mode with the exact notice the job logs.
    assert "offsite not configured" in backups
    assert "S3-compatible" in backups


def test_backups_documents_object_mirror_semantics(backups: str) -> None:
    # `mc mirror` without --remove: deleted app objects persist offsite.
    assert "without `--remove`" in backups


def test_backups_documents_the_heartbeat(backups: str) -> None:
    assert "LEARNY_BACKUP_HEARTBEAT_URL" in backups


def test_backups_documents_the_shipped_restore_script(backups: str) -> None:
    assert "restore.sh --latest --yes" in backups
    # The dry-run (no --yes) behaviour that refuses to touch the database.
    assert "without `--yes`" in backups


def test_backups_drops_the_deferral_text(backups: str) -> None:
    # The old "deliberately not fixed here" TODO must be gone (OPS-12).
    assert "deliberately not fixed here" not in backups


# --- point-in-time recovery (PITR-11) -------------------------------------------
# The runbook is the only place an operator learns that recovery to a moment exists,
# what the two artifact families are, and how their retentions interact. Every string
# pinned below is a code fact asserted elsewhere in this suite or in the shipped
# scripts, so a doc that drifts from the implementation fails here rather than during
# an incident.


def test_backups_documents_wal_archiving(backups: str) -> None:
    assert "archive_mode=on" in backups
    assert "archive_command=test ! -f /wal_archive/%f && cp %p /wal_archive/%f" in backups
    assert "LEARNY_WAL_ARCHIVE_TIMEOUT" in backups
    # archive_mode is postmaster-level: an operator who misses this enables nothing.
    assert "postmaster-level" in backups


def test_backups_documents_that_the_archive_lives_outside_the_data_volume(
    backups: str,
) -> None:
    # An archive inside db_data is lost with the directory it exists to recover.
    assert "not** inside `db_data`" in backups
    assert "wal_archive" in backups


def test_backups_adoption_warns_about_the_private_database_package(backups: str) -> None:
    # The adoption steps tell the operator to `pull db`, and `db` now runs a
    # repo-owned GHCR image that is private until the one-time visibility flip. Sending
    # them into that pull unwarned fails the deploy on the database itself.
    collapsed = _collapsed(backups)
    assert "learny-postgres" in collapsed
    assert "private by default" in collapsed
    assert "docs/ops/deploy.md" in collapsed
    assert "One-time: Flip GHCR packages to public" in collapsed


def test_backups_documents_what_a_base_backup_is_and_why(backups: str) -> None:
    assert "pg_basebackup -Ft -z -X stream --checkpoint=fast" in backups
    assert "LEARNY_BASEBACKUP_CRON" in backups
    assert "0 2 * * 0" in backups
    # The reason the nightly dump cannot play this role at all.
    assert "carries no WAL position" in _collapsed(backups)
    # The file the retention predicate reads.
    assert "START_WAL" in backups


def test_backups_documents_the_coupled_retention_rule(backups: str) -> None:
    assert "LEARNY_WAL_KEEP_DAYS" in backups
    assert "oldest *retained* base" in backups
    # The invariant, stated as such: age is a withholding condition, never a licence.
    assert "Age alone is never sufficient grounds to delete a segment" in backups
    # And its operational consequence.
    assert "Never delete files from `/wal_archive` by hand" in backups


def test_backups_documents_the_wal_offsite_recovery_point(backups: str) -> None:
    # WAL reaches the bucket on the sidecar's schedule, not continuously.
    assert "LEARNY_WAL_SHIP_CRON" in backups
    assert "*/15 * * * *" in backups


def test_backups_documents_the_lock_topology(backups: str) -> None:
    # Two locks, and why: sharing the dump's lock for WAL shipping would let one
    # nightly dump stretch the offsite recovery point.
    assert "LEARNY_BACKUP_LOCK" in backups
    assert "LEARNY_WAL_LOCK" in backups


def test_backups_documents_the_two_command_restore(backups: str) -> None:
    assert "two-command" in backups
    assert "restore-pitr.sh --target" in backups
    assert "--profile restore up -d --wait db-restore" in backups
    # The UTC-offset requirement the script enforces with exit 2.
    assert "+00:00" in backups
    # Dry run and the out-of-window failure, both non-destructive.
    assert "without `--yes`" in backups
    assert "earliest recoverable time" in backups


def test_backups_documents_the_state_a_restore_leaves_behind(backups: str) -> None:
    # Its own volume, never the live one — the property that makes a rehearsal safe.
    assert "pitr_data" in backups
    assert "never `db_data`" in _collapsed(backups)
    # Promoted and writable, not paused: "it accepts writes" must be a real signal.
    assert "recovery_target_action = 'promote'" in backups
    assert "archive_mode=off" in backups
    assert "read-only" in backups


def test_backups_drops_the_point_in_time_recovery_deferral(backups: str) -> None:
    # The runbook used to close by declaring PITR out of scope. It now ships.
    assert "out of scope" not in backups
    assert "## Point-in-time recovery" in backups


# --- the decision record behind the runbook (PITR-12) ---------------------------
# The runbook says how; the ADR says why each shape was forced. The pair only works
# if the ADR that deferred point-in-time recovery points at the one that ships it —
# a reader who lands on the older decision must not be left believing the deferral.


def test_the_recovery_decision_record_exists() -> None:
    assert _RECOVERY_ADR.is_file()


def test_the_recovery_record_states_what_it_supersedes(recovery_adr: str) -> None:
    assert "ADR-0024" in recovery_adr
    collapsed = _collapsed(recovery_adr)
    assert "PITR/WAL archiving remains a recorded future upgrade" in collapsed
    assert "superseded" in collapsed.lower()


def test_the_deferring_record_points_at_the_one_that_ships_it(backup_adr: str) -> None:
    assert "Superseded in part by ADR-0030" in backup_adr


# --- the pdf-worker size re-probe (PROBE-01) ------------------------------------


def test_the_pdf_worker_reprobe_is_recorded_with_its_outcome(backup_adr: str) -> None:
    collapsed = _collapsed(backup_adr)
    # The finding, and the version evidence behind it — the record is only useful if
    # the next reader can tell what was resolved rather than what was assumed.
    assert "Re-probed 2026-08-02" in collapsed
    assert "torch 2.13.0+cpu from `download.pytorch.org/whl/cpu`" in collapsed
    assert "Still no lockfile or pin change" in collapsed


def test_the_reprobe_left_the_dependency_pins_alone() -> None:
    """The probe was scoped record-only, and this is what makes that checkable.

    Adopting the CPU index later is a deliberate two-file change: the recipe lands in
    ``pyproject.toml`` and the note above stops saying no change was made.
    """
    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    assert "tool.uv.sources" not in pyproject
    assert "download.pytorch.org" not in pyproject


# --- deploy runbook secrets list (OPS-11) ---------------------------------------


def test_deploy_lists_the_backup_secrets_file(deploy: str) -> None:
    assert "backup.env" in deploy
    # Points operators at the single source of truth for the values.
    assert "backend/.env.production.example" in deploy


# --- monitoring runbook (OPS-15) ------------------------------------------------
# The netdata runbook must keep the loopback-tunnel access, the panels to watch,
# and backup-log inspection documented; pin the key strings so it cannot rot back
# into an empty stub or lose the security-relevant access instructions.


def test_monitoring_runbook_exists() -> None:
    assert _MONITORING.is_file()


def test_monitoring_documents_the_loopback_tunnel(monitoring: str) -> None:
    # Exact SSH local-forward of the loopback UI port — the only documented access.
    assert "ssh -L 19999:127.0.0.1:19999" in monitoring
    assert "http://localhost:19999" in monitoring


def test_monitoring_documents_the_loopback_only_exposure(monitoring: str) -> None:
    # Why the UI is not public: single public surface via Caddy.
    assert "127.0.0.1:19999:19999" in monitoring
    assert "single public surface" in monitoring.lower()


def test_monitoring_documents_the_panels_to_watch(monitoring: str) -> None:
    lowered = monitoring.lower()
    assert "mem_limit: 4g" in monitoring  # worker-pdf cap referenced by the memory panel
    assert "oom" in lowered
    assert "disk" in lowered


def test_monitoring_documents_backup_log_inspection(monitoring: str) -> None:
    assert "logs backup" in monitoring
    # The three run outcomes an operator distinguishes in those logs.
    assert "offsite not configured" in monitoring


def test_monitoring_documents_where_alert_hooks_attach(monitoring: str) -> None:
    lowered = monitoring.lower()
    assert "alert" in lowered
    assert "health" in lowered  # netdata's built-in health engine is the hook


def test_monitoring_documents_the_trust_boundary(monitoring: str) -> None:
    # The unauthenticated, host-privileged agent's sole boundary must be a documented
    # invariant (ADR-0024), not incidental — including the Docker-socket/API access.
    assert "Trust boundary" in monitoring
    lowered = monitoring.lower()
    assert "unauthenticated" in lowered
    assert "docker" in lowered


# --- app instrumentation runbook (OBS-24) ---------------------------------------
# The half of this note that earns its keep is the boundary half: a reader who
# quotes a number from a one-process, restart-volatile buffer as if it covered the
# deployment is worse off than one who never opened it. Pin how to reach the
# surface, both gates, the settings, and every stated limit.


def test_instrumentation_runbook_exists() -> None:
    assert _INSTRUMENTATION.is_file()


def test_instrumentation_documents_how_to_reach_the_surface(instrumentation: str) -> None:
    assert "GET /api/dev/instrument" in instrumentation
    # Through the Next.js proxy, which is what carries the session cookie.
    assert "http://localhost:3000/api/dev/instrument" in instrumentation


def test_instrumentation_documents_both_gates(instrumentation: str) -> None:
    assert "LEARNY_DEV_INSTRUMENT_ENABLED" in instrumentation
    assert "404" in instrumentation  # flag off
    assert "401" in instrumentation  # enabled but unauthenticated


def test_instrumentation_documents_the_settings(instrumentation: str) -> None:
    for var in (
        "LEARNY_INSTRUMENT_CAPACITY",
        "LEARNY_SLOW_QUERY_MS",
        "LEARNY_SLOW_QUERY_STATEMENT_CHARS",
    ):
        assert var in instrumentation


def test_instrumentation_documents_the_single_process_scope(instrumentation: str) -> None:
    lowered = instrumentation.lower()
    # Prod runs several API workers, so the surface is one worker's slice; local
    # runs a single worker, where it is complete.
    assert "LEARNY_API_WORKERS" in instrumentation
    assert "single" in lowered and "worker" in lowered
    assert "restart" in lowered


def test_instrumentation_documents_that_celery_durations_are_logs_only(
    instrumentation: str,
) -> None:
    assert "task.duration" in instrumentation
    assert "different process" in instrumentation.lower()


def test_instrumentation_documents_the_two_timing_semantics(instrumentation: str) -> None:
    # The header is the server's share; the log and the ranking are the whole
    # request, so streaming endpoints stay rankable by what they cost.
    assert "Server-Timing" in instrumentation
    assert "response_start_ms" in instrumentation
    assert "duration_ms" in instrumentation
    assert "time to response start" in instrumentation.lower()
    # The header ships on the instrument's switch, so a production deployment
    # sees none of it — a reader looking for the split must not be left hunting.
    collapsed = " ".join(instrumentation.lower().split())
    assert "no server-timing split in production" in collapsed


def test_instrumentation_documents_the_unhandled_exception_header_gap(
    instrumentation: str,
) -> None:
    assert "ServerErrorMiddleware" in instrumentation
    assert "X-Request-ID" in instrumentation


def test_instrumentation_documents_that_failed_statements_are_not_captured(
    instrumentation: str,
) -> None:
    assert "after_cursor_execute" in instrumentation
    assert "database error is not captured" in instrumentation


def test_instrumentation_documents_the_log_levels_and_the_truncation_asymmetry(
    instrumentation: str,
) -> None:
    assert "WARNING" in instrumentation
    lowered = instrumentation.lower()
    assert "untruncated" in lowered
    assert "one warning per statement" in lowered


def test_instrumentation_documents_why_production_does_not_expose_it(
    instrumentation: str,
) -> None:
    lowered = instrumentation.lower()
    assert "production" in lowered
    assert "statement text" in lowered
    # The refusal is the application's, not the compose file's omission: the
    # runbook must say which setting refuses it, since that is what an operator
    # would otherwise have to discover from a 404.
    assert "LEARNY_ENVIRONMENT=production" in instrumentation


def test_monitoring_points_at_the_instrumentation_runbook(monitoring: str) -> None:
    # Two tools, two questions — an operator landing on the host-metrics runbook
    # must be able to find the app-level one.
    assert "instrumentation.md" in monitoring


def test_rollback_documents_independent_image_revert(rollback: str) -> None:
    lowered = rollback.lower()
    assert "up -d api" in lowered
    assert "up -d worker" in lowered
    assert "up -d web" in lowered


def test_rollback_documents_migration_downgrade(rollback: str) -> None:
    assert "alembic downgrade" in rollback
    assert "forward-only" in rollback.lower()


def test_rollback_reproduces_the_trigger_table(rollback: str) -> None:
    for trigger in (
        "Auth or authorization regression",
        "Ingestion failures spike after worker deploy",
        "Migration failure",
    ):
        assert trigger in rollback


def test_rollback_notes_corpus_atomic_replace_implication(rollback: str) -> None:
    lowered = rollback.lower()
    assert "no versioning" in lowered or "no prior corpus version" in lowered
    assert "re-ingest" in lowered
