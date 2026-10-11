"""Interface-language choice router.

Thin FastAPI adapter over the caller's single locale preference row, mirroring the
AI-profile choice surface. The supported-set check is the boundary's own input
validation; storage is the dependencies' job.

Contract (also consumed by the Next.js proxy; the stored value rides ``GET /api/auth/me``):
- ``PUT    /api/me/locale`` → 200 ``{locale}``; auth + CSRF; a re-put replaces; a
  value outside ``{en, pt-BR}`` is a 422 and persists nothing.
- ``DELETE /api/me/locale`` → 204, idempotent (204 even when nothing was set);
  auth + CSRF. The learner is back to "automatic" (negotiate from the browser).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.domain.entities import User
from app.domain.locale import SUPPORTED_LOCALES, is_supported_locale
from app.infrastructure.web.csrf import enforce_csrf
from app.infrastructure.web.dependencies import (
    get_authenticated_user,
    get_clear_locale_choice,
    get_set_locale_choice,
)
from app.infrastructure.web.error_handlers import HTTP_422

router = APIRouter(tags=["locale"])


class LocaleChoiceBody(BaseModel):
    """The PUT body. Validated against the supported set by the route, not by the
    model, so the refusal is a 422 with a readable detail either way."""

    locale: str


class LocaleChoiceView(BaseModel):
    """The stored locale after a write."""

    locale: str


@router.put("/api/me/locale", dependencies=[Depends(enforce_csrf)])
def put_locale(
    body: LocaleChoiceBody,
    user: Annotated[User, Depends(get_authenticated_user)],
    store: Annotated[Callable[[str], str], Depends(get_set_locale_choice)],
) -> LocaleChoiceView:
    """Store the caller's locale (200; 422 outside the supported set; 401 if unauth)."""
    if not is_supported_locale(body.locale):
        raise HTTPException(
            status_code=HTTP_422,
            detail=f"locale must be one of: {', '.join(SUPPORTED_LOCALES)}",
        )
    return LocaleChoiceView(locale=store(body.locale))


@router.delete(
    "/api/me/locale",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(enforce_csrf)],
)
def delete_locale(
    user: Annotated[User, Depends(get_authenticated_user)],
    clear: Annotated[Callable[[], bool], Depends(get_clear_locale_choice)],
) -> Response:
    """Unset the caller's locale (204, also when nothing was set)."""
    clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
