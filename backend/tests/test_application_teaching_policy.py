"""Tutor hint ladder — table-driven transitions (TUTOR-16..22).

Each case encodes a spec outcome. A skipped transition (just-explain closing a
check, or the third ordinary staying in elicit) must fail these assertions.
"""

from __future__ import annotations

from app.application.teaching_policy import TeachingPolicy, TutorState
from app.domain.entities import (
    TUTOR_DONT_KNOW_MESSAGE,
    TUTOR_JUST_EXPLAIN_MESSAGE,
    TUTOR_OPENING_MESSAGE,
)

_CHECK_AFTER = 3
_REST = "Photosynthesis stores sunlight as sugar."


def _idle() -> TutorState:
    return TutorState()


def _open() -> TutorState:
    return TutorState(phase="open", hint_level="pump")


def _elicit(*, ordinary: int = 1, hint: str = "pump", misses: int = 0) -> TutorState:
    return TutorState(
        phase="elicit",
        hint_level=hint,
        ordinary_turns=ordinary,
        scaffold_misses=misses,
    )


def _scaffold(*, ordinary: int = 0, hint: str = "hint", misses: int = 1) -> TutorState:
    return TutorState(
        phase="scaffold",
        hint_level=hint,
        ordinary_turns=ordinary,
        scaffold_misses=misses,
    )


def _check(*, hint: str = "assert", ordinary: int = 0, misses: int = 0) -> TutorState:
    return TutorState(
        phase="check",
        hint_level=hint,
        ordinary_turns=ordinary,
        scaffold_misses=misses,
    )


def test_opening_sentinel_starts_open_at_pump() -> None:
    # TUTOR-16
    advanced = TeachingPolicy.advance(
        _idle(), message=TUTOR_OPENING_MESSAGE, check_after=_CHECK_AFTER
    )

    assert (advanced.phase, advanced.hint_level) == ("open", "pump")
    assert TeachingPolicy.after_tutor_turn(advanced) == advanced


def test_opening_retry_while_open_stays_open_at_pump() -> None:
    # TUTOR-12's retry is another opening; the ladder does not treat it as ordinary.
    advanced = TeachingPolicy.advance(
        _open(), message=TUTOR_OPENING_MESSAGE, check_after=_CHECK_AFTER
    )

    assert (advanced.phase, advanced.hint_level) == ("open", "pump")
    assert advanced.ordinary_turns == 0


def test_ordinary_while_open_moves_generate_to_elicit() -> None:
    # TUTOR-17
    advanced = TeachingPolicy.advance(_open(), message="chlorophyll", check_after=_CHECK_AFTER)

    assert advanced.phase == "elicit"
    assert advanced.hint_level == "pump"
    assert advanced.ordinary_turns == 1
    assert TeachingPolicy.after_tutor_turn(advanced) == advanced


def test_dont_know_advances_hint_and_counts_a_scaffold_miss_not_ordinary() -> None:
    # TUTOR-18
    advanced = TeachingPolicy.advance(
        _open(), message=TUTOR_DONT_KNOW_MESSAGE, check_after=_CHECK_AFTER
    )

    assert advanced.phase == "scaffold"
    assert advanced.hint_level == "hint"
    assert advanced.scaffold_misses == 1
    assert advanced.ordinary_turns == 0
    assert TeachingPolicy.after_tutor_turn(advanced) == advanced


def test_dont_know_from_assert_stays_assert() -> None:
    # TUTOR-18 already-assert stays assert
    started = _scaffold(hint="assert", misses=2)
    advanced = TeachingPolicy.advance(
        started, message=TUTOR_DONT_KNOW_MESSAGE, check_after=_CHECK_AFTER
    )

    assert advanced.hint_level == "assert"
    assert advanced.scaffold_misses == 3


def test_trimmed_dont_know_still_matches() -> None:
    # AD-294 exact trimmed match
    advanced = TeachingPolicy.advance(
        _open(), message=f"  {TUTOR_DONT_KNOW_MESSAGE}  ", check_after=_CHECK_AFTER
    )

    assert advanced.scaffold_misses == 1
    assert advanced.ordinary_turns == 0


def test_just_explain_generates_with_assert_then_persists_as_check() -> None:
    # TUTOR-19
    advanced = TeachingPolicy.advance(
        _open(), message=TUTOR_JUST_EXPLAIN_MESSAGE, check_after=_CHECK_AFTER
    )

    assert advanced.hint_level == "assert"
    assert advanced.phase == "open"
    assert advanced.ordinary_turns == 0
    persisted = TeachingPolicy.after_tutor_turn(advanced)
    assert persisted.phase == "check"
    assert persisted.hint_level == "assert"


def test_third_ordinary_moves_generate_to_check() -> None:
    # TUTOR-20 / AD-293. Sensor: a policy that never leaves elicit fails this.
    first = TeachingPolicy.advance(_open(), message="one", check_after=_CHECK_AFTER)
    second = TeachingPolicy.advance(first, message="two", check_after=_CHECK_AFTER)
    third = TeachingPolicy.advance(second, message="three", check_after=_CHECK_AFTER)

    assert first.phase == "elicit"
    assert second.phase == "elicit"
    assert second.ordinary_turns == 2
    assert third.phase == "check"
    assert third.ordinary_turns == 3
    assert TeachingPolicy.after_tutor_turn(third).phase == "check"


def test_ordinary_in_scaffold_also_forces_check_after_n() -> None:
    started = _scaffold(ordinary=2, hint="hint", misses=1)
    advanced = TeachingPolicy.advance(
        started, message="a restatement try", check_after=_CHECK_AFTER
    )

    assert advanced.phase == "check"
    assert advanced.ordinary_turns == 3
    assert advanced.scaffold_misses == 1


def test_two_scaffold_misses_generate_with_assert_then_persist_as_check() -> None:
    # TUTOR-21
    first = TeachingPolicy.advance(
        _open(), message=TUTOR_DONT_KNOW_MESSAGE, check_after=_CHECK_AFTER
    )
    second = TeachingPolicy.advance(
        first, message=TUTOR_DONT_KNOW_MESSAGE, check_after=_CHECK_AFTER
    )

    assert first.scaffold_misses == 1
    assert first.hint_level == "hint"
    assert second.scaffold_misses == 2
    assert second.hint_level == "assert"
    assert second.phase == "scaffold"
    persisted = TeachingPolicy.after_tutor_turn(second)
    assert persisted.phase == "check"
    assert persisted.hint_level == "assert"


def test_ordinary_in_check_closes_and_stores_the_message() -> None:
    # TUTOR-22
    advanced = TeachingPolicy.advance(_check(), message=_REST, check_after=_CHECK_AFTER)

    assert advanced.phase == "close"
    assert advanced.check_text == _REST
    assert TeachingPolicy.after_tutor_turn(advanced).phase == "close"


def test_just_explain_in_check_is_not_a_pass() -> None:
    # TUTOR-22 / AD-292. Sensor: treating the chip as a restatement would close.
    started = _check()
    advanced = TeachingPolicy.advance(
        started, message=TUTOR_JUST_EXPLAIN_MESSAGE, check_after=_CHECK_AFTER
    )

    assert advanced.phase == "check"
    assert advanced.check_text is None
    assert advanced.hint_level == "assert"
    assert TeachingPolicy.after_tutor_turn(advanced).phase == "check"


def test_dont_know_in_check_is_not_a_pass() -> None:
    started = _check(hint="pump")
    advanced = TeachingPolicy.advance(
        started, message=TUTOR_DONT_KNOW_MESSAGE, check_after=_CHECK_AFTER
    )

    assert advanced.phase == "check"
    assert advanced.check_text is None
    assert advanced.hint_level == "assert"
    assert advanced.scaffold_misses == started.scaffold_misses


def test_whitespace_in_check_is_not_a_pass() -> None:
    advanced = TeachingPolicy.advance(_check(), message="   ", check_after=_CHECK_AFTER)

    assert advanced.phase == "check"
    assert advanced.check_text is None


def test_null_phase_ordinary_does_not_start_the_ladder() -> None:
    # TUTOR-26 — Answer / pre-cycle teach. The opening sentinel is the only
    # message that begins a tutor thread.
    advanced = TeachingPolicy.advance(_idle(), message="what is this?", check_after=_CHECK_AFTER)

    assert advanced == _idle()
    assert TeachingPolicy.after_tutor_turn(advanced) == advanced


def test_null_phase_chip_does_not_start_the_ladder() -> None:
    advanced = TeachingPolicy.advance(
        _idle(), message=TUTOR_DONT_KNOW_MESSAGE, check_after=_CHECK_AFTER
    )

    assert advanced.phase is None


def test_close_is_unchanged_by_any_message() -> None:
    closed = TutorState(phase="close", hint_level="assert", check_text=_REST)
    advanced = TeachingPolicy.advance(closed, message="another try", check_after=_CHECK_AFTER)

    assert advanced == closed
