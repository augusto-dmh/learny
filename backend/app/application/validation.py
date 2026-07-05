"""Input validation for registration/login (FR-AUTH-010, task B4).

Conservative, dependency-free checks. Email uses a pragmatic format check (the
authoritative uniqueness/normalization is the DB ``citext`` column); password
policy is a minimum-length floor aligned with OWASP guidance (length over
composition rules). Raises :class:`~app.application.errors.ValidationError`.
"""

from __future__ import annotations

import re

from app.application.errors import InvalidSourceUpload, ValidationError

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


EPUB_EXTENSION = ".epub"
EPUB_CONTENT_TYPE = "application/epub+zip"
MAX_TITLE_LENGTH = 500


def validate_source_upload(
    *,
    title: str,
    filename: str,
    content_type: str,
    byte_size: int,
    max_bytes: int,
) -> None:
    """Guard an EPUB upload before any bytes are stored or a row persisted.

    Raises :class:`~app.application.errors.InvalidSourceUpload` carrying a
    ``kind`` the web layer maps to a status (design §Validation). EPUB structural
    validation is ingestion's job (Phase 5); here the content-type is
    client-asserted and only shape-checked.
    """
    if not filename.lower().endswith(EPUB_EXTENSION):
        raise InvalidSourceUpload("extension", "Only EPUB files are supported.")
    if content_type != EPUB_CONTENT_TYPE:
        raise InvalidSourceUpload("content_type", "Only EPUB files are supported.")
    if byte_size <= 0:
        raise InvalidSourceUpload("empty", "The uploaded file is empty.")
    if byte_size > max_bytes:
        raise InvalidSourceUpload("size", "File exceeds the maximum size.")
    stripped = title.strip()
    if not stripped:
        raise InvalidSourceUpload("title", "A title is required.")
    if len(stripped) > MAX_TITLE_LENGTH:
        raise InvalidSourceUpload(
            "title", f"Title must be at most {MAX_TITLE_LENGTH} characters."
        )
