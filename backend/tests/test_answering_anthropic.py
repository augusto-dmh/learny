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
from uuid import uuid4

from app.application.grounding import ground
from app.domain.entities import Evidence, HistoryTurn
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
