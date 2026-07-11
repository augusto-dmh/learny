"""Map application-layer errors to HTTP responses (task C1).

The application/domain layers raise framework-free exceptions
(``app.application.errors``); this is the only place they are translated into
HTTP status codes, keeping the layering boundary intact (ADR-007/009).

Status mapping (per spec / Phase C brief):
- ``ValidationError``     → 422 (input failed email/password policy, FR-AUTH-010)
- ``EmailAlreadyExists``  → 409 (register on an existing email, AC-2)
- ``InvalidCredentials``  → 401 (uniform login failure, no enumeration, AC-3)
- ``NotAuthenticated``    → 401 (no/invalid session, AC-3)
- ``NotAuthorized``       → 403 (authenticated but not the owner, AC-6)

Error bodies are intentionally terse and never echo the offending password or
token (NFR-SEC-004).
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.application.errors import (
    ActiveIngestionExists,
    CorpusNotFound,
    EmailAlreadyExists,
    EnqueueFailed,
    IngestionNotFound,
    InvalidCredentials,
    InvalidSourceUpload,
    NotAuthenticated,
    NotAuthorized,
    SourceNotFound,
    StorageUnavailable,
    ValidationError,
)

# 422 for validation; tolerate either spelling across Starlette versions
# (HTTP_422_UNPROCESSABLE_ENTITY was renamed to ..._CONTENT). Avoid evaluating
# the deprecated name unless the new one is absent (its access warns).
_HTTP_422 = getattr(
    status,
    "HTTP_422_UNPROCESSABLE_CONTENT",
    None,
) or getattr(status, "HTTP_422_UNPROCESSABLE_ENTITY", 422)

# 413 was likewise renamed (REQUEST_ENTITY_TOO_LARGE → CONTENT_TOO_LARGE).
_HTTP_413 = getattr(status, "HTTP_413_CONTENT_TOO_LARGE", None) or getattr(
    status, "HTTP_413_REQUEST_ENTITY_TOO_LARGE", 413
)

_STATUS_BY_ERROR = {
    ValidationError: _HTTP_422,
    EmailAlreadyExists: status.HTTP_409_CONFLICT,
    InvalidCredentials: status.HTTP_401_UNAUTHORIZED,
    NotAuthenticated: status.HTTP_401_UNAUTHORIZED,
    NotAuthorized: status.HTTP_403_FORBIDDEN,
    SourceNotFound: status.HTTP_404_NOT_FOUND,
    StorageUnavailable: status.HTTP_503_SERVICE_UNAVAILABLE,
    ActiveIngestionExists: status.HTTP_409_CONFLICT,
    IngestionNotFound: status.HTTP_404_NOT_FOUND,
    EnqueueFailed: status.HTTP_502_BAD_GATEWAY,
    CorpusNotFound: status.HTTP_404_NOT_FOUND,
}

# An invalid upload maps to a status keyed by its ``kind`` (design §Error Handling):
# type/extension → 415, size → 413, empty/title → 422.
_STATUS_BY_UPLOAD_KIND = {
    "extension": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    "content_type": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    "size": _HTTP_413,
    "empty": _HTTP_422,
    "title": _HTTP_422,
}


def _make_handler(status_code: int):
    async def handler(_request: Request, exc: Exception) -> JSONResponse:
        # The exception message is a safe, user-facing string by construction
        # (services never put secrets in it). Still, only the message is exposed.
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    return handler


async def _invalid_source_upload_handler(
    _request: Request, exc: InvalidSourceUpload
) -> JSONResponse:
    status_code = _STATUS_BY_UPLOAD_KIND.get(exc.kind, _HTTP_422)
    return JSONResponse(status_code=status_code, content={"detail": str(exc)})


def register_error_handlers(app: FastAPI) -> None:
    """Attach the identity + source-storage exception handlers to the FastAPI app."""
    for error_type, status_code in _STATUS_BY_ERROR.items():
        app.add_exception_handler(error_type, _make_handler(status_code))
    app.add_exception_handler(InvalidSourceUpload, _invalid_source_upload_handler)
