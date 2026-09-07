"""Generation adapters (implement ``GenerationPort``, ADR-0007/0020).

The provider SDK, model name, and citation format live only inside these
adapters; callers depend on ``GenerationPort`` and receive a Learny-owned
``GeneratedAnswer``. The default is a deterministic, network-free extractive
adapter (AD-024) that makes the answer path testable offline;
``build_generation_adapter`` selects the single concrete adapter from settings,
and ``build_generation_chain`` wraps the settings-declared profile registry in
the routing adapter — the composition root, so provider choice and chain order
never leak into application/domain code.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from app.infrastructure.answering.anthropic import AnthropicGenerationAdapter
from app.infrastructure.answering.local import DeterministicGenerationAdapter
from app.infrastructure.answering.routing import ChainEntry, RoutingGenerationAdapter
from app.infrastructure.providers import resolve_generation_profiles

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.domain.ports import GenerationPort
    from app.infrastructure.providers.profiles import GenerationProfileSettings

__all__ = [
    "AnthropicGenerationAdapter",
    "DeterministicGenerationAdapter",
    "RoutingGenerationAdapter",
    "build_generation_adapter",
    "build_generation_chain",
]


def build_generation_adapter(settings: Settings) -> GenerationPort:
    """Return the generation adapter named by ``settings.generation_provider``.

    One adapter serves both modes (D-2): the mode is a per-call argument, not a
    per-adapter choice, so one provider switch governs the whole turn path.

    ``local`` (default) → the deterministic, network-free adapter (CI/local needs
    no key); ``anthropic`` → the Claude adapter built from the key/model/max-tokens
    settings, which requires a non-empty ``anthropic_api_key`` so a misconfigured
    provider fails fast at composition rather than as a per-request 502. An
    unrecognized provider raises ``ValueError`` — a clear configuration error, not a
    silent fall back to the default (GEN-02).
    """
    provider = settings.generation_provider
    if provider == "local":
        return DeterministicGenerationAdapter()
    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError(
                "LEARNY_ANTHROPIC_API_KEY is required when the generation provider is 'anthropic'"
            )
        return AnthropicGenerationAdapter(
            api_key=settings.anthropic_api_key,
            model=settings.generation_model,
            max_tokens=settings.generation_max_tokens,
            effort=settings.generation_effort,
        )
    raise ValueError(f"unknown generation provider: {provider}")


def _build_sub_adapter(profile: GenerationProfileSettings, settings: Settings) -> GenerationPort:
    """Build the one adapter a profile names, from the settings it declares.

    A declared profile's key was validated present in its named env variable
    (ROUTE-05), so the env read here is the value the operator pointed
    ``api_key_env`` at; the legacy-seeded profile validated
    ``settings.anthropic_api_key``, which pydantic may have loaded from the env
    file rather than the process env — the settings value is that same
    variable's configured value, so it is the anthropic fallback. The profile's
    per-mode effort values feed the constructor (COST-01/AD-339): the legacy
    seed carries ``generation_effort`` on both modes, so today's behavior is
    unchanged until an operator declares otherwise.
    """
    if profile.kind == "local":
        return DeterministicGenerationAdapter()
    if profile.kind == "anthropic":
        return AnthropicGenerationAdapter(
            api_key=os.environ.get(profile.api_key_env) or settings.anthropic_api_key,
            model=profile.model,
            max_tokens=profile.max_tokens,
            effort_ask=profile.effort_ask,
            effort_teach=profile.effort_teach,
        )
    raise ValueError(
        f"generation profile '{profile.id}' names adapter kind '{profile.kind}', "
        "which has no adapter"
    )


def build_generation_chain(settings: Settings, *, explain: bool = False) -> GenerationPort:
    """Return the routing adapter over the settings-declared profile chain (ROUTE-01).

    The registry is resolved (validated, legacy-seeded) in one place, each
    profile is built into a :class:`ChainEntry`, and the ordered chain is wrapped
    in the routing adapter, so the application keeps calling one
    ``GenerationPort`` and never learns the chain exists (AD-338). Fail-fast is
    inherited from the resolution: a malformed registry or a missing key env
    raises here, at composition, not per request (ROUTE-05).

    With ``explain=True`` the chain is the selection-Explain ordering (AD-345):
    the profile ``generation_explain_profile`` names leads the chain when it is
    declared **and** ask-eligible, and the rest keep the registry order; an
    unset or ineligible name leaves the primary first. Routing policy itself
    stays inside the router — this only decides who stands first in line.
    """
    profiles = resolve_generation_profiles(settings)
    if explain:
        named = settings.generation_explain_profile
        head = next((p for p in profiles if p.id == named and p.ask_enabled), None)
        if head is not None:
            profiles = tuple([head, *(p for p in profiles if p is not head)])
    return RoutingGenerationAdapter(
        tuple(
            ChainEntry(adapter=_build_sub_adapter(profile, settings), profile=profile)
            for profile in profiles
        )
    )
