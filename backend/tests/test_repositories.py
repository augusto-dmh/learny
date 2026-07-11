"""B3 gate — PostgreSQL repository adapters (integration, live test DB).

Exercises create/fetch for users, credentials, and sessions, and proves the
security-critical constraints: case-insensitive unique email, unique session
``token_hash``, and that only the token hash (never the raw token) is stored.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection
from sqlalchemy.exc import IntegrityError

from app.domain.entities import PasswordCredential, Source, User
from app.infrastructure.db.repositories import (
    SqlAlchemyCredentialRepository,
    SqlAlchemySessionRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyUserRepository,
)
from app.infrastructure.security.tokens import generate_token, hash_token
from tests.conftest import requires_db

pytestmark = requires_db


def _new_user(email: str) -> User:
    return User(id=uuid4(), email=email, created_at=datetime.now(UTC))


def _new_source(user_id: UUID, *, object_key: str, created_at: datetime | None = None) -> Source:
    now = created_at or datetime.now(UTC)
    return Source(
        id=uuid4(),
        user_id=user_id,
        title="A Book",
        filename="a-book.epub",
        content_type="application/epub+zip",
        byte_size=1024,
        checksum="d" * 64,
        object_key=object_key,
        status="uploaded",
        created_at=now,
        updated_at=now,
    )


def test_user_create_and_fetch(db_conn: Connection) -> None:
    repo = SqlAlchemyUserRepository(db_conn)
    user = _new_user("alice@example.com")
    repo.add(user)

    by_id = repo.get_by_id(user.id)
    by_email = repo.get_by_email("alice@example.com")
    assert by_id is not None and by_id.email == "alice@example.com"
    assert by_email is not None and by_email.id == user.id


def test_user_email_is_case_insensitive_unique(db_conn: Connection) -> None:
    repo = SqlAlchemyUserRepository(db_conn)
    repo.add(_new_user("Bob@Example.com"))
    # citext: lookup with different casing resolves the same row.
    assert repo.get_by_email("bob@example.com") is not None
    with pytest.raises(IntegrityError):
        repo.add(_new_user("bob@EXAMPLE.com"))


def test_get_missing_user_returns_none(db_conn: Connection) -> None:
    repo = SqlAlchemyUserRepository(db_conn)
    assert repo.get_by_id(uuid4()) is None
    assert repo.get_by_email("nobody@example.com") is None


def test_credential_create_fetch_update(db_conn: Connection) -> None:
    users = SqlAlchemyUserRepository(db_conn)
    creds = SqlAlchemyCredentialRepository(db_conn)
    user = _new_user("carol@example.com")
    users.add(user)

    cred = PasswordCredential(
        user_id=user.id,
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$abc$def",
        algo_params={"t": 3},
        updated_at=datetime.now(UTC),
    )
    creds.add(cred)
    fetched = creds.get_by_user_id(user.id)
    assert fetched is not None
    assert fetched.password_hash == cred.password_hash
    assert fetched.algo_params == {"t": 3}

    updated = PasswordCredential(
        user_id=user.id,
        password_hash="$argon2id$v=19$m=131072,t=4,p=4$ghi$jkl",
        algo_params={"t": 4},
        updated_at=datetime.now(UTC),
    )
    creds.update(updated)
    refetched = creds.get_by_user_id(user.id)
    assert refetched is not None and refetched.algo_params == {"t": 4}


def test_session_create_stores_only_token_hash(db_conn: Connection) -> None:
    users = SqlAlchemyUserRepository(db_conn)
    sessions = SqlAlchemySessionRepository(db_conn)
    user = _new_user("dave@example.com")
    users.add(user)

    raw = generate_token()
    created = sessions.create(
        user_id=user.id,
        raw_token=raw,
        csrf_token="csrf-123",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    # Persisted value is the hash, not the raw token.
    assert created.token_hash == hash_token(raw)
    assert created.token_hash != raw
    assert created.csrf_token == "csrf-123"

    resolved = sessions.get_by_raw_token(raw)
    assert resolved is not None and resolved.id == created.id
    assert sessions.get_by_raw_token("not-the-token") is None


def test_session_token_hash_unique(db_conn: Connection) -> None:
    users = SqlAlchemyUserRepository(db_conn)
    sessions = SqlAlchemySessionRepository(db_conn)
    user = _new_user("erin@example.com")
    users.add(user)

    raw = generate_token()
    sessions.create(
        user_id=user.id,
        raw_token=raw,
        csrf_token="c1",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    # Same raw token → same token_hash → unique constraint must reject.
    with pytest.raises(IntegrityError):
        sessions.create(
            user_id=user.id,
            raw_token=raw,
            csrf_token="c2",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )


def test_session_touch_and_delete(db_conn: Connection) -> None:
    users = SqlAlchemyUserRepository(db_conn)
    sessions = SqlAlchemySessionRepository(db_conn)
    user = _new_user("frank@example.com")
    users.add(user)

    raw = generate_token()
    created = sessions.create(
        user_id=user.id,
        raw_token=raw,
        csrf_token="c",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    later = datetime.now(UTC) + timedelta(minutes=5)
    sessions.touch(created.id, later)
    touched = sessions.get_by_raw_token(raw)
    assert touched is not None and touched.last_seen_at >= created.last_seen_at

    sessions.delete(created.id)
    assert sessions.get_by_raw_token(raw) is None


def test_source_add_and_get_by_id(db_conn: Connection) -> None:
    users = SqlAlchemyUserRepository(db_conn)
    sources = SqlAlchemySourceRepository(db_conn)
    user = _new_user("grace@example.com")
    users.add(user)

    source = _new_source(user.id, object_key=f"sources/{user.id}/{uuid4()}.epub")
    returned = sources.add(source)
    assert returned.id == source.id

    fetched = sources.get_by_id(source.id)
    assert fetched is not None
    assert fetched.object_key == source.object_key
    assert fetched.user_id == user.id
    assert fetched.byte_size == 1024
    assert fetched.checksum == "d" * 64
    assert fetched.status == "uploaded"


def test_source_get_missing_returns_none(db_conn: Connection) -> None:
    sources = SqlAlchemySourceRepository(db_conn)
    assert sources.get_by_id(uuid4()) is None


def test_source_list_by_user_is_newest_first(db_conn: Connection) -> None:
    users = SqlAlchemyUserRepository(db_conn)
    sources = SqlAlchemySourceRepository(db_conn)
    user = _new_user("heidi@example.com")
    users.add(user)

    base = datetime.now(UTC)
    older = _new_source(user.id, object_key=f"sources/{user.id}/{uuid4()}.epub", created_at=base)
    newer = _new_source(
        user.id,
        object_key=f"sources/{user.id}/{uuid4()}.epub",
        created_at=base + timedelta(minutes=1),
    )
    sources.add(older)
    sources.add(newer)

    listed = sources.list_by_user(user.id)
    assert [s.id for s in listed] == [newer.id, older.id]


def test_source_list_is_owner_scoped(db_conn: Connection) -> None:
    users = SqlAlchemyUserRepository(db_conn)
    sources = SqlAlchemySourceRepository(db_conn)
    alice = _new_user("ivan@example.com")
    bob = _new_user("judy@example.com")
    users.add(alice)
    users.add(bob)

    a1 = _new_source(alice.id, object_key=f"sources/{alice.id}/{uuid4()}.epub")
    a2 = _new_source(alice.id, object_key=f"sources/{alice.id}/{uuid4()}.epub")
    b1 = _new_source(bob.id, object_key=f"sources/{bob.id}/{uuid4()}.epub")
    for source in (a1, a2, b1):
        sources.add(source)

    alice_ids = {s.id for s in sources.list_by_user(alice.id)}
    assert alice_ids == {a1.id, a2.id}
    assert b1.id not in alice_ids
    assert [s.id for s in sources.list_by_user(bob.id)] == [b1.id]


def test_source_object_key_is_unique(db_conn: Connection) -> None:
    users = SqlAlchemyUserRepository(db_conn)
    sources = SqlAlchemySourceRepository(db_conn)
    user = _new_user("mallory@example.com")
    users.add(user)

    key = f"sources/{user.id}/{uuid4()}.epub"
    sources.add(_new_source(user.id, object_key=key))
    with pytest.raises(IntegrityError):
        sources.add(_new_source(user.id, object_key=key))
