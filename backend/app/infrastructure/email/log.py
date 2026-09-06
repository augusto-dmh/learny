"""Log adapter for the email port (RFC-0007 Cycle F; AD-326).

The default adapter wherever no SMTP host is configured (local dev, self-host
without mail, the offline suite): the message goes to the log instead of a
network. Tests that need to *assert* on sent mail use a capturing double
(``tests.fakes.FakeEmailSender``); this adapter's only job is keeping a
host-less deployment fully functional without opening a socket.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class LogEmailSender:
    """``EmailPort`` adapter that logs the message; never touches a socket."""

    def send(self, *, to: str, subject: str, body: str) -> None:
        logger.info("email.sent via log to=%s subject=%s body=%s", to, subject, body)
