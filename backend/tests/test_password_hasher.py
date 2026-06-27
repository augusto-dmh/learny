"""B2 gate — Argon2id password hasher adapter (AD-006).

Unit checks: hashes are Argon2id and differ from plaintext, verification is
correct for match/mismatch, and the rehash hook detects outdated parameters.
"""

from __future__ import annotations

import pytest
from pwdlib.hashers.argon2 import Argon2Hasher

from app.domain.ports import PasswordHasher
from app.infrastructure.security.password_hasher import Argon2PasswordHasher


@pytest.fixture
def hasher() -> Argon2PasswordHasher:
    return Argon2PasswordHasher()


def test_adapter_satisfies_port(hasher: Argon2PasswordHasher) -> None:
    assert isinstance(hasher, PasswordHasher)


def test_hash_is_argon2id_and_not_plaintext(hasher: Argon2PasswordHasher) -> None:
    encoded = hasher.hash("correct horse battery staple")
    assert encoded.startswith("$argon2id$")
    assert "correct horse battery staple" not in encoded


def test_hash_is_salted_unique_per_call(hasher: Argon2PasswordHasher) -> None:
    assert hasher.hash("same-password") != hasher.hash("same-password")


def test_verify_true_on_match(hasher: Argon2PasswordHasher) -> None:
    encoded = hasher.hash("s3cret-pass")
    assert hasher.verify("s3cret-pass", encoded) is True


def test_verify_false_on_mismatch(hasher: Argon2PasswordHasher) -> None:
    encoded = hasher.hash("s3cret-pass")
    assert hasher.verify("wrong-pass", encoded) is False


def test_verify_returns_false_not_raises_on_garbage(hasher: Argon2PasswordHasher) -> None:
    assert hasher.verify("whatever", "not-a-valid-hash") is False


def test_needs_rehash_false_for_current_params(hasher: Argon2PasswordHasher) -> None:
    encoded = hasher.hash("pw")
    assert hasher.needs_rehash(encoded) is False


def test_needs_rehash_true_for_outdated_params() -> None:
    """A hash made with weaker parameters is flagged for rehash."""
    weak = Argon2PasswordHasher(
        argon2_hasher=Argon2Hasher(time_cost=1, memory_cost=8, parallelism=1)
    )
    current = Argon2PasswordHasher()
    weak_hash = weak.hash("pw")
    assert current.needs_rehash(weak_hash) is True
