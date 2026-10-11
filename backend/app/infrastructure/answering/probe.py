"""Testing a learner's provider key without spending it (ADR-0033).

The key routes' test action calls the provider's model-list endpoint with the
learner's key, through the host the bound profile serves from. Listing models
bills no tokens, so pressing Test never costs the learner anything. The outcome
is mapped onto three reasons from the Learny provider error taxonomy:
``rejected`` (the provider refused the key), ``rate_limited`` and
``unavailable`` (timeouts, outages, an unreachable host, or anything
unexpected).

The SDK reference stays inside this adapter package (ADR-0007/0009), and the
key goes only to the SDK client: it is never logged, raised or returned.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from app.infrastructure.answering.anthropic import raise_translated as _anthropic_translated
from app.infrastructure.answering.openai_compat import raise_translated as _openai_translated
from app.infrastructure.providers.errors import (
    ProviderUnavailable,
    RateLimited,
    RequestRejected,
    Timeout,
)

if TYPE_CHECKING:
    from app.infrastructure.providers.profiles import GenerationProfileSettings

logger = logging.getLogger(__name__)

#: Why a key test failed, as the key routes report it.
ProbeReason = Literal["rejected", "rate_limited", "unavailable"]

#: The probe's wall-clock bound per attempt; it never retries.
PROBE_TIMEOUT_SECONDS = 10.0

#: Lists the provider's models with ``(api_key, base_url)``, raising the Learny
#: taxonomy on failure.
ModelLister = Callable[[str, str], None]


@dataclass(frozen=True)
class ProbeOutcome:
    """The result of one key test: ``ok``, or the reason it failed."""

    ok: bool
    reason: ProbeReason | None = None


def _list_anthropic_models(api_key: str, base_url: str) -> None:
    """One model-list call on the Anthropic API (``base_url`` is unused: native host)."""
    import anthropic  # local import — the SDK stays inside the adapter package

    client = anthropic.Anthropic(api_key=api_key, timeout=PROBE_TIMEOUT_SECONDS, max_retries=0)
    try:
        client.models.list(limit=1)
    except Exception as exc:  # noqa: BLE001 — translated onto the Learny taxonomy
        _anthropic_translated(exc)
    finally:
        client.close()


def _list_openai_compatible_models(api_key: str, base_url: str) -> None:
    """One model-list call on an OpenAI-compatible host (the profile's ``base_url``)."""
    import openai  # local import — the SDK stays inside the adapter package

    client = openai.OpenAI(
        api_key=api_key,
        base_url=base_url or None,
        timeout=PROBE_TIMEOUT_SECONDS,
        max_retries=0,
    )
    try:
        client.models.list()
    except Exception as exc:  # noqa: BLE001 — translated onto the Learny taxonomy
        _openai_translated(exc)
    finally:
        client.close()


#: The lister for each adapter kind a profile may bind learner keys to.
MODEL_LISTERS: Mapping[str, ModelLister] = {
    "anthropic": _list_anthropic_models,
    "openai-compatible": _list_openai_compatible_models,
}


def probe_key(
    profile: GenerationProfileSettings,
    api_key: str,
    *,
    listers: Mapping[str, ModelLister] = MODEL_LISTERS,
) -> ProbeOutcome:
    """Test ``api_key`` against the host ``profile`` would send it to."""
    lister = listers[profile.kind]
    try:
        lister(api_key, profile.base_url)
    except RequestRejected:
        return ProbeOutcome(ok=False, reason="rejected")
    except RateLimited:
        return ProbeOutcome(ok=False, reason="rate_limited")
    except (Timeout, ProviderUnavailable):
        return ProbeOutcome(ok=False, reason="unavailable")
    except Exception as exc:  # noqa: BLE001 — anything else is reported, never raised
        # The class name only: an SDK message can quote the request back.
        logger.warning(
            "provider key test for profile %s failed unexpectedly (%s)",
            profile.id,
            type(exc).__name__,
        )
        return ProbeOutcome(ok=False, reason="unavailable")
    return ProbeOutcome(ok=True)
