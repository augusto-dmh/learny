"""Argon2id password hasher adapter (AD-006, task B2).

Implements the :class:`~app.domain.ports.PasswordHasher` port using ``pwdlib``
with the Argon2id backend (OWASP-preferred). This is the only place Argon2
parameters are decided, keeping the domain free of the hashing SDK (ADR-009).

Security:
- Password material is never logged, returned in errors, or stored anywhere but
  the resulting encoded hash (NFR-SEC-004 / AC-4).
- ``verify`` is constant-time and never raises on a wrong password — it returns
  ``False`` — so callers can apply a uniform login failure (no enumeration, AC-3).
"""

from __future__ import annotations

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher


class Argon2PasswordHasher:
    """Argon2id implementation of the ``PasswordHasher`` port.

    Wraps a ``pwdlib.PasswordHash`` whose primary (current) hasher is Argon2id.
    The default OWASP-aligned parameters from ``pwdlib`` are used unless explicit
    parameters are supplied; ``needs_rehash`` reports when an existing hash was
    produced with different parameters so credentials can be transparently
    upgraded on next successful login.
    """

    def __init__(self, *, argon2_hasher: Argon2Hasher | None = None) -> None:
        self._argon2 = argon2_hasher or Argon2Hasher()
        self._password_hash = PasswordHash((self._argon2,))

    def hash(self, password: str) -> str:
        """Return an Argon2id-encoded hash of ``password``."""
        return self._password_hash.hash(password)

    def verify(self, password: str, encoded_hash: str) -> bool:
        """Return whether ``password`` matches ``encoded_hash`` (constant-time).

        A malformed/unrecognized stored hash returns ``False`` rather than
        raising, so callers see a single uniform failure path (no enumeration,
        AC-3) regardless of whether the credential is wrong or corrupt.
        """
        try:
            return self._password_hash.verify(password, encoded_hash)
        except UnknownHashError:
            return False

    def needs_rehash(self, encoded_hash: str) -> bool:
        """Return whether ``encoded_hash`` should be re-hashed with current params."""
        return self._argon2.check_needs_rehash(encoded_hash)
