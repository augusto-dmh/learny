"""Anthropic adapter taxonomy-translation gate (unit, stubbed client, no network).

Derived from the taxonomy acceptance criteria: a provider call that exceeds the
adapter's wall-clock bound raises the Learny ``Timeout``; 429 raises
``RateLimited``; 5xx, the 529 overload, and an unreachable provider raise
``ProviderUnavailable``; any other 4xx raises ``RequestRejected`` — each
translated inside the adapter that owns the SDK, on **both** call paths, with
the original SDK exception chained as the cause. The translation is
routing metadata, not a new user-facing surface: an exception that is no
recognized transport failure propagates unchanged and identity-preserved, so
the application service's error envelope maps it exactly as before, and a
translated 4xx rejection still emits the same redacted log line (shape, status,
request id — never the request body).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import httpx
import pytest
from anthropic import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    OverloadedError,
    RateLimitError,
)

from app.domain.entities import MODE_ANSWER
from app.infrastructure.answering.anthropic import AnthropicGenerationAdapter
from app.infrastructure.providers import (
    ProviderError,
    ProviderUnavailable,
    RateLimited,
    RequestRejected,
    Timeout,
)

_MODEL = "claude-sonnet-4-6"
_LOGGER = "app.infrastructure.answering.anthropic"
_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
# Content the SDK's exception message quotes back and the log line must never carry.
_SECRET_SNIPPET = "the tides follow the moon in a way no log should repeat"


# --- Stubbed transport -----------------------------------------------------------


class _RaisingMessagesResource:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def create(self, **kwargs: object) -> object:
        raise self._error

    def stream(self, **kwargs: object) -> object:
        raise self._error


class _RaisingClient:
    def __init__(self, error: Exception) -> None:
        self.messages = _RaisingMessagesResource(error)


def _adapter(error: Exception) -> AnthropicGenerationAdapter:
    return AnthropicGenerationAdapter(
        api_key="unused-fake",
        model=_MODEL,
        max_tokens=1024,
        client=_RaisingClient(error),
    )


def _drive(adapter: AnthropicGenerationAdapter, *, stream: bool) -> Iterator[object]:
    if stream:
        return adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=[])

    # The buffered path raises from the call itself; wrap so both paths are
    # consumed the same way.
    def _call() -> Iterator[object]:
        yield adapter.generate(mode=MODE_ANSWER, message="q", evidence=[])

    return _call()


def _status_error(cls: type, status: int) -> object:
    """One real SDK status error carrying the given HTTP status."""
    return cls(
        f"Error code: {status} - {{'error': {{'message': '{_SECRET_SNIPPET}'}}}}",
        response=httpx.Response(status, request=_REQUEST),
        body=None,
    )


# --- Each SDK/HTTP failure class maps to the right Learny type (both paths) ------

_ERROR_CASES = [
    pytest.param(lambda: APITimeoutError(request=_REQUEST), Timeout, id="sdk-timeout"),
    pytest.param(lambda: TimeoutError(), Timeout, id="builtin-timeout"),
    pytest.param(lambda: httpx.ReadTimeout("timed out"), Timeout, id="httpx-timeout"),
    pytest.param(lambda: _status_error(RateLimitError, 429), RateLimited, id="429"),
    pytest.param(lambda: _status_error(InternalServerError, 500), ProviderUnavailable, id="500"),
    pytest.param(
        lambda: _status_error(OverloadedError, 529), ProviderUnavailable, id="529-overloaded"
    ),
    pytest.param(
        lambda: APIConnectionError(request=_REQUEST), ProviderUnavailable, id="unreachable"
    ),
    pytest.param(lambda: _status_error(BadRequestError, 400), RequestRejected, id="400"),
    pytest.param(lambda: _status_error(AuthenticationError, 401), RequestRejected, id="401"),
]


@pytest.mark.parametrize("stream", [False, True], ids=["buffered", "stream"])
@pytest.mark.parametrize(("make_error", "expected"), _ERROR_CASES)
def test_each_transport_failure_raises_its_mapped_learner_type(
    make_error, expected: type, stream: bool
) -> None:
    error = make_error()
    adapter = _adapter(error)  # type: ignore[arg-type]

    with pytest.raises(expected) as excinfo:
        list(_drive(adapter, stream=stream))

    assert isinstance(excinfo.value, ProviderError)
    assert excinfo.value.__cause__ is error


# --- Unrecognized failures propagate unchanged (envelope contract unchanged) -----


@pytest.mark.parametrize("stream", [False, True], ids=["buffered", "stream"])
def test_an_unrecognized_failure_propagates_unchanged(stream: bool) -> None:
    error = RuntimeError("not a transport signal")
    adapter = _adapter(error)

    with pytest.raises(RuntimeError) as excinfo:
        list(_drive(adapter, stream=stream))

    assert excinfo.value is error


# --- The redaction culture survives the translation ------------------------------


def test_a_translated_rejection_still_logs_the_redacted_line(caplog) -> None:  # noqa: ANN001
    adapter = _adapter(_status_error(BadRequestError, 400))

    with (
        caplog.at_level(logging.WARNING, logger=_LOGGER),
        pytest.raises(RequestRejected) as excinfo,
    ):
        adapter.generate(mode=MODE_ANSWER, message="q", evidence=[])

    lines = [r.getMessage() for r in caplog.records if r.name == _LOGGER]
    assert len(lines) == 1
    assert "request_shape=citations" in lines[0]
    assert "status=400" in lines[0]
    assert _SECRET_SNIPPET not in lines[0]
    # The translated error itself names the class and status, never the SDK message.
    assert _SECRET_SNIPPET not in str(excinfo.value)
