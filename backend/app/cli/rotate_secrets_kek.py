"""Re-wrap every learner key's DEK under the current KEK (``python -m app.cli.rotate_secrets_kek``).

The operator sets the new key-encryption key in ``LEARNY_SECRETS_KEK`` and moves
the old one to ``LEARNY_SECRETS_KEK_PREVIOUS``, then runs this command. Each row
whose ``kek_id`` is not the current KEK's has its DEK unwrapped with the old KEK
and wrapped again with the current one. The ciphertext is never touched and no
key is ever decrypted, so the command works on wrapped DEKs only.

Each row is re-wrapped in its own transaction, so a run that stops halfway can
simply be run again: rows already under the current KEK are counted and skipped.
A row under a KEK this process does not know is reported, never crashed on, and
makes the command exit ``1``. The command takes no flags: it reads the same
environment the application does.

Output is one line of counts on stdout (plus the ids, never the contents, of
rows it could not re-wrap on stderr). Exit codes: ``0`` all rows current,
``1`` some row is under an unknown KEK or failed authentication, ``2`` the
feature is not configured (no KEK).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import Connection, func, select, update

from app.core.config import get_settings
from app.infrastructure.db.engine import get_engine
from app.infrastructure.db.metadata import user_provider_credentials
from app.infrastructure.db.provider_credentials import sealed_from_row
from app.infrastructure.security.secrets_envelope import SealedSecretError, SecretsEnvelope


def _default_uow() -> AbstractContextManager[Connection]:
    """One committed unit of work per call: a fresh ``engine.begin()``."""
    return get_engine().begin()


#: The unit-of-work factory each step runs in (tests inject their own).
_uow: Callable[[], AbstractContextManager[Connection]] = _default_uow


@dataclass
class RotationReport:
    """What one run did, by outcome."""

    rewrapped: int = 0
    already_current: int = 0
    unknown_kek: list[UUID] = field(default_factory=list)
    unreadable: list[UUID] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.unknown_kek and not self.unreadable


def rotate(
    uow: Callable[[], AbstractContextManager[Connection]], envelope: SecretsEnvelope
) -> RotationReport:
    """Re-wrap every row not under the current KEK, one transaction per row."""
    report = RotationReport()
    with uow() as conn:
        listing = conn.execute(
            select(user_provider_credentials.c.id, user_provider_credentials.c.kek_id).order_by(
                user_provider_credentials.c.created_at, user_provider_credentials.c.id
            )
        ).all()
    for row_id, kek_id in listing:
        if kek_id == envelope.current_kek_id:
            report.already_current += 1
            continue
        if not envelope.knows(kek_id):
            report.unknown_kek.append(row_id)
            continue
        with uow() as conn:
            row = conn.execute(
                select(user_provider_credentials)
                .where(user_provider_credentials.c.id == row_id)
                .with_for_update()
            ).one_or_none()
            if row is None:  # deleted since the listing: nothing left to rotate
                continue
            if row.kek_id == envelope.current_kek_id:  # a concurrent run got there first
                report.already_current += 1
                continue
            try:
                rewrapped = envelope.rewrap(
                    sealed_from_row(row), user_id=row.user_id, provider=row.provider
                )
            except SealedSecretError:
                report.unreadable.append(row_id)
                continue
            conn.execute(
                update(user_provider_credentials)
                .where(user_provider_credentials.c.id == row_id)
                .values(
                    wrapped_dek=rewrapped.wrapped_dek,
                    dek_nonce=rewrapped.dek_nonce,
                    kek_id=rewrapped.kek_id,
                    updated_at=func.now(),
                )
            )
            report.rewrapped += 1
    return report


def main(argv: list[str] | None = None) -> int:
    """Run one rotation against the configured database and print the counts."""
    del argv  # no flags: configuration is the application's own environment
    keks = get_settings().secrets_keks()
    if keks is None:
        print("LEARNY_SECRETS_KEK is not set; there is nothing to rotate.", file=sys.stderr)
        return 2
    current, previous = keks
    report = rotate(_uow, SecretsEnvelope(current, previous))
    print(
        f"rewrapped={report.rewrapped} already_current={report.already_current} "
        f"unknown_kek={len(report.unknown_kek)} unreadable={len(report.unreadable)}"
    )
    for row_id in report.unknown_kek:
        print(f"credential {row_id}: wrapped by an unknown KEK", file=sys.stderr)
    for row_id in report.unreadable:
        print(f"credential {row_id}: failed authentication", file=sys.stderr)
    return 0 if report.clean else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
