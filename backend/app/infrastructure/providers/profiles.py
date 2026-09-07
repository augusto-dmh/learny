"""The settings-declared generation profile registry (cheaper-intelligence, ROUTE-01).

A *profile* is one serving configuration: which adapter kind builds it, which model
it names, how hard it thinks per mode, what its tokens cost, and which grounded
modes it may serve. The ordered registry is the single source of truth for
generation selection when declared; :func:`resolve_generation_profiles` is the one
place that turns settings into that registry, so the composition root (Phase 3's
chain builder) never re-derives the legacy rules.

Legacy seed (AD-342/ROUTE-06): when no registry is declared, exactly one profile is
synthesized from the pre-registry settings (``generation_provider`` /
``generation_model`` / ``generation_effort`` / the global ``price_*`` pair), so the
default deployment keeps today's single-provider behavior byte-for-byte.

This module imports the standard library and pydantic only — no provider SDK
crosses this boundary (fitness gate).
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

#: The adapter kinds a profile may name. ``local`` is the deterministic offline
#: adapter; ``anthropic`` the Claude Citations adapter; ``openai-compatible`` the
#: prompt-cited second adapter (Phase 5).
PROFILE_KINDS = ("local", "anthropic", "openai-compatible")

#: How much thinking a profile spends before answering — the Anthropic effort
#: literals ``generation_effort`` has always accepted (AD-339).
EFFORT_LITERALS = ("low", "medium", "high", "xhigh", "max")

#: The citation mechanism a profile's answers carry. ``verified-spans``: provider
#: char-level citations resolved against the exact document bodies sent (the
#: Anthropic Citations adapter). ``prompt-cited``: model-written markers into
#: supplied documents, verified by the grounding intersection (the OpenAI-compatible
#: adapter). ``none``: no citations (never eligible for grounded modes).
GROUNDING_KINDS = ("verified-spans", "prompt-cited", "none")

#: The id of the profile synthesized from the legacy settings when no registry is
#: declared (ROUTE-06). Stable so debits and eval records can name it.
LEGACY_PROFILE_ID = "default"

#: Cache-price defaults derived from the input price when a profile does not
#: override them: reads are cheap, creation pays the write premium (design §Tech
#: Decisions — Anthropic Sonnet actuals).
CACHE_READ_PRICE_FACTOR = 0.1
CACHE_CREATION_PRICE_FACTOR = 1.25


class GenerationProfileSettings(BaseModel):
    """One serving configuration in the ordered profile registry (design §2).

    Declared via the ``LEARNY_GENERATION_PROFILES`` JSON list. ``api_key_env`` is
    the *name* of the environment variable carrying the provider key — the value
    itself is never a setting (NFR-SEC-003). The four price fields are the
    profile's own catalog in USD per million tokens; ``effort_ask``/``effort_teach``
    are ignored by adapter kinds that cannot express them (ECON-05).
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["local", "anthropic", "openai-compatible"]
    model: str
    base_url: str = ""
    api_key_env: str = ""
    effort_ask: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    effort_teach: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    max_tokens: int
    price_input_usd_per_million_tokens: float
    price_output_usd_per_million_tokens: float
    price_cache_read_usd_per_million_tokens: float
    price_cache_creation_usd_per_million_tokens: float
    grounding: Literal["verified-spans", "prompt-cited", "none"]
    ask_enabled: bool
    teach_enabled: bool


def _validate_declared(profiles: list[GenerationProfileSettings]) -> None:
    """Reject a malformed declared registry before anything is built (ROUTE-05).

    Each branch raises ``ValueError`` naming the offending profile and the fix, so
    a misconfigured deployment fails at composition with an actionable message —
    never a silent single-profile downgrade (spec §Edge Cases).
    """
    seen: set[str] = set()
    for profile in profiles:
        if not profile.id:
            raise ValueError("a generation profile has an empty id; every profile must be named")
        if profile.id in seen:
            raise ValueError(
                f"duplicate generation profile id '{profile.id}': profile ids must be unique"
            )
        seen.add(profile.id)
    for profile in profiles:
        if profile.kind not in PROFILE_KINDS:
            raise ValueError(
                f"generation profile '{profile.id}' has unknown kind '{profile.kind}': "
                f"expected one of {', '.join(PROFILE_KINDS)}"
            )
        if profile.kind != "local":
            if not profile.api_key_env:
                raise ValueError(
                    f"generation profile '{profile.id}' (kind '{profile.kind}') must name "
                    "the environment variable carrying its API key (api_key_env)"
                )
            if not os.environ.get(profile.api_key_env):
                raise ValueError(
                    f"generation profile '{profile.id}' names api_key_env "
                    f"'{profile.api_key_env}', but that environment variable is not set"
                )


def _legacy_seed_profile(settings: Settings) -> GenerationProfileSettings:
    """Synthesize the one profile the pre-registry settings describe (AD-342).

    Behavior must equal today's single-provider configuration: the provider switch,
    model, effort (both modes), max-tokens, and the global price pair carry over;
    ask and teach stay enabled (the incumbent serves every grounded mode today);
    the cache prices take the derived defaults; grounding is ``verified-spans`` —
    the Citations-API mechanism the incumbent primary answers with.
    """
    provider = settings.generation_provider
    if provider == "local":
        api_key_env = ""
    elif provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError(
                "LEARNY_ANTHROPIC_API_KEY is required when the generation provider is 'anthropic'"
            )
        api_key_env = "LEARNY_ANTHROPIC_API_KEY"
    else:
        raise ValueError(f"unknown generation provider: {provider}")
    return GenerationProfileSettings(
        id=LEGACY_PROFILE_ID,
        kind=provider,
        model=settings.generation_model,
        api_key_env=api_key_env,
        effort_ask=settings.generation_effort,
        effort_teach=settings.generation_effort,
        max_tokens=settings.generation_max_tokens,
        price_input_usd_per_million_tokens=settings.price_input_usd_per_million_tokens,
        price_output_usd_per_million_tokens=settings.price_output_usd_per_million_tokens,
        price_cache_read_usd_per_million_tokens=(
            settings.price_input_usd_per_million_tokens * CACHE_READ_PRICE_FACTOR
        ),
        price_cache_creation_usd_per_million_tokens=(
            settings.price_input_usd_per_million_tokens * CACHE_CREATION_PRICE_FACTOR
        ),
        grounding="verified-spans",
        ask_enabled=True,
        teach_enabled=True,
    )


def resolve_generation_profiles(settings: Settings) -> tuple[GenerationProfileSettings, ...]:
    """Return the ordered profile registry the settings declare (design §2).

    A declared, non-empty list is validated and passed through in order; an empty
    list (the default — nothing declared) synthesizes the single legacy profile so
    the resolved registry is never empty. Called at composition only: a malformed
    registry fails fast at startup rather than as a per-request error.
    """
    declared = settings.generation_profiles
    if not declared:
        return (_legacy_seed_profile(settings),)
    _validate_declared(declared)
    return tuple(declared)


def resolve_serving_profile(
    profiles: tuple[GenerationProfileSettings, ...],
    profile_id: str | None,
) -> GenerationProfileSettings | None:
    """Return the profile a result's stamp names, for pricing and attribution.

    Resolution order (AD-344/PRICE-04): a stamp names its profile exactly — the
    exact match is what keeps two profiles sharing one model unambiguous. No stamp
    is the single-profile world, priced and attributed at the primary. A stamp
    that names no declared profile falls back to the primary **with a warning** —
    a correct-or-conservative debit, never a silent misprice. ``None`` when the
    registry itself is empty.
    """
    primary = profiles[0] if profiles else None
    if profile_id is None:
        return primary
    for profile in profiles:
        if profile.id == profile_id:
            return profile
    logger.warning(
        "generation profile '%s' is not declared; falling back to the primary profile '%s'",
        profile_id,
        primary.id if primary else "<none>",
    )
    return primary
