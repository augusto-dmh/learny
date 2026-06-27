"""Opaque token generation + hashing for sessions (AD-006/007, task B3).

Session and CSRF tokens are high-entropy random strings. The raw session token
lives only in the HTTP-only cookie; PostgreSQL stores SHA-256 of it
(``token_hash``). A fast cryptographic hash is the standard choice here — unlike
passwords, these tokens have full entropy, so a slow KDF (Argon2) is
unnecessary and the hash is only a defense for the at-rest value.
"""

from __future__ import annotations

import hashlib
import secrets

# 32 bytes → 43-char URL-safe token; SHA-256 hex digest is 64 chars (fits
# ``token_hash``/``csrf_token`` VARCHAR(128)).
_TOKEN_BYTES = 32


def generate_token() -> str:
    """Return a new high-entropy URL-safe opaque token."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_token(raw_token: str) -> str:
    """Return the hex SHA-256 of ``raw_token`` for storage/lookup."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class SecretsTokenGenerator:
    """``TokenGenerator`` port adapter backed by :func:`generate_token`."""

    def generate(self) -> str:
        return generate_token()
