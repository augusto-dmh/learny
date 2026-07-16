"""Application streaming events and the provider-independent sentinel hold-back.

The streaming answer/turn paths (design §6) reuse the same guards and grounding as
their buffered siblings, but consume the generation port's
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
    AnswerStreamEvent,
    AnswerTextDelta,
    GeneratedAnswer,
    QuestionAnswer,
    TeachingTurn,
)


@dataclass(frozen=True)
class StreamDelta:
    """One chunk of answer text ready to present to the client (post hold-back)."""

    text: str


@dataclass(frozen=True)
class StreamAnswer:
    """The terminal Q&A outcome — the same :class:`QuestionAnswer` the buffered path returns."""

    result: QuestionAnswer


@dataclass(frozen=True)
class StreamTurn:
    """The terminal teaching outcome — the persisted :class:`TeachingTurn`."""

    turn: TeachingTurn


# The Q&A stream yields zero or more deltas then exactly one terminal answer; the
# teaching stream yields zero or more deltas then exactly one terminal turn.
AskStreamEvent = StreamDelta | StreamAnswer
TurnStreamEvent = StreamDelta | StreamTurn


def hold_back_deltas(
    stream: Iterator[AnswerStreamEvent],
) -> Generator[StreamDelta, None, GeneratedAnswer]:
    """Yield presentable text deltas and return the authoritative completed answer.

    Provider-independent sentinel guard (design §6): while the accumulated text is
    still a prefix of :data:`~app.domain.entities.SENTINEL`, deltas are buffered
    (never streamed) because the reply might turn out to be the whole-reply
    not-found signal. On divergence the buffered prefix is flushed as one delta and
    subsequent deltas pass straight through. If the whole reply is the sentinel,
    nothing is emitted; a genuine short answer that merely *looked* like a prefix is
    flushed once at completion. The exactly-one :class:`AnswerCompleted` is the
    authoritative result (its ``answer`` is returned for grounding).

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
            if isinstance(event, AnswerTextDelta):
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
