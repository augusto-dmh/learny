"""Quiz deck-generation adapters (implement ``QuizGenerationPort``, QUIZ-05).

The provider SDK, model name, and structured-output shapes live only inside these
adapters; callers depend on ``QuizGenerationPort`` and receive Learny-owned candidates.
The default is a deterministic, network-free adapter that makes the deck pipeline
testable offline. The provider factory (``build_quiz_adapter``) arrives with the
Anthropic batch adapter.
"""

from __future__ import annotations

from app.infrastructure.quiz.local import DeterministicQuizAdapter

__all__ = ["DeterministicQuizAdapter"]
