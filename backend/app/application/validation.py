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

# The uniform ToS refusal (DOOR-25): missing consent is a 422 like every other
# validation failure. Defined beside the disposable lists — the two register
# rails added together — so the register copy has one home.
TOS_ACCEPTANCE_MESSAGE = "You must accept the Terms of Service to create an account."

# Documented privacy-alias domains (rq09): an address here is a real relay to
# the user's own inbox, never a throwaway, so the allow-list wins over the
# deny-list (DOOR-24). ``duck.com`` is the spec-named member.
ALLOWED_ALIAS_DOMAINS = frozenset(
    {
        "duck.com",  # DuckDuckGo Email Protection
        "privaterelay.appleid.com",  # iCloud Hide My Email
        "simplelogin.com",  # SimpleLogin
        "simplelogin.io",
    }
)

# Closed, committed deny-list of disposable-inbox providers (DOOR-23). Frozen
# on purpose: additions are a code change, so the register contract never
# shifts under a data-driven edit. Matching is exact-domain — no subdomain or
# substring matching — so ``mailinator.com`` rejects while any unlisted domain
# (including every alias above) registers normally.
DISPOSABLE_EMAIL_DOMAINS = frozenset(
    {
        "10minutemail.com",
        "20minutemail.com",
        "33mail.com",
        "bugmenot.com",
        "dispostable.com",
        "emailondeck.com",
        "fakeinbox.com",
        "getnada.com",
        "guerrillamail.com",
        "guerrillamail.net",
        "mailcatch.com",
        "maildrop.cc",
        "mailinator.com",
        "mailnesia.com",
        "mintemail.com",
        "mytemp.email",
        "sharklasers.com",
        "temp-mail.org",
        "tempinbox.com",
        "tempmail.com",
        "throwawaymail.com",
        "trashmail.com",
        "yopmail.com",
    }
)


def is_disposable_email(email: str) -> bool:
    """Whether the email's domain is on the committed disposable deny-list (DOOR-23)."""
    domain = email.rsplit("@", 1)[-1].strip().lower()
    if domain in ALLOWED_ALIAS_DOMAINS:
        return False
    return domain in DISPOSABLE_EMAIL_DOMAINS


def normalize_email(email: str) -> str:
    """Trim and lowercase an email for consistent storage/lookup."""
    return email.strip().lower()


# Password-less operator for the shared sample. RegisterUser rejects it;
# SeedSample creates the user without credentials.
SAMPLE_OPERATOR_EMAIL = "sample-operator@learny.invalid"


def validate_email(email: str) -> str:
    """Return the normalized email, or raise ``ValidationError``."""
    normalized = normalize_email(email)
    if not _EMAIL_RE.match(normalized):
        raise ValidationError("Invalid email address.")
    return normalized


def validate_password(password: str) -> str:
    """Return the password unchanged if it meets policy, else raise."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValidationError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters.")
    return password


EPUB_EXTENSION = ".epub"
EPUB_CONTENT_TYPE = "application/epub+zip"
PDF_EXTENSION = ".pdf"
PDF_CONTENT_TYPE = "application/pdf"
MAX_TITLE_LENGTH = 500

# Supported upload formats: filename extension → required content type (ING-09).
# Extension and content type must agree in both directions; any other combination
# stays rejected with the existing typed kinds.
SUPPORTED_FORMATS: dict[str, str] = {
    EPUB_EXTENSION: EPUB_CONTENT_TYPE,
    PDF_EXTENSION: PDF_CONTENT_TYPE,
}


def extension_of(filename: str) -> str | None:
    """Return the supported extension ``filename`` ends with, else ``None``.

    Case-insensitive; the returned extension is the lowercase table key so callers
    (object-key building, per-format cap selection) never re-derive it.
    """
    lowered = filename.lower()
    for extension in SUPPORTED_FORMATS:
        if lowered.endswith(extension):
            return extension
    return None


def validate_source_upload(
    *,
    title: str,
    filename: str,
    content_type: str,
    byte_size: int,
    max_bytes: int,
    pdf_max_bytes: int | None = None,
) -> None:
    """Guard a source upload before any bytes are stored or a row persisted.

    Accepts EPUB and PDF (ING-09): the filename extension must be supported and
    must agree with the client-asserted content type in both directions, and the
    byte size must fit the per-format cap (``max_bytes`` for EPUB, ``pdf_max_bytes``
    for PDF — falling back to ``max_bytes`` when a PDF cap is not supplied). Raises
    :class:`~app.application.errors.InvalidSourceUpload` carrying a ``kind`` the web
    layer maps to a status (design §Validation). Structural validation is
    ingestion's job (the content type is client-asserted and only shape-checked).
    """
    extension = extension_of(filename)
    if extension is None:
        raise InvalidSourceUpload("extension", "Only EPUB and PDF files are supported.")
    if content_type != SUPPORTED_FORMATS[extension]:
        raise InvalidSourceUpload("content_type", "The file type does not match its extension.")
    cap = pdf_max_bytes if extension == PDF_EXTENSION and pdf_max_bytes is not None else max_bytes
    if byte_size <= 0:
        raise InvalidSourceUpload("empty", "The uploaded file is empty.")
    if byte_size > cap:
        raise InvalidSourceUpload("size", "File exceeds the maximum size.")
    stripped = title.strip()
    if not stripped:
        raise InvalidSourceUpload("title", "A title is required.")
    if len(stripped) > MAX_TITLE_LENGTH:
        raise InvalidSourceUpload("title", f"Title must be at most {MAX_TITLE_LENGTH} characters.")
