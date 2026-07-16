"""UI Message Stream v1 presenter — the only module that knows the SSE wire format.

Maps Learny's protocol-free application stream events (``StreamDelta`` and the
terminal ``StreamAnswer`` / ``StreamTurn``) onto Vercel's UI Message Stream v1
parts so Cycle D's ``useChat`` frontend renders tokens, citations, and the answer
status as they arrive. The protocol vocabulary lives *only* here (design §7): the
domain and application layers never learn the wire format, and the JSON endpoints
are untouched.

Frame order (per response): ``start`` → ``text-start`` → ``text-delta``×N →
``text-end`` → ``data-citations`` (the grounded citations, same ``EvidenceView``
projection as the JSON endpoint) → ``data-answer-status`` (``answered`` |
``not_found_in_source``) → ``finish`` → the terminal ``[DONE]``. Message/part ids
are per-response ``uuid4``. A mid-stream ``AnswerGenerationFailed`` (the provider
failing after headers were already sent) is rendered as a protocol ``error`` part
carrying the same generic message as the buffered 502, then the stream terminates.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from fastapi.sse import EventSourceResponse, ServerSentEvent, format_sse_event

from app.application.errors import AnswerGenerationFailed
from app.application.streaming import (
    AskStreamEvent,
    StreamAnswer,
    StreamDelta,
    StreamTurn,
    TurnStreamEvent,
)
from app.domain.entities import Evidence
from app.infrastructure.web.error_handlers import ANSWER_GENERATION_FAILED_DETAIL
from app.infrastructure.web.retrieval import EvidenceView

# Header that opts ``useChat`` into UI Message Stream parsing; without it the client
# silently falls back to plain-text mode and drops every non-text part (research §7).
UI_MESSAGE_STREAM_HEADER_NAME = "x-vercel-ai-ui-message-stream"
UI_MESSAGE_STREAM_PROTOCOL = "v1"


def _terminal(event: StreamAnswer | StreamTurn) -> tuple[list[Evidence], str]:
    """Read the grounded citations and answer status from the terminal event.

    The Q&A stream ends with a :class:`~app.application.streaming.StreamAnswer`
    (a ``QuestionAnswer``); the teaching stream ends with a
    :class:`~app.application.streaming.StreamTurn` (the persisted ``TeachingTurn``).
    Both carry the same citation snapshots and an ``answered`` /
    ``not_found_in_source`` status, projected identically for the client.
    """
    if isinstance(event, StreamAnswer):
        return list(event.result.citations), event.result.status
    return list(event.turn.citations), event.turn.answer_status


def to_ui_message_stream(
    events: Iterator[AskStreamEvent | TurnStreamEvent],
) -> Iterator[ServerSentEvent]:
    """Render application stream events as UI Message Stream v1 SSE frames."""
    message_id = uuid4().hex
    text_id = uuid4().hex
    yield ServerSentEvent(data={"type": "start", "messageId": message_id})
    yield ServerSentEvent(data={"type": "text-start", "id": text_id})

    citations: list[Evidence] = []
    status = ""
    try:
        for event in events:
            if isinstance(event, StreamDelta):
                yield ServerSentEvent(
                    data={"type": "text-delta", "id": text_id, "delta": event.text}
                )
            else:  # terminal StreamAnswer / StreamTurn — carries citations + status
                citations, status = _terminal(event)
    except AnswerGenerationFailed:
        # Provider failed after headers were sent: surface the generic error as a
        # protocol part (never the wrapped detail) and terminate the stream.
        yield ServerSentEvent(
            data={"type": "error", "errorText": ANSWER_GENERATION_FAILED_DETAIL}
        )
        yield ServerSentEvent(raw_data="[DONE]")
        return

    yield ServerSentEvent(data={"type": "text-end", "id": text_id})
    yield ServerSentEvent(
        data={
            "type": "data-citations",
            "data": [
                EvidenceView.from_evidence(c).model_dump(mode="json") for c in citations
            ],
        }
    )
    yield ServerSentEvent(
        data={"type": "data-answer-status", "data": {"status": status}}
    )
    yield ServerSentEvent(data={"type": "finish"})
    yield ServerSentEvent(raw_data="[DONE]")


def _to_wire(frame: ServerSentEvent) -> bytes:
    """Serialize one frame to the same wire bytes FastAPI's SSE dispatch produces."""
    if frame.raw_data is not None:
        data_str: str | None = frame.raw_data
    elif frame.data is not None:
        data_str = json.dumps(jsonable_encoder(frame.data))
    else:
        data_str = None
    return format_sse_event(
        data_str=data_str,
        event=frame.event,
        id=frame.id,
        retry=frame.retry,
        comment=frame.comment,
    )


def to_sse_response(
    events: Iterator[AskStreamEvent | TurnStreamEvent],
) -> EventSourceResponse:
    """Wrap the frame stream in a directly-returned ``EventSourceResponse``.

    Returning the response instance — instead of declaring
    ``response_class=EventSourceResponse`` on the route — matters: the declared-class
    form switches FastAPI to its SSE dispatch, which invokes the handler body directly
    on the event loop (only the *returned generator* is iterated in the threadpool), so
    the eager ownership/readiness guards, query embedding, and hybrid retrieval would
    block every concurrent request. On the regular path a sync handler body runs in the
    threadpool, and Starlette also iterates this sync frame generator in the threadpool.
    Trade-off: no idle keep-alive pings — acceptable because generation frames flow
    continuously once the stream starts.
    """
    return EventSourceResponse(
        (_to_wire(frame) for frame in to_ui_message_stream(events)),
        headers={
            UI_MESSAGE_STREAM_HEADER_NAME: UI_MESSAGE_STREAM_PROTOCOL,
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
