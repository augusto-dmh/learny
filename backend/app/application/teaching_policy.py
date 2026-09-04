"""Application-owned tutor hint ladder (AD-291..AD-294).

Pure next-state functions. No I/O. ``PostConversationTurn`` copies the result
onto the conversation row and into the generation envelope; this module does not
know those seams exist.

``advance`` is the learner-message step (before generate). ``after_tutor_turn``
is the assert→check shift once that tutor reply has persisted (TUTOR-19, TUTOR-21).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.domain.entities import (
    TUTOR_DONT_KNOW_MESSAGE,
    TUTOR_JUST_EXPLAIN_MESSAGE,
    TUTOR_OPENING_MESSAGE,
)

_HINTS = ("pump", "hint", "prompt", "assert")


@dataclass(frozen=True)
class TutorState:
    """Current tutor ladder on a conversation (AD-291).

    ``phase`` and ``hint_level`` are all-or-nothing: both set, or both ``None``
    (Answer threads and pre-cycle teach threads).
    """

    phase: str | None = None
    hint_level: str | None = None
    ordinary_turns: int = 0
    scaffold_misses: int = 0
    check_text: str | None = None


class TeachingPolicy:
    """Next-state function for the tutor ladder. No I/O."""

    @staticmethod
    def is_opening(message: str) -> bool:
        return message.strip() == TUTOR_OPENING_MESSAGE

    @staticmethod
    def is_just_explain(message: str) -> bool:
        return message.strip() == TUTOR_JUST_EXPLAIN_MESSAGE

    @staticmethod
    def is_dont_know(message: str) -> bool:
        return message.strip() == TUTOR_DONT_KNOW_MESSAGE

    @staticmethod
    def advance(state: TutorState, *, message: str, check_after: int) -> TutorState:
        """Return the state the following generate should use."""
        text = message.strip()
        if state.phase == "close":
            return state

        if state.phase == "check":
            if TeachingPolicy.is_just_explain(message) or TeachingPolicy.is_dont_know(message):
                return replace(state, hint_level="assert")
            if text:
                return replace(state, phase="close", check_text=message)
            return state

        if TeachingPolicy.is_opening(message) and state.phase in (None, "open"):
            return TutorState(phase="open", hint_level="pump")

        if state.phase is None:
            return state

        if TeachingPolicy.is_dont_know(message):
            misses = state.scaffold_misses + 1
            hint = _next_hint(state.hint_level)
            if misses >= 2:
                hint = "assert"
            return replace(state, phase="scaffold", hint_level=hint, scaffold_misses=misses)

        if TeachingPolicy.is_just_explain(message):
            return replace(state, hint_level="assert")

        phase = "elicit" if state.phase == "open" else state.phase
        ordinary = state.ordinary_turns + 1
        if phase in ("elicit", "scaffold") and ordinary >= check_after:
            phase = "check"
        return replace(state, phase=phase, ordinary_turns=ordinary)

    @staticmethod
    def after_tutor_turn(state: TutorState) -> TutorState:
        """Shift assert generates into ``check`` once the tutor reply persists."""
        if state.phase in ("check", "close") or state.phase is None:
            return state
        if state.hint_level == "assert":
            return replace(state, phase="check")
        return state


def _next_hint(current: str | None) -> str:
    if current not in _HINTS:
        return "hint"
    index = _HINTS.index(current)
    return _HINTS[min(index + 1, len(_HINTS) - 1)]
