"""AI-profile catalog + per-user choice router (ADR-0020 amendment).

Thin FastAPI adapter over two resources with different owners: the deployment's
declared profile registry (settings-side, the same registry that resolves every
serving chain) and the caller's single stored preference row (account-side, read
and written on the request transaction through the wiring in ``dependencies``).
The handlers carry no policy beyond the boundary's own input validation — the
declared-registry membership check that refuses an unknown id before anything
persists.

Honesty bounds of the surface: the catalog is the providers layer's
learner-facing projection, so no operational field of a profile (adapter kind,
key env-var name, base URL, price, token budget) ever leaves this router; and a
stored choice is returned exactly as stored — an id the operator renamed or
removed is never rewritten behind the learner's back (serving falls back to the
deployment default instead).

Contract (also consumed by the Next.js proxy):
- ``GET    /api/ai/profiles``   → 200, the selectable catalog (empty when nothing
  is declared — the synthetic legacy seed is the operator default, not a choice);
  auth required.
- ``GET    /api/me/ai-profile`` → 200 ``{profile_id: string | null}``; auth.
- ``PUT    /api/me/ai-profile`` → 200 the stored choice; auth + CSRF; a re-put
  replaces; an id nothing declares is a 422 naming the problem and persists
  nothing.
- ``DELETE /api/me/ai-profile`` → 204, idempotent (204 even when nothing was set);
  auth + CSRF.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.domain.entities import User
from app.infrastructure.providers import LearnerProfile, learner_catalog
from app.infrastructure.web.csrf import enforce_csrf
from app.infrastructure.web.dependencies import (
    AppSettings,
    get_ai_profile_choice,
    get_authenticated_user,
    get_clear_ai_profile_choice,
    get_set_ai_profile_choice,
)

router = APIRouter(tags=["ai"])

# 422 for the unknown-id refusal; tolerate either spelling across Starlette
# versions (the same shim the global error handlers use — the old name's access
# warns, so it is only evaluated when the new one is absent).
_HTTP_422 = getattr(
    status,
    "HTTP_422_UNPROCESSABLE_CONTENT",
    None,
) or getattr(status, "HTTP_422_UNPROCESSABLE_ENTITY", 422)


class AiProfileChoiceBody(BaseModel):
    """The PUT body: the declared profile id the caller wants to lead their chain."""

    profile_id: str


class AiProfileChoiceView(BaseModel):
    """The choice resource: the stored id, or null when nothing is set."""

    profile_id: str | None


@router.get("/api/ai/profiles")
def list_ai_profiles(
    user: Annotated[User, Depends(get_authenticated_user)],
    settings: AppSettings,
) -> list[LearnerProfile]:
    """Return the deployment's selectable AI profiles (200; 401 if unauth).

    The declared registry in registry order, each entry carrying its honest
    copy (the display name falls back to the id; the description may be empty),
    its grounding mechanism, and its ask/teach eligibility. Derived per request
    from the current settings, so an operator's redeclaration is reflected on
    the next request without a restart.
    """
    return list(learner_catalog(settings))


@router.get("/api/me/ai-profile")
def read_ai_profile(
    choice: Annotated[str | None, Depends(get_ai_profile_choice)],
    user: Annotated[User, Depends(get_authenticated_user)],
) -> AiProfileChoiceView:
    """Return the caller's stored choice (200; ``profile_id`` null when unset)."""
    return AiProfileChoiceView(profile_id=choice)


@router.put("/api/me/ai-profile", dependencies=[Depends(enforce_csrf)])
def put_ai_profile(
    body: AiProfileChoiceBody,
    user: Annotated[User, Depends(get_authenticated_user)],
    settings: AppSettings,
    store: Annotated[Callable[[str], str], Depends(get_set_ai_profile_choice)],
) -> AiProfileChoiceView:
    """Store the caller's choice (200; 422 for an unknown id; 401 if unauth).

    Validated against the *current* declared registry, so a typo — or an id the
    operator has since removed — is refused before anything persists; a re-put
    replaces the previous choice on the caller's single row.
    """
    declared = {profile.id for profile in settings.generation_profiles}
    if body.profile_id not in declared:
        raise HTTPException(
            status_code=_HTTP_422,
            detail=(
                f"generation profile '{body.profile_id}' is not declared by this "
                "deployment; choose an id from GET /api/ai/profiles"
            ),
        )
    return AiProfileChoiceView(profile_id=store(body.profile_id))


@router.delete(
    "/api/me/ai-profile",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(enforce_csrf)],
)
def delete_ai_profile(
    user: Annotated[User, Depends(get_authenticated_user)],
    clear: Annotated[Callable[[], bool], Depends(get_clear_ai_profile_choice)],
) -> Response:
    """Unset the caller's choice (204, also when nothing was set). Serving
    returns to the operator default chain."""
    clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
