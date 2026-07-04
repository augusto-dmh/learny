"""Identity use-case services (design §3, task B4).

Framework-free application services orchestrating the domain ports. They contain
the security-relevant rules — input validation, uniform login failure (no user
enumeration), credential rehash-on-login, instant logout, and the ownership
authorization primitive — so the web layer (Phase C) stays a thin adapter.

A use case receives the ports it needs by constructor injection; nothing here
imports FastAPI, SQLAlchemy, or a provider SDK (ADR-007/009).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from app.application.errors import (
    EmailAlreadyExists,
    InvalidCredentials,
    NotAuthenticated,
    NotAuthorized,
)
from app.application.validation import validate_email, validate_password
from app.domain.entities import IssuedSession, PasswordCredential, Session, User
from app.domain.ports import (
    Clock,
    CredentialRepository,
    PasswordHasher,
    SessionRepository,
    TokenGenerator,
    UserRepository,
)

DEFAULT_SESSION_TTL = timedelta(days=14)

# How stale ``last_seen_at`` may become before an authenticated read refreshes it.
# Collapses bursts of reads (e.g. the SPA polling ``/me``) into at most one
# session write per interval, instead of a write on every request.
SESSION_TOUCH_INTERVAL = timedelta(seconds=60)


@dataclass(frozen=True)
class AuthResult:
    """Outcome of register/login: the user plus the issued session.

    Phase C reads ``issued.raw_token`` to set the HTTP-only session cookie and
    ``issued.session.csrf_token`` to surface the CSRF token to the SPA.
    """

    user: User
    issued: IssuedSession


def _start_session(
    *,
    user_id: UUID,
    sessions: SessionRepository,
    tokens: TokenGenerator,
    clock: Clock,
    session_ttl: timedelta,
) -> IssuedSession:
    """Mint a new session: raw opaque token + session-bound CSRF token."""
    raw_token = tokens.generate()
    csrf_token = tokens.generate()
    expires_at = clock.now() + session_ttl
    session = sessions.create(
        user_id=user_id,
        raw_token=raw_token,
        csrf_token=csrf_token,
        expires_at=expires_at,
    )
    return IssuedSession(session=session, raw_token=raw_token)


class RegisterUser:
    """Create an email/password account and start an authenticated session."""

    def __init__(
        self,
        *,
        users: UserRepository,
        credentials: CredentialRepository,
        sessions: SessionRepository,
        hasher: PasswordHasher,
        tokens: TokenGenerator,
        clock: Clock,
        session_ttl: timedelta = DEFAULT_SESSION_TTL,
    ) -> None:
        self._users = users
        self._credentials = credentials
        self._sessions = sessions
        self._hasher = hasher
        self._tokens = tokens
        self._clock = clock
        self._session_ttl = session_ttl

    def __call__(self, *, email: str, password: str) -> AuthResult:
        normalized_email = validate_email(email)
        validate_password(password)

        if self._users.get_by_email(normalized_email) is not None:
            raise EmailAlreadyExists("Email is already registered.")

        now = self._clock.now()
        user = User(id=uuid4(), email=normalized_email, created_at=now)
        self._users.add(user)

        password_hash = self._hasher.hash(password)
        self._credentials.add(
            PasswordCredential(
                user_id=user.id,
                password_hash=password_hash,
                algo_params={},
                updated_at=now,
            )
        )

        issued = _start_session(
            user_id=user.id,
            sessions=self._sessions,
            tokens=self._tokens,
            clock=self._clock,
            session_ttl=self._session_ttl,
        )
        return AuthResult(user=user, issued=issued)


class AuthenticateUser:
    """Validate credentials and start a session (uniform failure, no enumeration)."""

    def __init__(
        self,
        *,
        users: UserRepository,
        credentials: CredentialRepository,
        sessions: SessionRepository,
        hasher: PasswordHasher,
        tokens: TokenGenerator,
        clock: Clock,
        session_ttl: timedelta = DEFAULT_SESSION_TTL,
    ) -> None:
        self._users = users
        self._credentials = credentials
        self._sessions = sessions
        self._hasher = hasher
        self._tokens = tokens
        self._clock = clock
        self._session_ttl = session_ttl

    def __call__(self, *, email: str, password: str) -> AuthResult:
        normalized_email = validate_email(email)

        user = self._users.get_by_email(normalized_email)
        credential = (
            self._credentials.get_by_user_id(user.id) if user is not None else None
        )

        # Always verify against *some* hash to keep timing uniform and avoid
        # leaking whether the email exists. A dummy hash is used when absent.
        stored_hash = credential.password_hash if credential is not None else _DUMMY_HASH
        if not self._hasher.verify(password, stored_hash) or user is None:
            raise InvalidCredentials("Invalid email or password.")

        # Transparent credential upgrade if hashing parameters have changed.
        if credential is not None and self._hasher.needs_rehash(credential.password_hash):
            self._credentials.update(
                PasswordCredential(
                    user_id=user.id,
                    password_hash=self._hasher.hash(password),
                    algo_params={},
                    updated_at=self._clock.now(),
                )
            )

        issued = _start_session(
            user_id=user.id,
            sessions=self._sessions,
            tokens=self._tokens,
            clock=self._clock,
            session_ttl=self._session_ttl,
        )
        return AuthResult(user=user, issued=issued)


# A precomputed Argon2id hash of a random throwaway value, used so login verifies
# a real hash even when the email is unknown (constant work → no user
# enumeration via timing or code path). It never matches any user password.
_DUMMY_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$"
    "2cY4aXds1SwxMa6FpU2jsQ$"
    "QE0/tqeZu3lB0mPVJXSCtBpqRFC2uAvjsA/pnPLMWGk"
)


class Logout:
    """End an authenticated session (instant revocation)."""

    def __init__(self, *, sessions: SessionRepository) -> None:
        self._sessions = sessions

    def __call__(self, *, session_id: UUID) -> None:
        self._sessions.delete(session_id)


class CurrentUser:
    """Resolve a raw session token to its user, or signal not-authenticated."""

    def __init__(
        self,
        *,
        users: UserRepository,
        sessions: SessionRepository,
        clock: Clock,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._clock = clock

    def __call__(self, *, raw_token: str | None) -> tuple[User, Session]:
        if not raw_token:
            raise NotAuthenticated("No session token presented.")

        session = self._sessions.get_by_raw_token(raw_token)
        if session is None:
            raise NotAuthenticated("Unknown session token.")

        now = self._clock.now()
        if session.is_expired(now):
            # Expired sessions are revoked on resolution.
            self._sessions.delete(session.id)
            raise NotAuthenticated("Session expired.")

        user = self._users.get_by_id(session.user_id)
        if user is None:
            raise NotAuthenticated("Session user no longer exists.")

        # Refresh ``last_seen_at`` at most once per interval so authenticated
        # reads don't turn every request into a session-table write (a
        # write-on-read hotspot that contends under concurrency).
        if now - session.last_seen_at > SESSION_TOUCH_INTERVAL:
            self._sessions.touch(session.id, now)
        return user, session


class AuthorizeOwnership:
    """Ownership primitive (FR-AUTH-008): allow the owner, deny everyone else."""

    def __call__(self, *, user: User, owner_id: UUID) -> None:
        if user.id != owner_id:
            raise NotAuthorized("You do not have access to this resource.")

    def is_owner(self, *, user: User, owner_id: UUID) -> bool:
        """Non-raising variant for callers that want a boolean check."""
        return user.id == owner_id
