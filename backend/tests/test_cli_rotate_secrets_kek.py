"""KEK rotation CLI (live DB): re-wrap DEKs, never touch ciphertext, report unknown KEKs.

``python -m app.cli.rotate_secrets_kek`` reads the KEK env the application
reads. With a new current KEK and the old one in
``LEARNY_SECRETS_KEK_PREVIOUS`` it re-wraps every row, leaves each
``ciphertext`` byte-identical, sets ``kek_id`` to the new KEK's id and keeps
every key decryptable; a second run reports 0 re-wrapped. A row under a KEK
nobody configured is counted as unknown and the command exits ``1``.

Each row is re-wrapped in its own unit of work. The tests run those units as
savepoints on the shared rolled-back connection.
"""

from __future__ import annotations

import base64
import hashlib
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import Connection, select

from app.cli import rotate_secrets_kek
from app.domain.entities import User
from app.infrastructure.db.metadata import user_provider_credentials
from app.infrastructure.db.provider_credentials import SqlAlchemyProviderCredentialRepository
from app.infrastructure.db.repositories import SqlAlchemyUserRepository
from app.infrastructure.security.secrets_envelope import SecretsEnvelope
from tests.conftest import clear_settings_and_generation_caches, requires_db

pytestmark = requires_db

_OLD_KEK = os.urandom(32)
_NEW_KEK = os.urandom(32)


def _b64(kek: bytes) -> str:
    return base64.b64encode(kek).decode()


@pytest.fixture
def savepoint_uow(db_conn: Connection, monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def _uow() -> Iterator[Connection]:
        with db_conn.begin_nested():
            yield db_conn

    monkeypatch.setattr(rotate_secrets_kek, "_uow", _uow)


def _configure(monkeypatch: pytest.MonkeyPatch, current: bytes, *previous: bytes) -> None:
    monkeypatch.setenv("LEARNY_SECRETS_KEK", _b64(current))
    if previous:
        monkeypatch.setenv("LEARNY_SECRETS_KEK_PREVIOUS", ",".join(_b64(k) for k in previous))
    else:
        monkeypatch.delenv("LEARNY_SECRETS_KEK_PREVIOUS", raising=False)
    clear_settings_and_generation_caches()


def _user(db_conn: Connection) -> User:
    user = User(id=uuid4(), email=f"{uuid4()}@example.com", created_at=datetime.now(UTC))
    SqlAlchemyUserRepository(db_conn).add(user)
    return user


def _rows(db_conn: Connection) -> dict:
    return {row.id: row for row in db_conn.execute(select(user_provider_credentials)).all()}


def test_rewraps_without_touching_ciphertext(
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    savepoint_uow: None,
) -> None:
    old_repo = SqlAlchemyProviderCredentialRepository(db_conn, SecretsEnvelope(_OLD_KEK))
    keys = {
        (_user(db_conn), "anthropic"): "sk-ant-api03-rotation-key-one-111111",
        (_user(db_conn), "openai"): "sk-proj-rotation-key-two-2222222222",
    }
    stored = {
        (user.id, provider): old_repo.replace(user.id, provider, key)
        for (user, provider), key in keys.items()
    }
    before = _rows(db_conn)
    new_kek_id = hashlib.sha256(_NEW_KEK).hexdigest()[:16]
    assert all(row.kek_id != new_kek_id for row in before.values())

    _configure(monkeypatch, _NEW_KEK, _OLD_KEK)
    exit_code = rotate_secrets_kek.main([])
    first_output = capsys.readouterr().out

    assert exit_code == 0
    assert "rewrapped=2" in first_output
    assert "already_current=0" in first_output
    assert "unknown_kek=0" in first_output
    after = _rows(db_conn)
    assert set(after) == set(before)
    for row_id, row in after.items():
        assert bytes(row.ciphertext) == bytes(before[row_id].ciphertext)
        assert bytes(row.nonce) == bytes(before[row_id].nonce)
        assert bytes(row.wrapped_dek) != bytes(before[row_id].wrapped_dek)
        assert row.kek_id == new_kek_id
        assert row.fingerprint == before[row_id].fingerprint
    # Every key opens under the new KEK alone: the old one is no longer needed.
    new_only = SqlAlchemyProviderCredentialRepository(db_conn, SecretsEnvelope(_NEW_KEK))
    for (user, provider), key in keys.items():
        assert new_only.reveal(stored[(user.id, provider)]) == key

    # A second run finds nothing left to re-wrap.
    assert rotate_secrets_kek.main([]) == 0
    second_output = capsys.readouterr().out
    assert "rewrapped=0" in second_output
    assert "already_current=2" in second_output
    # Neither run printed key material.
    for key in keys.values():
        assert key not in first_output and key not in second_output


def test_unknown_kek_exits_one(
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    savepoint_uow: None,
) -> None:
    orphan_kek = os.urandom(32)
    orphan = SqlAlchemyProviderCredentialRepository(db_conn, SecretsEnvelope(orphan_kek)).replace(
        _user(db_conn).id, "anthropic", "sk-ant-api03-orphaned-key-33333333"
    )
    SqlAlchemyProviderCredentialRepository(db_conn, SecretsEnvelope(_OLD_KEK)).replace(
        _user(db_conn).id, "anthropic", "sk-ant-api03-rotatable-key-4444444"
    )
    orphan_before = _rows(db_conn)[orphan.id]

    _configure(monkeypatch, _NEW_KEK, _OLD_KEK)
    exit_code = rotate_secrets_kek.main([])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "unknown_kek=1" in captured.out
    assert "rewrapped=1" in captured.out
    assert str(orphan.id) in captured.err
    assert "orphaned-key" not in captured.out + captured.err
    # The unknown row is reported, never rewritten.
    orphan_after = _rows(db_conn)[orphan.id]
    assert bytes(orphan_after.wrapped_dek) == bytes(orphan_before.wrapped_dek)
    assert orphan_after.kek_id == orphan_before.kek_id


def test_unreadable_row_exits_one_and_is_left_untouched(
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    savepoint_uow: None,
) -> None:
    repo = SqlAlchemyProviderCredentialRepository(db_conn, SecretsEnvelope(_OLD_KEK))
    damaged = repo.replace(_user(db_conn).id, "anthropic", "sk-ant-api03-damaged-key-55555555")
    repo.replace(_user(db_conn).id, "anthropic", "sk-ant-api03-healthy-key-666666666")
    # A wrapped DEK that no longer authenticates under the KEK its row names.
    wrapped = bytearray(_rows(db_conn)[damaged.id].wrapped_dek)
    wrapped[0] ^= 0x01
    db_conn.execute(
        user_provider_credentials.update()
        .where(user_provider_credentials.c.id == damaged.id)
        .values(wrapped_dek=bytes(wrapped))
    )
    damaged_before = _rows(db_conn)[damaged.id]

    _configure(monkeypatch, _NEW_KEK, _OLD_KEK)
    exit_code = rotate_secrets_kek.main([])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "unreadable=1" in captured.out
    assert "unknown_kek=0" in captured.out
    assert "rewrapped=1" in captured.out
    assert f"credential {damaged.id}: failed authentication" in captured.err
    assert "damaged-key" not in captured.out + captured.err
    # The unreadable row is reported, never rewritten.
    damaged_after = _rows(db_conn)[damaged.id]
    assert bytes(damaged_after.wrapped_dek) == bytes(damaged_before.wrapped_dek)
    assert damaged_after.kek_id == damaged_before.kek_id


def test_without_a_kek_the_command_refuses_with_exit_two(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("LEARNY_SECRETS_KEK", raising=False)
    clear_settings_and_generation_caches()

    assert rotate_secrets_kek.main([]) == 2
    assert "LEARNY_SECRETS_KEK" in capsys.readouterr().err
