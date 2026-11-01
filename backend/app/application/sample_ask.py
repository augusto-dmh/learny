"""The capped guest sample ask (AD-320 thaw).

One grounded answer about the shared sample for a visitor with no account —
the "no-account taste of the sample" the 2026-09-30 research names. The service
reuses the exact rails an authenticated Ask runs — :class:`RetrieveEvidence`
over the sample source, the shared grounding guard (AD-027), the normal Ask
chain on :class:`~app.domain.ports.GenerationPort`, and the :class:`DailyBudget`
ledger — and persists nothing: no user, no session, no conversation, no turn,
no activation event. A guest who asks costs the sample's own daily budget, not
a per-learner one, so the ledger row is the seeded sample operator's (see the
cycle plan's one-way doors); the per-visitor brake is the web layer's IP-keyed
rate limiter.

Fail-honest by construction: an exhausted budget, a missing sample, and a
generation that grounds nothing each answer their explicit outcome — never a
lower-quality fallback, never placeholder text.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import uuid4

from app.application.budget import KIND_ASK, DailyBudget
from app.application.conversations import MODE_ANSWER
from app.application.errors import AnswerGenerationFailed, SampleUnavailable
from app.application.grounding import ground
from app.application.ingestion import SOURCE_STATUS_READY
from app.application.retrieval import RetrieveEvidence
from app.application.validation import SAMPLE_OPERATOR_EMAIL
from app.domain.entities import Evidence, GeneratedAnswer, User
from app.domain.ports import (
    Clock,
    GenerationPort,
    SourceRepository,
    UserRepository,
)

#: The honest refusal when the sample cannot serve: the seed has not run, the
#: sample is still processing, or its ledger account is absent.
SAMPLE_UNAVAILABLE_COPY = "The sample is unavailable right now. Please try again later."

#: An in-memory identity the retrieval pass runs under. The shared sample is
#: readable by anyone (``readable_source``), so the id is never checked against
#: an owner and never written anywhere — it exists because the retrieval seam
#: takes a user, not because a guest has an account.
GUEST_READER_EMAIL = "guest@learny.invalid"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GuestAnswer:
    """One guest ask's outcome: a grounded answer with citations, or not-found.

    ``model`` records which serving profile answered (the same single-type model
    identity an authenticated turn records); it is ``None`` when the port was
    never invoked or the answer grounded nothing. ``citations`` are empty unless
    ``found`` is true.
    """

    found: bool
    answer: str | None
    citations: list[Evidence]
    model: str | None


class GuestSampleAsk:
    """Answer one visitor question from the shared sample, capped and grounded."""

    def __init__(
        self,
        *,
        sources: SourceRepository,
        users: UserRepository,
        retrieve: RetrieveEvidence,
        generation: GenerationPort,
        budget: DailyBudget,
        clock: Clock,
    ) -> None:
        self._sources = sources
        self._users = users
        self._retrieve = retrieve
        self._generation = generation
        self._budget = budget
        self._clock = clock

    def __call__(self, *, question: str, response_language: str | None = None) -> GuestAnswer:
        # The sample must exist, be ready, and have its ledger identity. All three
        # are deployment facts (the seed owns them), so any miss is one honest 503.
        operator = self._users.get_by_email(SAMPLE_OPERATOR_EMAIL)
        source = self._sources.get_sample()
        if operator is None or source is None or source.status != SOURCE_STATUS_READY:
            raise SampleUnavailable(SAMPLE_UNAVAILABLE_COPY)

        # Budget before anything: an exhausted sample day refuses with nothing
        # retrieved, generated, or spent — the fail-honest cap.
        self._budget.assert_generation(operator.id, kind=KIND_ASK)

        guest = User(id=uuid4(), email=GUEST_READER_EMAIL, created_at=self._clock.now())
        evidence = self._retrieve(user=guest, source_id=source.id, query=question)

        if not evidence:
            # Nothing in the sample to answer from: the explicit not-found
            # outcome — the port is never invoked, so nothing is spent.
            logger.info("guest sample ask answered (found=false, no evidence)")
            return GuestAnswer(found=False, answer=None, citations=[], model=None)

        try:
            generated: GeneratedAnswer = self._generation.generate(
                message=question,
                mode=MODE_ANSWER,
                evidence=evidence,
                history=[],
                target_section_path=None,
                tutor_phase=None,
                hint_level=None,
                response_language=response_language,
            )
        except Exception as exc:  # any port failure maps to 502
            raise AnswerGenerationFailed("Answer generation failed.") from exc

        # Debit after the port returned, before the answer is shaped — the same
        # call-costs-when-it-ran rule an authenticated turn follows. The kind
        # carries the ask counter even when the adapter reported no usage.
        self._budget.record(
            operator.id,
            usd_micros=self._budget.usage_micros(
                generated.usage, generated.profile_id, user_keyed=generated.user_keyed
            ),
            kind=KIND_ASK,
        )

        grounded = ground(generated, evidence)
        if grounded is None:
            # The same grounding contract as every Ask (AD-027): nothing survives,
            # the answer is the explicit not-found — honest, not degraded.
            logger.info("guest sample ask answered (found=false, nothing grounded)")
            return GuestAnswer(found=False, answer=None, citations=[], model=generated.model)
        text, citations = grounded
        # Exactly one content-free log line per completed ask, mirroring the
        # conversation-turn convention — no question or answer text ever logged.
        logger.info("guest sample ask answered (found=true)")
        return GuestAnswer(found=True, answer=text, citations=citations, model=generated.model)
