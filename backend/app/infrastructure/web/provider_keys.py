"""The learner's provider keys: add, test, replace, delete and list (ADR-0033).

Thin FastAPI adapter over the sealed ``user_provider_credentials`` repository.
A learner pastes a key once; from then on only its last four characters and
when it was added ever leave the server. No response, error detail or log line
of this router carries key material: the request body is parsed by hand so a
malformed one is refused with fixed copy instead of a validation error that
echoes the input back.

The feature is on only when the operator configured a KEK and at least one
declared profile binds a provider. Off, the list answers ``enabled: false``
and every write answers 404, exactly as for a provider this instance does not
offer.

Contract (also consumed by the Next.js proxy):
- ``GET    /api/me/provider-keys``                   → 200 ``{enabled, hosted, providers[],
  usage}``; auth.
- ``PUT    /api/me/provider-keys/{provider}``        → 200 the provider's row; auth + CSRF +
  rate limit; 404 when not offered; 422 for a malformed key (fixed copy).
- ``POST   /api/me/provider-keys/{provider}/test``   → 200 ``{ok, reason}``; auth + CSRF +
  rate limit; 404 when not offered or no key is stored.
- ``DELETE /api/me/provider-keys/{provider}``        → 204, also when no key was stored;
  auth + CSRF; 404 when not offered.
- ``PUT    /api/me/provider-keys/budget``            → 200 the usage view; auth + CSRF +
  rate limit; 404 when the feature is off; 422 for an out-of-range budget (fixed copy).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.application.budget import MICROS_PER_USD
from app.domain.entities import ProviderCredential, User
from app.infrastructure.answering.probe import ProbeOutcome, ProbeReason, probe_key
from app.infrastructure.db.provider_credentials import (
    MIN_KEY_CHARS,
    SqlAlchemyProviderCredentialRepository,
)
from app.infrastructure.db.repositories import SqlAlchemyUserByokSettingsRepository
from app.infrastructure.providers import GenerationProfileSettings
from app.infrastructure.quiz.learner import QUIZ_KEY_PROVIDER
from app.infrastructure.web.csrf import enforce_csrf
from app.infrastructure.web.dependencies import (
    DbConnection,
    build_byok_policy,
    build_provider_credential_repository,
    evict_learner_adapters,
    get_authenticated_user,
    hosted_declaration,
    key_bound_profiles,
    offered_key_providers,
)
from app.infrastructure.web.error_handlers import HTTP_422
from app.infrastructure.web.rate_limit import rate_limit_provider_keys

router = APIRouter(tags=["provider-keys"])

#: How each provider reads on the account page (brand names, never translated).
PROVIDER_LABELS = {
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "gemini": "Google Gemini",
}

#: Key length bounds the routes accept (plan assumption: catches pasted typos
#: without coupling to undocumented formats). The floor is the repository's own,
#: so a key the route accepts is always one the repository will seal.
MAX_KEY_CHARS = 256

#: The prefix each provider's keys start with; Gemini keys are not checked.
_KEY_PREFIXES = {"anthropic": "sk-ant-", "openai": "sk-"}

# Fixed copy: none of it ever contains the submitted value.
_NOT_OFFERED = "This provider's keys are not accepted on this instance."
_NO_KEY = "No key is stored for this provider."
_MALFORMED = (
    "That does not look like a valid API key for this provider. Paste the whole key, "
    f"{MIN_KEY_CHARS} to {MAX_KEY_CHARS} characters with no spaces."
)
_BUDGET_INVALID = (
    "That does not look like a valid monthly budget. Enter a dollar amount "
    "between 0 (exclusive) and 10,000, or clear the budget."
)

#: Tests the stored key against a bound profile's host (overridable in tests).
KeyProbe = Callable[[GenerationProfileSettings, str], ProbeOutcome]


def get_key_probe() -> KeyProbe:
    """FastAPI dependency: the key test probe (overridable in tests)."""
    return probe_key


class PoweredProfile(BaseModel):
    """One declared profile a provider's key serves, with its mode eligibility."""

    profile_id: str
    display_name: str
    ask: bool
    teach: bool


class ProviderKeyView(BaseModel):
    """One offered provider as the account page shows it. Never key material."""

    provider: str
    label: str
    configured: bool
    last4: str | None
    added_at: datetime | None
    powers: list[PoweredProfile]
    powers_cards: bool


class ByokUsageView(BaseModel):
    """The caller's month-to-date own-key usage and their stored monthly budget.

    Zeros are a quiet month; ``budget_usd_micros`` is ``None`` while no budget
    is set. Cost is the learner's own estimate at the serving catalog — the
    operator's number is never shown here.
    """

    period: str
    input_tokens: int
    output_tokens: int
    cost_usd_micros: int
    budget_usd_micros: int | None


class ProviderKeysView(BaseModel):
    """The whole keys section: whether it exists here, and its provider rows.

    ``hosted`` is the instance's own declaration (not secret: the section's
    existence is already instance-visible) — the disclosure copy keys off it
    wherever the section renders. ``usage`` rides on every response so the
    section's budget control and month-to-date line render wherever the
    section does.
    """

    enabled: bool
    hosted: bool
    providers: list[ProviderKeyView]
    usage: ByokUsageView


class KeyTestView(BaseModel):
    """A key test outcome: ``ok``, or one reason it failed."""

    ok: bool
    reason: ProbeReason | None


def _view(provider: str, credential: ProviderCredential | None) -> ProviderKeyView:
    return ProviderKeyView(
        provider=provider,
        label=PROVIDER_LABELS.get(provider, provider),
        configured=credential is not None,
        last4=credential.last4 if credential is not None else None,
        added_at=credential.created_at if credential is not None else None,
        powers=[
            PoweredProfile(
                profile_id=profile.id,
                display_name=profile.display_name or profile.id,
                ask=profile.ask_enabled,
                teach=profile.teach_enabled,
            )
            for profile in key_bound_profiles(provider)
        ],
        powers_cards=provider == QUIZ_KEY_PROVIDER,
    )


def _offered_repo(conn: DbConnection, provider: str) -> SqlAlchemyProviderCredentialRepository:
    """The repository for an offered ``provider``, else the 404 every write shares."""
    repo = build_provider_credential_repository(conn)
    if repo is None or provider not in offered_key_providers():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_OFFERED)
    return repo


def _key_from_body(provider: str, body: Any) -> str:  # noqa: ANN401 — parsed by hand on purpose
    """The submitted key, or a 422 with fixed copy that never echoes the value."""
    api_key = body.get("api_key") if isinstance(body, dict) else None
    if (
        not isinstance(api_key, str)
        or not MIN_KEY_CHARS <= len(api_key) <= MAX_KEY_CHARS
        or any(ch.isspace() for ch in api_key)
        or not api_key.startswith(_KEY_PREFIXES.get(provider, ""))
    ):
        raise HTTPException(status_code=HTTP_422, detail=_MALFORMED)
    return api_key


def _usage_view(conn: DbConnection, user_id: UUID) -> ByokUsageView:
    """The caller's month-to-date usage and stored budget (zeros when quiet)."""
    policy = build_byok_policy(conn)
    period, tokens_in, tokens_out, cost = policy.month_usage(user_id)
    return ByokUsageView(
        period=period,
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        cost_usd_micros=cost,
        budget_usd_micros=policy.stored_budget(user_id),
    )


@router.get("/api/me/provider-keys")
def list_provider_keys(
    conn: DbConnection,
    user: Annotated[User, Depends(get_authenticated_user)],
) -> ProviderKeysView:
    """The offered providers with the caller's key state (200; 401 if unauth).

    ``enabled: false`` with no rows when the feature is off — the hosted
    declaration and the usage row still answer, so the disclosure and the
    budget control render wherever the section does. Rows follow the registry
    order of each provider's first binding.
    """
    usage = _usage_view(conn, user.id)
    repo = build_provider_credential_repository(conn)
    if repo is None:
        return ProviderKeysView(
            enabled=False, hosted=hosted_declaration(), providers=[], usage=usage
        )
    stored = {credential.provider: credential for credential in repo.list_for_user(user.id)}
    return ProviderKeysView(
        enabled=True,
        hosted=hosted_declaration(),
        providers=[_view(provider, stored.get(provider)) for provider in offered_key_providers()],
        usage=usage,
    )


@router.put(
    "/api/me/provider-keys/budget",
    dependencies=[Depends(enforce_csrf), Depends(rate_limit_provider_keys)],
)
def put_budget(
    conn: DbConnection,
    user: Annotated[User, Depends(get_authenticated_user)],
    body: Annotated[Any, Body()] = None,
) -> ByokUsageView:
    """Store (or clear) the caller's own monthly budget; the usage view, never an echo.

    A number greater than 0 and at most 10,000 stores its micros; ``null``
    clears the budget, and the next request serves — that is what makes the
    budget soft. Anything else is a 422 with fixed copy that echoes no
    submitted value, exactly like a malformed key.
    """
    if build_provider_credential_repository(conn) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_OFFERED)
    value = body.get("monthly_budget_usd") if isinstance(body, dict) else None
    micros: int | None
    if value is None:
        micros = None
    elif isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HTTPException(status_code=HTTP_422, detail=_BUDGET_INVALID)
    # Range-check the raw value BEFORE any conversion: a huge JSON integer
    # overflows ``float()`` (an unhandled OverflowError → 500), while this
    # comparison answers the fixed-copy 422 for it and still rejects NaN
    # (``nan > 0`` is False) whatever the value's precision.
    elif not (value > 0 and value <= 10_000):
        raise HTTPException(status_code=HTTP_422, detail=_BUDGET_INVALID)
    else:
        micros = int(round(float(value) * MICROS_PER_USD))
    SqlAlchemyUserByokSettingsRepository(conn).set_budget(user.id, micros)
    return _usage_view(conn, user.id)


@router.put(
    "/api/me/provider-keys/{provider}",
    dependencies=[Depends(enforce_csrf), Depends(rate_limit_provider_keys)],
)
def put_provider_key(
    provider: str,
    conn: DbConnection,
    user: Annotated[User, Depends(get_authenticated_user)],
    body: Annotated[Any, Body()] = None,
) -> ProviderKeyView:
    """Store (or replace) the caller's key for ``provider``; the row, never the key.

    A replace mints a new row id, so a deck pinned to the old key stops
    collecting and every cached adapter built from it stops resolving. Two
    racing saves end with one row (the repository retries the loser).
    """
    repo = _offered_repo(conn, provider)
    api_key = _key_from_body(provider, body)
    previous = repo.get(user.id, provider)
    credential = repo.replace(user.id, provider, api_key)
    if previous is not None:
        evict_learner_adapters(previous.fingerprint)
    return _view(provider, credential)


@router.post(
    "/api/me/provider-keys/{provider}/test",
    dependencies=[Depends(enforce_csrf), Depends(rate_limit_provider_keys)],
)
def test_provider_key(
    provider: str,
    conn: DbConnection,
    user: Annotated[User, Depends(get_authenticated_user)],
    probe: Annotated[KeyProbe, Depends(get_key_probe)],
) -> KeyTestView:
    """Test the stored key with one model-list call (no tokens billed).

    The call goes to the host of the first profile bound to ``provider``, the
    same host a turn would send the key to. 404 when no usable key is stored.
    """
    repo = _offered_repo(conn, provider)
    credential = repo.get(user.id, provider)
    api_key = repo.reveal(credential) if credential is not None else None
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NO_KEY)
    outcome = probe(key_bound_profiles(provider)[0], api_key)
    return KeyTestView(ok=outcome.ok, reason=None if outcome.ok else outcome.reason)


@router.delete(
    "/api/me/provider-keys/{provider}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(enforce_csrf)],
)
def delete_provider_key(
    provider: str,
    conn: DbConnection,
    user: Annotated[User, Depends(get_authenticated_user)],
) -> Response:
    """Remove the caller's key for ``provider`` (204, also when none was stored).

    The next request is served on the house chain; a deck pinned to the key
    fails terminally at its next poll.
    """
    repo = _offered_repo(conn, provider)
    previous = repo.get(user.id, provider)
    repo.delete(user.id, provider)
    if previous is not None:
        evict_learner_adapters(previous.fingerprint)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
