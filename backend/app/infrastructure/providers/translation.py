"""Shared provider-failure translation and usage extraction (TAX-02, design §Reuse).

The public seam every adapter that owns a provider SDK translates through:
:func:`raise_translated` maps one caught SDK/HTTP failure onto the Learny error
taxonomy so callers — the router above the port, the worker tasks — classify on
Learny classes only, and :func:`usage_of` maps a provider usage payload onto the
Learny DTO the debit prices. The SDK-specific exception *types* stay in the
adapter that owns the SDK and enter the shared classifier as inputs, so this
module — like the rest of the providers package — never imports a provider SDK
(httpx's transport families are shared, not provider-specific).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, NoReturn

from app.domain.entities import TokenUsage
from app.infrastructure.providers.errors import (
    ProviderUnavailable,
    RateLimited,
    RequestRejected,
    Timeout,
)


def classify_provider_failure(
    exc: BaseException,
    *,
    timeout_exceptions: Sequence[type[BaseException]] = (),
    unreachable_exceptions: Sequence[type[BaseException]] = (),
) -> BaseException:
    """Return the Learny taxonomy error ``exc`` translates to, else ``exc`` itself.

    Status failures are classified by the status read off the exception, not an
    SDK type: 429 → :class:`RateLimited`, 5xx (including the 529 overload) →
    :class:`ProviderUnavailable`, any other 4xx → :class:`RequestRejected`.
    Timeouts — the builtin, httpx's timeout family, and the adapter-supplied SDK
    timeout types — translate to :class:`Timeout`; an unreachable provider (the
    adapter-supplied connection-error types, without a timeout) to
    :class:`ProviderUnavailable`. A 4xx that logs as a rejection raises
    ``RequestRejected`` by the same read, so the log and the raise can never
    disagree.

    Anything else — an adapter bug, a malformed reply, a shaped test double — is
    not a transport signal and is returned unchanged, so the caller sees exactly
    the raise it has always seen (the port contract is untouched either way: an
    operational failure still raises).
    """
    import httpx  # local import — a transport reference, like in every adapter

    if isinstance(exc, (TimeoutError, httpx.TimeoutException, *timeout_exceptions)):
        return Timeout("the provider call exceeded its wall-clock bound")
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        if status == 429:
            return RateLimited("the provider answered 429")
        if status >= 500:
            return ProviderUnavailable(f"the provider answered {status}")
        if status >= 400:
            return RequestRejected(f"the provider rejected the request ({status})")
    if unreachable_exceptions and isinstance(exc, tuple(unreachable_exceptions)):
        return ProviderUnavailable("the provider could not be reached")
    return exc


def raise_translated(
    exc: BaseException,
    *,
    timeout_exceptions: Sequence[type[BaseException]] = (),
    unreachable_exceptions: Sequence[type[BaseException]] = (),
) -> NoReturn:
    """Re-raise a caught provider failure as its Learny taxonomy class.

    A recognized SDK/HTTP failure is re-raised as the mapped Learny error with
    the original attached as ``__cause__``, so server tracebacks keep the
    provider detail while callers classify on Learny classes only. An
    unrecognized exception is re-raised unchanged and identity-preserved. The
    messages on the translated errors name the failure class and status only,
    never the SDK's exception message, which quotes the rejected request back
    (NFR-SEC-004). The adapter that owns the SDK supplies its own timeout and
    connection-error types — that is the one SDK-specific branch, and it stays
    in the adapter.
    """
    translated = classify_provider_failure(
        exc,
        timeout_exceptions=timeout_exceptions,
        unreachable_exceptions=unreachable_exceptions,
    )
    if translated is exc:
        raise exc
    raise translated from exc


def usage_of(message: Any) -> TokenUsage | None:
    """Map a Claude Messages usage payload onto the Learny usage DTO (design §Reuse).

    The shared extractor for the adapters over the Messages API — the answering
    and quiz adapters read the same payload shape. Input and output counts plus
    the prompt-cache detail (cache-read and cache-creation tokens,
    COST-03/PRICE-02): the cached prefix a teach session re-reads is real spend,
    and the debit prices it at the serving profile's cache prices. A provider
    that reports no cache detail (the fields absent, as on an un-cached call)
    parses to zero, so the debit stays input+output only. A message without
    usage parses to ``None`` → the debit is 0 USD.
    """
    usage = getattr(message, "usage", None)
    if usage is None:
        return None
    return TokenUsage(
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
    )
