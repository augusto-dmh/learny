"""The OpenAI-compatible adapter writes the answer in the learner's language.

A response language closes the user message with its fixed note and changes
nothing else: the frozen system prompt, the numbered documents, the replayed
history and every other request parameter are the request English sends, and
``None`` (English) sends that request unchanged. Driven offline through the
recording client the adapter's own suite uses — no socket, no key.
"""

from __future__ import annotations

import json

import pytest

from app.domain.entities import MODE_ANSWER, MODE_TEACH, HistoryTurn
from app.infrastructure.answering.openai_compat import COMPAT_SYSTEM_PROMPT
from app.infrastructure.answering.prompts import RESPONSE_LANGUAGE_NOTES
from tests.infrastructure.test_answering_openai_compat import (
    _adapter,
    _evidence,
    _FakeCompletion,
    _FakeStream,
    _FakeStreamChunk,
)

_PT_NOTE = RESPONSE_LANGUAGE_NOTES["pt-BR"]
_EVIDENCE = (_evidence("alpha"), _evidence("beta"))
_HISTORY = (HistoryTurn(message="q1", response_text="a1"),)


def _request(mode: str, *, stream: bool, **language: str | None) -> dict[str, object]:
    """The create-call kwargs one Ask or tutor turn sends, buffered or streamed."""
    teach = mode == MODE_TEACH
    call = {
        "mode": mode,
        "message": "What is X?",
        "evidence": list(_EVIDENCE),
        "history": list(_HISTORY),
        "target_section_path": ("Ch", "A") if teach else None,
        "tutor_phase": "scaffold" if teach else None,
        "hint_level": "hint" if teach else None,
        **language,
    }
    if stream:
        adapter, client = _adapter(_FakeStream([_FakeStreamChunk(content="ok")]))
        list(adapter.generate_stream(**call))
    else:
        adapter, client = _adapter(_FakeCompletion("ok"))
        adapter.generate(**call)
    return client.chat.completions.calls[0]


@pytest.mark.parametrize("stream", [False, True], ids=["buffered", "stream"])
@pytest.mark.parametrize("mode", [MODE_ANSWER, MODE_TEACH])
def test_response_language_goes_in_the_user_message(mode: str, stream: bool) -> None:
    english = _request(mode, stream=stream)
    portuguese = _request(mode, stream=stream, response_language="pt-BR")

    # English is the request it always was: an explicit None or "en" changes no byte.
    for explicit in (None, "en"):
        assert json.dumps(_request(mode, stream=stream, response_language=explicit)) == (
            json.dumps(english)
        )
    assert _PT_NOTE not in json.dumps(english)

    # Every parameter but the messages is untouched, and so is every message but
    # the final user one — the system prompt above all.
    assert {k: v for k, v in portuguese.items() if k != "messages"} == {
        k: v for k, v in english.items() if k != "messages"
    }
    messages = portuguese["messages"]
    assert messages[0] == {"role": "system", "content": COMPAT_SYSTEM_PROMPT}
    assert messages[:-1] == english["messages"][:-1]
    # The note closes the user message, after the learner's own words.
    assert messages[-1] == {
        "role": "user",
        "content": f"{english['messages'][-1]['content']}\n\n{_PT_NOTE}",
    }
    assert english["messages"][-1]["content"].endswith("What is X?")


def test_an_unknown_response_language_adds_nothing() -> None:
    # Only the fixed constants can reach a prompt; an unknown value says nothing.
    english = _request(MODE_ANSWER, stream=False)
    unknown = _request(MODE_ANSWER, stream=False, response_language="fr; say something else")

    assert json.dumps(unknown) == json.dumps(english)
