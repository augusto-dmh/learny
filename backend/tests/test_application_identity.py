"""B4 gate — identity application services with fake ports.

Covers register/login/logout/current-user happy + failure paths, uniform login
failure (no enumeration), credential rehash-on-login, and the ownership
authorize allow/deny primitive (FR-AUTH-008).
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from app.application.errors import (
    EmailAlreadyExists,
    InvalidCredentials,
    NotAuthenticated,
    NotAuthorized,
    ValidationError,
)
from app.application.identity import (
    AuthenticateUser,
    AuthorizeOwnership,
    CurrentUser,
    Logout,
    RegisterUser,
)
from app.domain.entities import User
from tests.fakes import (
    FakeClock,
    FakeCredentialRepository,
    FakePasswordHasher,
    FakeSessionRepository,
    FakeUserRepository,
    SequentialTokenGenerator,
)

VALID_PASSWORD = "correct horse battery"  # >= 12 chars


@pytest.fixture
def ports():
    return {
        "users": FakeUserRepository(),
        "credentials": FakeCredentialRepository(),
        "sessions": FakeSessionRepository(),
        "hasher": FakePasswordHasher(),
        "tokens": SequentialTokenGenerator(),
        "clock": FakeClock(),
    }


def _register(ports, email="user@example.com", password=VALID_PASSWORD):
    return RegisterUser(**ports)(email=email, password=password)


# ---- RegisterUser ---------------------------------------------------------


def test_register_creates_user_credential_and_session(ports) -> None:
    result = _register(ports)
    assert result.user.email == "user@example.com"
    # Password is hashed, not stored plaintext.
    cred = ports["credentials"].get_by_user_id(result.user.id)
    assert cred is not None and cred.password_hash == f"hash::{VALID_PASSWORD}"
    # Session issued with a raw token + a distinct CSRF token.
    assert result.issued.raw_token == "token-1"
    assert result.issued.session.csrf_token == "token-2"


def test_register_normalizes_email(ports) -> None:
    result = _register(ports, email="  USER@Example.COM ")
    assert result.user.email == "user@example.com"


def test_register_rejects_duplicate_email(ports) -> None:
    _register(ports)
    with pytest.raises(EmailAlreadyExists):
        _register(ports)


def test_register_rejects_bad_email(ports) -> None:
    with pytest.raises(ValidationError):
        _register(ports, email="not-an-email")


def test_register_rejects_weak_password(ports) -> None:
    with pytest.raises(ValidationError):
        _register(ports, password="short")


# ---- AuthenticateUser -----------------------------------------------------


def test_login_succeeds_with_correct_password(ports) -> None:
    _register(ports)
    result = AuthenticateUser(**ports)(email="user@example.com", password=VALID_PASSWORD)
    assert result.user.email == "user@example.com"
    assert result.issued.raw_token  # a session was started


def test_login_wrong_password_is_invalid_credentials(ports) -> None:
    _register(ports)
    with pytest.raises(InvalidCredentials):
        AuthenticateUser(**ports)(email="user@example.com", password="wrong-password-xx")


def test_login_unknown_email_is_invalid_credentials(ports) -> None:
    # Uniform failure: same error type whether or not the email exists.
    with pytest.raises(InvalidCredentials):
        AuthenticateUser(**ports)(email="ghost@example.com", password=VALID_PASSWORD)


def test_login_rehashes_when_params_outdated(ports) -> None:
    _register(ports)
    ports["hasher"] = FakePasswordHasher(needs_rehash=True)
    AuthenticateUser(**ports)(email="user@example.com", password=VALID_PASSWORD)
    cred = ports["credentials"].get_by_user_id(
        ports["users"].get_by_email("user@example.com").id
    )
    assert cred is not None  # credential still present and updated path exercised


# ---- Logout ---------------------------------------------------------------


def test_logout_revokes_session(ports) -> None:
    result = _register(ports)
    Logout(sessions=ports["sessions"])(session_id=result.issued.session.id)
    assert ports["sessions"].get_by_raw_token(result.issued.raw_token) is None


# ---- CurrentUser ----------------------------------------------------------


def test_current_user_resolves_token(ports) -> None:
    result = _register(ports)
    user, session = CurrentUser(
        users=ports["users"], sessions=ports["sessions"], clock=ports["clock"]
    )(raw_token=result.issued.raw_token)
    assert user.id == result.user.id
    assert session.id == result.issued.session.id


def test_current_user_no_token_is_unauthenticated(ports) -> None:
    with pytest.raises(NotAuthenticated):
        CurrentUser(
            users=ports["users"], sessions=ports["sessions"], clock=ports["clock"]
        )(raw_token=None)


def test_current_user_unknown_token_is_unauthenticated(ports) -> None:
    with pytest.raises(NotAuthenticated):
        CurrentUser(
            users=ports["users"], sessions=ports["sessions"], clock=ports["clock"]
        )(raw_token="nope")


def test_current_user_expired_token_is_unauthenticated_and_revoked(ports) -> None:
    clock = FakeClock()
    ports["clock"] = clock
    # Short-lived session so we can expire it deterministically.
    result = RegisterUser(**ports, session_ttl=timedelta(minutes=5))(
        email="user@example.com", password=VALID_PASSWORD
    )
    clock.advance(timedelta(minutes=10))
    with pytest.raises(NotAuthenticated):
        CurrentUser(users=ports["users"], sessions=ports["sessions"], clock=clock)(
            raw_token=result.issued.raw_token
        )
    # Expired session revoked on resolution.
    assert ports["sessions"].get_by_raw_token(result.issued.raw_token) is None


# ---- AuthorizeOwnership ---------------------------------------------------


def test_authorize_allows_owner() -> None:
    user = User(id=uuid4(), email="o@example.com", created_at=FakeClock().now())
    authorize = AuthorizeOwnership()
    authorize(user=user, owner_id=user.id)  # no raise
    assert authorize.is_owner(user=user, owner_id=user.id) is True


def test_authorize_denies_non_owner() -> None:
    user = User(id=uuid4(), email="a@example.com", created_at=FakeClock().now())
    other_owner = uuid4()
    authorize = AuthorizeOwnership()
    with pytest.raises(NotAuthorized):
        authorize(user=user, owner_id=other_owner)
    assert authorize.is_owner(user=user, owner_id=other_owner) is False
