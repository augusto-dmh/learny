"""Conversation domain contracts (ADR-0029).

Unit coverage for the vocabulary a client reads off the wire — the per-turn modes and
the three answer statuses — and for the two conversation shapes the unified model
exists to allow: scoped (a teach target) and whole-book (none). Pure domain — no DB,
no framework.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.entities import (
    ANSWERED,
    MODE_ANSWER,
    MODE_TEACH,
    NOT_FOUND_IN_SCOPE,
    NOT_FOUND_IN_SOURCE,
    Conversation,
    ConversationSummary,
    ConversationTurn,
)

_NOW = datetime(2026, 7, 25, 12, 0, 0, tzinfo=UTC)


def _conversation(**overrides) -> Conversation:  # noqa: ANN003
    fields = {
        "id": uuid4(),
        "source_id": uuid4(),
        "title": "Chapter Two",
        "scope_anchors": ("ch2.xhtml",),
        "include_notes": False,
        "target_anchor": "ch2.xhtml",
        "target_section_path": ("Chapter Two",),
        "target_title": "Chapter Two",
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    return Conversation(**{**fields, **overrides})


def test_mode_values_are_the_wire_strings() -> None:
    # These cross the API verbatim in both directions (request ``mode``, stored turn),
    # so renaming either constant is a breaking change, not an implementation detail.
    assert (MODE_ANSWER, MODE_TEACH) == ("answer", "teach")


def test_answer_statuses_are_the_wire_strings_and_stay_distinct() -> None:
    assert (ANSWERED, NOT_FOUND_IN_SOURCE, NOT_FOUND_IN_SCOPE) == (
        "answered",
        "not_found_in_source",
        "not_found_in_scope",
    )
    # Scope is a promise: "your selection could not answer this" and "the book could
    # not answer this" are different verdicts, and a client can only offer to widen
    # the first. Collapsing them into one value would hide a scoped search.
    assert NOT_FOUND_IN_SCOPE != NOT_FOUND_IN_SOURCE
    assert len({ANSWERED, NOT_FOUND_IN_SOURCE, NOT_FOUND_IN_SCOPE}) == 3


def test_whole_book_conversation_has_empty_scope_and_no_target() -> None:
    # The shape the generalization exists to allow: no target trio at all, and the
    # empty tuple as the single spelling of "the whole book" (never None).
    whole_book = _conversation(
        title="What is this book about?",
        scope_anchors=(),
        include_notes=True,
        target_anchor=None,
        target_section_path=None,
        target_title=None,
    )

    assert whole_book.scope_anchors == ()
    assert (
        whole_book.target_anchor,
        whole_book.target_section_path,
        whole_book.target_title,
    ) == (None, None, None)
    assert whole_book.include_notes is True


def test_scoped_conversation_keeps_the_given_anchor_order() -> None:
    scoped = _conversation(scope_anchors=("ch5.xhtml", "ch2.xhtml"))

    # Stored scope is the reader's own selection, in the order they gave it —
    # expansion and dedup happen per turn, not on the stored value.
    assert scoped.scope_anchors == ("ch5.xhtml", "ch2.xhtml")


def test_conversation_and_turn_are_immutable() -> None:
    conversation = _conversation()
    turn = ConversationTurn(
        id=uuid4(),
        conversation_id=conversation.id,
        turn_index=0,
        message="explain this",
        mode=MODE_TEACH,
        answer_status=ANSWERED,
        answer_text="because",
        model="local-extractive",
        evidence_count=1,
        citations=(),
        created_at=_NOW,
    )

    with pytest.raises(FrozenInstanceError):
        conversation.title = "renamed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        turn.answer_status = NOT_FOUND_IN_SCOPE  # type: ignore[misc]


def test_summary_names_the_book_a_conversation_belongs_to() -> None:
    # The global list spans every source the caller owns, so a row that named only
    # the conversation would not say which book it is about.
    conversation = _conversation()
    summary = ConversationSummary(conversation=conversation, turn_count=3, source_title="A Book")

    assert summary.conversation is conversation
    assert (summary.turn_count, summary.source_title) == (3, "A Book")
