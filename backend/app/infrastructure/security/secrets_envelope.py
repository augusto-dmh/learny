"""Envelope encryption for learner-provided API keys (ADR-0033, points 1-2).

Each secret is sealed with AES-256-GCM under a fresh 32-byte data key (DEK) and
a fresh 96-bit nonce. The DEK is then wrapped with AES-256-GCM by the operator's
key-encryption key (KEK) under its own fresh nonce. Both layers bind the same
associated data, ``learny/provider-credential/v1/<user_id>/<provider>``, so a
sealed value only opens for the exact owner and provider it was sealed for: a
database writer who moves one learner's ciphertext onto another learner's row
gets an authentication failure, not a key.

A KEK is named by its ``kek_id``, the first 16 hex characters of its SHA-256.
Retired KEKs stay readable while the operator lists them as previous ones, so
rotation is a re-wrap of each DEK under the current KEK and never touches the
ciphertext.

Nothing here logs, and no exception or ``repr`` carries a plaintext, a DEK or
a KEK. Failures raise :class:`SealedSecretError` with fixed copy.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

#: Every key this module handles (DEK and KEK) is AES-256: 32 bytes.
KEY_BYTES = 32
#: GCM's standard 96-bit nonce, drawn fresh from the OS for every encryption.
NONCE_BYTES = 12
#: The versioned prefix of the associated data both layers bind.
ASSOCIATED_DATA_PREFIX = "learny/provider-credential/v1"
#: The domain separator of the row fingerprint (never a hash of the key itself).
_FINGERPRINT_DOMAIN = b"learny/provider-credential-fingerprint/v1\x00"


class SealedSecretError(Exception):
    """A sealed secret could not be opened or re-wrapped.

    The message is fixed copy: it never names the secret, a key, or the bytes
    that failed authentication.
    """


class UnknownKek(SealedSecretError):
    """The secret was wrapped by a KEK that is not configured on this process."""


def kek_id_for(kek: bytes) -> str:
    """The public name of a KEK: the first 16 hex characters of its SHA-256."""
    return hashlib.sha256(kek).hexdigest()[:16]


def associated_data(user_id: UUID, provider: str) -> bytes:
    """The owner binding both GCM layers authenticate (never secret)."""
    return f"{ASSOCIATED_DATA_PREFIX}/{user_id}/{provider}".encode()


@dataclass(frozen=True)
class SealedSecret:
    """The stored form of one secret: everything a row keeps, nothing plaintext.

    ``ciphertext`` and ``wrapped_dek`` include their GCM tags. The byte fields
    are kept out of ``repr`` so a logged entity shows only which KEK wraps it.
    """

    ciphertext: bytes = field(repr=False)
    nonce: bytes = field(repr=False)
    wrapped_dek: bytes = field(repr=False)
    dek_nonce: bytes = field(repr=False)
    kek_id: str


def fingerprint_of(sealed: SealedSecret, *, user_id: UUID, provider: str) -> str:
    """A stable, non-secret name for one sealed write, bound to its owner.

    Derived from the owner binding plus the nonce and ciphertext, never from the
    plaintext: it reveals nothing about the key, it changes on every write (a
    replaced key always gets a new one), and it survives a KEK rotation because
    rotation leaves the ciphertext untouched. Because the owner is part of the
    input, a row copied onto another learner computes a different fingerprint
    there.
    """
    digest = hashlib.sha256()
    digest.update(_FINGERPRINT_DOMAIN)
    digest.update(associated_data(user_id, provider))
    digest.update(b"\x00")
    digest.update(sealed.nonce)
    digest.update(sealed.ciphertext)
    return digest.hexdigest()


class SecretsEnvelope:
    """Seal, open and re-wrap secrets under the configured KEKs.

    ``current`` wraps every new DEK; ``previous`` KEKs may still unwrap. Each
    KEK must be exactly 32 bytes. The instance holds the KEKs in memory and
    never prints them.
    """

    def __init__(self, current: bytes, previous: Sequence[bytes] = ()) -> None:
        keks: dict[str, AESGCM] = {}
        for kek in (current, *previous):
            if len(kek) != KEY_BYTES:
                raise ValueError("a secrets KEK must be exactly 32 bytes")
            keks.setdefault(kek_id_for(kek), AESGCM(kek))
        self._keks = keks
        self._current_id = kek_id_for(current)

    def __repr__(self) -> str:
        return f"SecretsEnvelope(current_kek_id={self._current_id!r}, keks={len(self._keks)})"

    @property
    def current_kek_id(self) -> str:
        """The id of the KEK every new or re-wrapped DEK is wrapped under."""
        return self._current_id

    def knows(self, kek_id: str) -> bool:
        """Whether a secret wrapped under ``kek_id`` can be opened here."""
        return kek_id in self._keks

    def seal(self, plaintext: str, *, user_id: UUID, provider: str) -> SealedSecret:
        """Encrypt ``plaintext`` under a fresh DEK and wrap that DEK (fresh nonces)."""
        aad = associated_data(user_id, provider)
        dek = AESGCM.generate_key(bit_length=KEY_BYTES * 8)
        nonce = os.urandom(NONCE_BYTES)
        ciphertext = AESGCM(dek).encrypt(nonce, plaintext.encode("utf-8"), aad)
        dek_nonce = os.urandom(NONCE_BYTES)
        wrapped_dek = self._keks[self._current_id].encrypt(dek_nonce, dek, aad)
        return SealedSecret(
            ciphertext=ciphertext,
            nonce=nonce,
            wrapped_dek=wrapped_dek,
            dek_nonce=dek_nonce,
            kek_id=self._current_id,
        )

    def _unwrap_dek(self, sealed: SealedSecret, aad: bytes) -> bytes:
        kek = self._keks.get(sealed.kek_id)
        if kek is None:
            raise UnknownKek("the sealed secret is wrapped by a KEK that is not configured")
        try:
            return kek.decrypt(sealed.dek_nonce, sealed.wrapped_dek, aad)
        except InvalidTag:
            raise SealedSecretError("the sealed secret failed authentication") from None

    def open(self, sealed: SealedSecret, *, user_id: UUID, provider: str) -> str:
        """Return the plaintext, or raise when the owner binding or any byte is off."""
        aad = associated_data(user_id, provider)
        dek = self._unwrap_dek(sealed, aad)
        try:
            plaintext = AESGCM(dek).decrypt(sealed.nonce, sealed.ciphertext, aad)
        except InvalidTag:
            raise SealedSecretError("the sealed secret failed authentication") from None
        return plaintext.decode("utf-8")

    def rewrap(self, sealed: SealedSecret, *, user_id: UUID, provider: str) -> SealedSecret:
        """Re-wrap the DEK under the current KEK; the ciphertext stays byte-identical.

        The DEK is unwrapped under its own KEK and wrapped again under the current
        one with a fresh nonce. The plaintext is never decrypted.
        """
        aad = associated_data(user_id, provider)
        dek = self._unwrap_dek(sealed, aad)
        dek_nonce = os.urandom(NONCE_BYTES)
        wrapped_dek = self._keks[self._current_id].encrypt(dek_nonce, dek, aad)
        return SealedSecret(
            ciphertext=sealed.ciphertext,
            nonce=sealed.nonce,
            wrapped_dek=wrapped_dek,
            dek_nonce=dek_nonce,
            kek_id=self._current_id,
        )
