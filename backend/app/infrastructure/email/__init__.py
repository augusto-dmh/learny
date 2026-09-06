"""Email adapters (implement ``EmailPort``, RFC-0007 Cycle F; AD-326).

No ESP SDK (Resend/Postmark/SES): the production transport is stdlib SMTP.
``build_email_sender`` selects the concrete adapter from settings at the
composition root — the ``build_generation_adapter`` pattern — so application
code only ever sees the port.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.infrastructure.email.log import LogEmailSender
from app.infrastructure.email.smtp import SmtpEmailSender

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.domain.ports import EmailPort

__all__ = [
    "LogEmailSender",
    "SmtpEmailSender",
    "build_email_sender",
]


def build_email_sender(settings: Settings) -> EmailPort:
    """Return the email adapter named by ``settings.smtp_host``.

    Host set → the stdlib SMTP adapter (the production default, built from the
    host/port/from settings); host empty (the default) → the log adapter, so a
    deployment without mail configured keeps working and the offline suite never
    opens a socket. An empty ``smtp_from`` with a host set is accepted here —
    the relay will refuse it at send time, which is a configuration error the
    operator sees in the failure log, not one to guess around.
    """
    if settings.smtp_host:
        return SmtpEmailSender(
            host=settings.smtp_host,
            port=settings.smtp_port,
            sender=settings.smtp_from,
        )
    return LogEmailSender()
