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


@pytest.fixture
def backups() -> str:
    return _BACKUPS.read_text()


@pytest.fixture
def rollback() -> str:
    return _ROLLBACK.read_text()


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
