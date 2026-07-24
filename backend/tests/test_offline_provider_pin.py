"""The offline suite must stay network-free regardless of a local ``backend/.env``.

These tests pin the contract of the autouse ``_force_local_providers`` fixture
(conftest): a bare ``pytest`` resolves the deterministic ``local`` adapters, no real
provider client is built, and an explicit provider override still reaches the real
factory branch. See spec AC-1/AC-2/AC-5.
"""

from __future__ import annotations

import os

import pytest

from app.core.config import get_settings
from app.infrastructure.answering import (
    AnthropicAnswerAdapter,
    AnthropicTeachingAdapter,
    DeterministicAnswerAdapter,
    DeterministicTeachingAdapter,
    build_answer_adapter,
    build_teaching_adapter,
)
from app.infrastructure.embeddings import (
    DeterministicEmbeddingAdapter,
    OpenAIEmbeddingAdapter,
    build_embedding_adapter,
)
from app.infrastructure.quiz import (
    AnthropicQuizAdapter,
    DeterministicQuizAdapter,
    build_quiz_adapter,
)


def test_offline_suite_pins_local_providers() -> None:
    """AC-1: the autouse pin sets both provider vars to ``local`` and settings follow.

    Asserting the ``os.environ`` value (not just the settings default) is what kills
    a pin that is removed: without the fixture the vars are absent, not ``"local"``.
    """
    assert os.environ.get("LEARNY_GENERATION_PROVIDER") == "local"
    assert os.environ.get("LEARNY_EMBEDDING_PROVIDER") == "local"

    settings = get_settings()
    assert settings.generation_provider == "local"
    assert settings.embedding_provider == "local"


def test_default_factories_are_deterministic() -> None:
    """AC-5: every factory returns the network-free adapter in the default context."""
    settings = get_settings()
    assert isinstance(build_answer_adapter(settings), DeterministicAnswerAdapter)
    assert isinstance(build_teaching_adapter(settings), DeterministicTeachingAdapter)
    assert isinstance(build_quiz_adapter(settings), DeterministicQuizAdapter)
    assert isinstance(build_embedding_adapter(settings), DeterministicEmbeddingAdapter)


def test_explicit_generation_override_reaches_real_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-2: an explicit ``anthropic`` choice wins over the default-local pin."""
    monkeypatch.setenv("LEARNY_GENERATION_PROVIDER", "anthropic")
    monkeypatch.setenv("LEARNY_ANTHROPIC_API_KEY", "test-key")
    get_settings.cache_clear()

    settings = get_settings()
    assert isinstance(build_answer_adapter(settings), AnthropicAnswerAdapter)
    assert isinstance(build_teaching_adapter(settings), AnthropicTeachingAdapter)
    assert isinstance(build_quiz_adapter(settings), AnthropicQuizAdapter)


def test_explicit_embedding_override_reaches_real_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-2: an explicit ``openai`` choice wins over the default-local pin."""
    monkeypatch.setenv("LEARNY_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("LEARNY_OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()

    settings = get_settings()
    assert isinstance(build_embedding_adapter(settings), OpenAIEmbeddingAdapter)
