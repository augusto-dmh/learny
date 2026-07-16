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
import os
from uuid import uuid4

import pytest

from app.application.grounding import ground
from app.domain.entities import (
    AnswerCompleted,
    AnswerTextDelta,
    Evidence,
    HistoryTurn,
)
from app.domain.ports import AnswerGenerationPort, TeachingGenerationPort
from app.infrastructure.answering import anthropic as anthropic_module
from app.infrastructure.answering.anthropic import (
    AnthropicAnswerAdapter,
    AnthropicTeachingAdapter,
)
from app.infrastructure.answering.prompts import (
    ANSWER_SYSTEM_PROMPT,
    SENTINEL,
    TEACHING_SYSTEM_PROMPT,
)

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 1024


# --- Fake Anthropic client (records the create call, returns a canned message) ---


class _FakeCitation:
    def __init__(self, document_index: int, *, document_title: str = "") -> None:
        self.type = "char_location"
        self.document_index = document_index
        self.cited_text = "cited"
        self.document_title = document_title


class _FakeTextBlock:
    def __init__(self, text: str, citations: list[_FakeCitation] | None = None) -> None:
        self.type = "text"
        self.text = text
        self.citations = citations


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


def _adapter(message: _FakeMessage) -> tuple[AnthropicAnswerAdapter, _FakeClient]:
    client = _FakeClient(message)
    adapter = AnthropicAnswerAdapter(
        api_key="unused-fake", model=_MODEL, max_tokens=_MAX_TOKENS, client=client
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

    adapter.generate(question="What is X?", evidence=evidence)

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

    adapter.generate(question="q", evidence=[item])

    doc = client.messages.calls[0]["messages"][0]["content"][0]
    assert doc["title"] == item.anchor


# --- Citation mapping (GEN-05) -------------------------------------------------


def test_citations_map_by_document_index_not_title() -> None:
    # The citation's document_title is deliberately wrong; mapping must follow the
    # 0-based document_index into the request's evidence order.
    evidence = [_evidence("alpha"), _evidence("beta")]
    message = _FakeMessage(
        [_FakeTextBlock("answer", [_FakeCitation(1, document_title="MISLEADING")])]
    )
    adapter, _ = _adapter(message)

    result = adapter.generate(question="q", evidence=evidence)

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

    result = adapter.generate(question="q", evidence=evidence)

    # First-occurrence order across blocks (1 then 0); the repeat of 1 is dropped.
    assert result.cited_chunk_ids == (evidence[1].chunk_id, evidence[0].chunk_id)


# --- Sentinel / not-found (GEN-06 + edge cases) --------------------------------


def test_whole_reply_sentinel_is_not_found_with_empty_text() -> None:
    evidence = [_evidence("alpha")]
    adapter, _ = _adapter(_FakeMessage([_FakeTextBlock(SENTINEL)]))

    result = adapter.generate(question="q", evidence=evidence)

    assert result.found is False
    assert result.text == ""
    assert result.cited_chunk_ids == ()
    assert result.model == _MODEL


def test_sentinel_surrounded_by_whitespace_is_not_found() -> None:
    evidence = [_evidence("alpha")]
    adapter, _ = _adapter(_FakeMessage([_FakeTextBlock(f"  {SENTINEL}\n")]))

    result = adapter.generate(question="q", evidence=evidence)

    assert result.found is False
    assert result.text == ""


def test_embedded_sentinel_stays_prose() -> None:
    # An occurrence inside a longer answer is not a not-found signal (leak guard).
    evidence = [_evidence("alpha")]
    prose = f"The term {SENTINEL} is discussed here as an answer."
    message = _FakeMessage([_FakeTextBlock(prose, [_FakeCitation(0)])])
    adapter, _ = _adapter(message)

    result = adapter.generate(question="q", evidence=evidence)

    assert result.found is True
    assert result.text == prose
    assert result.cited_chunk_ids == (evidence[0].chunk_id,)


# --- max_tokens partial (edge case) --------------------------------------------


def test_max_tokens_returns_partial_answer_without_raising() -> None:
    evidence = [_evidence("alpha")]
    message = _FakeMessage(
        [_FakeTextBlock("Partial answer", [_FakeCitation(0)])],
        stop_reason="max_tokens",
    )
    adapter, _ = _adapter(message)

    result = adapter.generate(question="q", evidence=evidence)

    assert result.found is True
    assert result.text == "Partial answer"
    assert result.cited_chunk_ids == (evidence[0].chunk_id,)


# --- Model identity (GEN-04) ---------------------------------------------------


def test_model_identity_readable_without_a_generate_call() -> None:
    adapter = AnthropicAnswerAdapter(
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

    result = adapter.generate(question="q", evidence=evidence)

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
) -> tuple[AnthropicTeachingAdapter, _FakeClient]:
    client = _FakeClient(message)
    adapter = AnthropicTeachingAdapter(
        api_key="unused-fake", model=_MODEL, max_tokens=_MAX_TOKENS, client=client
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
        message="first",
        target_section_path=("Ch 1", "A"),
        history=[HistoryTurn(message="q1", response_text="a1")],
        evidence=[_evidence("alpha")],
    )
    adapter.generate(
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
    assert first_system[0]["cache_control"] == _CACHE_1H


def test_only_latest_history_block_carries_second_breakpoint() -> None:
    history = [
        HistoryTurn(message="q1", response_text="a1"),
        HistoryTurn(message="q2", response_text="a2"),
    ]
    adapter, client = _teaching_adapter(_FakeMessage([_FakeTextBlock("ok")]))

    adapter.generate(
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
        message="Please explain the loci method.",
        target_section_path=("Part I", "Chapter 3", "The Method of Loci"),
        history=[],
        evidence=[_evidence("alpha")],
    )

    text_block = client.messages.calls[0]["messages"][0]["content"][-1]
    assert text_block["type"] == "text"
    assert "Part I > Chapter 3 > The Method of Loci" in text_block["text"]
    assert "Please explain the loci method." in text_block["text"]


def test_teaching_whole_reply_sentinel_is_not_found() -> None:
    adapter, _ = _teaching_adapter(_FakeMessage([_FakeTextBlock(SENTINEL)]))

    result = adapter.generate(
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
        message="teach me",
        target_section_path=("Ch", "A"),
        history=[],
        evidence=evidence,
    )

    assert result.found is True
    assert result.text == "Here is the teaching."
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


class _FakeStream:
    """Fake ``MessageStream``: iterates text events, exposes the final message, closes."""

    def __init__(self, deltas: list[str], final_message: _FakeMessage) -> None:
        self._deltas = deltas
        self._final = final_message
        self.closed = False

    def __iter__(self):  # noqa: ANN204 — yields fake text events
        for text in self._deltas:
            yield _FakeTextStreamEvent(text)

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
) -> tuple[AnthropicAnswerAdapter, _FakeStreamingClient]:
    client = _FakeStreamingClient(stream)
    adapter = AnthropicAnswerAdapter(
        api_key="unused-fake", model=_MODEL, max_tokens=_MAX_TOKENS, client=client
    )
    return adapter, client


def test_answer_stream_maps_text_events_to_deltas_then_one_completed() -> None:
    evidence = [_evidence("alpha")]
    stream = _FakeStream(
        deltas=["Hello ", "world"], final_message=_FakeMessage([_FakeTextBlock("Hello world")])
    )
    adapter, client = _streaming_answer_adapter(stream)

    events = list(adapter.generate_stream(question="q", evidence=evidence))

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


def test_answer_stream_completed_parse_equals_buffered_parse() -> None:
    # The completed event parses the final message with the SAME parser as the
    # buffered path → identical GeneratedAnswer (document_index mapping included).
    evidence = [_evidence("alpha"), _evidence("beta")]
    final = _FakeMessage([_FakeTextBlock("answer", [_FakeCitation(1, document_title="WRONG")])])

    stream_adapter, _ = _streaming_answer_adapter(
        _FakeStream(deltas=["answer"], final_message=final)
    )
    completed = list(stream_adapter.generate_stream(question="q", evidence=evidence))[-1]

    buffered_adapter, _ = _adapter(final)
    buffered = buffered_adapter.generate(question="q", evidence=evidence)

    assert isinstance(completed, AnswerCompleted)
    assert completed.answer == buffered
    assert completed.answer.cited_chunk_ids == (evidence[1].chunk_id,)


def test_answer_stream_close_closes_the_sdk_stream() -> None:
    # Consumer cancellation (generator close) must close the SDK stream so no
    # provider generation leaks on client disconnect.
    stream = _FakeStream(
        deltas=["one ", "two"], final_message=_FakeMessage([_FakeTextBlock("one two")])
    )
    adapter, _ = _streaming_answer_adapter(stream)

    gen = adapter.generate_stream(question="q", evidence=[_evidence("alpha")])
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
    adapter = AnthropicTeachingAdapter(
        api_key="unused-fake", model=_MODEL, max_tokens=_MAX_TOKENS, client=client
    )

    events = list(
        adapter.generate_stream(
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


def test_anthropic_adapters_conform_to_their_port_protocols() -> None:
    # GEN-12: with generate_stream added, the Anthropic adapters satisfy the
    # runtime-checkable generation ports structurally.
    answer = AnthropicAnswerAdapter(api_key="x", model=_MODEL, max_tokens=_MAX_TOKENS)
    teaching = AnthropicTeachingAdapter(api_key="x", model=_MODEL, max_tokens=_MAX_TOKENS)
    assert isinstance(answer, AnswerGenerationPort)
    assert isinstance(teaching, TeachingGenerationPort)


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


def _live_answer_adapter() -> AnthropicAnswerAdapter:
    return AnthropicAnswerAdapter(
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
    adapter = AnthropicTeachingAdapter(
        api_key=os.environ["LEARNY_ANTHROPIC_API_KEY"], model=_MODEL, max_tokens=_MAX_TOKENS
    )

    result = adapter.generate(
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
