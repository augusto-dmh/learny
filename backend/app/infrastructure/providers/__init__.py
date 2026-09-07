"""Provider-support package shared by the adapters that own provider SDKs.

Holds the Learny-owned provider error taxonomy: the classes a provider adapter
raises instead of vendor SDK/HTTP exception types, so routing and retry
decisions are made on Learny classes rather than by string-matching provider
exceptions (ADR-0020). Everything in this package imports the standard library
only — no provider SDK crosses this boundary.
"""

from app.infrastructure.providers.errors import (
    ProviderError,
    ProviderUnavailable,
    RateLimited,
    RequestRejected,
    Timeout,
)

__all__ = [
    "ProviderError",
    "ProviderUnavailable",
    "RateLimited",
    "RequestRejected",
    "Timeout",
]
