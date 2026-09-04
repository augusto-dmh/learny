"""Application streaming events and the provider-independent sentinel hold-back.

The streaming turn path (design §6) reuses the same guards and grounding as its
buffered sibling, but consumes the generation port's
:class:`~app.domain.entities.AnswerStreamEvent` iterator incrementally. This module
holds the Learny-owned, protocol-free stream events the services yield and the
shared hold-back generator that keeps the not-found sentinel from ever streaming to
a client. No FastAPI / SQLAlchemy / provider-SDK type crosses this boundary
(ADR-0007/0009): the SSE wire vocabulary lives only in the web presenter.
"""

from __future__ import annotations

from collections.abc import Generator, Iterator
from dataclasses import dataclass

from app.application.errors import AnswerGenerationFailed
from app.domain.entities import (
    SENTINEL,
    AnswerReasoningDelta,
    AnswerStreamEvent,
    AnswerTextDelta,
    ConversationTurn,
    GeneratedAnswer,
)

# The turn is searching the book for evidence. Announced before retrieval runs, so
# the wait for it is accounted for rather than blank.
PHASE_SEARCHING = "searching"


@dataclass(frozen=True)
class StreamPhase:
    """The work the turn is starting now — emitted *before* that work runs."""

    phase: str


@dataclass(frozen=True)
class StreamDelta:
    """One chunk of answer text ready to present to the client (post hold-back)."""

    text: str


@dataclass(frozen=True)
class StreamReasoningDelta:
    """One chunk of the model's reasoning, presented as it arrives.

    Distinct from :class:`StreamDelta` all the way to the wire: reasoning is shown
    while the turn is in flight and is not the answer, so it is never held back,
    never grounded, and never persisted.
    """

    text: str


@dataclass(frozen=True)
class StreamTurn:
    """The terminal outcome — the persisted :class:`ConversationTurn`.

    Tutor ladder columns are the conversation's, not the turn's: the buffered JSON
    path reads them off the conversation row, and the stream echoes the same three
    fields here so a live Teach client does not have to refetch every citation of
    every turn to learn one word of phase. Answer threads leave them ``None``.
    """

    turn: ConversationTurn
    tutor_phase: str | None = None
    hint_level: str | None = None
    tutor_check_text: str | None = None


# A turn stream opens with a phase, then yields zero or more reasoning and answer
# deltas, then exactly one terminal turn.
TurnStreamEvent = StreamPhase | StreamDelta | StreamReasoningDelta | StreamTurn


def hold_back_deltas(
    stream: Iterator[AnswerStreamEvent],
) -> Generator[StreamDelta | StreamReasoningDelta, None, GeneratedAnswer]:
    """Yield presentable text deltas and return the authoritative completed answer.

    Provider-independent sentinel guard (design §6): while the accumulated text is
    still a prefix of :data:`~app.domain.entities.SENTINEL`, deltas are buffered
    (never streamed) because the reply might turn out to be the whole-reply
    not-found signal. On divergence the buffered prefix is flushed as one delta and
    subsequent deltas pass straight through. If the whole reply is the sentinel,
    nothing is emitted; a genuine short answer that merely *looked* like a prefix is
    flushed once at completion. The exactly-one :class:`AnswerCompleted` is the
    authoritative result (its ``answer`` is returned for grounding).

    Reasoning deltas are not answer text and take no part in that decision: they
    pass straight through, even while text is still being buffered, so a model that
    thinks before it writes is visible immediately without the sentinel guard ever
    seeing a byte of it.

    Any error from the port stream becomes :class:`AnswerGenerationFailed` (the web
    presenter renders it as a protocol error part, since headers are already sent),
    and the ``finally`` closes the port stream so a consumer disconnect
    (``GeneratorExit``) never leaks a provider generation.
    """
    accumulated = ""
    held = True
    answer: GeneratedAnswer | None = None
    try:
        for event in stream:
            if isinstance(event, AnswerReasoningDelta):
                yield StreamReasoningDelta(text=event.text)
            elif isinstance(event, AnswerTextDelta):
                if not held:
                    yield StreamDelta(text=event.text)
                    continue
                accumulated += event.text
                if SENTINEL.startswith(accumulated):
                    continue  # still possibly the sentinel — keep buffering
                held = False
                yield StreamDelta(text=accumulated)  # diverged — flush the buffered prefix
            else:  # AnswerCompleted — authoritative, always last
                answer = event.answer
        if answer is None:
            # Contract violation: a stream must end with exactly one completed event.
            raise AnswerGenerationFailed("Answer generation failed.")
        if held and accumulated and answer.found and answer.text.strip():
            # A genuine short answer whose text merely coincided with a sentinel prefix.
            yield StreamDelta(text=accumulated)
        return answer
    except AnswerGenerationFailed:
        raise
    except Exception as exc:  # any port failure maps to the generic 502/error part
        raise AnswerGenerationFailed("Answer generation failed.") from exc
    finally:
        close = getattr(stream, "close", None)
        if close is not None:
            close()
