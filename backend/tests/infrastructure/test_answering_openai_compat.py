"""OpenAI-compatible adapter contract (unit, stubbed transport, no network).

Derived from the economy-adapter acceptance criteria (ECON-01..03, ECON-05,
ECON-06, TAX-02/03): the adapter implements ``GenerationPort`` with Learny DTOs
in and out (ECON-01); it requests prompt-id citations — documents numbered
``[n]`` in evidence order, the model citing ``[^n]`` — and the ``[^n]`` markers
parse to chunk-level citation attribution the existing grounding intersection
verifies, with no fabricated character offsets (ECON-02); a whole-reply sentinel
is the not-found outcome while an embedded occurrence stays prose; usage maps
``prompt_tokens``/``completion_tokens`` plus the cached-token detail the host
reports, and an absent usage parses to ``None`` → the debit is 0 (ECON-03);
effort values are accepted and never sent — no effort/thinking key exists in the
captured request body (ECON-05); and every SDK/HTTP transport failure translates
to its Learny taxonomy class inside this adapter, with unrecognized failures
propagating unchanged so the application's error envelope is exactly today's
(TAX-02/03). The SDK is imported lazily and every test drives a fake client —
no test opens a network socket (ECON-06).
"""

from __future__ import annotations

import ast
import inspect
import logging
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

from app.application.grounding import ground
from app.application.streaming import hold_back_deltas
from app.domain.entities import (
    CITATION_MARKER_RE,
    MODE_ANSWER,
    AnswerCompleted,
    AnswerTextDelta,
    Evidence,
    GeneratedAnswer,
    TokenUsage,
)
from app.domain.ports import GenerationPort
from app.infrastructure.answering import openai_compat as compat_module
from app.infrastructure.answering.openai_compat import OpenAICompatibleGenerationAdapter
from app.infrastructure.answering.prompts import SENTINEL
from app.infrastructure.providers import (
    ProviderError,
    ProviderUnavailable,
    RateLimited,
    RequestRejected,
    Timeout,
)

_MODEL = "zai-org/glm-5.3-flash"
_MAX_TOKENS = 2048
_BASE_URL = "https://api.fireworks.ai/inference/v1"
_LOGGER = "app.infrastructure.answering.openai_compat"
_REQUEST = httpx.Request("POST", f"{_BASE_URL}/chat/completions")
# Content the SDK's exception message quotes back and the log line must never carry.
_SECRET_SNIPPET = "the tides follow the moon in a way no log should repeat"


# --- Stubbed transport (ECON-06: no socket is ever opened) ------------------------


class _FakeUsage:
    def __init__(self, *, prompt: int = 42, completion: int = 7, cached: int | None = None) -> None:
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.prompt_tokens_details = _FakeTokenDetails(cached) if cached is not None else None


class _FakeTokenDetails:
    def __init__(self, cached: int) -> None:
        self.cached_tokens = cached


# Distinguishes "no usage argument" (a populated usage object) from an explicit
# ``usage=None`` (the absent-usage shape a host that reports none produces).
_UNSET: Any = object()


class _FakeCompletion:
    """A buffered chat-completion reply: one choice whose message carries text."""

    def __init__(self, content: str, usage: Any = _UNSET) -> None:
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage() if usage is _UNSET else usage


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeResponseMessage(content)


class _FakeResponseMessage:
    def __init__(self, content: str) -> None:
        self.content = content


# --- Stream shapes -----------------------------------------------------------------


class _FakeDelta:
    def __init__(self, content: str | None) -> None:
        self.content = content


class _FakeDeltaChoice:
    def __init__(self, content: str | None) -> None:
        self.delta = _FakeDelta(content)


class _FakeStreamChunk:
    """One SSE chunk: a delta choice and/or a usage report (the final one)."""

    def __init__(
        self,
        *,
        content: str | None = None,
        usage: Any = None,
        with_choices: bool = True,
    ) -> None:
        self.choices = [_FakeDeltaChoice(content)] if with_choices else []
        self.usage = usage


class _FakeStream:
    """Fake SDK stream: iterates chunks, remembers close (early-cancel sensor).

    A chunk that is an ``Exception`` is raised mid-iteration, so a case can put
    a transport failure after the first delta.
    """

    def __init__(self, chunks: list[object]) -> None:
        self._chunks = chunks
        self.closed = False

    def __iter__(self) -> Iterator[object]:
        return self._generate()

    def _generate(self) -> Iterator[object]:
        for chunk in self._chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk

    def close(self) -> None:
        self.closed = True


class _RecordingCompletions:
    """The ``chat.completions`` resource: records every create call.

    The outcome is returned as-is unless it is an exception, which is raised —
    so one fake serves the buffered reply, an iterable of stream chunks, and
    every transport failure the taxonomy matrix drives through either path.
    """

    def __init__(self, outcome: object) -> None:
        self._outcome = outcome
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


class _FakeClient:
    def __init__(self, outcome: object) -> None:
        self.chat = _FakeChatResource(outcome)


class _FakeChatResource:
    def __init__(self, outcome: object) -> None:
        self.completions = _RecordingCompletions(outcome)


def _adapter(
    outcome: object, *, effort_ask: str = "medium", effort_teach: str = "medium"
) -> tuple[OpenAICompatibleGenerationAdapter, _FakeClient]:
    client = _FakeClient(outcome)
    adapter = OpenAICompatibleGenerationAdapter(
        api_key="unused-fake",
        model=_MODEL,
        base_url=_BASE_URL,
        max_tokens=_MAX_TOKENS,
        effort_ask=effort_ask,
        effort_teach=effort_teach,
        client=client,
    )
    return adapter, client


def _evidence(snippet: str) -> Evidence:
    return Evidence(
        chunk_id=uuid4(),
        source_id=uuid4(),
        section_path=("Chapter 1", "Sec"),
        anchor=f"ch1.xhtml#{snippet}",
        page_span=None,
        snippet=snippet,
        score=0.5,
    )


def _generate(adapter: OpenAICompatibleGenerationAdapter, evidence: list[Evidence]) -> object:
    return adapter.generate(mode=MODE_ANSWER, message="What is X?", evidence=evidence)


# --- ECON-01/02: the request asks for prompt-id citations -------------------------


def test_request_sends_the_frozen_prompt_numbered_documents_and_the_question() -> None:
    first, second = _evidence("alpha"), _evidence("beta")
    adapter, client = _adapter(_FakeCompletion("ok"))

    adapter.generate(mode=MODE_ANSWER, message="What is X?", evidence=[first, second])

    call = client.chat.completions.calls[0]
    assert call["model"] == _MODEL
    assert call["max_tokens"] == _MAX_TOKENS
    messages = call["messages"]
    assert messages[0]["role"] == "system"
    # The frozen system prompt carries the Learny not-found sentinel and the
    # ``[^n]`` marker convention — the prompt-cited citation contract (ECON-02).
    assert SENTINEL in messages[0]["content"]
    assert "[^1]" in messages[0]["content"]
    user = messages[-1]
    assert user["role"] == "user"
    # One numbered document per evidence chunk, in evidence order, with the exact
    # snippet body the marker's number resolves against, then the question.
    assert "[1]\nalpha" in user["content"]
    assert "[2]\nbeta" in user["content"]
    assert user["content"].index("[1]\nalpha") < user["content"].index("[2]\nbeta")
    assert user["content"].endswith("What is X?")


def test_history_renders_as_alternating_messages_with_markers_stripped() -> None:
    from app.domain.entities import HistoryTurn

    adapter, client = _adapter(_FakeCompletion("ok"))

    adapter.generate(
        mode=MODE_ANSWER,
        message="follow-up",
        evidence=[],
        history=[
            HistoryTurn(message="first question", response_text="first answer[^1]"),
        ],
    )

    messages = client.chat.completions.calls[0]["messages"]
    assert messages[1] == {"role": "user", "content": "first question"}
    # A stored answer's marks are Learny's, not the model's: replaying them would
    # teach a token the model cannot number correctly (the Anthropic discipline).
    assert messages[2] == {"role": "assistant", "content": "first answer"}


def test_adapter_is_a_generation_port_and_reports_its_model_without_a_call() -> None:
    adapter, client = _adapter(_FakeCompletion("ok"))

    assert isinstance(adapter, GenerationPort)
    assert adapter.model == _MODEL
    assert client.chat.completions.calls == []


# --- ECON-02: markers parse to chunk-level attribution; grounding verifies --------


def test_markers_parse_to_chunk_ids_in_first_occurrence_order_without_offsets() -> None:
    first, second = _evidence("alpha"), _evidence("beta")
    adapter, _ = _adapter(_FakeCompletion("Claim two [^2]. Claim one [^1]. Again [^2]."))

    answer = _generate(adapter, [first, second])

    assert isinstance(answer, GeneratedAnswer)
    # First-occurrence order, deduped: marker n names evidence[n-1]'s chunk.
    assert answer.cited_chunk_ids == (second.chunk_id, first.chunk_id)
    assert answer.found is True
    # The text stays exactly as the model wrote it — markers and all.
    assert answer.text == "Claim two [^2]. Claim one [^1]. Again [^2]."
    # No fabricated character offsets: a prompt-cited reply cannot honestly place
    # a span, so none is reported (the chunk attribution is the whole claim).
    assert answer.spans == ()
    assert answer.model == _MODEL


def test_an_out_of_range_marker_names_no_chunk() -> None:
    first = _evidence("alpha")
    adapter, _ = _adapter(_FakeCompletion("An answer[^9]."))

    answer = _generate(adapter, [first])

    assert isinstance(answer, GeneratedAnswer)
    assert answer.cited_chunk_ids == ()
    assert CITATION_MARKER_RE.sub("", answer.text).strip() == "An answer."


def test_grounding_keeps_only_the_cited_chunks_in_evidence_order() -> None:
    first, second, third = _evidence("alpha"), _evidence("beta"), _evidence("gamma")
    adapter, _ = _adapter(_FakeCompletion("Cites the second [^2] and first [^1]."))

    answer = _generate(adapter, [first, second, third])

    grounded = ground(answer, [first, second, third])
    assert grounded is not None
    text, citations = grounded
    assert text == answer.text
    # Grounding keeps the cited chunks in evidence-rank order and drops the rest.
    assert [item.chunk_id for item in citations] == [first.chunk_id, second.chunk_id]
    assert third.chunk_id not in {item.chunk_id for item in citations}


def test_a_whole_reply_sentinel_is_the_not_found_outcome() -> None:
    adapter, _ = _adapter(_FakeCompletion(f"  {SENTINEL}  "))

    answer = _generate(adapter, [_evidence("alpha")])

    assert isinstance(answer, GeneratedAnswer)
    assert answer.found is False
    assert answer.text == ""
    assert answer.cited_chunk_ids == ()
    assert answer.spans == ()


def test_an_embedded_sentinel_stays_prose() -> None:
    adapter, _ = _adapter(_FakeCompletion(f"The phrase {SENTINEL} appears in the book [^1]."))

    answer = _generate(adapter, [_evidence("alpha")])

    assert isinstance(answer, GeneratedAnswer)
    assert answer.found is True
    assert answer.text == f"The phrase {SENTINEL} appears in the book [^1]."


# --- ECON-03: usage mapping --------------------------------------------------------


def test_usage_maps_prompt_completion_and_cached_tokens() -> None:
    adapter, _ = _adapter(
        _FakeCompletion("ok", usage=_FakeUsage(prompt=100, completion=20, cached=60))
    )

    answer = _generate(adapter, [_evidence("alpha")])

    assert isinstance(answer, GeneratedAnswer)
    assert answer.usage == TokenUsage(
        input_tokens=100, output_tokens=20, cache_read_input_tokens=60
    )


def test_usage_without_cache_detail_is_input_plus_output_only() -> None:
    adapter, _ = _adapter(_FakeCompletion("ok", usage=_FakeUsage(prompt=10, completion=5)))

    answer = _generate(adapter, [_evidence("alpha")])

    assert isinstance(answer, GeneratedAnswer)
    assert answer.usage == TokenUsage(input_tokens=10, output_tokens=5)


def test_absent_usage_parses_to_none_so_the_debit_is_zero() -> None:
    adapter, _ = _adapter(_FakeCompletion("ok", usage=None))

    answer = _generate(adapter, [_evidence("alpha")])

    assert isinstance(answer, GeneratedAnswer)
    assert answer.usage is None


# --- ECON-05: effort is accepted and never sent ------------------------------------


def test_effort_values_are_never_sent_in_the_request_body() -> None:
    adapter, client = _adapter(_FakeCompletion("ok"), effort_ask="max", effort_teach="xhigh")

    adapter.generate(mode=MODE_ANSWER, message="q", evidence=[_evidence("alpha")])

    call = client.chat.completions.calls[0]
    for key in ("effort", "effort_ask", "effort_teach", "thinking", "reasoning_effort"):
        assert key not in call


# --- TAX-02: each transport failure raises its mapped Learny type ------------------


def _status_error(cls: type, status: int) -> object:
    """One real SDK status error carrying the given HTTP status."""
    return cls(
        f"Error code: {status} - {{'error': {{'message': '{_SECRET_SNIPPET}'}}}}",
        response=httpx.Response(status, request=_REQUEST),
        body=None,
    )


_ERROR_CASES = [
    pytest.param(lambda: APITimeoutError(request=_REQUEST), Timeout, id="sdk-timeout"),
    pytest.param(lambda: TimeoutError(), Timeout, id="builtin-timeout"),
    pytest.param(lambda: httpx.ReadTimeout("timed out"), Timeout, id="httpx-timeout"),
    pytest.param(lambda: _status_error(RateLimitError, 429), RateLimited, id="429"),
    pytest.param(lambda: _status_error(InternalServerError, 500), ProviderUnavailable, id="500"),
    pytest.param(lambda: _status_error(APIStatusError, 503), ProviderUnavailable, id="503"),
    pytest.param(lambda: _status_error(APIStatusError, 529), ProviderUnavailable, id="529"),
    pytest.param(
        lambda: APIConnectionError(request=_REQUEST), ProviderUnavailable, id="unreachable"
    ),
    pytest.param(lambda: _status_error(BadRequestError, 400), RequestRejected, id="400"),
    pytest.param(lambda: _status_error(AuthenticationError, 401), RequestRejected, id="401"),
]


@pytest.mark.parametrize(("make_error", "expected"), _ERROR_CASES)
def test_each_transport_failure_raises_its_mapped_learny_type(make_error, expected: type) -> None:
    error = make_error()
    adapter, _ = _adapter(error)  # type: ignore[arg-type]

    with pytest.raises(expected) as excinfo:
        adapter.generate(mode=MODE_ANSWER, message="q", evidence=[])

    assert isinstance(excinfo.value, ProviderError)
    assert excinfo.value.__cause__ is error


def test_an_unrecognized_failure_propagates_unchanged() -> None:
    error = RuntimeError("not a transport signal")
    adapter, _ = _adapter(error)

    with pytest.raises(RuntimeError) as excinfo:
        adapter.generate(mode=MODE_ANSWER, message="q", evidence=[])

    assert excinfo.value is error


# --- The redaction culture survives the translation --------------------------------


def test_a_translated_rejection_logs_the_redacted_line(caplog) -> None:  # noqa: ANN001
    adapter, _ = _adapter(_status_error(BadRequestError, 400))

    with (
        caplog.at_level(logging.WARNING, logger=_LOGGER),
        pytest.raises(RequestRejected) as excinfo,
    ):
        adapter.generate(mode=MODE_ANSWER, message="q", evidence=[_evidence("alpha")])

    lines = [r.getMessage() for r in caplog.records if r.name == _LOGGER]
    assert len(lines) == 1
    assert "request_shape=prompt-cited" in lines[0]
    assert "status=400" in lines[0]
    # Never the request body, the documents, or the SDK's echoed message.
    assert _SECRET_SNIPPET not in lines[0]
    assert "alpha" not in lines[0]
    assert _SECRET_SNIPPET not in str(excinfo.value)


def test_a_successful_call_logs_one_content_free_line(caplog) -> None:  # noqa: ANN001
    adapter, _ = _adapter(
        _FakeCompletion(
            "Grounded prose [^1].", usage=_FakeUsage(prompt=100, completion=20, cached=60)
        )
    )

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        answer = _generate(adapter, [_evidence("alpha")])

    assert isinstance(answer, GeneratedAnswer)
    lines = [r.getMessage() for r in caplog.records if r.name == _LOGGER]
    assert len(lines) == 1
    assert f"model={_MODEL}" in lines[0]
    assert "input_tokens=100" in lines[0]
    assert "output_tokens=20" in lines[0]
    assert "cached_input_tokens=60" in lines[0]
    assert "found=True" in lines[0]
    # Content-free: no answer text, no document body on the line.
    assert "Grounded prose" not in lines[0]
    assert "alpha" not in lines[0]


# --- The streaming contract (the port's stream rule, ROUTE-04 fail-over candidacy) -
#
# Derived from the port contract and the streaming acceptance criteria: zero or
# more raw text deltas (markers ride inside them exactly as the Citations
# adapter streams its block text), then exactly ONE authoritative
# ``AnswerCompleted`` whose answer is parsed from the accumulated text — so a
# marker split across SSE chunks still parses. A failure before the first delta
# raises the translated error (what makes the adapter a legal router fail-over
# candidate); after a delta is out the failure still translates but can no
# longer be retried by the router. The sentinel hold-back that keeps
# ``NOT_FOUND_IN_SOURCE`` from ever reaching a client lives in the application
# stream path and is provider-independent — proven here over this adapter's
# stream, exactly as the suite does for the Anthropic one.


def _stream_chunks(*, pieces: list[str], usage: Any = _UNSET) -> list[object]:
    """Content deltas followed by one choice-less usage chunk (the host shape)."""
    chunks: list[object] = [_FakeStreamChunk(content=piece) for piece in pieces if piece]
    if usage is not _UNSET:
        chunks.append(_FakeStreamChunk(with_choices=False, usage=usage))
    return chunks


def _collect(events: Iterator[object]) -> list[object]:
    return list(events)


def test_stream_yields_raw_deltas_then_exactly_one_completed_with_parsed_answer() -> None:
    first = _evidence("alpha")
    adapter, _ = _adapter(
        _FakeStream(
            _stream_chunks(
                pieces=["Grounded", " text[^1]", "."],
                usage=_FakeUsage(prompt=100, completion=20, cached=60),
            )
        )
    )

    events = _collect(adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=[first]))

    deltas = [event for event in events if isinstance(event, AnswerTextDelta)]
    completed = [event for event in events if isinstance(event, AnswerCompleted)]
    assert [delta.text for delta in deltas] == ["Grounded", " text[^1]", "."]
    # Exactly one terminal event, always last, authoritative.
    assert len(completed) == 1
    assert events[-1] is completed[0]
    answer = completed[0].answer
    assert answer.text == "Grounded text[^1]."
    assert answer.found is True
    assert answer.cited_chunk_ids == (first.chunk_id,)
    assert answer.usage == TokenUsage(
        input_tokens=100, output_tokens=20, cache_read_input_tokens=60
    )


def test_a_marker_split_across_deltas_parses_from_the_accumulated_text() -> None:
    first = _evidence("alpha")
    adapter, _ = _adapter(_FakeStream(_stream_chunks(pieces=["see [^", "1] done"])))

    events = _collect(adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=[first]))

    completed = [event for event in events if isinstance(event, AnswerCompleted)]
    assert len(completed) == 1
    assert completed[0].answer.text == "see [^1] done"
    assert completed[0].answer.cited_chunk_ids == (first.chunk_id,)


def test_zero_deltas_still_complete_exactly_once() -> None:
    adapter, _ = _adapter(_FakeStream([_FakeStreamChunk(content="")]))

    events = _collect(
        adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=[_evidence("a")])
    )

    assert len(events) == 1
    assert isinstance(events[0], AnswerCompleted)


def test_a_sentinel_reply_streams_raw_and_completes_not_found() -> None:
    # Raw passthrough parity: the sentinel text rides the deltas exactly as the
    # Citations adapter's stream would carry it — the router treats a sentinel
    # first delta as a commit, and the application hold-back does the leaking.
    adapter, _ = _adapter(_FakeStream(_stream_chunks(pieces=[SENTINEL[:4], SENTINEL[4:]])))

    events = _collect(
        adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=[_evidence("a")])
    )

    deltas = [event.text for event in events if isinstance(event, AnswerTextDelta)]
    assert deltas == [SENTINEL[:4], SENTINEL[4:]]
    completed = [event for event in events if isinstance(event, AnswerCompleted)]
    assert len(completed) == 1
    assert completed[0].answer.found is False
    assert completed[0].answer.text == ""


def test_the_sentinel_never_leaks_to_the_client_as_a_delta() -> None:
    # The provider-independent hold-back (application/streaming.py) is what keeps
    # the sentinel from the client: over this adapter's stream, nothing at all is
    # presented and the authoritative answer is the not-found outcome.
    adapter, _ = _adapter(_FakeStream(_stream_chunks(pieces=[SENTINEL])))

    generator = hold_back_deltas(
        adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=[_evidence("a")])
    )
    presented: list[object] = []
    answer = None
    try:
        while True:
            presented.append(next(generator))
    except StopIteration as stop:  # the generator returns the authoritative answer
        answer = stop.value

    assert presented == []
    assert answer is not None
    assert answer.found is False
    assert answer.text == ""


def test_the_stream_request_matches_the_buffered_shape_and_asks_for_usage() -> None:
    buffered_adapter, buffered_client = _adapter(_FakeCompletion("ok"))
    stream_adapter, stream_client = _adapter(_FakeStream(_stream_chunks(pieces=["ok"])))

    buffered_adapter.generate(mode=MODE_ANSWER, message="q", evidence=[_evidence("a")])
    _collect(
        stream_adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=[_evidence("a")])
    )

    buffered_call = buffered_client.chat.completions.calls[0]
    stream_call = stream_client.chat.completions.calls[0]
    # One request shape for both paths — only the streaming half differs.
    assert stream_call["messages"] == buffered_call["messages"]
    assert stream_call["model"] == buffered_call["model"]
    assert stream_call["max_tokens"] == buffered_call["max_tokens"]
    assert stream_call["stream"] is True
    # Usage rides the final chunk only when the request asks for it.
    assert stream_call["stream_options"] == {"include_usage": True}
    # A stream proves progress as frames arrive: no wall-clock bound here, and
    # never an effort/thinking parameter (ECON-05 on both paths).
    assert "timeout" not in stream_call
    for key in ("effort", "effort_ask", "effort_teach", "thinking", "reasoning_effort"):
        assert key not in stream_call


def test_stream_usage_absent_parses_to_none() -> None:
    adapter, _ = _adapter(_FakeStream(_stream_chunks(pieces=["ok"], usage=None)))

    events = _collect(
        adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=[_evidence("a")])
    )

    completed = [event for event in events if isinstance(event, AnswerCompleted)]
    assert len(completed) == 1
    assert completed[0].answer.usage is None


def test_closing_the_stream_early_closes_the_underlying_stream() -> None:
    stream = _FakeStream(_stream_chunks(pieces=["one", "two"]))
    adapter, _ = _adapter(stream)

    generator = adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=[_evidence("a")])
    next(generator)  # one delta out, then the consumer walks away
    generator.close()

    # A client disconnect must not leak a provider generation (the port's
    # early-cancel contract).
    assert stream.closed is True


@pytest.mark.parametrize(("make_error", "expected"), _ERROR_CASES)
def test_a_pre_delta_stream_failure_raises_its_mapped_learny_type(
    make_error, expected: type
) -> None:
    error = make_error()
    adapter, _ = _adapter(error)  # type: ignore[arg-type]

    # The request opens lazily: the raise surfaces on first iteration, before
    # any delta — exactly the window in which the router may fail over.
    with pytest.raises(expected) as excinfo:
        _collect(adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=[]))

    assert isinstance(excinfo.value, ProviderError)
    assert excinfo.value.__cause__ is error


def test_an_error_after_the_first_delta_propagates_translated_exactly_once() -> None:
    error = _status_error(RateLimitError, 429)
    adapter, _ = _adapter(_FakeStream([_FakeStreamChunk(content="first"), error]))

    events: list[object] = []
    with pytest.raises(RateLimited) as excinfo:
        for event in adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=[]):
            events.append(event)

    # The reader saw the delta; the failure surfaced once, translated, chained.
    assert [event.text for event in events if isinstance(event, AnswerTextDelta)] == ["first"]
    assert not any(isinstance(event, AnswerCompleted) for event in events)
    assert excinfo.value.__cause__ is error


def test_an_unrecognized_stream_failure_propagates_unchanged() -> None:
    error = RuntimeError("not a transport signal")
    adapter, _ = _adapter(error)

    with pytest.raises(RuntimeError) as excinfo:
        _collect(adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=[]))

    assert excinfo.value is error


# --- ECON-06: the SDK import stays lazy (fitness boundary, mirrored) ---------------


def test_adapter_module_imports_no_sdk_at_module_level() -> None:
    # The openai SDK is imported lazily inside _get_client only, never at load.
    tree = ast.parse(inspect.getsource(compat_module))
    top_level: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level.add(node.module.split(".")[0])

    assert "openai" not in top_level
    assert "httpx" not in top_level
