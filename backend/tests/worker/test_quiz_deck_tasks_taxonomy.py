"""Deck-task fault classification gate (unit, fake adapters, no DB, no broker).

Derived from the deck-task acceptance criteria: a transport-class failure raised
by the adapter — including the newly translated Learny taxonomy errors — keeps
taking the *retryable* path (a retry is scheduled, the job is left running), so
the translation changed which class the task sees without changing what the task
does about it. The terminal contrast (an undeclared handle provider fails with
no retry at all) is pinned in the provider-pinning suite.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.domain.entities import QuizDeckHandle, QuizDeckResult
from app.infrastructure.providers import ProviderUnavailable, RateLimited, Timeout
from app.worker.tasks import poll_quiz_deck

_poll = poll_quiz_deck.run.__func__


class FakeSelf:
    """A controllable bound-task ``self``: request.retries, max_retries, retry()."""

    class RetrySignal(Exception):
        """Sentinel raised by :meth:`retry`, standing in for Celery's ``Retry``."""

    def __init__(self, *, retries: int = 0, max_retries: int = 3) -> None:
        self.request = SimpleNamespace(retries=retries)
        self.max_retries = max_retries
        self.retry_calls: list[dict] = []

    def retry(self, *, exc, countdown):  # noqa: ANN001, ANN202
        self.retry_calls.append({"exc": exc, "countdown": countdown})
        raise self.RetrySignal


class FakeQuizAdapter:
    """``QuizGenerationPort`` double whose ``collect_deck`` raises the stubbed error."""

    model = "fake-quiz@1"

    def __init__(self, error: Exception) -> None:
        self._error = error

    def begin_deck(self, sections):  # noqa: ANN001, ANN201
        raise AssertionError("begin_deck must not be called by the poll task")

    def collect_deck(self, handle: QuizDeckHandle) -> QuizDeckResult | None:
        raise self._error


@pytest.mark.parametrize(
    "error",
    [
        Timeout("the provider call exceeded its wall-clock bound"),
        RateLimited("the provider answered 429"),
        ProviderUnavailable("the provider could not be reached"),
    ],
    ids=["timeout", "rate-limited", "unavailable"],
)
def test_a_translated_transport_failure_still_takes_the_retry_path(error: Exception) -> None:
    fake = FakeQuizAdapter(error)
    bound = FakeSelf(retries=0, max_retries=3)
    handle = QuizDeckHandle(provider="anthropic", batch_id="batch-1", payload={}).to_payload()
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

    with patch("app.worker.tasks.build_quiz_adapter", lambda settings, provider=None: fake):
        with pytest.raises(FakeSelf.RetrySignal):
            _poll(bound, str(uuid4()), handle, future)

    # Exactly one retry, with a positive backoff, carrying the translated error
    # itself — exactly what a raw provider fault has always produced.
    assert len(bound.retry_calls) == 1
    assert bound.retry_calls[0]["exc"] is error
    assert bound.retry_calls[0]["countdown"] > 0
