"""B1 gate — identity domain entity invariants + import boundary.

Unit-level checks that the domain layer encodes its security invariants and
stays free of outward (infrastructure/framework/SDK) imports (ADR-007/009).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.domain import (
    Clock,
    CredentialRepository,
    IssuedSession,
    PasswordCredential,
    PasswordHasher,
    Session,
    SessionRepository,
    StoragePort,
    User,
    UserRepository,
)

_SECRET_FIELD_HINTS = ("password", "secret", "hash", "token")


def test_user_has_no_password_material() -> None:
    """User must not expose password/secret material (spec AC-4 / NFR-SEC-004)."""
    field_names = {f.name for f in dataclasses.fields(User)}
    assert field_names == {"id", "email", "created_at"}
    for name in field_names:
        assert not any(hint in name for hint in _SECRET_FIELD_HINTS), name


def test_user_is_frozen() -> None:
    user = User(id=uuid4(), email="a@b.com", created_at=datetime.now(UTC))
    try:
        user.email = "c@d.com"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("User should be immutable")


def test_password_credential_holds_hash_not_plaintext() -> None:
    cred = PasswordCredential(
        user_id=uuid4(),
        password_hash="$argon2id$dummy",
        algo_params={"m": 65536},
        updated_at=datetime.now(UTC),
    )
    assert cred.password_hash.startswith("$argon2id$")
    assert "plaintext" not in {f.name for f in dataclasses.fields(PasswordCredential)}


def test_session_persists_only_token_hash() -> None:
    """Session entity stores the hash, never the raw opaque token (design §4)."""
    field_names = {f.name for f in dataclasses.fields(Session)}
    assert "token_hash" in field_names
    assert "raw_token" not in field_names
    assert "token" not in field_names


def test_session_is_expired() -> None:
    now = datetime.now(UTC)
    expired = Session(
        id=uuid4(),
        user_id=uuid4(),
        token_hash="h",
        csrf_token="c",
        expires_at=now - timedelta(seconds=1),
        created_at=now,
        last_seen_at=now,
    )
    active = dataclasses.replace(expired, expires_at=now + timedelta(hours=1))
    assert expired.is_expired(now) is True
    assert active.is_expired(now) is False


def test_issued_session_carries_raw_token_once() -> None:
    now = datetime.now(UTC)
    session = Session(
        id=uuid4(),
        user_id=uuid4(),
        token_hash="h",
        csrf_token="c",
        expires_at=now + timedelta(hours=1),
        created_at=now,
        last_seen_at=now,
    )
    issued = IssuedSession(session=session, raw_token="raw-opaque")
    assert issued.raw_token == "raw-opaque"
    assert issued.session.token_hash == "h"


def test_ports_are_runtime_checkable_protocols() -> None:
    """Ports are structural Protocols so any conforming adapter satisfies them."""
    for port in (
        Clock,
        PasswordHasher,
        UserRepository,
        CredentialRepository,
        SessionRepository,
        StoragePort,
    ):
        assert getattr(port, "_is_runtime_protocol", False), port


def test_domain_has_no_outward_imports() -> None:
    """domain/ source must not import infrastructure, FastAPI, or known SDKs."""
    import pathlib

    import app.domain as domain_pkg

    forbidden = (
        "app.infrastructure",
        "app.application",
        "fastapi",
        "sqlalchemy",
        "alembic",
        "celery",
        "argon2",
        "pwdlib",
        "openai",
        "anthropic",
    )
    domain_dir = pathlib.Path(domain_pkg.__file__).parent
    for path in domain_dir.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert (
                f"import {token}" not in source and f"from {token}" not in source
            ), f"{path.name} imports forbidden module {token}"
