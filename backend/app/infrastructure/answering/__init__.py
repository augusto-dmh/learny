"""Answer-generation adapters (implement ``AnswerGenerationPort``, ADR-0007).

The provider SDK, model name, and citation format live only inside these
adapters; callers depend on ``AnswerGenerationPort`` and receive a Learny-owned
``GeneratedAnswer``. The default is a deterministic, network-free extractive
adapter (AD-024) that makes the answer path testable offline.
"""

from app.infrastructure.answering.local import (
    DeterministicAnswerAdapter,
    DeterministicTeachingAdapter,
)

__all__ = ["DeterministicAnswerAdapter", "DeterministicTeachingAdapter"]
