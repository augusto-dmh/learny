"""Once-per-user first-session activation events.

Closed names only: callers never accept a client-supplied event name. The
insert is conflict-do-nothing, so a second stamp of the same name is a no-op.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.domain.ports import ActivationEventRepository, Clock

logger = logging.getLogger(__name__)

ACTIVATION_ACCOUNT_CREATED = "account_created"
ACTIVATION_SAMPLE_OPENED = "sample_opened"
ACTIVATION_FIRST_CITED_ANSWER = "first_cited_answer"
ACTIVATION_FIRST_REVIEW = "first_review"

ACTIVATION_NAMES = frozenset(
    {
        ACTIVATION_ACCOUNT_CREATED,
        ACTIVATION_SAMPLE_OPENED,
        ACTIVATION_FIRST_CITED_ANSWER,
        ACTIVATION_FIRST_REVIEW,
    }
)


class RecordActivation:
    """Insert a closed activation name once per user; log INFO on the first write."""

    def __init__(self, *, activations: ActivationEventRepository, clock: Clock) -> None:
        self._activations = activations
        self._clock = clock

    def __call__(self, *, user_id: UUID, name: str) -> None:
        if name not in ACTIVATION_NAMES:
            raise ValueError(f"unknown activation name: {name}")
        inserted = self._activations.insert_if_absent(
            user_id=user_id,
            name=name,
            occurred_at=self._clock.now(),
        )
        if inserted:
            logger.info(
                "activation recorded user_id=%s name=%s",
                user_id,
                name,
            )
