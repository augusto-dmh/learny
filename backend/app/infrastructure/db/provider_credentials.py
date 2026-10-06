"""Learner provider keys at rest: the ``user_provider_credentials`` repository.

Seals on write and opens on demand through the envelope (ADR-0033 point 1).
Every statement is scoped by ``user_id``. What leaves this module through the
port is :class:`~app.domain.entities.ProviderCredential` metadata only; the one
method that returns a plaintext key, :meth:`reveal`, is not on the port, so
only the infrastructure composition that builds an adapter can call it.

A row counts as "no credential" when it cannot be used: its KEK is not
configured here, or its stored fingerprint does not match the one recomputed
for the learner asking (a row copied onto another account). Neither case
raises on the request path.
"""

from __future__ import annotations

import logging
from uuid import UUID, uuid4

from sqlalchemy import Connection, Row, insert, select
from sqlalchemy import delete as sa_delete

from app.domain.entities import ProviderCredential
from app.infrastructure.db.metadata import user_provider_credentials
from app.infrastructure.security.secrets_envelope import (
    SealedSecret,
    SealedSecretError,
    SecretsEnvelope,
    fingerprint_of,
)

logger = logging.getLogger(__name__)

#: How many trailing characters of a key the account page may show.
LAST4_CHARS = 4


def sealed_from_row(row: Row) -> SealedSecret:
    """The envelope view of a stored row."""
    return SealedSecret(
        ciphertext=bytes(row.ciphertext),
        nonce=bytes(row.nonce),
        wrapped_dek=bytes(row.wrapped_dek),
        dek_nonce=bytes(row.dek_nonce),
        kek_id=row.kek_id,
    )


def _to_credential(row: Row) -> ProviderCredential:
    return ProviderCredential(
        id=row.id,
        user_id=row.user_id,
        provider=row.provider,
        last4=row.last4,
        fingerprint=row.fingerprint,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyProviderCredentialRepository:
    """``ProviderCredentialRepository`` over ``user_provider_credentials``.

    One row per (user, provider), enforced by the table's unique constraint. A
    replace deletes the old row and inserts a new one with a new id, so anything
    pinned to the old row id (and any adapter cached on the old fingerprint)
    stops resolving.
    """

    def __init__(self, connection: Connection, envelope: SecretsEnvelope) -> None:
        self._conn = connection
        self._envelope = envelope

    def __repr__(self) -> str:
        return "SqlAlchemyProviderCredentialRepository()"

    def _usable(self, row: Row) -> bool:
        if not self._envelope.knows(row.kek_id):
            logger.warning(
                "provider credential %s is wrapped by an unconfigured KEK; treating it as absent",
                row.id,
            )
            return False
        expected = fingerprint_of(sealed_from_row(row), user_id=row.user_id, provider=row.provider)
        if expected != row.fingerprint:
            logger.warning(
                "provider credential %s does not match its owner binding; treating it as absent",
                row.id,
            )
            return False
        return True

    def list_for_user(self, user_id: UUID) -> list[ProviderCredential]:
        rows = self._conn.execute(
            select(user_provider_credentials)
            .where(user_provider_credentials.c.user_id == user_id)
            .order_by(user_provider_credentials.c.provider)
        ).all()
        return [_to_credential(row) for row in rows if self._usable(row)]

    def get(self, user_id: UUID, provider: str) -> ProviderCredential | None:
        row = self._conn.execute(
            select(user_provider_credentials).where(
                user_provider_credentials.c.user_id == user_id,
                user_provider_credentials.c.provider == provider,
            )
        ).one_or_none()
        if row is None or not self._usable(row):
            return None
        return _to_credential(row)

    def replace(self, user_id: UUID, provider: str, api_key: str) -> ProviderCredential:
        """Seal ``api_key`` into a new row, removing any previous row for the provider."""
        sealed = self._envelope.seal(api_key, user_id=user_id, provider=provider)
        self.delete(user_id, provider)
        row = self._conn.execute(
            insert(user_provider_credentials)
            .values(
                id=uuid4(),
                user_id=user_id,
                provider=provider,
                ciphertext=sealed.ciphertext,
                nonce=sealed.nonce,
                wrapped_dek=sealed.wrapped_dek,
                dek_nonce=sealed.dek_nonce,
                kek_id=sealed.kek_id,
                fingerprint=fingerprint_of(sealed, user_id=user_id, provider=provider),
                last4=api_key[-LAST4_CHARS:],
            )
            .returning(user_provider_credentials)
        ).one()
        return _to_credential(row)

    def delete(self, user_id: UUID, provider: str) -> bool:
        """Remove the learner's key for ``provider``; ``True`` only when a row existed."""
        result = self._conn.execute(
            sa_delete(user_provider_credentials).where(
                user_provider_credentials.c.user_id == user_id,
                user_provider_credentials.c.provider == provider,
            )
        )
        return bool(result.rowcount)

    def reveal(self, credential: ProviderCredential) -> str | None:
        """Open the key of exactly this live row, or ``None`` when it cannot be used.

        The row is re-read by id, owner and provider, so a credential entity
        whose row was replaced or deleted reveals nothing. Infrastructure-only:
        this is not part of the domain port.
        """
        row = self._conn.execute(
            select(user_provider_credentials).where(
                user_provider_credentials.c.id == credential.id,
                user_provider_credentials.c.user_id == credential.user_id,
                user_provider_credentials.c.provider == credential.provider,
            )
        ).one_or_none()
        if row is None or not self._usable(row):
            return None
        try:
            return self._envelope.open(
                sealed_from_row(row), user_id=row.user_id, provider=row.provider
            )
        except SealedSecretError:
            logger.warning(
                "provider credential %s could not be opened; treating it as absent", row.id
            )
            return None
