"""The request transaction must keep a failed generation turn.

Web clients override ``get_db_connection`` with the shared rolled-back test
connection, so HTTP tests cannot see whether this generator committed. Driving
the generator itself is what fails if the ``AnswerGenerationFailed`` branch is
removed.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.application.errors import AnswerGenerationFailed
from app.infrastructure.web.dependencies import get_db_connection


class _RecordingTransaction:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _RecordingConnection:
    def __init__(self) -> None:
        self.transaction = _RecordingTransaction()
        self.closed = False

    def begin(self) -> _RecordingTransaction:
        return self.transaction

    def close(self) -> None:
        self.closed = True


class _RecordingEngine:
    def __init__(self) -> None:
        self.connection = _RecordingConnection()

    def connect(self) -> _RecordingConnection:
        return self.connection


def _throw(engine: _RecordingEngine, exc: BaseException) -> None:
    gen = get_db_connection(SimpleNamespace())  # request is unused
    next(gen)
    with pytest.raises(type(exc)):
        gen.throw(exc)


def test_generation_failure_commits_the_request_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _RecordingEngine()
    monkeypatch.setattr("app.infrastructure.web.dependencies.get_engine", lambda: engine)

    _throw(engine, AnswerGenerationFailed())

    assert engine.connection.transaction.commits == 1
    assert engine.connection.transaction.rollbacks == 0
    assert engine.connection.closed is True


def test_any_other_handler_exception_rolls_back_the_request_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _RecordingEngine()
    monkeypatch.setattr("app.infrastructure.web.dependencies.get_engine", lambda: engine)

    _throw(engine, RuntimeError("not a generation failure"))

    assert engine.connection.transaction.rollbacks == 1
    assert engine.connection.transaction.commits == 0
    assert engine.connection.closed is True
