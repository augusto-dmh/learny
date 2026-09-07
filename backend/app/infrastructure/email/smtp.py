"""SMTP adapter for the email port (RFC-0007 Cycle F; AD-326).

The stdlib ``smtplib`` client lives only here (ADR-0007/0009): application code
depends on :class:`~app.domain.ports.EmailPort` and never imports a mail library.
Plain-text messages only — the header block is assembled by hand because the
body carries no MIME parts this letter. The *connection* is not plaintext by
default: STARTTLS upgrades it before credentials or payload move, and the relay
is authenticated when a username is configured.
"""

from __future__ import annotations

import logging
import smtplib
import ssl

logger = logging.getLogger(__name__)


class SmtpEmailSender:
    """``EmailPort`` adapter over the stdlib SMTP client (the production default).

    One connection per send: verify/reset mail is a rare, operator-rails-gated
    write, so there is no pool to manage and a dead relay surfaces as this
    call's exception (the caller owns the failure policy).
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        sender: str,
        use_tls: bool = True,
        username: str = "",
        password: str = "",
    ) -> None:
        self._host = host
        self._port = port
        self._sender = sender
        self._use_tls = use_tls
        self._username = username
        self._password = password

    def send(self, *, to: str, subject: str, body: str) -> None:
        message = f"From: {self._sender}\r\nTo: {to}\r\nSubject: {subject}\r\n\r\n{body}"
        with smtplib.SMTP(self._host, self._port) as client:
            if self._use_tls:
                client.starttls(context=ssl.create_default_context())
            if self._username:
                client.login(self._username, self._password)
            client.sendmail(self._sender, [to], message)
        logger.info("email.sent via smtp to=%s subject=%s", to, subject)
