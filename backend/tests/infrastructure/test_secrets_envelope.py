"""Envelope encryption of learner keys: fresh material per seal, owner-bound, tamper-evident.

The format is the one the decision record fixes: AES-256-GCM under a fresh
32-byte DEK and a 12-byte random nonce, the DEK wrapped by the KEK with
AES-256-GCM under its own nonce, and the associated data
``learny/provider-credential/v1/<user_id>/<provider>`` on both layers. These
tests unwrap with the raw primitive where they need to see a DEK, so they
check the literal format rather than the module's own reading of it.
"""

from __future__ import annotations

import hashlib
import os
from uuid import UUID, uuid4

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.infrastructure.security.secrets_envelope import (
    SealedSecret,
    SealedSecretError,
    SecretsEnvelope,
    UnknownKek,
    kek_id_for,
)

_KEK = bytes(range(32))
_KEY = "sk-ant-api03-envelope-test-key-0123456789"


def _aad(user_id: UUID, provider: str) -> bytes:
    return f"learny/provider-credential/v1/{user_id}/{provider}".encode()


def _unwrap(sealed: SealedSecret, user_id: UUID, provider: str) -> bytes:
    return AESGCM(_KEK).decrypt(sealed.dek_nonce, sealed.wrapped_dek, _aad(user_id, provider))


def test_fresh_dek_and_nonce_per_seal() -> None:
    envelope = SecretsEnvelope(_KEK)
    user_id = uuid4()

    first = envelope.seal(_KEY, user_id=user_id, provider="anthropic")
    second = envelope.seal(_KEY, user_id=user_id, provider="anthropic")

    first_dek = _unwrap(first, user_id, "anthropic")
    second_dek = _unwrap(second, user_id, "anthropic")
    assert len(first_dek) == len(second_dek) == 32
    assert first_dek != second_dek
    assert len(first.nonce) == len(second.nonce) == 12
    assert first.nonce != second.nonce
    assert first.dek_nonce != second.dek_nonce
    assert first.wrapped_dek != second.wrapped_dek
    assert first.ciphertext != second.ciphertext
    # Both open to the same plaintext, through the module and through the raw format.
    assert envelope.open(first, user_id=user_id, provider="anthropic") == _KEY
    assert envelope.open(second, user_id=user_id, provider="anthropic") == _KEY
    raw = AESGCM(second_dek).decrypt(second.nonce, second.ciphertext, _aad(user_id, "anthropic"))
    assert raw.decode() == _KEY
    # The KEK id is the first 16 hex characters of the KEK's SHA-256.
    assert first.kek_id == hashlib.sha256(_KEK).hexdigest()[:16] == kek_id_for(_KEK)


def test_associated_data_binds_owner() -> None:
    envelope = SecretsEnvelope(_KEK)
    owner = uuid4()
    sealed = envelope.seal(_KEY, user_id=owner, provider="anthropic")

    with pytest.raises(SealedSecretError) as other_user:
        envelope.open(sealed, user_id=uuid4(), provider="anthropic")
    with pytest.raises(SealedSecretError) as other_provider:
        envelope.open(sealed, user_id=owner, provider="openai")

    for raised in (other_user, other_provider):
        assert _KEY not in str(raised.value)
        assert _KEY not in repr(raised.value)
    # The rightful owner still opens it.
    assert envelope.open(sealed, user_id=owner, provider="anthropic") == _KEY


def test_associated_data_binds_owner_on_the_wrapped_dek_too() -> None:
    """The DEK layer authenticates the same owner binding: re-wrapping a sealed
    value for another learner fails before any ciphertext is touched."""
    envelope = SecretsEnvelope(_KEK)
    owner = uuid4()
    sealed = envelope.seal(_KEY, user_id=owner, provider="anthropic")

    with pytest.raises(SealedSecretError):
        envelope.rewrap(sealed, user_id=uuid4(), provider="anthropic")


@pytest.mark.parametrize("field", ["ciphertext", "nonce", "wrapped_dek", "dek_nonce"])
def test_tampered_ciphertext_rejected(field: str) -> None:
    envelope = SecretsEnvelope(_KEK)
    owner = uuid4()
    sealed = envelope.seal(_KEY, user_id=owner, provider="anthropic")
    original = getattr(sealed, field)
    flipped = bytes([original[0] ^ 0x01]) + original[1:]
    tampered = SealedSecret(**{**sealed.__dict__, field: flipped})

    with pytest.raises(SealedSecretError) as raised:
        envelope.open(tampered, user_id=owner, provider="anthropic")

    assert _KEY not in str(raised.value)


def test_a_secret_under_an_unconfigured_kek_raises_unknown_kek() -> None:
    owner = uuid4()
    sealed = SecretsEnvelope(os.urandom(32)).seal(_KEY, user_id=owner, provider="anthropic")

    with pytest.raises(UnknownKek):
        SecretsEnvelope(_KEK).open(sealed, user_id=owner, provider="anthropic")


def test_rewrap_moves_the_dek_to_the_current_kek_and_keeps_the_ciphertext() -> None:
    owner = uuid4()
    old_kek, new_kek = os.urandom(32), os.urandom(32)
    sealed = SecretsEnvelope(old_kek).seal(_KEY, user_id=owner, provider="openai")
    rotated_envelope = SecretsEnvelope(new_kek, previous=[old_kek])

    rewrapped = rotated_envelope.rewrap(sealed, user_id=owner, provider="openai")

    assert rewrapped.ciphertext == sealed.ciphertext
    assert rewrapped.nonce == sealed.nonce
    assert rewrapped.kek_id == kek_id_for(new_kek) != sealed.kek_id
    assert SecretsEnvelope(new_kek).open(rewrapped, user_id=owner, provider="openai") == _KEY


def test_a_kek_of_the_wrong_length_is_refused() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        SecretsEnvelope(b"\x00" * 16)


def test_no_repr_carries_key_material() -> None:
    envelope = SecretsEnvelope(_KEK)
    sealed = envelope.seal(_KEY, user_id=uuid4(), provider="anthropic")

    for shown in (repr(envelope), repr(sealed)):
        assert _KEY not in shown
        assert _KEK.hex() not in shown
        assert sealed.ciphertext.hex() not in shown
