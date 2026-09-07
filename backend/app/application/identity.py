"""Identity use-case services (design §3, task B4).

Framework-free application services orchestrating the domain ports. They contain
the security-relevant rules — input validation, uniform login failure (no user
enumeration), credential rehash-on-login, instant logout, and the ownership
authorization primitive — so the web layer (Phase C) stays a thin adapter.

A use case receives the ports it needs by constructor injection; nothing here
imports FastAPI, SQLAlchemy, or a provider SDK (ADR-007/009).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from app.application.activation import ACTIVATION_ACCOUNT_CREATED, RecordActivation
from app.application.errors import (
    AccountDeleteFailed,
    EmailAlreadyExists,
    InvalidCredentials,
    InvalidToken,
    InviteRequired,
    NotAuthenticated,
    NotAuthorized,
    StorageUnavailable,
    ValidationError,
)
from app.application.invites import INVITE_REQUIRED_MESSAGE, InviteRepository
from app.application.media import media_object_key
from app.application.validation import (
    SAMPLE_OPERATOR_EMAIL,
    TOS_ACCEPTANCE_MESSAGE,
    is_disposable_email,
    validate_email,
    validate_password,
)
from app.domain.entities import IssuedSession, PasswordCredential, Session, User
from app.domain.ports import (
    Clock,
    CorpusRepository,
    CredentialRepository,
    EmailPort,
    EmailTokenRepository,
    PasswordHasher,
    SessionRepository,
    SourceRepository,
    StoragePort,
    TokenGenerator,
    UserRepository,
)

DEFAULT_SESSION_TTL = timedelta(days=14)

# How stale ``last_seen_at`` may become before an authenticated read refreshes it.
# Collapses bursts of reads (e.g. the SPA polling ``/me``) into at most one
# session write per interval, instead of a write on every request.
SESSION_TOUCH_INTERVAL = timedelta(seconds=60)

# Media references embedded in section markdown by the corpus builder
# (``application/media.py``): ``/api/sources/{id}/media/{sha256}``. The digest
# is the storage key's file stem — the one shape ``media_object_key`` builds.
_MEDIA_DIGEST = re.compile(r"/api/sources/[\da-f-]+/media/([\da-f]{64})")

logger = logging.getLogger(__name__)

# The closed purpose vocabulary for ``email_tokens.purpose``. A token minted for
# one purpose can never serve the other: the consume predicate matches the hash
# *and* the purpose, so a verify link can never reset a password (DOOR-35).
PURPOSE_VERIFY = "verify"
PURPOSE_RESET = "reset"

# The uniform user-facing copy for a token that is not live (DOOR-35): unknown,
# consumed, expired, and wrong-purpose are indistinguishable to the client.
INVALID_TOKEN_MESSAGE = "This link is invalid or has expired."

VERIFY_SUBJECT = "Verify your Learny email"
VERIFY_BODY = (
    "Welcome to Learny!\n\n"
    "Confirm your email address with this single-use token:\n\n{token}\n\n"
    "If you did not create an account, you can ignore this message."
)
RESET_SUBJECT = "Reset your Learny password"
RESET_BODY = (
    "Someone asked to reset your Learny password.\n\n"
    "Use this single-use token to choose a new one:\n\n{token}\n\n"
    "If this was not you, you can ignore this message."
)


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
    """Create an email/password account and start an authenticated session.

    When an ``invites`` gate is wired (the composition root wires one exactly
    where ``LEARNY_INVITE_REQUIRED`` is on), a live invite code is demanded and
    consumed; without the gate an absent code is ignored, so self-host and CI
    register exactly as before the rail existed (DOOR-26).
    """

    def __init__(
        self,
        *,
        users: UserRepository,
        credentials: CredentialRepository,
        sessions: SessionRepository,
        hasher: PasswordHasher,
        tokens: TokenGenerator,
        clock: Clock,
        record_activation: RecordActivation,
        invites: InviteRepository | None = None,
        send_verification: SendEmailVerification | None = None,
        session_ttl: timedelta = DEFAULT_SESSION_TTL,
    ) -> None:
        self._users = users
        self._credentials = credentials
        self._sessions = sessions
        self._hasher = hasher
        self._tokens = tokens
        self._clock = clock
        self._record_activation = record_activation
        self._invites = invites
        self._send_verification = send_verification
        self._session_ttl = session_ttl

    def __call__(
        self,
        *,
        email: str,
        password: str,
        invite_code: str | None = None,
        accepted_tos: bool = True,
    ) -> AuthResult:
        # Consent first (DOOR-25): without an explicit acceptance nothing else is
        # validated — no user material is created and no invite is consumed. The
        # HTTP boundary defaults this to False, so an absent field is a refusal;
        # programmatic callers default to True because consent is a client-facing
        # concern they satisfy upstream.
        if not accepted_tos:
            raise ValidationError(TOS_ACCEPTANCE_MESSAGE)

        normalized_email = validate_email(email)
        if is_disposable_email(normalized_email):
            # The same generic invalid-email copy as a malformed address: the
            # response must not reveal that disposability is the reason (DOOR-23).
            raise ValidationError("Invalid email address.")
        validate_password(password)
        if normalized_email == SAMPLE_OPERATOR_EMAIL:
            raise ValidationError("Invalid email address.")

        # The invite gate runs before any user material is written and before the
        # duplicate-email check, so a rejected register leaves no user, session,
        # or half-burned code behind, and a bad code cannot probe which emails
        # exist (DOOR-20). Absent code, unknown, exhausted, and expired codes all
        # answer the same uniform 403 copy (DOOR-22).
        if self._invites is not None:
            if not invite_code:
                raise InviteRequired(INVITE_REQUIRED_MESSAGE)
            self._invites.consume(invite_code, now=self._clock.now())

        if self._users.get_by_email(normalized_email) is not None:
            raise EmailAlreadyExists("Email is already registered.")

        now = self._clock.now()
        user = User(id=uuid4(), email=normalized_email, created_at=now, accepted_tos_at=now)
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
        self._record_activation(user_id=user.id, name=ACTIVATION_ACCOUNT_CREATED)
        # The verify mail is fire-and-forget (DOOR-34/40): the token row was
        # written with the register writes above, and the service below swallows
        # its own transport failures, so a dead relay can never turn this 201 —
        # the invited first session (AD-327) — into a 500. Verification never
        # gates this session: the account is usable unverified.
        if self._send_verification is not None:
            self._send_verification(user_id=user.id, email=normalized_email)
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
        credential = self._credentials.get_by_user_id(user.id) if user is not None else None

        # Always verify against *some* hash to keep timing uniform and avoid
        # leaking whether the email exists. When the credential is absent, use a
        # dummy hash sourced from the hasher port so it always matches the active
        # adapter's format (the encoding never leaks into this layer).
        stored_hash = (
            credential.password_hash if credential is not None else self._hasher.dummy_hash()
        )
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


class SendEmailVerification:
    """Mint a single-use verify token for an account and email it (DOOR-34).

    The token row is written first, inside the caller's transaction, so it
    exists whether or not the send succeeds; the send itself is best-effort by
    design (DOOR-40): a transport failure is logged — never with the raw token,
    which lives only in the mail body — and swallowed, because a dead relay must
    not fail the register or resend that triggered it. The learner re-requests
    the mail later.

    ``emails`` may raise anything: ``send`` never lets it escape. The port is
    wired wherever register/resend are, so callers need no guard of their own.
    """

    def __init__(
        self,
        *,
        email_tokens: EmailTokenRepository,
        emails: EmailPort,
        tokens: TokenGenerator,
        clock: Clock,
        ttl: timedelta,
    ) -> None:
        self._email_tokens = email_tokens
        self._emails = emails
        self._tokens = tokens
        self._clock = clock
        self._ttl = ttl

    def __call__(self, *, user_id: UUID, email: str) -> None:
        raw_token = self._tokens.generate()
        self._email_tokens.create(
            user_id=user_id,
            purpose=PURPOSE_VERIFY,
            raw_token=raw_token,
            expires_at=self._clock.now() + self._ttl,
        )
        try:
            self._emails.send(
                to=email, subject=VERIFY_SUBJECT, body=VERIFY_BODY.format(token=raw_token)
            )
        except Exception:
            # Best-effort (DOOR-40): the failure is named for the operator
            # without the raw token — logging the body or the token would put a
            # live capability in the logs.
            logger.exception("email.send.failed purpose=%s", PURPOSE_VERIFY)


class VerifyEmail:
    """Consume a raw verify token and stamp ``email_verified_at`` (DOOR-35)."""

    def __init__(
        self,
        *,
        email_tokens: EmailTokenRepository,
        users: UserRepository,
        clock: Clock,
    ) -> None:
        self._email_tokens = email_tokens
        self._users = users
        self._clock = clock

    def __call__(self, *, raw_token: str) -> None:
        now = self._clock.now()
        user_id = self._email_tokens.consume(raw_token, purpose=PURPOSE_VERIFY, now=now)
        if user_id is None:
            raise InvalidToken(INVALID_TOKEN_MESSAGE)
        self._users.set_email_verified(user_id, now)


class RequestPasswordReset:
    """Mint + email a reset token when — and only when — the email exists (DOOR-36).

    Unknown and known addresses must be indistinguishable from the outside: this
    service answers quietly (no token row, no send) for an unknown email and
    raises nothing for a known one, so the HTTP layer can return the same 204
    either way and the flow cannot enumerate accounts. Like the verify send, the
    send itself is best-effort and swallowed.
    """

    def __init__(
        self,
        *,
        users: UserRepository,
        email_tokens: EmailTokenRepository,
        emails: EmailPort,
        tokens: TokenGenerator,
        clock: Clock,
        ttl: timedelta,
    ) -> None:
        self._users = users
        self._email_tokens = email_tokens
        self._emails = emails
        self._tokens = tokens
        self._clock = clock
        self._ttl = ttl

    def __call__(self, *, email: str) -> None:
        normalized = validate_email(email)
        user = self._users.get_by_email(normalized)
        if user is None:
            # No mail, no row, no error: the observable outcome is identical to
            # the known-address path (DOOR-36).
            return
        raw_token = self._tokens.generate()
        self._email_tokens.create(
            user_id=user.id,
            purpose=PURPOSE_RESET,
            raw_token=raw_token,
            expires_at=self._clock.now() + self._ttl,
        )
        try:
            self._emails.send(
                to=user.email, subject=RESET_SUBJECT, body=RESET_BODY.format(token=raw_token)
            )
        except Exception:
            logger.exception("email.send.failed purpose=%s", PURPOSE_RESET)


class ResetPassword:
    """Consume a live reset token and set a new password (DOOR-37).

    The password policy is checked *before* the consume, so a rejected password
    costs no token; the consume (single-use, purpose-checked, atomic) gates the
    credential write, so a replayed or wrong-purpose token updates nothing.
    """

    def __init__(
        self,
        *,
        email_tokens: EmailTokenRepository,
        credentials: CredentialRepository,
        hasher: PasswordHasher,
        clock: Clock,
    ) -> None:
        self._email_tokens = email_tokens
        self._credentials = credentials
        self._hasher = hasher
        self._clock = clock

    def __call__(self, *, raw_token: str, password: str) -> None:
        validate_password(password)
        now = self._clock.now()
        user_id = self._email_tokens.consume(raw_token, purpose=PURPOSE_RESET, now=now)
        if user_id is None:
            raise InvalidToken(INVALID_TOKEN_MESSAGE)
        updated = PasswordCredential(
            user_id=user_id,
            password_hash=self._hasher.hash(password),
            algo_params={},
            updated_at=now,
        )
        # A reset establishes a credential for an account without one (and
        # replaces the hash for everyone else).
        if self._credentials.get_by_user_id(user_id) is None:
            self._credentials.add(updated)
        else:
            self._credentials.update(updated)


class Logout:
    """End an authenticated session (instant revocation)."""

    def __init__(self, *, sessions: SessionRepository) -> None:
        self._sessions = sessions

    def __call__(self, *, session_id: UUID) -> None:
        self._sessions.delete(session_id)


class DeleteAccount:
    """Erase the caller's account: storage objects first, then the user row.

    The order is the fail-closed guarantee (DOOR-30..32): every object key
    derived from the caller's *owned* sources — the uploaded file plus the
    figure rasters the corpus embeds — is deleted before ``users.delete`` fires,
    so a storage fault leaves the account fully intact (no half-erased user) and
    surfaces as :class:`AccountDeleteFailed` (502, retry-safe: object deletes
    are idempotent, so a retry converges). The shared sample is never owned by
    the caller and no other user's key is ever derivable from their rows, so
    neither is ever in the delete list (DOOR-33).
    """

    def __init__(
        self,
        *,
        users: UserRepository,
        sources: SourceRepository,
        corpus: CorpusRepository,
        storage: StoragePort,
    ) -> None:
        self._users = users
        self._sources = sources
        self._corpus = corpus
        self._storage = storage

    def _object_keys(self, *, user: User) -> list[str]:
        """Every storage key derived from ``user``'s owned sources, deduplicated."""
        keys: list[str] = []
        for source in self._sources.list_by_user(user.id):
            if source.user_id != user.id:
                continue  # the shared sample (and only it) is visible but not owned
            keys.append(source.object_key)
            for markdown in self._corpus.list_section_markdown(source.id):
                keys.extend(
                    media_object_key(user_id=user.id, source_id=source.id, digest=digest)
                    for digest in _MEDIA_DIGEST.findall(markdown)
                )
        return list(dict.fromkeys(keys))

    def __call__(self, *, user: User) -> None:
        keys = self._object_keys(user=user)
        try:
            for key in keys:
                self._storage.delete_object(key)
        except StorageUnavailable as exc:
            raise AccountDeleteFailed("Account deletion failed. Please try again.") from exc
        self._users.delete(user.id)


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
