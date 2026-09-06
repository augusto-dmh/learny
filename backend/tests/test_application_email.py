"""Email port tests (RFC-0007 Cycle F; matrix row "EmailPort").

Adapter selection and the two transports behind :class:`~app.domain.ports.EmailPort`
(DOOR-34/40). No test here opens a network socket: the SMTP adapter is exercised
by patching the ``smtplib.SMTP`` class in the adapter's own module, and the log
adapter writes to the logging framework.

The verify/reset flows built on top of this port land with their own cases in
this file (see the T16 section at the bottom).
"""

from __future__ import annotations

import logging
from unittest.mock import patch

from app.core.config import Settings
from app.domain.ports import EmailPort
from app.infrastructure.email import (
    LogEmailSender,
    SmtpEmailSender,
    build_email_sender,
)
from tests.fakes import FakeEmailSender


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
