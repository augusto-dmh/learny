"""Anthropic quiz adapter taxonomy-translation gate (unit, stubbed client, offline).

Derived from the taxonomy acceptance criteria on the quiz plane: every SDK call
this adapter makes — the batch create behind ``begin_deck``, the poll's
``retrieve`` and paginated ``results`` read, and the two foreground suggest
calls bounded at 30s — translates a recognized transport failure into the
Learny taxonomy class (timeout → ``Timeout``, 429 → ``RateLimited``, 5xx or an
unreachable provider → ``ProviderUnavailable``, other 4xx → ``RequestRejected``)
with the original exception chained as the cause. Anything that is no transport
failure propagates unchanged, so the worker's broad fault handling sees exactly
the raise it has always seen and the retryable-vs-terminal task semantics are
untouched. A per-request batch failure remains a section error, never a
transport translation.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from anthropic import (
    APIConnectionError,
    APITimeoutError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

from app.domain.entities import QuizDeckHandle, QuizSection
from app.infrastructure.providers import (
    ProviderError,
    ProviderUnavailable,
    RateLimited,
    RequestRejected,
    Timeout,
)
from app.infrastructure.quiz.anthropic import AnthropicQuizAdapter

_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


# --- Scripted transport (each SDK call can be handed one error) ------------------


class _ScriptedBatches:
    """``messages.batches`` scripted per call: a scripted error is raised."""

    def __init__(
        self,
        *,
        create_error: Exception | None = None,
        retrieve_error: Exception | None = None,
        results_error: Exception | None = None,
    ) -> None:
        self._create_error = create_error
        self._retrieve_error = retrieve_error
        self._results_error = results_error

    def create(self, *, requests):  # noqa: ANN001, ANN201
        if self._create_error is not None:
            raise self._create_error
        return SimpleNamespace(id="batch_abc", processing_status="in_progress")

    def retrieve(self, batch_id):  # noqa: ANN001, ANN201
        if self._retrieve_error is not None:
            raise self._retrieve_error
        return SimpleNamespace(id=batch_id, processing_status="ended")

    def results(self, batch_id):  # noqa: ANN001, ANN201
        # The SDK streams results lazily, so a fault surfaces on iteration.
        if self._results_error is not None:

            def _gen():
                raise self._results_error
                yield  # pragma: no cover — makes this a generator

            return _gen()
        return iter(())


def _batches_adapter(error: Exception, *, call: str) -> AnthropicQuizAdapter:
    """An adapter whose ``batches.<call>`` raises the stubbed error."""
    batches = _ScriptedBatches(**{f"{call}_error": error})
    client = SimpleNamespace(messages=SimpleNamespace(batches=batches))
    return AnthropicQuizAdapter(
        api_key="sk-test", model="claude-haiku-4-5", max_tokens=1024, client=client
    )


def _suggest_adapter(error: Exception) -> AnthropicQuizAdapter:
    """An adapter whose foreground ``messages.create`` raises the stubbed error."""

    def _raise(**kwargs):  # noqa: ANN001, ANN202
        raise error

    client = SimpleNamespace(messages=SimpleNamespace(create=_raise, batches=_ScriptedBatches()))
    return AnthropicQuizAdapter(
        api_key="sk-test", model="claude-haiku-4-5", max_tokens=1024, client=client
    )


# --- Helpers ---------------------------------------------------------------------


def _status_error(cls: type, status: int) -> Exception:
    """One real SDK status error carrying the given HTTP status."""
    return cls(
        f"Error code: {status} - rejected",
        response=httpx.Response(status, request=_REQUEST),
        body=None,
    )


_ERROR_CASES = [
    pytest.param(lambda: APITimeoutError(request=_REQUEST), Timeout, id="sdk-timeout"),
    pytest.param(lambda: _status_error(RateLimitError, 429), RateLimited, id="429"),
    pytest.param(lambda: _status_error(InternalServerError, 503), ProviderUnavailable, id="503"),
    pytest.param(
        lambda: APIConnectionError(request=_REQUEST), ProviderUnavailable, id="unreachable"
    ),
    pytest.param(lambda: _status_error(BadRequestError, 400), RequestRejected, id="400"),
]

_SECTION = QuizSection(
    section_path=("Unit", "A"),
    anchor="a.xhtml#s",
    title="A",
    chunks=((str(uuid4()), "Text for the chunk."),),
)


# --- Translated entry points -----------------------------------------------------


@pytest.mark.parametrize(("make_error", "expected"), _ERROR_CASES)
def test_begin_deck_translates_batch_create_failures(make_error, expected: type) -> None:
    error = make_error()
    adapter = _batches_adapter(error, call="create")

    with pytest.raises(expected) as excinfo:
        adapter.begin_deck([_SECTION])

    assert isinstance(excinfo.value, ProviderError)
    assert excinfo.value.__cause__ is error


@pytest.mark.parametrize(("make_error", "expected"), _ERROR_CASES)
def test_collect_deck_translates_the_poll_retrieve_failure(make_error, expected: type) -> None:
    error = make_error()
    adapter = _batches_adapter(error, call="retrieve")
    handle = QuizDeckHandle(provider="anthropic", batch_id="batch_abc", payload={})

    with pytest.raises(expected):
        adapter.collect_deck(handle)


def test_collect_deck_translates_a_mid_iteration_results_failure() -> None:
    # The paginated results read is a transport surface too: the batch has been
    # read as ended, then the result pages fail. The poll must see the mapped
    # class, not a raw SDK connection error.
    error = APIConnectionError(request=_REQUEST)
    adapter = _batches_adapter(error, call="results")
    handle = QuizDeckHandle(provider="anthropic", batch_id="batch_abc", payload={})

    with pytest.raises(ProviderUnavailable) as excinfo:
        adapter.collect_deck(handle)

    assert excinfo.value.__cause__ is error


@pytest.mark.parametrize(
    ("make_error", "expected"),
    [
        pytest.param(lambda: APITimeoutError(request=_REQUEST), Timeout, id="sdk-timeout"),
        pytest.param(lambda: _status_error(RateLimitError, 429), RateLimited, id="429"),
    ],
)
def test_suggest_cards_translates_the_bounded_call_failure(make_error, expected: type) -> None:
    error = make_error()
    adapter = _suggest_adapter(error)

    with pytest.raises(expected) as excinfo:
        adapter.suggest_cards(_SECTION, "The key term.", 3)

    assert excinfo.value.__cause__ is error


@pytest.mark.parametrize(
    ("make_error", "expected"),
    [
        pytest.param(
            lambda: _status_error(InternalServerError, 503), ProviderUnavailable, id="503"
        ),
        pytest.param(lambda: _status_error(BadRequestError, 400), RequestRejected, id="400"),
    ],
)
def test_suggest_note_cards_translates_the_bounded_call_failure(make_error, expected: type) -> None:
    error = make_error()
    adapter = _suggest_adapter(error)

    with pytest.raises(expected) as excinfo:
        adapter.suggest_note_cards("A note body.", "", 3)

    assert excinfo.value.__cause__ is error


# --- Non-transport failures propagate unchanged ----------------------------------


@pytest.mark.parametrize("entrypoint", ["begin_deck", "suggest_cards"])
def test_an_unrecognized_failure_propagates_unchanged(entrypoint: str) -> None:
    error = RuntimeError("not a transport signal")
    adapter = (
        _suggest_adapter(error)
        if entrypoint == "suggest_cards"
        else _batches_adapter(error, call="create")
    )

    if entrypoint == "suggest_cards":
        with pytest.raises(RuntimeError) as excinfo:
            adapter.suggest_cards(_SECTION, "The key term.", 3)
    else:
        with pytest.raises(RuntimeError) as excinfo:
            adapter.begin_deck([_SECTION])

    assert excinfo.value is error
