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
