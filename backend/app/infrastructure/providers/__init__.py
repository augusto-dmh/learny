"""Provider-support package shared by the adapters that own provider SDKs.

Holds the Learny-owned provider error taxonomy — the classes a provider adapter
raises instead of vendor SDK/HTTP exception types, so routing and retry decisions
are made on Learny classes rather than by string-matching provider exceptions
(ADR-0020) — and the settings-declared generation profile registry the composition
root resolves the serving chain from. The taxonomy imports the standard library
only and the registry adds pydantic; no provider SDK crosses this boundary.
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
    resolve_generation_profiles,
)

__all__ = [
    "GenerationProfileSettings",
    "ProviderError",
    "ProviderUnavailable",
    "RateLimited",
    "RequestRejected",
    "Timeout",
    "resolve_generation_profiles",
]
