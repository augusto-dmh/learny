"""Input validation for registration/login (FR-AUTH-010, task B4).

Conservative, dependency-free checks. Email uses a pragmatic format check (the
authoritative uniqueness/normalization is the DB ``citext`` column); password
policy is a minimum-length floor aligned with OWASP guidance (length over
composition rules). Raises :class:`~app.application.errors.ValidationError`.
"""

from __future__ import annotations

import re

from app.application.errors import ValidationError

# Pragmatic email shape check: non-empty local part, "@", domain with a dot.
# Not a full RFC 5322 validator — the DB citext column is authoritative.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128  # bound work / avoid DoS on the hasher


def normalize_email(email: str) -> str:
    """Trim and lowercase an email for consistent storage/lookup."""
    return email.strip().lower()


def validate_email(email: str) -> str:
    """Return the normalized email, or raise ``ValidationError``."""
    normalized = normalize_email(email)
    if not _EMAIL_RE.match(normalized):
        raise ValidationError("Invalid email address.")
    return normalized


def validate_password(password: str) -> str:
    """Return the password unchanged if it meets policy, else raise."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValidationError(
            f"Password must be at most {MAX_PASSWORD_LENGTH} characters."
        )
    return password
