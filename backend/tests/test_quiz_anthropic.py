"""B3 gate — the Anthropic Message Batches quiz adapter (unit, fake client, offline).

Pins the batched-generation contract without a network call: ``begin_deck`` submits one
structured-output request per section whose ``source_chunk_id`` enum is that section's
chunk ids; ``collect_deck`` returns ``None`` while the batch is processing, maps ended
results back to candidates by ``custom_id`` once it ends, and records per-request failures
as section errors (partial-success deck, QUIZ-05).
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from app.domain.entities import QuizItemType, QuizSection
from app.infrastructure.quiz.anthropic import AnthropicQuizAdapter

# --- Fake Anthropic batch client (the narrow slice the adapter uses) -------------


class _Block:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _Message:
    def __init__(self, text: str) -> None:
        self.content = [_Block(text)]


class _Result:
    def __init__(self, type_: str, message: _Message | None = None) -> None:
        self.type = type_
        self.message = message


class _Response:
    def __init__(self, custom_id: str, result: _Result) -> None:
        self.custom_id = custom_id
        self.result = result


class _Batch:
    def __init__(self, id_: str, processing_status: str) -> None:
        self.id = id_
        self.processing_status = processing_status


class _FakeBatches:
    def __init__(self, *, status: str = "ended", results: list[_Response] | None = None) -> None:
        self._status = status
        self._results = results or []
        self.created_requests: list[dict] | None = None
        self.create_calls = 0

    def create(self, *, requests):  # noqa: ANN001, ANN201
        self.create_calls += 1
        self.created_requests = list(requests)
        return _Batch("batch_abc", "in_progress")

    def retrieve(self, batch_id):  # noqa: ANN001, ANN201
        return _Batch(batch_id, self._status)

    def results(self, batch_id):  # noqa: ANN001, ANN201
        return iter(self._results)


class _FakeMessages:
    def __init__(self, batches: _FakeBatches, reply: str | None = None) -> None:
        self.batches = batches
        self._reply = reply
        self.create_kwargs: dict | None = None
        self.create_calls = 0

    def create(self, **kwargs):  # noqa: ANN003, ANN201
        self.create_calls += 1
        self.create_kwargs = kwargs
        return _Message(self._reply or "")


class _FakeClient:
    def __init__(self, batches: _FakeBatches, reply: str | None = None) -> None:
        self.messages = _FakeMessages(batches, reply)


def _adapter(
    batches: _FakeBatches, *, reply: str | None = None
) -> AnthropicQuizAdapter:
    return AnthropicQuizAdapter(
        api_key="sk-test",
        model="claude-haiku-4-5",
        max_tokens=1024,
        client=_FakeClient(batches, reply),
    )


def _section(title: str, chunk_ids) -> QuizSection:
    return QuizSection(
        section_path=("Unit", title),
        anchor=f"{title}.xhtml#s",
        title=title,
        chunks=tuple((cid, f"Text for {title} chunk {cid}.") for cid in chunk_ids),
    )


def _items_json(source_chunk_id) -> str:
    return json.dumps(
        {
            "items": [
                {
                    "item_type": "free_recall",
                    "question": "Q1?",
                    "answer": "A1",
                    "source_chunk_id": str(source_chunk_id),
                    "anchor_quote": "A verbatim sentence.",
                },
                {
                    "item_type": "cloze",
                    "question": "The ____ term.",
                    "answer": "key",
                    "source_chunk_id": str(source_chunk_id),
                    "anchor_quote": "The key term.",
                },
            ]
        }
    )


# --- begin_deck -----------------------------------------------------------------


def test_begin_deck_submits_one_request_per_section_with_constrained_schema() -> None:
    chunk_a, chunk_b = uuid4(), uuid4()
    section_a = _section("A", [chunk_a])
    section_b = _section("B", [chunk_b])
    batches = _FakeBatches()
    adapter = _adapter(batches)

    handle = adapter.begin_deck([section_a, section_b])

    assert batches.create_calls == 1
    assert len(batches.created_requests) == 2
    # Each request is a structured-output message constraining source_chunk_id to that
    # section's chunk ids (QUIZ-05).
    first = batches.created_requests[0]
    assert first["params"]["model"] == "claude-haiku-4-5"
    schema = first["params"]["output_config"]["format"]["schema"]
    enum = schema["properties"]["items"]["items"]["properties"]["source_chunk_id"]["enum"]
    assert enum == [str(chunk_a)]
    second_enum = batches.created_requests[1]["params"]["output_config"]["format"]["schema"][
        "properties"
    ]["items"]["items"]["properties"]["source_chunk_id"]["enum"]
    assert second_enum == [str(chunk_b)]
    # Custom ids are unique and batch-legal.
    ids = [r["custom_id"] for r in batches.created_requests]
    assert len(set(ids)) == 2
    assert all(all(ch.isalnum() or ch in "-_" for ch in cid) for cid in ids)
    # The handle carries the batch id and the section map for polling.
    assert handle.provider == "anthropic"
    assert handle.batch_id == "batch_abc"
    assert set(handle.payload["sections"]) == set(ids)


def test_begin_deck_with_no_sections_creates_no_batch() -> None:
    batches = _FakeBatches()
    adapter = _adapter(batches)

    handle = adapter.begin_deck([])

    assert batches.create_calls == 0
    assert handle.batch_id is None
    # collect returns an empty result immediately, never None.
    result = adapter.collect_deck(handle)
    assert result is not None
    assert result.candidates == ()
    assert result.errors == ()


# --- collect_deck ---------------------------------------------------------------


def test_collect_deck_returns_none_while_processing() -> None:
    chunk = uuid4()
    batches = _FakeBatches(status="in_progress")
    adapter = _adapter(batches)
    handle = adapter.begin_deck([_section("A", [chunk])])

    assert adapter.collect_deck(handle) is None


def test_collect_deck_maps_succeeded_results_to_candidates() -> None:
    chunk = uuid4()
    section = _section("A", [chunk])
    # Build the handle first to learn the custom_id, then wire matching results.
    plan = _adapter(_FakeBatches())
    handle = plan.begin_deck([section])
    custom_id = next(iter(handle.payload["sections"]))

    batches = _FakeBatches(
        status="ended",
        results=[_Response(custom_id, _Result("succeeded", _Message(_items_json(chunk))))],
    )
    adapter = _adapter(batches)
    result = adapter.collect_deck(handle)

    assert result is not None
    assert result.errors == ()
    assert len(result.candidates) == 2
    assert {c.item_type for c in result.candidates} == {
        QuizItemType.FREE_RECALL,
        QuizItemType.CLOZE,
    }
    assert all(c.source_chunk_id == chunk for c in result.candidates)


def test_collect_deck_records_per_request_error_but_keeps_others() -> None:
    good_chunk, bad_chunk = uuid4(), uuid4()
    handle = _adapter(_FakeBatches()).begin_deck(
        [_section("Good", [good_chunk]), _section("Bad", [bad_chunk])]
    )
    good_id, bad_id = list(handle.payload["sections"])

    batches = _FakeBatches(
        status="ended",
        results=[
            _Response(good_id, _Result("succeeded", _Message(_items_json(good_chunk)))),
            _Response(bad_id, _Result("errored")),  # per-request failure
        ],
    )
    result = _adapter(batches).collect_deck(handle)

    assert len(result.candidates) == 2  # the good section still contributes
    assert len(result.errors) == 1
    assert bad_id in result.errors[0]
    assert "errored" in result.errors[0]


def test_collect_deck_malformed_json_becomes_section_error() -> None:
    chunk = uuid4()
    handle = _adapter(_FakeBatches()).begin_deck([_section("A", [chunk])])
    custom_id = next(iter(handle.payload["sections"]))

    batches = _FakeBatches(
        status="ended",
        results=[_Response(custom_id, _Result("succeeded", _Message("not json at all")))],
    )
    result = _adapter(batches).collect_deck(handle)

    assert result.candidates == ()
    assert len(result.errors) == 1
    assert custom_id in result.errors[0]


# --- suggest_cards (quote-scoped, single synchronous call — CAP-02) --------------


def test_suggest_cards_constrains_source_chunk_id_to_the_section_chunks() -> None:
    chunk_a, chunk_b = uuid4(), uuid4()
    section = _section("A", [chunk_a, chunk_b])
    adapter = _adapter(_FakeBatches(), reply=_items_json(chunk_a))

    adapter.suggest_cards(section, "The key term.", 3)

    kwargs = adapter._get_client().messages.create_kwargs
    schema = kwargs["output_config"]["format"]["schema"]
    enum = schema["properties"]["items"]["items"]["properties"]["source_chunk_id"]["enum"]
    assert enum == [str(chunk_a), str(chunk_b)]
    assert kwargs["model"] == "claude-haiku-4-5"


def test_suggest_cards_issues_exactly_one_message_and_no_batch() -> None:
    chunk = uuid4()
    batches = _FakeBatches()
    adapter = _adapter(batches, reply=_items_json(chunk))

    adapter.suggest_cards(_section("A", [chunk]), "The key term.", 3)

    assert adapter._get_client().messages.create_calls == 1
    assert batches.create_calls == 0


def test_suggest_cards_never_exceeds_the_limit() -> None:
    chunk = uuid4()
    # The stubbed reply carries two items; a limit of one must truncate it.
    adapter = _adapter(_FakeBatches(), reply=_items_json(chunk))

    candidates = adapter.suggest_cards(_section("A", [chunk]), "The key term.", 1)

    assert len(candidates) == 1


def test_suggest_cards_parses_candidates_from_the_structured_reply() -> None:
    chunk = uuid4()
    adapter = _adapter(_FakeBatches(), reply=_items_json(chunk))

    candidates = adapter.suggest_cards(_section("A", [chunk]), "The key term.", 3)

    assert {c.item_type for c in candidates} == {
        QuizItemType.FREE_RECALL,
        QuizItemType.CLOZE,
    }
    assert all(c.source_chunk_id == chunk for c in candidates)


def test_suggest_cards_malformed_reply_raises_for_a_retryable_failure() -> None:
    chunk = uuid4()
    adapter = _adapter(_FakeBatches(), reply="not json at all")

    with pytest.raises(ValueError):
        adapter.suggest_cards(_section("A", [chunk]), "The key term.", 3)


def test_suggest_cards_with_a_non_positive_limit_calls_no_provider() -> None:
    chunk = uuid4()
    adapter = _adapter(_FakeBatches(), reply=_items_json(chunk))

    assert adapter.suggest_cards(_section("A", [chunk]), "The key term.", 0) == []
    assert adapter._get_client().messages.create_calls == 0


def test_model_identity_is_the_configured_quiz_model() -> None:
    assert _adapter(_FakeBatches()).model == "claude-haiku-4-5"


def test_suggest_cards_bounds_the_foreground_call_with_a_timeout() -> None:
    """The one synchronous generation call must not inherit the SDK's 600s default.

    It runs on the shared threadpool while a student waits on a popover, so an
    unbounded read holds a slot long after they have given up. The deck path is
    batched and asynchronous, so it is deliberately left alone.
    """
    chunk = uuid4()
    adapter = _adapter(_FakeBatches(), reply=_items_json(chunk))

    adapter.suggest_cards(_section("A", [chunk]), "The key term.", 3)

    timeout = adapter._get_client().messages.create_kwargs["timeout"]
    assert timeout is not None
    assert 0 < timeout <= 60
