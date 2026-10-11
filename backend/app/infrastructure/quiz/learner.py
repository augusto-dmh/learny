"""Cards and decks on a learner's own Anthropic key (ADR-0033).

:class:`LearnerKeyedQuizAdapter` wraps the quiz adapter the composition root
built with one learner's key and marks everything it produces: a deck handle
carries the key's credential row id (so the poll collects with exactly that
key, or fails), and every result is stamped ``user_keyed`` (so the house ledger
debits 0 USD for it). The application keeps receiving a plain
``QuizGenerationPort``; it never learns whose key served.

Only Anthropic keys power cards and decks: the quiz adapters are Anthropic-only
(an OpenAI or Gemini quiz adapter is outside ADR-0033's scope).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import UUID

from app.domain.entities import (
    QuizDeckHandle,
    QuizDeckResult,
    QuizSection,
    SuggestResult,
)
from app.infrastructure.quiz.anthropic import AnthropicQuizAdapter

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.domain.ports import QuizGenerationPort

#: The one provider whose learner keys serve card suggestions and decks.
QUIZ_KEY_PROVIDER = "anthropic"


class LearnerKeyedQuizAdapter:
    """``QuizGenerationPort`` over an adapter built with one learner's key."""

    def __init__(self, inner: QuizGenerationPort, *, credential_id: UUID) -> None:
        self._inner = inner
        self._credential_id = credential_id

    def __repr__(self) -> str:
        return f"LearnerKeyedQuizAdapter(model={self.model!r}, credential_id={self._credential_id})"

    @property
    def model(self) -> str:
        return self._inner.model

    def begin_deck(self, sections: Sequence[QuizSection]) -> QuizDeckHandle:
        handle = self._inner.begin_deck(sections)
        return replace(handle, credential_id=self._credential_id)

    def collect_deck(self, handle: QuizDeckHandle) -> QuizDeckResult | None:
        result = self._inner.collect_deck(handle)
        return None if result is None else replace(result, user_keyed=True)

    def suggest_cards(self, section: QuizSection, quote: str, limit: int) -> SuggestResult:
        return replace(self._inner.suggest_cards(section, quote, limit), user_keyed=True)

    def suggest_note_cards(self, note_body: str, context: str, limit: int) -> SuggestResult:
        return replace(self._inner.suggest_note_cards(note_body, context, limit), user_keyed=True)


def build_user_keyed_quiz_adapter(
    settings: Settings, api_key: str, *, credential_id: UUID
) -> LearnerKeyedQuizAdapter:
    """The quiz adapter for one learner's Anthropic key and ``quiz_model``.

    Built whatever the house provider is: a deployment that serves the house on
    the local adapter still runs a learner's cards and decks on their own key.
    """
    return LearnerKeyedQuizAdapter(
        AnthropicQuizAdapter(
            api_key=api_key,
            model=settings.quiz_model,
            max_tokens=settings.generation_max_tokens,
        ),
        credential_id=credential_id,
    )
