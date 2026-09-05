"""First-session activation recording (unit, in-memory fakes)."""

from __future__ import annotations

import logging
from uuid import uuid4

import pytest

from app.application.activation import (
    ACTIVATION_ACCOUNT_CREATED,
    RecordActivation,
)
from app.application.identity import RegisterUser
from tests.fakes import (
    FakeActivationEventRepository,
    FakeClock,
    FakeCredentialRepository,
    FakePasswordHasher,
    FakeSessionRepository,
    FakeUserRepository,
    SequentialTokenGenerator,
)

VALID_PASSWORD = "correct horse battery"


def test_register_inserts_one_account_created_row() -> None:
    activations = FakeActivationEventRepository()
    clock = FakeClock()
    record = RecordActivation(activations=activations, clock=clock)
    result = RegisterUser(
        users=FakeUserRepository(),
        credentials=FakeCredentialRepository(),
        sessions=FakeSessionRepository(),
        hasher=FakePasswordHasher(),
        tokens=SequentialTokenGenerator(),
        clock=clock,
        record_activation=record,
    )(email="user@example.com", password=VALID_PASSWORD)

    assert list(activations.rows) == [(result.user.id, ACTIVATION_ACCOUNT_CREATED)]


def test_second_record_activation_of_the_same_name_does_not_add_a_row() -> None:
    activations = FakeActivationEventRepository()
    clock = FakeClock()
    record = RecordActivation(activations=activations, clock=clock)
    user_id = uuid4()

    record(user_id=user_id, name=ACTIVATION_ACCOUNT_CREATED)
    record(user_id=user_id, name=ACTIVATION_ACCOUNT_CREATED)

    assert list(activations.rows) == [(user_id, ACTIVATION_ACCOUNT_CREATED)]


def test_record_activation_logs_info_only_on_the_first_insert(
    caplog: pytest.LogCaptureFixture,
) -> None:
    activations = FakeActivationEventRepository()
    record = RecordActivation(activations=activations, clock=FakeClock())
    user_id = uuid4()

    with caplog.at_level(logging.INFO, logger="app.application.activation"):
        record(user_id=user_id, name=ACTIVATION_ACCOUNT_CREATED)
        record(user_id=user_id, name=ACTIVATION_ACCOUNT_CREATED)

    recorded = [r for r in caplog.records if r.message.startswith("activation recorded")]
    assert len(recorded) == 1
    assert str(user_id) in recorded[0].message
    assert ACTIVATION_ACCOUNT_CREATED in recorded[0].message


def test_record_activation_rejects_an_unknown_name() -> None:
    record = RecordActivation(activations=FakeActivationEventRepository(), clock=FakeClock())

    with pytest.raises(ValueError, match="unknown activation name"):
        record(user_id=uuid4(), name="aha_moment")
