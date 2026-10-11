"""Learner provider keys at rest (live DB): sealed columns only, owner-scoped, cascading.

A stored key leaves only ciphertext, nonce, wrapped DEK, DEK nonce, the KEK id,
a fingerprint and the last four characters in its row; neither the plaintext
nor the plaintext DEK appears in any column. The row dies with its user. What
the repository hands back is metadata only, and a row that cannot be used
(an unconfigured KEK, a row copied onto another account) reads as absent.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import Connection, select, update

from app.domain.entities import User
from app.infrastructure.db.metadata import user_provider_credentials
from app.infrastructure.db.provider_credentials import SqlAlchemyProviderCredentialRepository
from app.infrastructure.db.repositories import SqlAlchemyUserRepository
from app.infrastructure.security.secrets_envelope import SecretsEnvelope, kek_id_for
from tests.conftest import requires_db

pytestmark = requires_db

_KEK = bytes(range(100, 132))
_KEY = "sk-ant-api03-repository-test-key-ABCDEFGH-wxyz"


def _user(db_conn: Connection) -> User:
    user = User(id=uuid4(), email=f"{uuid4()}@example.com", created_at=datetime.now(UTC))
    SqlAlchemyUserRepository(db_conn).add(user)
    return user


def _repo(db_conn: Connection, kek: bytes = _KEK) -> SqlAlchemyProviderCredentialRepository:
    return SqlAlchemyProviderCredentialRepository(db_conn, SecretsEnvelope(kek))


def _raw_row(db_conn: Connection, user_id: object):  # noqa: ANN202
    return db_conn.execute(
        select(user_provider_credentials).where(user_provider_credentials.c.user_id == user_id)
    ).one()


def test_row_holds_no_plaintext(db_conn: Connection) -> None:
    user = _user(db_conn)

    stored = _repo(db_conn).replace(user.id, "anthropic", _KEY)

    row = _raw_row(db_conn, user.id)
    assert set(row._mapping) == {
        "id",
        "user_id",
        "provider",
        "ciphertext",
        "nonce",
        "wrapped_dek",
        "dek_nonce",
        "kek_id",
        "fingerprint",
        "last4",
        "created_at",
        "updated_at",
    }
    aad = f"learny/provider-credential/v1/{user.id}/anthropic".encode()
    dek = AESGCM(_KEK).decrypt(bytes(row.dek_nonce), bytes(row.wrapped_dek), aad)
    key_bytes = _KEY.encode()
    for name, value in row._mapping.items():
        raw = bytes(value) if isinstance(value, (bytes, memoryview)) else str(value).encode()
        assert key_bytes not in raw, f"plaintext key in column {name}"
        assert dek not in raw, f"plaintext DEK in column {name}"
        assert dek.hex().encode() not in raw, f"hex DEK in column {name}"
        # No long run of the key survives in text form either (the last four do, by design).
        assert _KEY[:-4].encode() not in raw, f"key prefix in column {name}"
    assert row.last4 == "wxyz"
    assert len(bytes(row.nonce)) == 12 and len(bytes(row.dek_nonce)) == 12
    # The wrapped DEK is the 32-byte DEK plus its 16-byte GCM tag; the ciphertext
    # is the key's length plus a tag.
    assert len(bytes(row.wrapped_dek)) == 48
    assert len(bytes(row.ciphertext)) == len(key_bytes) + 16
    # The entity that leaves the repository carries metadata only.
    assert stored.last4 == "wxyz" and stored.provider == "anthropic"
    assert _KEY not in repr(stored)
    assert not hasattr(stored, "ciphertext") and not hasattr(stored, "api_key")
    # And the sealed row opens back to the key through the repository.
    assert _repo(db_conn).reveal(stored) == _KEY


def test_cascades_with_its_user(db_conn: Connection) -> None:
    doomed, survivor = _user(db_conn), _user(db_conn)
    repo = _repo(db_conn)
    repo.replace(doomed.id, "anthropic", _KEY)
    repo.replace(doomed.id, "openai", "sk-proj-openai-test-key-0123456789")
    repo.replace(survivor.id, "anthropic", _KEY)

    SqlAlchemyUserRepository(db_conn).delete(doomed.id)

    remaining = db_conn.execute(
        select(user_provider_credentials.c.user_id).where(
            user_provider_credentials.c.user_id.in_([doomed.id, survivor.id])
        )
    ).all()
    assert [r.user_id for r in remaining] == [survivor.id]


def test_replace_mints_a_new_row_and_keeps_one_per_provider(db_conn: Connection) -> None:
    user = _user(db_conn)
    repo = _repo(db_conn)
    first = repo.replace(user.id, "anthropic", _KEY)

    second = repo.replace(user.id, "anthropic", "sk-ant-api03-the-replacement-key-0000")

    rows = db_conn.execute(
        select(user_provider_credentials).where(user_provider_credentials.c.user_id == user.id)
    ).all()
    assert len(rows) == 1
    assert second.id != first.id
    assert second.fingerprint != first.fingerprint
    assert repo.reveal(first) is None  # the old row id no longer resolves
    assert repo.reveal(second) == "sk-ant-api03-the-replacement-key-0000"
    assert [c.provider for c in repo.list_for_user(user.id)] == ["anthropic"]


def test_a_replace_that_loses_the_unique_race_retries_once(
    db_conn: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A racing save lands between this replace's delete and its insert: the
    insert hits the unique constraint, and the replace retries and wins."""
    user = _user(db_conn)
    repo = _repo(db_conn)
    rival = _repo(db_conn)
    real_delete = SqlAlchemyProviderCredentialRepository.delete
    deletes: list[int] = []

    def _delete_then_lose(self: SqlAlchemyProviderCredentialRepository, *args: object) -> bool:
        removed = real_delete(self, *args)
        if self is repo and not deletes:
            deletes.append(1)
            rival.replace(user.id, "anthropic", "sk-ant-api03-the-racing-winner-key-0000")
        return removed

    monkeypatch.setattr(SqlAlchemyProviderCredentialRepository, "delete", _delete_then_lose)

    credential = repo.replace(user.id, "anthropic", _KEY)

    rows = db_conn.execute(
        select(user_provider_credentials).where(user_provider_credentials.c.user_id == user.id)
    ).all()
    assert deletes == [1]  # the race really happened
    assert len(rows) == 1
    assert rows[0].id == credential.id
    assert repo.reveal(credential) == _KEY


def test_reads_are_scoped_to_their_owner(db_conn: Connection) -> None:
    owner, other = _user(db_conn), _user(db_conn)
    repo = _repo(db_conn)
    stored = repo.replace(owner.id, "anthropic", _KEY)

    assert repo.get(other.id, "anthropic") is None
    assert repo.list_for_user(other.id) == []
    assert repo.delete(other.id, "anthropic") is False
    assert repo.get(owner.id, "anthropic") == stored
    assert repo.delete(owner.id, "anthropic") is True
    assert repo.get(owner.id, "anthropic") is None


def test_a_row_under_an_unknown_kek_reads_as_absent(db_conn: Connection) -> None:
    user = _user(db_conn)
    stored = _repo(db_conn).replace(user.id, "anthropic", _KEY)

    other_kek_repo = _repo(db_conn, os.urandom(32))

    assert other_kek_repo.list_for_user(user.id) == []
    assert other_kek_repo.get(user.id, "anthropic") is None
    assert other_kek_repo.reveal(stored) is None


def test_a_row_moved_onto_another_account_reads_as_absent(db_conn: Connection) -> None:
    """A database writer who copies one learner's sealed columns onto another
    learner's row gains nothing: the owner binding fails, so the copy reads as
    no credential rather than serving the first learner's key."""
    victim, thief = _user(db_conn), _user(db_conn)
    repo = _repo(db_conn)
    repo.replace(victim.id, "anthropic", _KEY)
    repo.replace(thief.id, "anthropic", "sk-ant-api03-thief-own-key-000000000")
    source = _raw_row(db_conn, victim.id)
    db_conn.execute(
        update(user_provider_credentials)
        .where(user_provider_credentials.c.user_id == thief.id)
        .values(
            ciphertext=source.ciphertext,
            nonce=source.nonce,
            wrapped_dek=source.wrapped_dek,
            dek_nonce=source.dek_nonce,
            kek_id=source.kek_id,
            fingerprint=source.fingerprint,
        )
    )

    assert repo.list_for_user(thief.id) == []
    assert repo.get(thief.id, "anthropic") is None


@pytest.mark.parametrize("provider", ["anthropic", "openai", "gemini"])
def test_each_provider_literal_round_trips(db_conn: Connection, provider: str) -> None:
    user = _user(db_conn)
    repo = _repo(db_conn)

    stored = repo.replace(user.id, provider, "k" * 30 + provider)

    assert repo.reveal(stored) == "k" * 30 + provider


def _damage_wrapped_dek(db_conn: Connection, credential_id: object) -> None:
    row = db_conn.execute(
        select(user_provider_credentials).where(user_provider_credentials.c.id == credential_id)
    ).one()
    wrapped = bytearray(row.wrapped_dek)
    wrapped[0] ^= 0x01
    db_conn.execute(
        update(user_provider_credentials)
        .where(user_provider_credentials.c.id == credential_id)
        .values(wrapped_dek=bytes(wrapped))
    )


def test_a_row_whose_wrapped_dek_fails_authentication_reveals_nothing(
    db_conn: Connection, caplog: pytest.LogCaptureFixture
) -> None:
    # The fingerprint covers the ciphertext and nonce, not the wrapped DEK, so a
    # damaged DEK passes the usability check and only the open itself fails.
    user = _user(db_conn)
    stored = _repo(db_conn).replace(user.id, "anthropic", _KEY)
    _damage_wrapped_dek(db_conn, stored.id)

    with caplog.at_level("DEBUG"):
        assert _repo(db_conn).reveal(stored) is None

    assert _repo(db_conn).get(user.id, "anthropic") is not None
    assert _KEY not in caplog.text
    assert str(stored.id) in caplog.text


@pytest.mark.parametrize(
    "bad_key",
    [
        pytest.param("sk-ant-short", id="shorter-than-the-floor"),
        pytest.param("k" * 19, id="one-under-the-floor"),
        pytest.param("abcd", id="four-characters"),
        pytest.param("sk-ant-api03-pasted-with-newline\n", id="trailing-newline"),
        pytest.param("sk-ant-api03 with-a-space-inside-it", id="inner-space"),
    ],
)
def test_a_key_too_short_or_holding_whitespace_is_never_sealed(
    db_conn: Connection, bad_key: str
) -> None:
    user = _user(db_conn)

    with pytest.raises(ValueError) as excinfo:
        _repo(db_conn).replace(user.id, "anthropic", bad_key)

    assert bad_key.strip() not in str(excinfo.value)
    assert _repo(db_conn).get(user.id, "anthropic") is None


def test_a_key_exactly_at_the_floor_is_sealed(db_conn: Connection) -> None:
    user = _user(db_conn)
    key = "k" * 16 + "wxyz"

    stored = _repo(db_conn).replace(user.id, "anthropic", key)

    assert len(key) == 20
    assert _repo(db_conn).reveal(stored) == key


def _damage_ciphertext(db_conn: Connection, credential_id: object) -> None:
    row = db_conn.execute(
        select(user_provider_credentials).where(user_provider_credentials.c.id == credential_id)
    ).one()
    ciphertext = bytearray(row.ciphertext)
    ciphertext[0] ^= 0x01
    db_conn.execute(
        update(user_provider_credentials)
        .where(user_provider_credentials.c.id == credential_id)
        .values(ciphertext=bytes(ciphertext))
    )


def test_rewrap_moves_a_row_without_opening_its_key(db_conn: Connection) -> None:
    # A damaged ciphertext only fails when the key is opened; re-wrapping the
    # DEK alone never looks at it, so the row still moves to the new KEK.
    old_kek, new_kek = os.urandom(32), os.urandom(32)
    stored = _repo(db_conn, old_kek).replace(_user(db_conn).id, "anthropic", _KEY)
    _damage_ciphertext(db_conn, stored.id)
    rotating = SqlAlchemyProviderCredentialRepository(db_conn, SecretsEnvelope(new_kek, [old_kek]))

    assert rotating.rewrap(stored.id) == "rewrapped"
    assert dict(rotating.kek_listing())[stored.id] == kek_id_for(new_kek)


def test_rewrap_reports_each_outcome_of_one_row(db_conn: Connection) -> None:
    old_kek, new_kek, stray_kek = os.urandom(32), os.urandom(32), os.urandom(32)
    old_repo = _repo(db_conn, old_kek)
    movable = old_repo.replace(_user(db_conn).id, "anthropic", _KEY)
    damaged = old_repo.replace(_user(db_conn).id, "anthropic", _KEY)
    _damage_wrapped_dek(db_conn, damaged.id)
    stray = _repo(db_conn, stray_kek).replace(_user(db_conn).id, "openai", "sk-proj-" + "x" * 24)
    rotating = SqlAlchemyProviderCredentialRepository(db_conn, SecretsEnvelope(new_kek, [old_kek]))

    assert rotating.rewrap(movable.id) == "rewrapped"
    assert rotating.rewrap(movable.id) == "current"  # a second run, or a concurrent one
    assert rotating.rewrap(damaged.id) == "unreadable"
    assert rotating.rewrap(stray.id) == "unknown_kek"
    assert rotating.rewrap(uuid4()) == "gone"  # deleted since it was listed
    assert _repo(db_conn, new_kek).reveal(movable) == _KEY
    listing = dict(rotating.kek_listing())
    assert set(listing) == {movable.id, damaged.id, stray.id}
    assert listing[movable.id] == kek_id_for(new_kek)
