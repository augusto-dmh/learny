"""SMTP adapter for the email port (RFC-0007 Cycle F; AD-326).

The stdlib ``smtplib`` client lives only here (ADR-0007/0009): application code
depends on :class:`~app.domain.ports.EmailPort` and never imports a mail library.
Plain-text messages only — the header block is assembled by hand because the
body carries no MIME parts this letter.
"""

from __future__ import annotations

import logging
import smtplib

logger = logging.getLogger(__name__)


class SmtpEmailSender:
    """``EmailPort`` adapter over the stdlib SMTP client (the production default).

    One connection per send: verify/reset mail is a rare, operator-rails-gated
    write, so there is no pool to manage and a dead relay surfaces as this
    call's exception (the caller owns the failure policy).
    """

    def __init__(self, *, host: str, port: int, sender: str) -> None:
        self._host = host
        self._port = port
        self._sender = sender

    def send(self, *, to: str, subject: str, body: str) -> None:
        message = f"From: {self._sender}\r\nTo: {to}\r\nSubject: {subject}\r\n\r\n{body}"
        with smtplib.SMTP(self._host, self._port) as client:
            client.sendmail(self._sender, [to], message)
        logger.info("email.sent via smtp to=%s subject=%s", to, subject)
