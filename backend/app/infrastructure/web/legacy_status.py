"""Answer-status collapse for the pre-unification endpoints (AD-196).

The unified model tells a scoped miss (``not_found_in_scope`` — the reader's own
selection came up short) apart from a whole-book miss (``not_found_in_source``).
The legacy Ask/Teach clients only ever learned the second spelling, and a legacy
teaching session is scoped, so its misses now arrive here as the first. These
presenters collapse the scoped verdict on the way out — in the JSON bodies and in
the ``data-answer-status`` SSE frame alike — while the stored turn and the unified
surface keep the precise value. Deleted with the legacy endpoints.

Placement rule for the compatibility shim, whose two halves sit in different layers
on purpose. A *value* the unified model knows and the frozen wire does not is
projected here, at the transport edge, because the routers choose it per response
and nothing below them should know the old vocabulary. A *message* attached to an
error travels on the error's own type through the global handlers, so it is authored
where the error is raised — ``_teaching_wording`` / ``_questions_wording`` in
``app/application/{teaching,qa}.py`` — rather than being rebuilt here from a type map
the handlers would have to consult. Both halves die with the endpoints.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace

from app.application.streaming import (
    AskStreamEvent,
    StreamAnswer,
    StreamTurn,
    TurnStreamEvent,
)
from app.domain.entities import NOT_FOUND_IN_SCOPE, NOT_FOUND_IN_SOURCE


def legacy_answer_status(status: str) -> str:
    """Map the scoped not-found verdict onto the only one a legacy client knows."""
    return NOT_FOUND_IN_SOURCE if status == NOT_FOUND_IN_SCOPE else status


def collapse_stream_status(
    events: Iterator[AskStreamEvent | TurnStreamEvent],
) -> Iterator[AskStreamEvent | TurnStreamEvent]:
    """Collapse the terminal event's status so the SSE frame matches the JSON body.

    Text deltas pass through untouched; only the terminal event — the persisted turn
    or the answer result the frame presenter reads the status from — is rewritten,
    and only in this projection. The stored row is never touched.
    """
    for event in events:
        if isinstance(event, StreamTurn):
            yield StreamTurn(
                replace(event.turn, answer_status=legacy_answer_status(event.turn.answer_status))
            )
        elif isinstance(event, StreamAnswer):
            yield StreamAnswer(
                replace(event.result, status=legacy_answer_status(event.result.status))
            )
        else:
            yield event
