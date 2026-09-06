"""Invite-code gating for register (RFC-0007 Cycle F; design §Invite + disposable).

While ``LEARNY_INVITE_REQUIRED`` is on, register must present a *live* invite
code: one that exists, still has remaining uses, and has not expired. The
application side of that gate is deliberately tiny — a consume-only port plus
the one uniform failure message — because the security property lives in the
consume contract (one atomic decrement, one uniform refusal), not in code the
operator runs to mint codes. Minting is operator-side SQL on the
``invite_codes`` table; there is no product surface for it.

Framework-free: no FastAPI, SQLAlchemy, or provider SDK imports (ADR-007/009).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

# The uniform user-facing copy for every rejected register (DOOR-20): absent,
# unknown, exhausted, and expired codes are indistinguishable by design.
INVITE_REQUIRED_MESSAGE = (
    "This instance is invite-only. A valid invite code is required to register."
)


class InviteRepository(Protocol):
    """Persistence port for consuming invite codes."""

    def consume(self, code: str, *, now: datetime) -> None:
        """Consume one use of the live code named by ``code``.

        A code is live when it exists, ``remaining_uses`` is above zero, and
        ``expires_at`` is in the future (or NULL). A successful consume
        decrements the remaining uses by exactly one; any non-live code raises
        :class:`~app.application.errors.InviteRequired` — the same failure for
        unknown, exhausted, and expired (DOOR-20/22).
        """
        ...
