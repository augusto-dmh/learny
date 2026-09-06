"""Email port + verify/reset flow tests (RFC-0007 Cycle F; matrix row "EmailPort").

Adapter selection and the two transports behind :class:`~app.domain.ports.EmailPort`
(DOOR-34/40), then the verify/reset flows built on top of it (DOOR-34..40). No
test here opens a network socket: the SMTP adapter is exercised by patching the
``smtplib.SMTP`` class in the adapter's own module, the log adapter writes to
the logging framework, and the flow tests capture mail with a recording fake.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, func, select

from app.application.activation import RecordActivation
from app.application.errors import InvalidToken, ValidationError
from app.application.identity import (
    INVALID_TOKEN_MESSAGE,
    RequestPasswordReset,
    ResetPassword,
    SendEmailVerification,
    VerifyEmail,
)
from app.core.config import Settings
from app.domain.entities import PasswordCredential, User
from app.domain.ports import EmailPort
from app.infrastructure.email import (
    LogEmailSender,
    SmtpEmailSender,
    build_email_sender,
)
from app.infrastructure.security.tokens import hash_token
from tests.conftest import TEST_PASSWORD, requires_db
from tests.fakes import (
    FakeActivationEventRepository,
    FakeClock,
    FakeCredentialRepository,
    FakeEmailSender,
    FakeEmailTokenRepository,
    FakePasswordHasher,
    FakeSessionRepository,
    FakeUserRepository,
    SequentialTokenGenerator,
)

MAIL_TTL = timedelta(minutes=60)
NEW_PASSWORD = "a brand new long password"


def _settings(**overrides: object) -> Settings:
    """Settings without the developer's ``backend/.env`` (defaults + overrides)."""
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


# ---- Adapter selection (host set → SMTP; host empty → log) --------------------


def test_host_set_selects_the_smtp_adapter() -> None:
    sender = build_email_sender(
        _settings(smtp_host="mail.example.com", smtp_port=2525, smtp_from="learny@example.com")
    )
    assert isinstance(sender, SmtpEmailSender)
    # Both adapters satisfy the runtime-checkable port structurally.
    assert isinstance(sender, EmailPort)


def test_empty_host_selects_the_log_adapter() -> None:
    sender = build_email_sender(_settings())
    assert isinstance(sender, LogEmailSender)
    assert isinstance(sender, EmailPort)


# ---- SMTP transport: the message assembly, with the client class patched ------


def test_smtp_adapter_hands_one_plain_text_message_to_smtplib() -> None:
    with patch("app.infrastructure.email.smtp.smtplib.SMTP") as smtp_cls:
        client = smtp_cls.return_value.__enter__.return_value
        sender = SmtpEmailSender(host="mail.example.com", port=2525, sender="learny@example.com")

        sender.send(to="reader@example.com", subject="Verify your email", body="token-1")

        # One SMTP client, pointed at the configured host/port, no TLS/socket
        # work of our own beyond what smtplib does internally.
        smtp_cls.assert_called_once_with("mail.example.com", 2525)
        # The full payload is asserted by value: envelope sender, recipient, and
        # a message whose headers and body carry the subject/body we were given.
        client.sendmail.assert_called_once_with(
            "learny@example.com",
            ["reader@example.com"],
            "From: learny@example.com\r\n"
            "To: reader@example.com\r\n"
            "Subject: Verify your email\r\n"
            "\r\n"
            "token-1",
        )


# ---- Log transport: host-less default, no socket ------------------------------


def test_log_adapter_logs_the_message_without_a_socket(caplog) -> None:  # noqa: ANN001
    with patch("app.infrastructure.email.smtp.smtplib.SMTP") as smtp_cls:
        with caplog.at_level(logging.INFO, logger="app.infrastructure.email.log"):
            LogEmailSender().send(
                to="reader@example.com", subject="Verify your email", body="token-1"
            )
        assert smtp_cls.call_count == 0

    records = [r for r in caplog.records if r.name == "app.infrastructure.email.log"]
    assert len(records) == 1
    assert "reader@example.com" in records[0].getMessage()
    assert "Verify your email" in records[0].getMessage()


# ---- Capturing double (what the flow tests assert with) -----------------------


def test_fake_email_sender_captures_messages_in_memory() -> None:
    fake = FakeEmailSender()
    assert isinstance(fake, EmailPort)

    fake.send(to="reader@example.com", subject="Reset your password", body="token-2")

    assert fake.sent == [
        {"to": "reader@example.com", "subject": "Reset your password", "body": "token-2"}
    ]


# ---- Verify/reset flows: unit level (fakes only, deterministic tokens) --------


def _user(email: str = "mail-flow@example.com") -> tuple[FakeUserRepository, User]:
    users = FakeUserRepository()
    user = User(id=uuid4(), email=email, created_at=FakeClock().now())
    users.add(user)
    return users, user


def _credential(user_id, password_hash: str, clock: FakeClock) -> PasswordCredential:  # noqa: ANN001
    return PasswordCredential(
        user_id=user_id, password_hash=password_hash, algo_params={}, updated_at=clock.now()
    )


def _send_verification(
    *,
    email_tokens: FakeEmailTokenRepository,
    emails: FakeEmailSender,
    tokens: SequentialTokenGenerator,
    clock: FakeClock,
) -> SendEmailVerification:
    return SendEmailVerification(
        email_tokens=email_tokens, emails=emails, tokens=tokens, clock=clock, ttl=MAIL_TTL
    )


def _register_user(
    ports: dict[str, object],
    *,
    send_verification: SendEmailVerification | None = None,
):  # noqa: ANN202 — RegisterUser
    from app.application.identity import RegisterUser

    return RegisterUser(
        **ports,  # type: ignore[arg-type]
        record_activation=RecordActivation(
            activations=FakeActivationEventRepository(),
            clock=ports["clock"],  # type: ignore[arg-type]
        ),
        send_verification=send_verification,
    )


def test_send_verification_stores_only_the_hash_and_mails_the_raw_token() -> None:
    users, user = _user()
    email_tokens = FakeEmailTokenRepository()
    emails = FakeEmailSender()
    tokens = SequentialTokenGenerator()
    clock = FakeClock()

    _send_verification(email_tokens=email_tokens, emails=emails, tokens=tokens, clock=clock)(
        user_id=user.id, email=user.email
    )

    # The mail body carries the raw token to the user's address; the store
    # carries only its SHA-256 — the raw token never lands at rest.
    assert len(emails.sent) == 1
    assert emails.sent[0]["to"] == user.email
    assert "token-1" in emails.sent[0]["body"]
    assert email_tokens.stored_hashes() == [hash_token("token-1")]


def test_register_mints_user_and_session_even_when_the_sender_raises() -> None:
    ports: dict[str, object] = {
        "users": FakeUserRepository(),
        "credentials": FakeCredentialRepository(),
        "sessions": FakeSessionRepository(),
        "hasher": FakePasswordHasher(),
        "tokens": SequentialTokenGenerator(),
        "clock": FakeClock(),
    }
    email_tokens = FakeEmailTokenRepository()
    send = _send_verification(
        email_tokens=email_tokens,
        emails=FakeEmailSender(error=RuntimeError("smtp relay down")),
        tokens=ports["tokens"],  # type: ignore[arg-type]
        clock=ports["clock"],  # type: ignore[arg-type]
    )

    result = _register_user(ports, send_verification=send)(
        email="raised@example.com", password="correct horse battery"
    )

    # The raising adapter changed nothing about the outcome (DOOR-40): user,
    # credential, and the invited first session all exist (AD-327).
    assert result.user.email == "raised@example.com"
    assert result.issued.raw_token
    assert ports["sessions"].get_by_raw_token(result.issued.raw_token) is not None  # type: ignore[attr-defined]
    # The verify token row was written before the failing send.
    assert len(email_tokens.stored_hashes()) == 1


def test_confirm_stamps_email_verified_at_and_replay_fails() -> None:
    users, user = _user()
    email_tokens = FakeEmailTokenRepository()
    clock = FakeClock()
    _send_verification(
        email_tokens=email_tokens,
        emails=FakeEmailSender(),
        tokens=SequentialTokenGenerator(),
        clock=clock,
    )(user_id=user.id, email=user.email)

    verify = VerifyEmail(email_tokens=email_tokens, users=users, clock=clock)
    verify(raw_token="token-1")
    assert users.get_by_email(user.email).email_verified_at == clock.now()  # type: ignore[union-attr]

    # A consumed token is dead: the replay is the same uniform failure (DOOR-35).
    with pytest.raises(InvalidToken) as replay:
        verify(raw_token="token-1")
    assert str(replay.value) == INVALID_TOKEN_MESSAGE


def test_expired_token_is_rejected() -> None:
    users, user = _user()
    email_tokens = FakeEmailTokenRepository()
    clock = FakeClock()
    _send_verification(
        email_tokens=email_tokens,
        emails=FakeEmailSender(),
        tokens=SequentialTokenGenerator(),
        clock=clock,
    )(user_id=user.id, email=user.email)
    clock.advance(MAIL_TTL + timedelta(minutes=1))

    with pytest.raises(InvalidToken):
        VerifyEmail(email_tokens=email_tokens, users=users, clock=clock)(raw_token="token-1")
    assert users.get_by_email(user.email).email_verified_at is None  # type: ignore[union-attr]


def test_a_verify_token_cannot_reset_and_a_reset_token_cannot_verify() -> None:
    users, user = _user()
    email_tokens = FakeEmailTokenRepository()
    emails = FakeEmailSender()
    clock = FakeClock()
    tokens = SequentialTokenGenerator()
    _send_verification(email_tokens=email_tokens, emails=emails, tokens=tokens, clock=clock)(
        user_id=user.id, email=user.email
    )
    RequestPasswordReset(
        users=users,
        email_tokens=email_tokens,
        emails=emails,
        tokens=tokens,
        clock=clock,
        ttl=MAIL_TTL,
    )(email=user.email)
    credentials = FakeCredentialRepository()
    credentials.add(_credential(user.id, "hash::correct horse battery", clock))
    reset = ResetPassword(
        email_tokens=email_tokens, credentials=credentials, hasher=FakePasswordHasher(), clock=clock
    )
    verify = VerifyEmail(email_tokens=email_tokens, users=users, clock=clock)

    # token-1 is a verify token: it resets nothing.
    with pytest.raises(InvalidToken):
        reset(raw_token="token-1", password=NEW_PASSWORD)
    assert credentials.get_by_user_id(user.id).password_hash == "hash::correct horse battery"  # type: ignore[union-attr]

    # token-2 is a reset token: it verifies nothing.
    with pytest.raises(InvalidToken):
        verify(raw_token="token-2")
    assert users.get_by_email(user.email).email_verified_at is None  # type: ignore[union-attr]


def test_reset_request_for_unknown_email_sends_nothing_and_stores_nothing() -> None:
    users, _ = _user()
    email_tokens = FakeEmailTokenRepository()
    emails = FakeEmailSender()

    RequestPasswordReset(
        users=users,
        email_tokens=email_tokens,
        emails=emails,
        tokens=SequentialTokenGenerator(),
        clock=FakeClock(),
        ttl=MAIL_TTL,
    )(email="ghost@example.com")

    # The unknown path is silent: no mail, no token row, no error (DOOR-36).
    assert emails.sent == []
    assert email_tokens.stored_hashes() == []


def test_reset_with_valid_token_replaces_the_hash_exactly_once() -> None:
    users, user = _user()
    email_tokens = FakeEmailTokenRepository()
    emails = FakeEmailSender()
    tokens = SequentialTokenGenerator()
    clock = FakeClock()
    RequestPasswordReset(
        users=users,
        email_tokens=email_tokens,
        emails=emails,
        tokens=tokens,
        clock=clock,
        ttl=MAIL_TTL,
    )(email=user.email)
    credentials = FakeCredentialRepository()
    credentials.add(_credential(user.id, "hash::correct horse battery", clock))
    reset = ResetPassword(
        email_tokens=email_tokens, credentials=credentials, hasher=FakePasswordHasher(), clock=clock
    )

    reset(raw_token="token-1", password=NEW_PASSWORD)

    # The old hash is gone; the new password verifies against the stored hash.
    stored = credentials.get_by_user_id(user.id)  # type: ignore[union-attr]
    assert stored.password_hash == f"hash::{NEW_PASSWORD}"
    assert FakePasswordHasher().verify("correct horse battery", stored.password_hash) is False
    assert FakePasswordHasher().verify(NEW_PASSWORD, stored.password_hash) is True

    # The token was consumed exactly once: the replay fails and changes nothing.
    with pytest.raises(InvalidToken):
        reset(raw_token="token-1", password="another long password")
    assert credentials.get_by_user_id(user.id).password_hash == f"hash::{NEW_PASSWORD}"  # type: ignore[union-attr]


def test_rejected_password_does_not_burn_the_reset_token() -> None:
    users, user = _user()
    email_tokens = FakeEmailTokenRepository()
    emails = FakeEmailSender()
    tokens = SequentialTokenGenerator()
    clock = FakeClock()
    RequestPasswordReset(
        users=users,
        email_tokens=email_tokens,
        emails=emails,
        tokens=tokens,
        clock=clock,
        ttl=MAIL_TTL,
    )(email=user.email)
    reset = ResetPassword(
        email_tokens=email_tokens,
        credentials=FakeCredentialRepository(),
        hasher=FakePasswordHasher(),
        clock=clock,
    )

    with pytest.raises(ValidationError):
        reset(raw_token="token-1", password="too-short")

    # The policy check ran before the consume: the same token still works.
    reset(raw_token="token-1", password=NEW_PASSWORD)


# ---- Verify/reset flows: integration (real Postgres, FastAPI TestClient) ------


def _token_from_body(body: str) -> str:
    """The raw token is the standalone paragraph of the mail body."""
    return body.split("\n\n")[2]


def _override_sender(client: TestClient, emails: FakeEmailSender) -> None:
    from app.infrastructure.web.dependencies import get_email_sender

    client.app.dependency_overrides[get_email_sender] = lambda: emails


@requires_db
def test_register_is_201_and_mails_a_hashed_token_even_when_smtp_raises(
    auth_client: TestClient, db_conn: Connection
) -> None:
    from app.infrastructure.db.metadata import email_tokens
    from app.infrastructure.db.metadata import users as users_table

    emails = FakeEmailSender(error=RuntimeError("smtp relay down"))
    _override_sender(auth_client, emails)

    resp = auth_client.post(
        "/api/auth/register",
        json={"email": "raised@example.com", "password": TEST_PASSWORD, "accepted_tos": True},
    )
    assert resp.status_code == 201, resp.text

    # The unverified session is a real one (DOOR-39/AD-327): /me answers while
    # ``email_verified_at`` is still NULL.
    me = auth_client.get("/api/auth/me")
    assert me.status_code == 200, me.text
    user_id = UUID(me.json()["id"])
    stamp = db_conn.execute(
        select(users_table.c.email_verified_at).where(users_table.c.id == user_id)
    ).scalar_one()
    assert stamp is None

    # The captured mail holds the raw token (the send raised after delivering
    # its payload to the port boundary); the DB holds only the hash — the raw
    # token appears nowhere at rest.
    assert len(emails.sent) == 1
    raw = _token_from_body(emails.sent[0]["body"])
    raw_at_rest = db_conn.execute(
        select(func.count()).select_from(email_tokens).where(email_tokens.c.secret_hash == raw)
    ).scalar_one()
    assert raw_at_rest == 0
    stored = db_conn.execute(
        select(email_tokens.c.purpose, email_tokens.c.secret_hash, email_tokens.c.consumed_at)
    ).all()
    assert stored == [("verify", hash_token(raw), None)]


@requires_db
def test_confirm_sets_email_verified_then_replay_and_cross_purpose_are_403(
    auth_client: TestClient, db_conn: Connection
) -> None:
    from app.infrastructure.db.metadata import users as users_table

    emails = FakeEmailSender()
    _override_sender(auth_client, emails)
    registered = auth_client.post(
        "/api/auth/register",
        json={"email": "confirm@example.com", "password": TEST_PASSWORD, "accepted_tos": True},
    )
    assert registered.status_code == 201, registered.text
    token = _token_from_body(emails.sent[0]["body"])

    confirmed = auth_client.post("/api/auth/email/verify", json={"token": token})
    assert confirmed.status_code == 204, confirmed.text
    stamp = db_conn.execute(
        select(users_table.c.email_verified_at).where(users_table.c.email == "confirm@example.com")
    ).scalar_one()
    assert stamp is not None

    # The replay of the consumed token is the same uniform 403 (DOOR-35).
    replay = auth_client.post("/api/auth/email/verify", json={"token": token})
    assert replay.status_code == 403, replay.text
    assert replay.json() == {"detail": INVALID_TOKEN_MESSAGE}

    # A verify token can never serve as a reset token either.
    wrong_purpose = auth_client.post(
        "/api/auth/password/reset",
        json={"token": token, "password": NEW_PASSWORD},
    )
    assert wrong_purpose.status_code == 403, wrong_purpose.text


@requires_db
def test_unknown_reset_email_is_204_with_no_mail_like_the_known_one(
    auth_client: TestClient,
) -> None:
    emails = FakeEmailSender()
    _override_sender(auth_client, emails)
    registered = auth_client.post(
        "/api/auth/register",
        json={"email": "known@example.com", "password": TEST_PASSWORD, "accepted_tos": True},
    )
    assert registered.status_code == 201, registered.text
    emails.sent.clear()

    unknown = auth_client.post(
        "/api/auth/password/reset-request", json={"email": "ghost@example.com"}
    )
    assert unknown.status_code == 204, unknown.text
    assert unknown.content == b""
    # Zero sends for the unknown address (DOOR-36): no enumeration channel.
    assert emails.sent == []

    known = auth_client.post(
        "/api/auth/password/reset-request", json={"email": "known@example.com"}
    )
    assert known.status_code == 204, known.text
    assert known.content == b""
    # The known address answered the identical 204 — and this time mail went out.
    assert len(emails.sent) == 1
    assert emails.sent[0]["to"] == "known@example.com"


@requires_db
def test_reset_with_valid_token_sets_a_new_password_exactly_once(
    auth_client: TestClient,
) -> None:
    emails = FakeEmailSender()
    _override_sender(auth_client, emails)
    registered = auth_client.post(
        "/api/auth/register",
        json={"email": "resetter@example.com", "password": TEST_PASSWORD, "accepted_tos": True},
    )
    assert registered.status_code == 201, registered.text
    auth_client.cookies.clear()
    emails.sent.clear()  # drop the register's verify mail; we want the reset mail

    requested = auth_client.post(
        "/api/auth/password/reset-request", json={"email": "resetter@example.com"}
    )
    assert requested.status_code == 204, requested.text
    token = _token_from_body(emails.sent[0]["body"])

    reset = auth_client.post(
        "/api/auth/password/reset",
        json={"token": token, "password": NEW_PASSWORD},
    )
    assert reset.status_code == 204, reset.text

    # The old password stops working; the new one signs in.
    auth_client.cookies.clear()
    old_login = auth_client.post(
        "/api/auth/login",
        json={"email": "resetter@example.com", "password": TEST_PASSWORD},
    )
    assert old_login.status_code == 401, old_login.text
    new_login = auth_client.post(
        "/api/auth/login",
        json={"email": "resetter@example.com", "password": NEW_PASSWORD},
    )
    assert new_login.status_code == 200, new_login.text

    # The token was consumed exactly once: a second reset with it is the
    # uniform 403 and changes no credential (the first password still signs in).
    replay = auth_client.post(
        "/api/auth/password/reset",
        json={"token": token, "password": "yet another long password"},
    )
    assert replay.status_code == 403, replay.text
    auth_client.cookies.clear()
    still_new = auth_client.post(
        "/api/auth/login",
        json={"email": "resetter@example.com", "password": NEW_PASSWORD},
    )
    assert still_new.status_code == 200, still_new.text


@requires_db
def test_reset_request_and_resend_consume_auth_limiter_budget(
    auth_client: TestClient,
) -> None:
    from app.infrastructure.web.rate_limit import (
        InMemoryFixedWindowRateLimiter,
        get_rate_limiter,
        set_rate_limiter,
    )

    _override_sender(auth_client, FakeEmailSender())
    registered = auth_client.post(
        "/api/auth/register",
        json={"email": "throttleme@example.com", "password": TEST_PASSWORD, "accepted_tos": True},
    )
    assert registered.status_code == 201, registered.text

    # One attempt per window, per route (the auth limiter keys on IP + path).
    previous = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=1, window_seconds=300))
    try:
        first_resend = auth_client.post("/api/auth/email/verify/resend")
        assert first_resend.status_code == 204, first_resend.text
        second_resend = auth_client.post("/api/auth/email/verify/resend")
        assert second_resend.status_code == 429, second_resend.text
        assert "retry-after" in {k.lower() for k in second_resend.headers}

        first_request = auth_client.post(
            "/api/auth/password/reset-request", json={"email": "throttleme@example.com"}
        )
        assert first_request.status_code == 204, first_request.text
        second_request = auth_client.post(
            "/api/auth/password/reset-request", json={"email": "throttleme@example.com"}
        )
        assert second_request.status_code == 429, second_request.text
    finally:
        set_rate_limiter(previous)
