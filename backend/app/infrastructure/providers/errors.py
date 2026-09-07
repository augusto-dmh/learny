"""Learny-owned provider error taxonomy (stdlib-only).

Provider adapters translate SDK and HTTP failures **inside their own module** and
raise these classes, so callers — the router above the port, the worker tasks —
classify failures without importing a vendor exception shape. The port contract
is unchanged: an operational failure still raises; these classes only name *which*
failure it was.

The retryability contract each subclass docstring states:

- :class:`Timeout` and :class:`ProviderUnavailable` are retryable across providers.
- :class:`RateLimited` earns one same-provider backoff retry, then may cross.
- :class:`RequestRejected` is never retried blindly across providers.
"""

from __future__ import annotations


class ProviderError(Exception):
    """Base class for the Learny-owned provider failure taxonomy.

    Raised by the adapter that owns the provider SDK after it has translated a
    transport-level failure; the original SDK/HTTP exception rides along as
    ``__cause__`` so server logs keep the provider detail while callers see only
    the Learny class.
    """


class Timeout(ProviderError):
    """The provider call exceeded the adapter's wall-clock bound.

    Retryable across providers: a slow or hung call is a transport condition, not
    a verdict on the request, so a later attempt may be served by any provider.
    """


class RateLimited(ProviderError):
    """The provider answered 429 — it asked us to slow down.

    One same-provider backoff retry is earned first (the throttle is usually
    measured in seconds and the same provider may serve the retry), and after
    that backoff the retry may cross to another provider.
    """


class ProviderUnavailable(ProviderError):
    """The provider is failing or unreachable: 5xx, overloaded, connection refused.

    Retryable across providers: an outage or overload is a reason to leave, not
    to wait, so a later attempt may be served by any provider.
    """


class RequestRejected(ProviderError):
    """The provider refused the request itself: any other 4xx (shape, auth, validation).

    Never retried blindly across providers: the request that was sent is at
    fault, so handing the same request to another provider would earn the same
    rejection — only an adapter that builds a genuinely different request shape
    may be tried.
    """
