"""The routing adapter hands the response language to whichever adapter serves.

The router owns fail-over policy and nothing about prompts, so the learner's
response language must reach the entry that answers unchanged — the first one,
a fail-over candidate after a pre-delta failure, or the house chain a learner's
chain rides beside — on the buffered and the streamed path alike.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.domain.entities import (
    MODE_ANSWER,
    MODE_TEACH,
    AnswerCompleted,
    AnswerStreamEvent,
    AnswerTextDelta,
    GeneratedAnswer,
)
from app.infrastructure.answering.routing import ChainEntry, RoutingGenerationAdapter
from app.infrastructure.providers import Timeout
from tests.infrastructure.test_answering_routing import _profile


class _RecordingAdapter:
    """A port double that records each call's ``response_language`` and serves.

    ``fail_first`` makes its first call (buffered or streamed) raise a pre-delta
    timeout, so a router fails over past it.
    """

    def __init__(self, model: str, *, fail_first: bool = False) -> None:
        self.model = model
        self._fail = fail_first
        self.languages: list[object] = []

    def _maybe_fail(self) -> None:
        if self._fail:
            self._fail = False
            raise Timeout("hung before speaking")

    def generate(self, **kwargs: object) -> GeneratedAnswer:
        self.languages.append(kwargs.get("response_language", "<missing>"))
        self._maybe_fail()
        return GeneratedAnswer(text="ok", cited_chunk_ids=(), model=self.model, found=True)

    def generate_stream(self, **kwargs: object) -> Iterator[AnswerStreamEvent]:
        self.languages.append(kwargs.get("response_language", "<missing>"))
        return self._events()

    def _events(self) -> Iterator[AnswerStreamEvent]:
        # A stream fails while it is iterated, like the real adapters' streams.
        self._maybe_fail()
        answer = GeneratedAnswer(text="ok", cited_chunk_ids=(), model=self.model, found=True)
        yield AnswerTextDelta(text="ok")
        yield AnswerCompleted(answer=answer)


def _call(router: RoutingGenerationAdapter, *, stream: bool, mode: str, language: str | None):
    kwargs = {
        "message": "q",
        "mode": mode,
        "evidence": (),
        "response_language": language,
    }
    if stream:
        return list(router.generate_stream(**kwargs))[-1].answer
    return router.generate(**kwargs)


@pytest.mark.parametrize("language", ["pt-BR", None])
@pytest.mark.parametrize("stream", [False, True], ids=["buffered", "stream"])
def test_response_language_is_forwarded(stream: bool, language: str | None) -> None:
    # The primary fails before speaking; the fallback serves. Both saw the value.
    primary = _RecordingAdapter("a-model", fail_first=True)
    fallback = _RecordingAdapter("b-model")
    router = RoutingGenerationAdapter(
        (
            ChainEntry(adapter=primary, profile=_profile("primary")),
            ChainEntry(adapter=fallback, profile=_profile("fallback", "local")),
        ),
        rate_retry_delay=0.0,
    )

    served = _call(router, stream=stream, mode=MODE_ANSWER, language=language)

    assert served.profile_id == "fallback"
    assert primary.languages == [language]
    assert fallback.languages == [language]

    # A learner chain with no entry for the mode hands the turn to the house
    # chain, response language included.
    house = _RecordingAdapter("house-model")
    learner = _RecordingAdapter("learner-model")
    beside = RoutingGenerationAdapter(
        (ChainEntry(adapter=learner, profile=_profile("mine", teach=False)),),
        rate_retry_delay=0.0,
        house=house,
    )

    _call(beside, stream=stream, mode=MODE_TEACH, language=language)

    assert learner.languages == []
    assert house.languages == [language]
