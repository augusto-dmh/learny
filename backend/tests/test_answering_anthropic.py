"""A2 gate — Anthropic cited-answer adapter (unit, fake client, no network).

Derived from spec ACs GEN-04..GEN-08 and the listed edge cases: the request sends
one plain-text citations-enabled document per evidence chunk in evidence order
plus the frozen system prompt and the question; the response's ``document_index``
citations resolve back to ``chunk_id``s (never ``document_title``) in
first-occurrence order and deduped; a whole-reply sentinel maps to ``found=False``
while an embedded occurrence stays prose; a ``max_tokens`` stop reason returns the
partial answer; ``model`` is readable without a call; the SDK is imported lazily
(never at module load); and an adapter-shaped out-of-set citation collapses to the
not-found outcome through the shared grounding guard.
"""

from __future__ import annotations

import ast
import inspect
import json
import logging
import os
import re
from uuid import uuid4

import pytest

from app.application.grounding import ground, ground_spans
from app.domain.entities import (
    MODE_ANSWER,
    MODE_TEACH,
    TUTOR_CARD_QUESTION,
    TUTOR_DONT_KNOW_MESSAGE,
    TUTOR_JUST_EXPLAIN_MESSAGE,
    TUTOR_OPENING_MESSAGE,
    AnswerCompleted,
    AnswerReasoningDelta,
    AnswerTextDelta,
    Evidence,
    HistoryTurn,
)
from app.domain.ports import GenerationPort
from app.infrastructure.answering import anthropic as anthropic_module
from app.infrastructure.answering.anthropic import AnthropicGenerationAdapter
from app.infrastructure.answering.prompts import (
    ANSWER_SYSTEM_PROMPT,
    SENTINEL,
    TEACHING_SYSTEM_PROMPT,
)

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 1024
# Deliberately not the settings default, so an adapter that hard-coded the default
# effort instead of spending the configured one fails these assertions.
_EFFORT = "high"
_SUMMARIZED_THINKING = {"type": "adaptive", "display": "summarized"}
_LOGGER = "app.infrastructure.answering.anthropic"


# --- Fake Anthropic client (records the create call, returns a canned message) ---


class _FakeCitation:
    """A ``char_location`` citation. Offsets default to absent (reported as ``None``)."""

    def __init__(
        self,
        document_index: int,
        *,
        document_title: str = "",
        cited_text: str = "cited",
        start_char_index: int | None = None,
        end_char_index: int | None = None,
    ) -> None:
        self.type = "char_location"
        self.document_index = document_index
        self.cited_text = cited_text
        self.document_title = document_title
        self.start_char_index = start_char_index
        self.end_char_index = end_char_index


class _FakeTextBlock:
    def __init__(self, text: str, citations: list[_FakeCitation] | None = None) -> None:
        self.type = "text"
        self.text = text
        self.citations = citations


class _FakeThinkingBlock:
    """A summarized-thinking block: the model's reasoning, never the answer."""

    def __init__(self, thinking: str) -> None:
        self.type = "thinking"
        self.thinking = thinking


class _FakeUsage:
    def __init__(self) -> None:
        self.input_tokens = 42
        self.output_tokens = 7
        self.cache_read_input_tokens = 0


class _FakeMessage:
    def __init__(self, content: list[_FakeTextBlock], stop_reason: str = "end_turn") -> None:
        self.content = content
        self.stop_reason = stop_reason
        self.usage = _FakeUsage()


class _FakeMessagesResource:
    def __init__(self, message: _FakeMessage) -> None:
        self._message = message
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _FakeMessage:
        self.calls.append(kwargs)
        return self._message


class _FakeClient:
    def __init__(self, message: _FakeMessage) -> None:
        self.messages = _FakeMessagesResource(message)


def _adapter(message: _FakeMessage) -> tuple[AnthropicGenerationAdapter, _FakeClient]:
    client = _FakeClient(message)
    adapter = AnthropicGenerationAdapter(
        api_key="unused-fake",
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        effort=_EFFORT,
        client=client,
    )
    return adapter, client


def _evidence(snippet: str, *, section_path: tuple[str, ...] = ("Chapter 1", "Sec")) -> Evidence:
    return Evidence(
        chunk_id=uuid4(),
        source_id=uuid4(),
        section_path=section_path,
        anchor=f"ch1.xhtml#{snippet}",
        page_span=None,
        snippet=snippet,
        score=0.5,
    )


# --- Request shape (GEN-04) ----------------------------------------------------


def test_request_sends_one_citations_enabled_document_per_chunk_in_order() -> None:
    evidence = [_evidence("alpha"), _evidence("beta")]
    adapter, client = _adapter(_FakeMessage([_FakeTextBlock("ok")]))

    adapter.generate(mode=MODE_ANSWER, message="What is X?", evidence=evidence)

    call = client.messages.calls[0]
    assert call["model"] == _MODEL
    assert call["max_tokens"] == _MAX_TOKENS
    assert call["system"] == [{"type": "text", "text": ANSWER_SYSTEM_PROMPT}]
    messages = call["messages"]
    assert messages[0]["role"] == "user"
    content = messages[0]["content"]
    # One document block per evidence chunk, in evidence order, then the question.
    documents = content[:-1]
    assert len(documents) == len(evidence)
    for doc, item in zip(documents, evidence, strict=True):
        assert doc["type"] == "document"
        assert doc["source"] == {
            "type": "text",
            "media_type": "text/plain",
            "data": item.snippet,
        }
        assert doc["title"] == item.section_path[-1]
        assert json.loads(doc["context"]) == {
            "chunk_id": str(item.chunk_id),
            "anchor": item.anchor,
        }
        # Citations enabled on every document (all-or-none API rule).
        assert doc["citations"] == {"enabled": True}
    assert content[-1] == {"type": "text", "text": "What is X?"}


def test_document_title_falls_back_to_anchor_when_section_path_empty() -> None:
    item = _evidence("solo", section_path=())
    adapter, client = _adapter(_FakeMessage([_FakeTextBlock("ok")]))

    adapter.generate(mode=MODE_ANSWER, message="q", evidence=[item])

    doc = client.messages.calls[0]["messages"][0]["content"][0]
    assert doc["title"] == item.anchor


# --- The citations request shape, and what it must never carry (ASK-07, ASK-09) --
#
# Derived from the request-shape ACs. Anthropic rejects a request that asks for
# citations and a structured-output format together, and that rejection is a 400 the
# reader sees as "answer generation failed" with no clue which half was wrong. The
# two shapes therefore live in two tests that cannot both pass on a mixed request:
# this one asserts the citations half is present and the schema half is absent, and
# the quiz suite asserts the mirror. Both request paths are pinned, because a request
# that is only correct when buffered fails exactly where the reader is watching.


def _document_blocks(content: list[dict[str, object]]) -> list[dict[str, object]]:
    return [block for block in content if block.get("type") == "document"]


@pytest.mark.parametrize("mode", [MODE_ANSWER, MODE_TEACH])
def test_buffered_request_enables_citations_and_sends_no_output_format(mode: str) -> None:
    adapter, client = _adapter(_FakeMessage([_FakeTextBlock("ok")]))

    adapter.generate(
        mode=mode,
        message="q",
        evidence=[_evidence("alpha"), _evidence("beta")],
        target_section_path=("Ch", "A") if mode == MODE_TEACH else None,
    )

    call = client.messages.calls[0]
    documents = _document_blocks(call["messages"][-1]["content"])
    assert len(documents) == 2
    assert all(doc["citations"] == {"enabled": True} for doc in documents)
    # ``output_config`` carries the thinking effort and nothing else. A structured
    # output format alongside citations is the documented 400.
    assert call["output_config"] == {"effort": _EFFORT}
    assert "format" not in call["output_config"]


@pytest.mark.parametrize("mode", [MODE_ANSWER, MODE_TEACH])
def test_stream_request_enables_citations_and_sends_no_output_format(mode: str) -> None:
    stream = _FakeStream(deltas=["ok"], final_message=_FakeMessage([_FakeTextBlock("ok")]))
    adapter, client = _streaming_answer_adapter(stream)

    list(
        adapter.generate_stream(
            mode=mode,
            message="q",
            evidence=[_evidence("alpha"), _evidence("beta")],
            target_section_path=("Ch", "A") if mode == MODE_TEACH else None,
        )
    )

    call = client.messages.stream_calls[0]
    documents = _document_blocks(call["messages"][-1]["content"])
    assert len(documents) == 2
    assert all(doc["citations"] == {"enabled": True} for doc in documents)
    assert call["output_config"] == {"effort": _EFFORT}
    assert "format" not in call["output_config"]


# --- Deliberate thinking config (ANSW-04, ANSW-06) -----------------------------
#
# Derived from the generation-config ACs: every request the adapter builds — either
# path, either mode — asks for adaptive thinking with its content *summarized*
# rather than omitted (the omission is what makes a thinking model look hung), at
# the effort the composition root configured, inside the shared token budget. The
# effort also reaches the log line, so the latency and spend on that same line can
# be read against the setting that bought them.


@pytest.mark.parametrize("mode", [MODE_ANSWER, MODE_TEACH])
def test_buffered_request_asks_for_summarized_thinking_at_the_configured_effort(
    mode: str,
) -> None:
    adapter, client = _adapter(_FakeMessage([_FakeTextBlock("ok")]))

    adapter.generate(
        mode=mode,
        message="q",
        evidence=[_evidence("alpha")],
        target_section_path=("Ch", "A") if mode == MODE_TEACH else None,
    )

    call = client.messages.calls[0]
    assert call["thinking"] == _SUMMARIZED_THINKING
    assert call["output_config"] == {"effort": _EFFORT}
    # The budget covers thinking and answer together, so it is part of this contract.
    assert call["max_tokens"] == _MAX_TOKENS
    # The buffered call shows nothing until it returns and holds a threadpool slot
    # throughout, so it is bounded well under the SDK's ten-minute default.
    assert 0 < call["timeout"] <= 180


@pytest.mark.parametrize("mode", [MODE_ANSWER, MODE_TEACH])
def test_stream_request_asks_for_summarized_thinking_at_the_configured_effort(
    mode: str,
) -> None:
    stream = _FakeStream(deltas=["ok"], final_message=_FakeMessage([_FakeTextBlock("ok")]))
    adapter, client = _streaming_answer_adapter(stream)

    list(
        adapter.generate_stream(
            mode=mode,
            message="q",
            evidence=[_evidence("alpha")],
            target_section_path=("Ch", "A") if mode == MODE_TEACH else None,
        )
    )

    call = client.messages.stream_calls[0]
    assert call["thinking"] == _SUMMARIZED_THINKING
    assert call["output_config"] == {"effort": _EFFORT}
    assert call["max_tokens"] == _MAX_TOKENS
    # No bound on this one: its frames are the proof of progress the buffered call
    # cannot give, and a long teach turn streaming steadily is not a hung one.
    assert "timeout" not in call


def test_buffered_answer_ignores_thinking_blocks_in_the_reply() -> None:
    # Summarized thinking arrives as its own block type; it is the model's scratchpad,
    # never part of the answer text or its citations.
    evidence = [_evidence("alpha")]
    message = _FakeMessage(
        [
            _FakeThinkingBlock("Weighing the two passages against the question."),
            _FakeTextBlock("The tides follow the moon.", [_FakeCitation(0)]),
        ]
    )
    adapter, _ = _adapter(message)

    result = adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    assert result.text == "The tides follow the moon.[^1]"
    assert result.cited_chunk_ids == (evidence[0].chunk_id,)


def test_buffered_call_logs_the_effort_it_spent(caplog) -> None:
    adapter, _ = _adapter(_FakeMessage([_FakeTextBlock("ok")]))

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        adapter.generate(mode=MODE_ANSWER, message="q", evidence=[_evidence("alpha")])

    lines = [r.getMessage() for r in caplog.records if r.name == _LOGGER]
    assert len(lines) == 1
    assert f"effort={_EFFORT}" in lines[0]


def test_streamed_call_logs_the_effort_it_spent(caplog) -> None:
    stream = _FakeStream(deltas=["ok"], final_message=_FakeMessage([_FakeTextBlock("ok")]))
    adapter, _ = _streaming_answer_adapter(stream)

    with caplog.at_level(logging.INFO, logger=_LOGGER):
        list(adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=[_evidence("alpha")]))

    lines = [r.getMessage() for r in caplog.records if r.name == _LOGGER]
    assert len(lines) == 1
    assert f"effort={_EFFORT}" in lines[0]


# --- A rejected request says which shape was rejected (ASK-10) -----------------
#
# Derived from ASK-10 and its edge case. A provider 4xx is what the reader sees as
# "answer generation failed"; the operator needs the request shape, the status, and
# the request id to tell the documented citations-plus-schema 400 from anything else
# and to quote the call to the provider. The same line must stay clean: the SDK's
# error message quotes the rejected request back, so document bodies, the system
# prompt, and the learner's question would ride along if the exception were logged
# (NFR-SEC-004). A 4xx with no request id still logs status and shape.

_SECRET_SNIPPET = "the tides follow the moon in a way no log should repeat"
_SECRET_QUESTION = "why do the tides follow the moon"


class _FakeAPIStatusError(Exception):
    """Shaped like the SDK's ``APIStatusError``: HTTP status, request id, body."""

    def __init__(
        self,
        status_code: int,
        *,
        request_id: str | None,
        body: str,
        payload: dict[str, object] | None = None,
    ) -> None:
        super().__init__(body)
        self.status_code = status_code
        self.request_id = request_id
        self.body = payload


def _rejection(request_id: str | None) -> _FakeAPIStatusError:
    """A 400 whose message quotes the request back, exactly as the SDK's does."""
    return _FakeAPIStatusError(
        400,
        request_id=request_id,
        body=(
            "Error code: 400 - {'error': {'message': \"documents.0.source.data: "
            f"'{_SECRET_SNIPPET}' ... messages.0: '{_SECRET_QUESTION}' ... "
            f"system: '{ANSWER_SYSTEM_PROMPT[:40]}'\"}}"
        ),
    )


class _RejectingMessagesResource:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def create(self, **kwargs: object) -> object:
        raise self._error

    def stream(self, **kwargs: object) -> object:
        raise self._error


class _RejectingClient:
    def __init__(self, error: Exception) -> None:
        self.messages = _RejectingMessagesResource(error)


def _rejecting_adapter(error: Exception) -> AnthropicGenerationAdapter:
    return AnthropicGenerationAdapter(
        api_key="unused-fake",
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        effort=_EFFORT,
        client=_RejectingClient(error),
    )


def _rejected_call_lines(caplog, error: Exception, *, stream: bool) -> list[str]:
    """Drive one rejected call and return this adapter's log lines."""
    adapter = _rejecting_adapter(error)
    with caplog.at_level(logging.WARNING, logger=_LOGGER), pytest.raises(_FakeAPIStatusError):
        if stream:
            list(
                adapter.generate_stream(
                    mode=MODE_ANSWER,
                    message=_SECRET_QUESTION,
                    evidence=[_evidence(_SECRET_SNIPPET)],
                )
            )
        else:
            adapter.generate(
                mode=MODE_ANSWER,
                message=_SECRET_QUESTION,
                evidence=[_evidence(_SECRET_SNIPPET)],
            )
    return [r.getMessage() for r in caplog.records if r.name == _LOGGER]


@pytest.mark.parametrize("stream", [False, True], ids=["buffered", "stream"])
def test_a_rejected_request_logs_its_shape_status_and_request_id(caplog, stream: bool) -> None:
    lines = _rejected_call_lines(caplog, _rejection("req_011CQ7x"), stream=stream)

    assert len(lines) == 1
    assert "request_shape=citations" in lines[0]
    assert "status=400" in lines[0]
    assert "request_id=req_011CQ7x" in lines[0]
    assert "error_type=None" in lines[0]


@pytest.mark.parametrize("stream", [False, True], ids=["buffered", "stream"])
def test_a_rejected_request_never_logs_the_body_it_was_rejected_for(caplog, stream: bool) -> None:
    lines = _rejected_call_lines(caplog, _rejection("req_011CQ7x"), stream=stream)

    assert len(lines) == 1
    assert _SECRET_SNIPPET not in lines[0]
    assert _SECRET_QUESTION not in lines[0]
    assert ANSWER_SYSTEM_PROMPT[:40] not in lines[0]


def test_a_rejection_without_a_request_id_still_logs_status_and_shape(caplog) -> None:
    lines = _rejected_call_lines(caplog, _rejection(None), stream=False)

    assert len(lines) == 1
    assert "request_shape=citations" in lines[0]
    assert "status=400" in lines[0]


def test_a_rejected_request_logs_the_provider_error_type_not_its_message(caplog) -> None:
    """A billing 400 is still 400; the type distinguishes it from a mixed shape."""
    error = _FakeAPIStatusError(
        400,
        request_id="req_011CehjX",
        body=(
            "Error code: 400 - {'error': {'message': \"documents.0.source.data: "
            f"'{_SECRET_SNIPPET}'\"}}"
        ),
        payload={
            "type": "error",
            "error": {
                "type": "invalid_request_error",
                "message": "Your credit balance is too low to access the Anthropic API.",
            },
        },
    )
    lines = _rejected_call_lines(caplog, error, stream=False)

    assert len(lines) == 1
    assert "error_type=invalid_request_error" in lines[0]
    assert "credit balance" not in lines[0]
    assert _SECRET_SNIPPET not in lines[0]


# --- Answer-mode conversation history (CONV-14, CONV-26 AC2) -------------------
#
# An answer turn inside a conversation carries the bounded prior turns, so a
# follow-up resolves against what was already said. The assembled request is
# asserted offline against the fake client: prior turns alternate ahead of the
# current question, the system prompt and citation mechanics are untouched, and a
# history-less call is byte-identical to the single-shot ask that shipped before.


def test_answer_request_without_history_is_the_single_shot_ask() -> None:
    evidence = [_evidence("alpha")]
    adapter, client = _adapter(_FakeMessage([_FakeTextBlock("ok")]))

    adapter.generate(mode=MODE_ANSWER, message="What is X?", evidence=evidence)

    call = client.messages.calls[0]
    # Exactly the pre-history request: the frozen system prompt with no breakpoint,
    # and one user message holding the documents (shape pinned above) + the question.
    assert call["system"] == [{"type": "text", "text": ANSWER_SYSTEM_PROMPT}]
    messages = call["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    content = messages[0]["content"]
    assert [block["type"] for block in content] == ["document", "text"]
    assert content[-1] == {"type": "text", "text": "What is X?"}
    assert all("cache_control" not in block for block in content)


def test_answer_request_renders_history_before_the_current_question() -> None:
    evidence = [_evidence("alpha"), _evidence("beta")]
    history = [
        HistoryTurn(message="Who wrote it?", response_text="Kahneman did."),
        HistoryTurn(message="When?", response_text="In 2011."),
    ]
    adapter, client = _adapter(_FakeMessage([_FakeTextBlock("ok")]))

    adapter.generate(mode=MODE_ANSWER, message="And why?", evidence=evidence, history=history)

    call = client.messages.calls[0]
    # The system prompt is untouched by history — no interpolation, no breakpoint.
    assert call["system"] == [{"type": "text", "text": ANSWER_SYSTEM_PROMPT}]
    messages = call["messages"]
    assert messages[0] == {"role": "user", "content": "Who wrote it?"}
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"][0]["text"] == "Kahneman did."
    assert messages[2] == {"role": "user", "content": "When?"}
    assert messages[3]["content"][0]["text"] == "In 2011."
    # This turn's evidence documents and the question stay in the final user turn,
    # with the citation mechanics unchanged.
    final = messages[4]
    assert final["role"] == "user"
    documents = final["content"][:-1]
    assert len(documents) == len(evidence)
    for doc, item in zip(documents, evidence, strict=True):
        assert doc["type"] == "document"
        assert doc["source"]["data"] == item.snippet
        assert doc["citations"] == {"enabled": True}
    assert final["content"][-1] == {"type": "text", "text": "And why?"}


def test_only_the_latest_answer_history_block_carries_the_cache_breakpoint() -> None:
    history = [
        HistoryTurn(message="q1", response_text="a1"),
        HistoryTurn(message="q2", response_text="a2"),
    ]
    adapter, client = _adapter(_FakeMessage([_FakeTextBlock("ok")]))

    adapter.generate(
        mode=MODE_ANSWER, message="now", evidence=[_evidence("alpha")], history=history
    )

    messages = client.messages.calls[0]["messages"]
    assert "cache_control" not in messages[1]["content"][0]
    assert messages[3]["content"][0]["cache_control"] == _CACHE_1H


def test_history_replays_a_prior_answer_without_the_marks_we_wrote_into_it() -> None:
    # The stored answer carries our `[^n]` marks; the model never wrote them and its
    # numbering restarts every turn, so replaying them would teach it a token it can
    # only get wrong — and an imitation landing inside this turn's range would be
    # rendered to the reader as a link to a passage the model never cited. The prose
    # around the marks is replayed exactly.
    history = [
        HistoryTurn(
            message="Who wrote it?",
            response_text="Kahneman did.[^1] He worked with Tversky.[^2][^10]",
        )
    ]
    adapter, client = _adapter(_FakeMessage([_FakeTextBlock("ok")]))

    adapter.generate(
        mode=MODE_ANSWER, message="And why?", evidence=[_evidence("alpha")], history=history
    )

    block = client.messages.calls[0]["messages"][1]["content"][0]
    assert block["text"] == "Kahneman did. He worked with Tversky."
    # Rewriting the text does not cost the block its breakpoint — the cached prefix
    # is still the settled history.
    assert block["cache_control"] == _CACHE_1H
    # The learner's own message is theirs — it is replayed untouched either way.
    assert client.messages.calls[0]["messages"][0]["content"] == "Who wrote it?"


def test_answer_stream_sends_the_same_request_as_the_buffered_path() -> None:
    # Both paths assemble the request through one helper, so history reaches the
    # streamed answer identically — no second, drifting assembly.
    evidence = [_evidence("alpha")]
    history = [HistoryTurn(message="q1", response_text="a1")]
    buffered_adapter, buffered_client = _adapter(_FakeMessage([_FakeTextBlock("ok")]))
    stream_adapter, stream_client = _streaming_answer_adapter(
        _FakeStream(deltas=["ok"], final_message=_FakeMessage([_FakeTextBlock("ok")]))
    )

    buffered_adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence, history=history)
    list(
        stream_adapter.generate_stream(
            mode=MODE_ANSWER, message="q", evidence=evidence, history=history
        )
    )

    buffered_call = buffered_client.messages.calls[0]
    streamed_call = stream_client.messages.stream_calls[0]
    assert streamed_call["system"] == buffered_call["system"]
    assert streamed_call["messages"] == buffered_call["messages"]


# --- Citation mapping (GEN-05) -------------------------------------------------


def test_citations_map_by_document_index_not_title() -> None:
    # The citation's document_title is deliberately wrong; mapping must follow the
    # 0-based document_index into the request's evidence order.
    evidence = [_evidence("alpha"), _evidence("beta")]
    message = _FakeMessage(
        [_FakeTextBlock("answer", [_FakeCitation(1, document_title="MISLEADING")])]
    )
    adapter, _ = _adapter(message)

    result = adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    assert result.found is True
    assert result.cited_chunk_ids == (evidence[1].chunk_id,)


def test_citations_dedup_keeping_first_occurrence_order() -> None:
    evidence = [_evidence("alpha"), _evidence("beta")]
    message = _FakeMessage(
        [
            _FakeTextBlock("first", [_FakeCitation(1), _FakeCitation(0)]),
            _FakeTextBlock("second", [_FakeCitation(1)]),
        ]
    )
    adapter, _ = _adapter(message)

    result = adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    # First-occurrence order across blocks (1 then 0); the repeat of 1 is dropped.
    assert result.cited_chunk_ids == (evidence[1].chunk_id, evidence[0].chunk_id)


# --- Claim-level citation spans (ASK-12, ASK-13, ASK-14) -----------------------
#
# Derived from the citation-span ACs: a citation that reports its quote and the
# characters it occupies becomes a Learny ``CitedSpan`` whose offsets index the very
# string the request sent as that document's ``source.data``, so the reader can be
# shown the sentence instead of the whole chunk. Offsets that do not select that
# quote are dropped and the chunk id survives alone, and a span never outlives the
# citation grounding kept.


def _located_citation(document_index: int, body: str, quote: str) -> _FakeCitation:
    """The citation the API returns for ``quote`` as it occurs inside ``body``."""
    start = body.index(quote)
    return _FakeCitation(
        document_index,
        cited_text=quote,
        start_char_index=start,
        end_char_index=start + len(quote),
    )


def _sent_document_body(client: _FakeClient, index: int = 0) -> str:
    """The exact ``source.data`` string the recorded request carried."""
    return client.messages.calls[0]["messages"][0]["content"][index]["source"]["data"]


def test_span_offsets_index_the_exact_document_body_that_was_sent() -> None:
    # The golden. The offsets are checked back against the string pulled out of the
    # recorded request, never against a local copy of the fixture, so an index that
    # drifts from what the provider was given cannot pass by agreeing with the test.
    body = "The tides follow the moon. Volcanoes vent magma. A press sets type."
    quote = "Volcanoes vent magma."
    evidence = [_evidence(body)]
    message = _FakeMessage(
        [_FakeTextBlock("Magma escapes upward.", [_located_citation(0, body, quote)])]
    )
    adapter, client = _adapter(message)

    result = adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    (span,) = result.spans
    assert span.chunk_id == evidence[0].chunk_id
    assert span.quote == quote
    assert _sent_document_body(client)[span.start : span.end] == quote


def test_span_offsets_are_character_indices_not_byte_offsets() -> None:
    # Accented prose ahead of the quote makes its byte offset larger than its
    # character offset, so an adapter measuring encoded bytes lands mid-sentence.
    body = "Não é só a maré que sobe. Volcanoes vent magma."
    quote = "Volcanoes vent magma."
    evidence = [_evidence(body)]
    message = _FakeMessage([_FakeTextBlock("Magma.", [_located_citation(0, body, quote)])])
    adapter, client = _adapter(message)

    result = adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    (span,) = result.spans
    sent = _sent_document_body(client)
    assert sent[span.start : span.end] == quote
    # The fixture only discriminates if the two measurements actually disagree here.
    assert span.start != len(sent[: span.start].encode("utf-8"))


def test_out_of_range_offsets_drop_the_span_and_keep_the_chunk() -> None:
    # Spec edge case: offsets past the end of the body are unusable, but the citation
    # itself is still a citation — the mark stays and opens the whole passage.
    body = "Volcanoes vent magma."
    citation = _FakeCitation(
        0, cited_text="magma.", start_char_index=15, end_char_index=len(body) + 40
    )
    evidence = [_evidence(body)]
    adapter, _ = _adapter(_FakeMessage([_FakeTextBlock("An answer", [citation])]))

    result = adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    assert result.spans == ()
    assert result.cited_chunk_ids == (evidence[0].chunk_id,)
    assert result.text == "An answer[^1]"


def test_offsets_that_do_not_select_the_reported_quote_drop_the_span() -> None:
    # In range, but slicing the body with them yields different text — a normalized
    # body or an off-by-one on the provider side. Highlighting the wrong sentence is
    # worse than highlighting none, so the span goes and the chunk stays.
    body = "The tides follow the moon. Volcanoes vent magma."
    citation = _FakeCitation(
        0, cited_text="Volcanoes vent magma.", start_char_index=0, end_char_index=21
    )
    evidence = [_evidence(body)]
    adapter, _ = _adapter(_FakeMessage([_FakeTextBlock("An answer", [citation])]))

    result = adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    assert result.spans == ()
    assert result.cited_chunk_ids == (evidence[0].chunk_id,)


def test_a_citation_reporting_no_offsets_yields_no_span() -> None:
    # A citation without a location is still a citation. The passage-level behaviour
    # that shipped before spans is what the reader gets (ASK-17).
    evidence = [_evidence("Volcanoes vent magma.")]
    adapter, _ = _adapter(_FakeMessage([_FakeTextBlock("An answer", [_FakeCitation(0)])]))

    result = adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    assert result.spans == ()
    assert result.cited_chunk_ids == (evidence[0].chunk_id,)


def test_grounding_discards_the_spans_of_a_chunk_it_dropped() -> None:
    # A span is a location inside a citation, so a citation grounding refuses takes
    # its quote with it — otherwise the reader gets a highlight into a passage that
    # is not among the ones shown.
    retrieved_body = "The tides follow the moon. Volcanoes vent magma."
    ungrounded_body = "A press sets movable type."
    retrieved, ungrounded = _evidence(retrieved_body), _evidence(ungrounded_body)
    message = _FakeMessage(
        [
            _FakeTextBlock(
                "Both claims.",
                [
                    _located_citation(0, retrieved_body, "Volcanoes vent magma."),
                    _located_citation(1, ungrounded_body, "A press sets movable type."),
                ],
            )
        ]
    )
    adapter, _ = _adapter(message)

    result = adapter.generate(mode=MODE_ANSWER, message="q", evidence=[retrieved, ungrounded])
    grounded = ground(result, [retrieved])

    assert [span.quote for span in result.spans] == [
        "Volcanoes vent magma.",
        "A press sets movable type.",
    ]
    assert grounded is not None
    _, citations = grounded
    assert [span.quote for span in ground_spans(result, citations)] == ["Volcanoes vent magma."]


def test_streamed_completed_answer_carries_the_same_spans_as_the_buffered_parse() -> None:
    # The streamed path is the one the reader actually watches; its completed event
    # is parsed by the same walk, so its spans must be the buffered ones exactly.
    body = "The tides follow the moon. Volcanoes vent magma."
    quote = "Volcanoes vent magma."
    evidence = [_evidence(body)]
    final = _FakeMessage([_FakeTextBlock("Magma escapes.", [_located_citation(0, body, quote)])])
    stream_adapter, _ = _streaming_answer_adapter(
        _FakeStream(deltas=_stream_events_for(final), final_message=final)
    )
    buffered_adapter, _ = _adapter(final)

    completed = list(
        stream_adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=evidence)
    )[-1]
    buffered = buffered_adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    assert isinstance(completed, AnswerCompleted)
    assert completed.answer.spans == buffered.spans
    assert [span.quote for span in completed.answer.spans] == [quote]


# --- Inline citation marks (ANSW-07) -------------------------------------------
#
# Derived from the citations-in-flow ACs: the answer text itself carries a ``[^n]``
# token wherever the model attached a citation, so a mark can be rendered at the
# point it belongs instead of a chip detached from the prose. The number is the
# cited chunk's position in ``cited_chunk_ids`` — the two come out of one walk, so
# these tests pin the mapping rather than the literal numbers. The API attaches
# citations to whole text blocks and gives no character span into the reply, so a
# block's marks sit directly after its text.


def _marker_numbers(text: str) -> list[int]:
    """The ``[^n]`` numbers in the order they appear in the answer text."""
    return [int(number) for number in re.findall(r"\[\^(\d+)\]", text)]


def test_each_cited_block_carries_its_mark_after_the_cited_text() -> None:
    evidence = [_evidence("alpha"), _evidence("beta")]
    message = _FakeMessage(
        [
            _FakeTextBlock("The tides follow the moon.", [_FakeCitation(0)]),
            _FakeTextBlock(" Volcanoes vent magma.", [_FakeCitation(1)]),
        ]
    )
    adapter, _ = _adapter(message)

    result = adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    assert result.text == "The tides follow the moon.[^1] Volcanoes vent magma.[^2]"


def test_mark_n_names_the_nth_citation() -> None:
    # The load-bearing contract for the reader: activating mark n opens
    # citations[n - 1]. Asserted through the mapping, not through fixed numbers.
    evidence = [_evidence("alpha"), _evidence("beta"), _evidence("gamma")]
    message = _FakeMessage(
        [
            _FakeTextBlock("Second first.", [_FakeCitation(2)]),
            _FakeTextBlock(" Then the first.", [_FakeCitation(0)]),
        ]
    )
    adapter, _ = _adapter(message)

    result = adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    numbers = _marker_numbers(result.text)
    assert numbers == [1, 2]
    assert [result.cited_chunk_ids[n - 1] for n in numbers] == [
        evidence[2].chunk_id,
        evidence[0].chunk_id,
    ]


def test_a_chunk_cited_again_later_reuses_its_first_mark() -> None:
    # One passage, one number, wherever it is referenced — the citation list still
    # holds it once (first-occurrence dedupe), so the mark points at the same entry.
    evidence = [_evidence("alpha"), _evidence("beta")]
    message = _FakeMessage(
        [
            _FakeTextBlock("First.", [_FakeCitation(1), _FakeCitation(0)]),
            _FakeTextBlock(" Second.", [_FakeCitation(1)]),
        ]
    )
    adapter, _ = _adapter(message)

    result = adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    assert result.text == "First.[^1][^2] Second.[^1]"
    assert result.cited_chunk_ids == (evidence[1].chunk_id, evidence[0].chunk_id)


def test_a_block_citing_one_chunk_twice_carries_one_mark() -> None:
    # A repeated mark on the same sentence would only lead the reader to a passage
    # the first mark already reaches.
    evidence = [_evidence("alpha")]
    message = _FakeMessage([_FakeTextBlock("Twice cited.", [_FakeCitation(0), _FakeCitation(0)])])
    adapter, _ = _adapter(message)

    result = adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    assert result.text == "Twice cited.[^1]"
    assert result.cited_chunk_ids == (evidence[0].chunk_id,)


def test_uncited_prose_carries_no_marks() -> None:
    evidence = [_evidence("alpha")]
    message = _FakeMessage(
        [
            _FakeTextBlock("A framing sentence."),
            _FakeTextBlock(" The cited claim.", [_FakeCitation(0)]),
            _FakeTextBlock(" A closing thought."),
        ]
    )
    adapter, _ = _adapter(message)

    result = adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    assert result.text == "A framing sentence. The cited claim.[^1] A closing thought."


def test_answer_without_citations_is_marker_free() -> None:
    adapter, _ = _adapter(_FakeMessage([_FakeTextBlock("Plain prose, no citations.")]))

    result = adapter.generate(mode=MODE_ANSWER, message="q", evidence=[_evidence("alpha")])

    assert result.text == "Plain prose, no citations."
    assert result.cited_chunk_ids == ()


def test_malformed_document_index_leaves_no_mark_behind() -> None:
    # The skipped citation must not leave a mark either: a mark with no citation to
    # open is a control that does nothing.
    evidence = [_evidence("alpha")]
    message = _FakeMessage([_FakeTextBlock("An answer", [_FakeCitation(5), _FakeCitation(0)])])
    adapter, _ = _adapter(message)

    result = adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    assert result.text == "An answer[^1]"
    assert result.cited_chunk_ids == (evidence[0].chunk_id,)


def test_a_marker_the_model_itself_wrote_passes_through_the_walk_untouched() -> None:
    # Documenting the accepted residual risk of AD-222: the walk writes marks, it does
    # not police them. A `[^n]` that arrives inside the model's own text — quoted book
    # prose with a footnote, or an imitation — survives into the answer alongside the
    # marks the citations earned. Stripping every marker from model text would corrupt
    # a legitimately quoted footnote, and the reader's renderer already leaves an
    # out-of-range token as plain prose. What keeps this rare is that the model is
    # never shown a marker: history is replayed stripped.
    evidence = [_evidence("alpha")]
    message = _FakeMessage(
        [_FakeTextBlock('The footnote reads "see[^7] the appendix".', [_FakeCitation(0)])]
    )
    adapter, _ = _adapter(message)

    result = adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    assert result.text == 'The footnote reads "see[^7] the appendix".[^1]'
    # The model's token bought no citation — only the reported one is grounded.
    assert result.cited_chunk_ids == (evidence[0].chunk_id,)


def test_sentinel_reply_stays_not_found_even_when_the_model_cites_it() -> None:
    # Marks are written into the answer text, so the not-found comparison runs on the
    # unmarked text: a decline the model happened to attach a citation to is still a
    # decline, never a one-word answer with a footnote.
    evidence = [_evidence("alpha")]
    adapter, _ = _adapter(_FakeMessage([_FakeTextBlock(SENTINEL, [_FakeCitation(0)])]))

    result = adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    assert result.found is False
    assert result.text == ""
    assert result.cited_chunk_ids == ()


def test_teaching_answers_are_marked_by_the_same_walk() -> None:
    # One parser serves both modes, so the teaching turn is marked identically.
    evidence = [_evidence("alpha"), _evidence("beta")]
    message = _FakeMessage(
        [_FakeTextBlock("Here is the teaching.", [_FakeCitation(1), _FakeCitation(0)])]
    )
    adapter, _ = _teaching_adapter(message)

    result = adapter.generate(
        mode=MODE_TEACH,
        message="teach me",
        target_section_path=("Ch", "A"),
        history=[],
        evidence=evidence,
    )

    assert result.text == "Here is the teaching.[^1][^2]"
    assert result.cited_chunk_ids == (evidence[1].chunk_id, evidence[0].chunk_id)


# --- Sentinel / not-found (GEN-06 + edge cases) --------------------------------


def test_whole_reply_sentinel_is_not_found_with_empty_text() -> None:
    evidence = [_evidence("alpha")]
    adapter, _ = _adapter(_FakeMessage([_FakeTextBlock(SENTINEL)]))

    result = adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    assert result.found is False
    assert result.text == ""
    assert result.cited_chunk_ids == ()
    assert result.model == _MODEL


def test_sentinel_surrounded_by_whitespace_is_not_found() -> None:
    evidence = [_evidence("alpha")]
    adapter, _ = _adapter(_FakeMessage([_FakeTextBlock(f"  {SENTINEL}\n")]))

    result = adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    assert result.found is False
    assert result.text == ""


def test_embedded_sentinel_stays_prose() -> None:
    # An occurrence inside a longer answer is not a not-found signal (leak guard).
    evidence = [_evidence("alpha")]
    prose = f"The term {SENTINEL} is discussed here as an answer."
    message = _FakeMessage([_FakeTextBlock(prose, [_FakeCitation(0)])])
    adapter, _ = _adapter(message)

    result = adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    assert result.found is True
    assert result.text == f"{prose}[^1]"
    assert result.cited_chunk_ids == (evidence[0].chunk_id,)


# --- max_tokens partial (edge case) --------------------------------------------


def test_max_tokens_returns_partial_answer_without_raising() -> None:
    evidence = [_evidence("alpha")]
    message = _FakeMessage(
        [_FakeTextBlock("Partial answer", [_FakeCitation(0)])],
        stop_reason="max_tokens",
    )
    adapter, _ = _adapter(message)

    result = adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    assert result.found is True
    assert result.text == "Partial answer[^1]"
    assert result.cited_chunk_ids == (evidence[0].chunk_id,)


# --- Model identity (GEN-04) ---------------------------------------------------


def test_model_identity_readable_without_a_generate_call() -> None:
    adapter = AnthropicGenerationAdapter(
        api_key="unused-fake", model=_MODEL, max_tokens=_MAX_TOKENS, client=None
    )

    assert adapter.model == _MODEL


# --- Lazy SDK import (GEN-03) --------------------------------------------------


def test_adapter_module_imports_no_sdk_at_module_level() -> None:
    # The anthropic SDK is imported lazily inside _get_client only, never at load.
    tree = ast.parse(inspect.getsource(anthropic_module))
    top_level: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level.add(node.module.split(".")[0])

    assert "anthropic" not in top_level


# --- Grounding of adapter-shaped malformed output (GEN-08) ---------------------


def test_out_of_range_index_yields_no_citation_and_grounds_to_not_found() -> None:
    # A malformed out-of-range document_index resolves to no chunk; the resulting
    # ungrounded prose collapses to the not-found outcome through grounding (AD-027).
    evidence = [_evidence("alpha"), _evidence("beta")]
    message = _FakeMessage([_FakeTextBlock("An answer", [_FakeCitation(5)])])
    adapter, _ = _adapter(message)

    result = adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    assert result.cited_chunk_ids == ()
    assert ground(result, list(evidence)) is None


# --- Teaching adapter: layout + prompt caching (GEN-10, GEN-11) -----------------
#
# Derived from the P1-teaching ACs: the frozen teaching system prompt carries a
# 1-hour cache breakpoint, bounded history renders as alternating user/assistant
# messages with the second breakpoint on the latest history block, this turn's
# evidence and the target section + learner message sit after the cached prefix,
# the system prompt has no per-session/per-turn interpolation, the sentinel yields
# the not-found turn, and citations map by document_index through the shared parser.

_CACHE_1H = {"type": "ephemeral", "ttl": "1h"}


def _teaching_adapter(
    message: _FakeMessage,
) -> tuple[AnthropicGenerationAdapter, _FakeClient]:
    client = _FakeClient(message)
    adapter = AnthropicGenerationAdapter(
        api_key="unused-fake",
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        effort=_EFFORT,
        client=client,
    )
    return adapter, client


def test_teaching_request_layout_history_evidence_and_final_turn() -> None:
    evidence = [_evidence("alpha"), _evidence("beta")]
    history = [
        HistoryTurn(message="Hi", response_text="Hello, let's begin."),
        HistoryTurn(message="Go on", response_text="Here is more."),
    ]
    adapter, client = _teaching_adapter(_FakeMessage([_FakeTextBlock("ok")]))

    adapter.generate(
        mode=MODE_TEACH,
        message="What is X?",
        target_section_path=("Chapter 1", "Section A"),
        history=history,
        evidence=evidence,
    )

    call = client.messages.calls[0]
    assert call["model"] == _MODEL
    assert call["max_tokens"] == _MAX_TOKENS
    assert call["system"] == [
        {"type": "text", "text": TEACHING_SYSTEM_PROMPT, "cache_control": _CACHE_1H}
    ]
    messages = call["messages"]
    # Alternating history: plain-text user turn, block-list assistant turn.
    assert messages[0] == {"role": "user", "content": "Hi"}
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"][0]["type"] == "text"
    assert messages[1]["content"][0]["text"] == "Hello, let's begin."
    assert messages[2] == {"role": "user", "content": "Go on"}
    assert messages[3]["role"] == "assistant"
    assert messages[3]["content"][0]["text"] == "Here is more."
    # Final user turn: this turn's evidence documents (citations-enabled, in order),
    # then the section + message text — all volatile content, after the cached prefix.
    final = messages[4]
    assert final["role"] == "user"
    documents = final["content"][:-1]
    assert len(documents) == len(evidence)
    for doc, item in zip(documents, evidence, strict=True):
        assert doc["type"] == "document"
        assert doc["source"]["data"] == item.snippet
        assert doc["citations"] == {"enabled": True}
    assert final["content"][-1]["type"] == "text"


def test_teaching_system_prompt_is_frozen_and_byte_stable_across_calls() -> None:
    adapter, client = _teaching_adapter(_FakeMessage([_FakeTextBlock("ok")]))

    adapter.generate(
        mode=MODE_TEACH,
        message="first",
        target_section_path=("Ch 1", "A"),
        history=[HistoryTurn(message="q1", response_text="a1")],
        evidence=[_evidence("alpha")],
    )
    adapter.generate(
        mode=MODE_TEACH,
        message="second",
        target_section_path=("Ch 9", "Z"),
        history=[
            HistoryTurn(message="q1", response_text="a1"),
            HistoryTurn(message="q2", response_text="a2"),
        ],
        evidence=[_evidence("beta")],
    )

    first_system = client.messages.calls[0]["system"]
    second_system = client.messages.calls[1]["system"]
    # No per-session/per-turn interpolation → byte-identical across calls/sessions.
    assert first_system == second_system
    assert first_system[0]["text"] == TEACHING_SYSTEM_PROMPT
    assert first_system[0]["text"].encode("utf-8") == TEACHING_SYSTEM_PROMPT.encode("utf-8")
    assert first_system[0]["cache_control"] == _CACHE_1H
    # Phase and hint belong on the user turn (TUTOR-03); the cache prefix must
    # not grow them, timestamps, or format slots.
    prompt = first_system[0]["text"]
    assert "Phase:" not in prompt
    assert "HintLevel:" not in prompt
    assert "{" not in prompt
    assert "}" not in prompt


def test_teaching_system_prompt_two_reads_are_identical_bytes() -> None:
    first = TEACHING_SYSTEM_PROMPT.encode("utf-8")
    second = TEACHING_SYSTEM_PROMPT.encode("utf-8")
    assert first == second
    assert first == TEACHING_SYSTEM_PROMPT.encode("utf-8")


def test_teaching_system_prompt_encodes_playbook_constraints() -> None:
    prompt = TEACHING_SYSTEM_PROMPT
    lowered = prompt.lower()
    assert "one move per turn" in lowered
    assert "single question" in lowered
    assert "pump then hint then prompt then assert" in lowered
    assert "two failed elicitations" in lowered
    assert "assert and cite" in lowered
    assert "asks to be told" in lowered
    assert "tell and demand a restatement" in lowered
    assert "socratic questions and checks may omit citations" in lowered
    assert "claims about the book must cite" in lowered
    assert SENTINEL in prompt
    assert "end after a passing unaided check" in lowered


def test_answer_system_prompt_is_byte_identical_to_pre_cycle_value() -> None:
    # TUTOR-04: the answering prefix must not move with the teach playbook.
    pre_cycle = (
        "You are Learny's book-grounded answering assistant. Answer the reader's "
        "question using only the information contained in the provided documents. "
        "Cite the specific passages you rely on. Do not use outside knowledge and do "
        "not speculate beyond what the documents state. If the provided documents do "
        "not contain the information needed to answer the question, reply with "
        "exactly NOT_FOUND_IN_SOURCE and nothing else."
    )
    assert ANSWER_SYSTEM_PROMPT.encode("utf-8") == pre_cycle.encode("utf-8")


def test_tutor_playbook_prompt_frozen_messages() -> None:
    assert TUTOR_OPENING_MESSAGE == "(session start)"
    assert TUTOR_JUST_EXPLAIN_MESSAGE == "Just explain this."
    assert TUTOR_DONT_KNOW_MESSAGE == "I don't know."
    assert TUTOR_CARD_QUESTION == 'In your own words, what is "{title}" arguing?'


def test_only_latest_history_block_carries_second_breakpoint() -> None:
    history = [
        HistoryTurn(message="q1", response_text="a1"),
        HistoryTurn(message="q2", response_text="a2"),
    ]
    adapter, client = _teaching_adapter(_FakeMessage([_FakeTextBlock("ok")]))

    adapter.generate(
        mode=MODE_TEACH,
        message="now",
        target_section_path=("Ch", "A"),
        history=history,
        evidence=[_evidence("alpha")],
    )

    messages = client.messages.calls[0]["messages"]
    # Assistant history turns are messages[1] and messages[3]; only the latest one
    # carries the second cache breakpoint. User turns never carry a breakpoint.
    assert "cache_control" not in messages[1]["content"][0]
    assert messages[3]["content"][0]["cache_control"] == _CACHE_1H
    assert isinstance(messages[0]["content"], str)
    assert isinstance(messages[2]["content"], str)


def test_empty_history_has_only_the_system_breakpoint() -> None:
    adapter, client = _teaching_adapter(_FakeMessage([_FakeTextBlock("ok")]))

    adapter.generate(
        mode=MODE_TEACH,
        message="hello",
        target_section_path=("Ch", "A"),
        history=[],
        evidence=[_evidence("alpha")],
    )

    call = client.messages.calls[0]
    messages = call["messages"]
    # Only the final user turn; no cache_control anywhere in the message list.
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    for block in messages[0]["content"]:
        assert "cache_control" not in block
    # The system prompt still carries its breakpoint.
    assert call["system"][0]["cache_control"] == _CACHE_1H


def test_target_section_rendered_with_arrow_separator_and_message() -> None:
    adapter, client = _teaching_adapter(_FakeMessage([_FakeTextBlock("ok")]))

    adapter.generate(
        mode=MODE_TEACH,
        message="Please explain the loci method.",
        target_section_path=("Part I", "Chapter 3", "The Method of Loci"),
        history=[],
        evidence=[_evidence("alpha")],
    )

    text_block = client.messages.calls[0]["messages"][0]["content"][-1]
    assert text_block["type"] == "text"
    assert "Part I > Chapter 3 > The Method of Loci" in text_block["text"]
    assert "Please explain the loci method." in text_block["text"]


def test_answer_mode_with_a_target_still_sends_the_answer_request() -> None:
    # A conversation scoped to a chapter carries that chapter as its target snapshot
    # in either mode (AD-194), so a target can accompany an answer turn. The mode is
    # what picks the prompt: an adapter reading "teach" from the target's presence
    # would answer scoped questions with the teaching prompt and a section header the
    # reader never asked for.
    adapter, client = _adapter(_FakeMessage([_FakeTextBlock("ok")]))

    adapter.generate(
        mode=MODE_ANSWER,
        message="What is anchoring?",
        target_section_path=("Part I", "Chapter 3"),
        evidence=[_evidence("alpha")],
    )

    call = client.messages.calls[0]
    assert call["system"] == [{"type": "text", "text": ANSWER_SYSTEM_PROMPT}]
    text_block = call["messages"][0]["content"][-1]
    assert text_block == {"type": "text", "text": "What is anchoring?"}


def test_answer_mode_stream_with_a_target_still_sends_the_answer_request() -> None:
    # The streaming half of the same trap, assembled through the same helper.
    stream = _FakeStream(deltas=["ok"], final_message=_FakeMessage([_FakeTextBlock("ok")]))
    adapter, client = _streaming_answer_adapter(stream)

    list(
        adapter.generate_stream(
            mode=MODE_ANSWER,
            message="What is anchoring?",
            target_section_path=("Part I", "Chapter 3"),
            evidence=[_evidence("alpha")],
        )
    )

    call = client.messages.stream_calls[0]
    assert call["system"] == [{"type": "text", "text": ANSWER_SYSTEM_PROMPT}]
    assert call["messages"][0]["content"][-1] == {"type": "text", "text": "What is anchoring?"}


def test_teaching_whole_reply_sentinel_is_not_found() -> None:
    adapter, _ = _teaching_adapter(_FakeMessage([_FakeTextBlock(SENTINEL)]))

    result = adapter.generate(
        mode=MODE_TEACH,
        message="unrelated question",
        target_section_path=("Ch", "A"),
        history=[],
        evidence=[_evidence("alpha")],
    )

    assert result.found is False
    assert result.text == ""
    assert result.cited_chunk_ids == ()
    assert result.model == _MODEL


def test_teaching_citations_map_by_document_index() -> None:
    evidence = [_evidence("alpha"), _evidence("beta")]
    message = _FakeMessage(
        [
            _FakeTextBlock(
                "Here is the teaching.",
                [_FakeCitation(1, document_title="WRONG")],
            )
        ]
    )
    adapter, _ = _teaching_adapter(message)

    result = adapter.generate(
        mode=MODE_TEACH,
        message="teach me",
        target_section_path=("Ch", "A"),
        history=[],
        evidence=evidence,
    )

    assert result.found is True
    assert result.text == "Here is the teaching.[^1]"
    assert result.cited_chunk_ids == (evidence[1].chunk_id,)


# --- Streaming (GEN-12) --------------------------------------------------------
#
# Derived from the C2 Done-when: text-delta events map to AnswerTextDelta in order;
# the completed event parses the final message with the SAME parser as the buffered
# path (equal result); and closing the consumer generator early closes the SDK
# stream (no leaked provider stream on client disconnect).


class _FakeTextStreamEvent:
    """The SDK's synthetic ``text`` event: a text delta plus running snapshot."""

    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _FakeThinkingStreamEvent:
    """The SDK's synthetic ``thinking`` event: a reasoning delta plus running snapshot."""

    def __init__(self, thinking: str) -> None:
        self.type = "thinking"
        self.thinking = thinking
        self.snapshot = thinking


class _FakeContentBlockStopEvent:
    """The SDK's ``content_block_stop``: the finished block, citations attached."""

    def __init__(self, content_block: object) -> None:
        self.type = "content_block_stop"
        self.content_block = content_block


class _FakeOtherStreamEvent:
    """Any event the adapter has no mapping for (bookkeeping, or a future type)."""

    def __init__(self, event_type: str) -> None:
        self.type = event_type


def _stream_events_for(message: _FakeMessage) -> list[object]:
    """Replay a final message as the event sequence the SDK's stream would fire.

    Each block arrives as its deltas (text or thinking) followed by the
    ``content_block_stop`` carrying the finished block with its citations. Text is
    deliberately split across two deltas, so a mark inserted anywhere but the block's
    end lands in the middle of the streamed prose and the parity check catches it.
    Driving the streaming path from the *same* object the buffered path parses is
    what makes that check a statement about one provider response seen two ways,
    instead of two hand-written fixtures that were written to agree.
    """
    events: list[object] = []
    for block in message.content:
        if block.type == "text":
            split = len(block.text) // 2
            events.append(_FakeTextStreamEvent(block.text[:split]))
            events.append(_FakeTextStreamEvent(block.text[split:]))
        else:
            events.append(_FakeThinkingStreamEvent(block.thinking))
        events.append(_FakeContentBlockStopEvent(block))
    return events


class _FakeStream:
    """Fake ``MessageStream``: iterates events, exposes the final message, closes.

    A plain string in ``deltas`` is a text event; any other item is yielded as-is, so
    a case can interleave thinking (or unmapped) events between text deltas.
    """

    def __init__(self, deltas: list[object], final_message: _FakeMessage) -> None:
        self._deltas = deltas
        self._final = final_message
        self.closed = False

    def __iter__(self):  # noqa: ANN204 — yields fake stream events
        for delta in self._deltas:
            yield _FakeTextStreamEvent(delta) if isinstance(delta, str) else delta

    def get_final_message(self) -> _FakeMessage:
        return self._final

    def close(self) -> None:
        self.closed = True


class _FakeStreamManager:
    """Fake ``MessageStreamManager`` context manager: records the call, closes on exit."""

    def __init__(
        self, stream: _FakeStream, calls: list[dict[str, object]], kwargs: dict[str, object]
    ) -> None:
        self._stream = stream
        self._calls = calls
        self._kwargs = kwargs

    def __enter__(self) -> _FakeStream:
        self._calls.append(self._kwargs)
        return self._stream

    def __exit__(self, *exc: object) -> bool:
        self._stream.close()
        return False


class _FakeStreamingMessagesResource:
    def __init__(self, stream: _FakeStream) -> None:
        self._stream = stream
        self.stream_calls: list[dict[str, object]] = []

    def stream(self, **kwargs: object) -> _FakeStreamManager:
        return _FakeStreamManager(self._stream, self.stream_calls, kwargs)


class _FakeStreamingClient:
    def __init__(self, stream: _FakeStream) -> None:
        self.messages = _FakeStreamingMessagesResource(stream)


def _streaming_answer_adapter(
    stream: _FakeStream,
) -> tuple[AnthropicGenerationAdapter, _FakeStreamingClient]:
    client = _FakeStreamingClient(stream)
    adapter = AnthropicGenerationAdapter(
        api_key="unused-fake",
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        effort=_EFFORT,
        client=client,
    )
    return adapter, client


def test_answer_stream_maps_text_events_to_deltas_then_one_completed() -> None:
    evidence = [_evidence("alpha")]
    stream = _FakeStream(
        deltas=["Hello ", "world"], final_message=_FakeMessage([_FakeTextBlock("Hello world")])
    )
    adapter, client = _streaming_answer_adapter(stream)

    events = list(adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=evidence))

    deltas = [e for e in events if isinstance(e, AnswerTextDelta)]
    assert deltas == [AnswerTextDelta(text="Hello "), AnswerTextDelta(text="world")]
    assert isinstance(events[-1], AnswerCompleted)
    assert len([e for e in events if isinstance(e, AnswerCompleted)]) == 1
    # The streaming request carries the same citations-enabled documents + question.
    call = client.messages.stream_calls[0]
    assert call["model"] == _MODEL
    assert call["system"] == [{"type": "text", "text": ANSWER_SYSTEM_PROMPT}]
    content = call["messages"][0]["content"]
    assert content[0]["type"] == "document"
    assert content[0]["citations"] == {"enabled": True}
    assert content[-1] == {"type": "text", "text": "q"}


# --- Streamed reasoning (ANSW-02) ----------------------------------------------
#
# Derived from the phases ACs: thinking the provider streams reaches the caller as
# reasoning events, in arrival order relative to the answer text, so a panel can
# show the model reasoning instead of a blank wait. A provider that does not think
# yields none of them, and an event the adapter has no mapping for is not quietly
# filed as either kind.


def test_stream_maps_thinking_events_to_reasoning_deltas_in_arrival_order() -> None:
    evidence = [_evidence("alpha")]
    stream = _FakeStream(
        deltas=[
            _FakeThinkingStreamEvent("Weighing "),
            _FakeThinkingStreamEvent("the passages."),
            "The tides ",
            _FakeThinkingStreamEvent("(checking the second passage)"),
            "follow the moon.",
        ],
        final_message=_FakeMessage([_FakeTextBlock("The tides follow the moon.")]),
    )
    adapter, _ = _streaming_answer_adapter(stream)

    events = list(adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=evidence))

    assert events[:-1] == [
        AnswerReasoningDelta(text="Weighing "),
        AnswerReasoningDelta(text="the passages."),
        AnswerTextDelta(text="The tides "),
        AnswerReasoningDelta(text="(checking the second passage)"),
        AnswerTextDelta(text="follow the moon."),
    ]
    assert isinstance(events[-1], AnswerCompleted)


def test_stream_without_thinking_emits_no_reasoning_events() -> None:
    # Adaptive thinking may decide an easy question needs none; the turn then has
    # no reasoning at all rather than an empty one.
    stream = _FakeStream(
        deltas=["Hello ", "world"], final_message=_FakeMessage([_FakeTextBlock("Hello world")])
    )
    adapter, _ = _streaming_answer_adapter(stream)

    events = list(
        adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=[_evidence("alpha")])
    )

    assert [e for e in events if isinstance(e, AnswerReasoningDelta)] == []


def test_stream_ignores_events_it_has_no_mapping_for() -> None:
    # The SDK's stream carries bookkeeping events (and will carry types that do not
    # exist yet); each mapped kind is matched by name so none of them can arrive as
    # answer text or as reasoning.
    stream = _FakeStream(
        deltas=[
            _FakeOtherStreamEvent("message_start"),
            "Hello",
            _FakeOtherStreamEvent("signature"),
            _FakeOtherStreamEvent("message_delta"),
        ],
        final_message=_FakeMessage([_FakeTextBlock("Hello")]),
    )
    adapter, _ = _streaming_answer_adapter(stream)

    events = list(
        adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=[_evidence("alpha")])
    )

    assert events[:-1] == [AnswerTextDelta(text="Hello")]
    assert isinstance(events[-1], AnswerCompleted)


def test_answer_stream_completed_parse_equals_buffered_parse() -> None:
    # The completed event parses the final message with the SAME parser as the
    # buffered path → identical GeneratedAnswer (document_index mapping included).
    evidence = [_evidence("alpha"), _evidence("beta")]
    final = _FakeMessage([_FakeTextBlock("answer", [_FakeCitation(1, document_title="WRONG")])])

    stream_adapter, _ = _streaming_answer_adapter(
        _FakeStream(deltas=["answer"], final_message=final)
    )
    completed = list(
        stream_adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=evidence)
    )[-1]

    buffered_adapter, _ = _adapter(final)
    buffered = buffered_adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    assert isinstance(completed, AnswerCompleted)
    assert completed.answer == buffered
    assert completed.answer.cited_chunk_ids == (evidence[1].chunk_id,)


# --- Streamed citation marks and stream/buffered parity (ANSW-07) --------------
#
# A mark is answer text, so it has to reach the reader the same way the prose does —
# and it has to land in the same place in the streamed text as in the text that gets
# persisted, or a reader who reloads sees their marks move. The API attaches
# citations mid-block while the buffered parser can only write a block's marks after
# its text, so the stream emits them when the block finishes; these tests pin that
# the two paths produce byte-identical text for the same provider response.


def test_stream_marks_each_block_when_the_block_finishes() -> None:
    evidence = [_evidence("alpha"), _evidence("beta")]
    first = _FakeTextBlock("The tides follow the moon.", [_FakeCitation(0)])
    # The second block cites a new chunk and then the one already marked [^1].
    second = _FakeTextBlock(" Volcanoes vent magma.", [_FakeCitation(1), _FakeCitation(0)])
    final = _FakeMessage([first, second])
    # The first block's prose arrives in two deltas: the mark belongs after the last
    # of them, not after whichever delta the citation happened to attach near.
    adapter, _ = _streaming_answer_adapter(
        _FakeStream(
            deltas=[
                _FakeTextStreamEvent("The tides "),
                _FakeTextStreamEvent("follow the moon."),
                _FakeContentBlockStopEvent(first),
                _FakeTextStreamEvent(" Volcanoes vent magma."),
                _FakeContentBlockStopEvent(second),
            ],
            final_message=final,
        )
    )

    events = list(adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=evidence))

    assert [e.text for e in events if isinstance(e, AnswerTextDelta)] == [
        "The tides ",
        "follow the moon.",
        "[^1]",
        " Volcanoes vent magma.",
        "[^2][^1]",
    ]


def test_stream_emits_no_marker_delta_for_a_block_with_no_citations() -> None:
    # An empty marker run must not become an empty delta: a frame carrying nothing
    # is a frame the client has to learn to ignore.
    final = _FakeMessage([_FakeThinkingBlock("Weighing it."), _FakeTextBlock("Plain prose.")])
    adapter, _ = _streaming_answer_adapter(
        _FakeStream(deltas=_stream_events_for(final), final_message=final)
    )

    events = list(
        adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=[_evidence("alpha")])
    )

    texts = [e.text for e in events if isinstance(e, AnswerTextDelta)]
    assert "".join(texts) == "Plain prose."
    assert all(texts), "an empty marker run must not be sent as a delta"
    assert [e.text for e in events if isinstance(e, AnswerReasoningDelta)] == ["Weighing it."]


def test_stream_of_a_declined_turn_carries_no_marks() -> None:
    # The not-found reply cites nothing, so nothing marks it — the hold-back never
    # sees a marker it would have to reason about.
    final = _FakeMessage([_FakeTextBlock(SENTINEL)])
    adapter, _ = _streaming_answer_adapter(
        _FakeStream(deltas=_stream_events_for(final), final_message=final)
    )

    events = list(
        adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=[_evidence("alpha")])
    )

    assert "".join(e.text for e in events if isinstance(e, AnswerTextDelta)) == SENTINEL
    assert isinstance(events[-1], AnswerCompleted)
    assert events[-1].answer.found is False


def _cited_answer_message() -> _FakeMessage:
    return _FakeMessage([_FakeTextBlock("One claim.", [_FakeCitation(1)])])


def _repeated_citation_message() -> _FakeMessage:
    return _FakeMessage(
        [
            _FakeTextBlock("First.", [_FakeCitation(2), _FakeCitation(0)]),
            _FakeTextBlock(" Second.", [_FakeCitation(2)]),
            _FakeTextBlock(" Third.", [_FakeCitation(1)]),
        ]
    )


def _thinking_then_answer_message() -> _FakeMessage:
    return _FakeMessage(
        [
            _FakeThinkingBlock("Weighing the passages."),
            _FakeTextBlock("A framing sentence."),
            _FakeTextBlock(" The cited claim.", [_FakeCitation(0)]),
        ]
    )


def _malformed_citation_message() -> _FakeMessage:
    return _FakeMessage([_FakeTextBlock("An answer", [_FakeCitation(9), _FakeCitation(0)])])


def _uncited_message() -> _FakeMessage:
    return _FakeMessage([_FakeTextBlock("Plain prose, no citations.")])


@pytest.mark.parametrize(
    "build_message",
    [
        _cited_answer_message,
        _repeated_citation_message,
        _thinking_then_answer_message,
        _malformed_citation_message,
        _uncited_message,
    ],
)
def test_streamed_text_equals_the_answer_text_that_gets_persisted(build_message) -> None:
    # The parity invariant: concatenating what the reader watched arrive gives exactly
    # the text stored on the turn — marks, positions and numbering included. Both
    # paths are driven from the same message object, so a fixture cannot paper over a
    # divergence.
    evidence = [_evidence("alpha"), _evidence("beta"), _evidence("gamma")]
    final = build_message()
    stream_adapter, _ = _streaming_answer_adapter(
        _FakeStream(deltas=_stream_events_for(final), final_message=final)
    )
    buffered_adapter, _ = _adapter(build_message())

    events = list(stream_adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=evidence))
    buffered = buffered_adapter.generate(mode=MODE_ANSWER, message="q", evidence=evidence)

    streamed = "".join(e.text for e in events if isinstance(e, AnswerTextDelta))
    assert streamed == buffered.text
    assert isinstance(events[-1], AnswerCompleted)
    assert events[-1].answer.text == streamed


def test_teaching_stream_marks_cited_blocks_too() -> None:
    # One stream runner serves both modes, so the teaching turn is marked identically.
    evidence = [_evidence("alpha"), _evidence("beta")]
    final = _FakeMessage([_FakeTextBlock("Here is the teaching.", [_FakeCitation(1)])])
    adapter, _ = _streaming_answer_adapter(
        _FakeStream(deltas=_stream_events_for(final), final_message=final)
    )

    events = list(
        adapter.generate_stream(
            mode=MODE_TEACH,
            message="teach me",
            target_section_path=("Ch", "A"),
            evidence=evidence,
        )
    )

    texts = [e.text for e in events if isinstance(e, AnswerTextDelta)]
    assert "".join(texts) == "Here is the teaching.[^1]"
    assert texts[-1] == "[^1]"


def test_answer_stream_close_closes_the_sdk_stream() -> None:
    # Consumer cancellation (generator close) must close the SDK stream so no
    # provider generation leaks on client disconnect.
    stream = _FakeStream(
        deltas=["one ", "two"], final_message=_FakeMessage([_FakeTextBlock("one two")])
    )
    adapter, _ = _streaming_answer_adapter(stream)

    gen = adapter.generate_stream(mode=MODE_ANSWER, message="q", evidence=[_evidence("alpha")])
    first = next(gen)
    assert first == AnswerTextDelta(text="one ")
    assert stream.closed is False  # still open mid-stream

    gen.close()

    assert stream.closed is True  # closing the consumer closed the SDK stream


def test_teaching_stream_maps_deltas_and_carries_cached_system() -> None:
    evidence = [_evidence("alpha")]
    stream = _FakeStream(
        deltas=["Teach ", "this"], final_message=_FakeMessage([_FakeTextBlock("Teach this")])
    )
    client = _FakeStreamingClient(stream)
    adapter = AnthropicGenerationAdapter(
        api_key="unused-fake",
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        effort=_EFFORT,
        client=client,
    )

    events = list(
        adapter.generate_stream(
            mode=MODE_TEACH,
            message="explain",
            target_section_path=("Ch", "A"),
            history=[HistoryTurn(message="hi", response_text="hello")],
            evidence=evidence,
        )
    )

    deltas = [e for e in events if isinstance(e, AnswerTextDelta)]
    assert deltas == [AnswerTextDelta(text="Teach "), AnswerTextDelta(text="this")]
    assert isinstance(events[-1], AnswerCompleted)
    # The streaming teaching request carries the frozen, cache-broken system prompt.
    call = client.messages.stream_calls[0]
    assert call["system"] == [
        {"type": "text", "text": TEACHING_SYSTEM_PROMPT, "cache_control": _CACHE_1H}
    ]


def test_anthropic_adapter_conforms_to_the_port_protocol() -> None:
    # GEN-12: with generate_stream added, the Anthropic adapter satisfies the
    # runtime-checkable generation port structurally.
    adapter = AnthropicGenerationAdapter(api_key="x", model=_MODEL, max_tokens=_MAX_TOKENS)
    assert isinstance(adapter, GenerationPort)


# --- Provider failure and timeout (QA-17 / TEACH-13) ---------------------------
#
# The adapter catches nothing: a provider failure — a timeout like any other —
# leaves this boundary as the exact exception the SDK raised, in either mode and on
# either path, and it is the application service that turns it into the 502-mapped
# ``AnswerGenerationFailed``. An adapter that swallowed, retried, or re-wrapped a
# provider error would silently change what the reader is told.


class _APITimeoutError(Exception):
    """Stand-in for the SDK's timeout error — an ordinary exception to this layer."""


class _RaisingMessagesResource:
    def __init__(self, error: Exception) -> None:
        self._error = error
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        raise self._error

    def stream(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        raise self._error


class _RaisingClient:
    def __init__(self, error: Exception) -> None:
        self.messages = _RaisingMessagesResource(error)


@pytest.mark.parametrize("mode", [MODE_ANSWER, MODE_TEACH])
@pytest.mark.parametrize("error", [_APITimeoutError("timed out"), RuntimeError("provider down")])
def test_provider_failure_propagates_unwrapped_from_the_buffered_path(
    mode: str, error: Exception
) -> None:
    adapter = AnthropicGenerationAdapter(
        api_key="unused-fake",
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        client=_RaisingClient(error),
    )

    with pytest.raises(type(error)) as excinfo:
        adapter.generate(
            message="q",
            mode=mode,
            evidence=[_evidence("alpha")],
            target_section_path=("Ch", "A") if mode == MODE_TEACH else None,
        )

    assert excinfo.value is error


@pytest.mark.parametrize("mode", [MODE_ANSWER, MODE_TEACH])
@pytest.mark.parametrize("error", [_APITimeoutError("timed out"), RuntimeError("provider down")])
def test_provider_failure_propagates_unwrapped_from_the_streaming_path(
    mode: str, error: Exception
) -> None:
    adapter = AnthropicGenerationAdapter(
        api_key="unused-fake",
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        client=_RaisingClient(error),
    )

    stream = adapter.generate_stream(
        message="q",
        mode=mode,
        evidence=[_evidence("alpha")],
        target_section_path=("Ch", "A") if mode == MODE_TEACH else None,
    )

    with pytest.raises(type(error)) as excinfo:
        list(stream)

    assert excinfo.value is error


# --- Live smoke (GEN-20) — real provider, skipped offline / without a key -------
#
# Derived from the P2-eval AC4 and F5: one real answer call returns cited prose
# grounded in the inline evidence; one real teaching turn does the same; and an
# irrelevant-evidence question returns the sentinel not-found (found=False) — the
# live proof that the relevance-aware decline (F5) works end to end. Marked
# `live` + `eval` so the nightly `pytest -m "live and eval"` runs them; skipped
# whenever `LEARNY_ANTHROPIC_API_KEY` is unset, so CI stays offline.

_LIVE_SKIP = pytest.mark.skipif(
    not os.getenv("LEARNY_ANTHROPIC_API_KEY"),
    reason="LEARNY_ANTHROPIC_API_KEY unset — live Anthropic smoke skipped (CI stays offline)",
)

# Inline evidence drawn from the golden book's chapters (tides / volcanoes /
# printing), so a real call has a single unambiguous passage to cite.
_TIDES = "Ocean tides rise and fall because the moon's gravity pulls seawater across the planet."
_VOLCANO = "A volcano erupts when molten magma escapes upward through a vent in the crust."
_PRINTING = "The printing press let a workshop reproduce a page from movable metal type."


def _live_answer_adapter() -> AnthropicGenerationAdapter:
    return AnthropicGenerationAdapter(
        api_key=os.environ["LEARNY_ANTHROPIC_API_KEY"], model=_MODEL, max_tokens=_MAX_TOKENS
    )


@pytest.mark.live
@pytest.mark.eval
@_LIVE_SKIP
def test_live_answer_returns_cited_prose() -> None:
    evidence = [_evidence(_TIDES)]

    result = _live_answer_adapter().generate(
        question="Why do ocean tides rise and fall?", evidence=evidence
    )

    assert result.found is True
    assert result.text.strip(), "expected synthesized prose"
    assert result.cited_chunk_ids, "expected at least one citation"
    assert set(result.cited_chunk_ids) <= {item.chunk_id for item in evidence}
    assert result.model == _MODEL


@pytest.mark.live
@pytest.mark.eval
@_LIVE_SKIP
def test_live_teaching_turn_returns_cited_prose() -> None:
    evidence = [_evidence(_VOLCANO)]
    adapter = AnthropicGenerationAdapter(
        api_key=os.environ["LEARNY_ANTHROPIC_API_KEY"], model=_MODEL, max_tokens=_MAX_TOKENS
    )

    result = adapter.generate(
        mode=MODE_TEACH,
        message="How does a volcano erupt?",
        target_section_path=("How Volcanoes Erupt",),
        history=[],
        evidence=evidence,
    )

    assert result.found is True
    assert result.text.strip(), "expected synthesized teaching prose"
    assert result.cited_chunk_ids, "expected at least one citation"
    assert set(result.cited_chunk_ids) <= {item.chunk_id for item in evidence}


@pytest.mark.live
@pytest.mark.eval
@_LIVE_SKIP
def test_live_irrelevant_evidence_returns_sentinel_not_found() -> None:
    # F5 live proof: the evidence cannot answer the question, so the model must
    # reply with the sentinel and the adapter maps it to found=False.
    evidence = [_evidence(_PRINTING)]

    result = _live_answer_adapter().generate(
        question="How does photosynthesis convert sunlight inside plant leaves?",
        evidence=evidence,
    )

    assert result.found is False
    assert result.text == ""
    assert result.cited_chunk_ids == ()
