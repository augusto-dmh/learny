"""Port-convergence gate — one generation port, mode carried explicitly.

Derived from the cycle's "one generation port" acceptance criteria: the turn path
speaks to a single protocol (no second teaching protocol exists), and that protocol
takes ``mode`` as its own argument with an optional ``target_section_path``, so no
caller or adapter has to infer the mode from whether a target is present.
"""

from __future__ import annotations

import inspect
import typing

import app.domain.ports as ports_module
from app.application.conversations import PostConversationTurn
from app.domain.ports import GenerationPort


def test_only_one_generation_protocol_exists() -> None:
    # The teaching protocol described the same capability with a differently named
    # message parameter and a different argument order; it is gone, and every caller
    # speaks to the one port.
    assert not hasattr(ports_module, "TeachingGenerationPort")
    assert not hasattr(ports_module, "AnswerGenerationPort")


def test_generation_takes_mode_explicitly_with_an_optional_target() -> None:
    # ``mode`` is a required argument of its own: the target section path is a
    # snapshot a scoped conversation carries in either mode, so it can never stand in
    # as the mode signal.
    for method in (GenerationPort.generate, GenerationPort.generate_stream):
        parameters = inspect.signature(method).parameters
        assert parameters["mode"].default is inspect.Parameter.empty
        assert parameters["target_section_path"].default is None
        assert parameters["tutor_phase"].default is None
        assert parameters["hint_level"].default is None


def test_the_turn_service_takes_exactly_one_generator_of_a_single_type() -> None:
    # The union that reading a turn's model identity used to force came from the
    # service holding two differently typed generators. It holds one, annotated with
    # the one port and nothing else.
    hints = typing.get_type_hints(PostConversationTurn.__init__)
    generators = [name for name, hint in hints.items() if hint is GenerationPort]

    assert generators == ["generation"]
    assert typing.get_origin(hints["generation"]) is None
