"""Provider-support package shared by the adapters that own provider SDKs.

Holds the Learny-owned provider error taxonomy — the classes a provider adapter
raises instead of vendor SDK/HTTP exception types, so routing and retry decisions
are made on Learny classes rather than by string-matching provider exceptions
(ADR-0020) —, the shared translation and usage-extraction helpers the adapters
translate through (TAX-02), and the settings-declared generation profile registry
the composition root resolves the serving chain from. The taxonomy imports the
standard library only, translation adds the domain usage DTO, and the registry
adds pydantic; no provider SDK crosses this boundary — each adapter keeps its own
SDK's exception types and field names and hands the shared helpers its inputs.
"""

from app.infrastructure.providers.errors import (
    ProviderError,
    ProviderUnavailable,
    RateLimited,
    RequestRejected,
    Timeout,
)
from app.infrastructure.providers.profiles import (
    GenerationProfileSettings,
    LearnerProfile,
    learner_catalog,
    resolve_generation_profiles,
    resolve_serving_profile,
)
from app.infrastructure.providers.translation import (
    classify_provider_failure,
    raise_translated,
    usage_of,
)

__all__ = [
    "GenerationProfileSettings",
    "LearnerProfile",
    "ProviderError",
    "ProviderUnavailable",
    "RateLimited",
    "RequestRejected",
    "Timeout",
    "classify_provider_failure",
    "learner_catalog",
    "raise_translated",
    "resolve_generation_profiles",
    "resolve_serving_profile",
    "usage_of",
]
