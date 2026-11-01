"""The capped guest sample ask (integration + unit, live test DB).

Application level: the service reuses the exact Ask rails — sample-only
retrieval, the shared grounding guard, the house generation chain, and the
sample's own daily budget — asserted before and debited after the call, with
nothing persisted for the visitor. Web level: the boundary refuses an empty or
oversized question with 422 before anything runs, throttles per trusted client
IP with ``Retry-After``, and answers the honest outcomes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.application.budget import DailyBudget, TokenPrices, usd_to_micros
from app.application.errors import (
    AnswerGenerationFailed,
    DailyBudgetExhausted,
    SampleUnavailable,
)
from app.application.retrieval import RetrieveEvidence
from app.application.sample_ask import SAMPLE_UNAVAILABLE_COPY, GuestSampleAsk
from app.core.config import get_settings
from app.domain.entities import (
    Evidence,
    GeneratedAnswer,
    Source,
    TokenUsage,
    User,
)
from app.infrastructure.web.dependencies import get_guest_sample_ask
from app.infrastructure.web.rate_limit import (
    InMemoryFixedWindowRateLimiter,
    set_sample_ask_limiter,
)
from app.main import create_app
from tests.conftest import TEST_ORIGIN, requires_db
from tests.fakes import (
    FakeAiSpendDayRepository,
    FakeAnswerGeneration,
    FakeClock,
    FakeEmbeddingPort,
    FakeRetrievalPort,
    FakeSourceRepository,
    FakeUserRepository,
)

pytestmark = requires_db

SAMPLE_OPERATOR_EMAIL = "sample-operator@learny.invalid"
_NOW = datetime(2026, 10, 31, 12, 0, 0, tzinfo=UTC)


def _evidence(chunk_id: UUID | None = None) -> Evidence:
    return Evidence(
        chunk_id=chunk_id or uuid4(),
        source_id=uuid4(),
        section_path=("I. Laying Plans",),
        anchor="sun-tzu#I.1",
        page_span=None,
        snippet="All warfare is based on deception.",
        score=1.0,
    )


def _sample_source(status: str = "ready") -> Source:
    return Source(
        id=uuid4(),
        user_id=uuid4(),
        title="The Art of War",
        filename="art-of-war.epub",
        content_type="application/epub+zip",
        byte_size=10_000,
        checksum="a" * 64,
        object_key="samples/art-of-war.epub",
        status=status,
        created_at=_NOW,
        updated_at=_NOW,
        is_sample=True,
    )


def _generated(
    evidence: list[Evidence], *, text: str = "Deception precedes every battle."
) -> GeneratedAnswer:
    return GeneratedAnswer(
        text=text,
        cited_chunk_ids=(evidence[0].chunk_id,),
        model="local-extractive",
        found=True,
    )


def _usage(input_tokens: int, output_tokens: int) -> TokenUsage:
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


class _positions_stub:
    """The guest pass never reads a reading position: the stub fails loudly."""

    def get(self, user_id: UUID, source_id: UUID):
        raise AssertionError("the guest retrieval pass must not read positions")


class _authorize_stub:
    def __call__(self, *, user: User, owner_id: UUID) -> None:
        raise AssertionError("the sample short-circuits before ownership")


def _service(
    *,
    source: Source | None = "default",
    operator: User | object = "default",
    results: list[Evidence] | None = None,
    generation: FakeAnswerGeneration | None = None,
    spend: FakeAiSpendDayRepository | None = None,
    ask_daily_cap: int = 50,
) -> tuple[GuestSampleAsk, FakeAiSpendDayRepository, FakeAnswerGeneration]:
    """Build the guest service on fakes. The ``"default"`` sentinels install a
    ready sample and its operator; ``None`` removes them, so a test can name
    the missing-deployment fact directly."""
    spend = spend or FakeAiSpendDayRepository()
    evidence = results if results is not None else [_evidence()]
    generation = generation or FakeAnswerGeneration(
        answer=_generated(evidence) if evidence else None
    )
    sources = FakeSourceRepository()
    if source == "default":
        sources.add(_sample_source())
    elif source is not None:
        sources.add(source)
    retrieve = RetrieveEvidence(
        sources=sources,
        retrieval=FakeRetrievalPort(results=evidence),
        embeddings=FakeEmbeddingPort(),
        positions=_positions_stub(),
        authorize=_authorize_stub(),
        semantic_limit=8,
        lexical_limit=8,
        rrf_k=60,
        ef_search=40,
        default_top_k=6,
        activations=None,
        clock=None,
    )
    budget = DailyBudget(
        repo=spend,
        clock=FakeClock(now=_NOW),
        daily_cap_micros=usd_to_micros(0.5),
        prices=TokenPrices(
            input_micros_per_million=usd_to_micros(3.0),
            output_micros_per_million=usd_to_micros(15.0),
            embed_micros_per_million=usd_to_micros(0.13),
        ),
        ask_daily_cap=ask_daily_cap,
        teach_start_daily_cap=0,
    )
    users = FakeUserRepository()
    if operator == "default":
        users.add(User(id=uuid4(), email=SAMPLE_OPERATOR_EMAIL, created_at=_NOW))
    elif operator is not None:
        users.add(operator)
    service = GuestSampleAsk(
        sources=sources,
        users=users,
        retrieve=retrieve,
        generation=generation,
        budget=budget,
        clock=FakeClock(now=_NOW),
    )
    return service, spend, generation


# --- Application level ----------------------------------------------------------


def test_guest_askes_the_sample_grounded_without_an_account() -> None:
    """A guest question returns a grounded answer with citations, and the
    negotiated language reaches the port. Nothing is persisted anywhere: no
    activation row, no conversation, no user — the in-memory guest identity
    never reaches a repository, and the sample-opened activation stays an
    account-holder's event."""
    service, spend, generation = _service()
    result = service(question="What is warfare based on?", response_language="pt-BR")

    assert result.found is True
    assert result.answer == "Deception precedes every battle."
    assert len(result.citations) == 1
    assert result.model == "local-extractive"
    # The language reached the port; the mode is a plain ask with no history.
    assert generation.response_languages == ["pt-BR"]
    assert generation.calls[0]["mode"] == "answer"
    assert generation.history_calls[0] == []
    # Exactly one debit, on the sample's UTC-day row — not on a guest identity.
    assert len(spend.record_calls) == 1
    assert spend.record_calls[0][1] == _NOW.date()
    assert spend.record_calls[0][3:] == (1, 0)


def test_answers_the_honest_outcomes_for_a_missing_sample_or_nothing_grounded() -> None:
    """No seeded operator (the ledger identity) → the unavailable refusal; a
    sample whose ingestion never finished → the same refusal; a generation that
    grounds nothing → the explicit not-found with no citations; retrieval coming
    up empty → the same not-found with the port never invoked."""
    service, _, _ = _service(operator=None)
    with pytest.raises(SampleUnavailable):
        service(question="anything")

    service, _, _ = _service(source=_sample_source(status="processing"))
    with pytest.raises(SampleUnavailable):
        service(question="anything")

    stray = FakeAnswerGeneration(
        answer=GeneratedAnswer(text="Unrelated prose.", cited_chunk_ids=(), model="m", found=True)
    )
    service, spend, _ = _service(results=[_evidence()], generation=stray)
    result = service(question="What is warfare based on?")
    assert result.found is False
    assert result.answer is None
    assert result.citations == []
    assert result.model == "m"
    # The call ran and costs the sample's day even when it grounded nothing —
    # the same call-costs-when-it-ran rule an authenticated turn follows.
    assert len(spend.record_calls) == 1

    service, spend, generation = _service(results=[])
    result = service(question="What is warfare based on?")
    assert result.found is False
    assert generation.calls == []
    assert spend.record_calls == []


def test_refuses_honestly_when_the_sample_budget_is_gone() -> None:
    """An exhausted sample day refuses with the come-back-tomorrow copy before
    retrieval or generation runs — on the ask counter and on the USD alike."""
    operator = User(id=uuid4(), email=SAMPLE_OPERATOR_EMAIL, created_at=_NOW)

    spend = FakeAiSpendDayRepository()
    spend.record(operator.id, _NOW.date(), usd_micros=0, asks=50, teach_starts=0)
    service, _, generation = _service(operator=operator, spend=spend, ask_daily_cap=50)
    with pytest.raises(DailyBudgetExhausted):
        service(question="What is warfare based on?")
    assert generation.calls == []
    assert len(spend.record_calls) == 1  # only the seeded row, nothing new

    spend2 = FakeAiSpendDayRepository()
    spend2.record(operator.id, _NOW.date(), usd_micros=usd_to_micros(0.5), asks=0, teach_starts=0)
    service, _, generation = _service(operator=operator, spend=spend2)
    with pytest.raises(DailyBudgetExhausted):
        service(question="What is warfare based on?")
    assert generation.calls == []


def test_debits_the_sample_ledger_only_after_success() -> None:
    """A failed generation debits nothing; a successful one debits the reported
    usage at the operator catalog plus one ask, and the guest's identity is
    never the ledger key."""
    evidence = [_evidence()]
    breaking = FakeAnswerGeneration(error=RuntimeError("provider down"))
    service, spend, _ = _service(results=evidence, generation=breaking)
    with pytest.raises(AnswerGenerationFailed):
        service(question="What is warfare based on?")
    assert spend.record_calls == []

    usage_answer = GeneratedAnswer(
        text="Deception precedes every battle.",
        cited_chunk_ids=(evidence[0].chunk_id,),
        model="claude-sonnet-5",
        found=True,
        usage=_usage(1000, 200),
        profile_id="claude-sonnet-5",
    )
    service, spend, _ = _service(
        results=evidence, generation=FakeAnswerGeneration(answer=usage_answer)
    )
    result = service(question="What is warfare based on?")
    assert result.found is True
    (recorded_user, day, usd_micros, asks, teach_starts) = spend.record_calls[0]
    assert day == _NOW.date()
    # 1000 input + 200 output tokens at the default catalog (3.0/15.0 USD per
    # million): 3000 micros + 3000 micros = 6000 micros, one ask, no teach start.
    assert usd_micros == 6000
    assert (asks, teach_starts) == (1, 0)
    # The ledger row resolves for the operator user the service resolved.
    assert spend.get_for_day(recorded_user, day) is not None


# --- Web level ------------------------------------------------------------------


class _RecordingService:
    """A ``GuestSampleAsk`` double at the web boundary: records the question.

    With no explicit result it answers a small grounded one, so route tests
    that exercise the refusals and the caps still get a 200 shape back.
    """

    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result or _GuestAnswerStub(
            found=True, answer="A grounded answer.", citations=[_evidence()], model="m"
        )
        self.error = error
        self.questions: list[str] = []
        self.languages: list[str | None] = []

    def __call__(self, *, question: str, response_language=None):
        self.questions.append(question)
        self.languages.append(response_language)
        if self.error is not None:
            raise self.error
        return self.result


def _client(service, monkeypatch: pytest.MonkeyPatch, *, max_attempts: int = 3) -> TestClient:
    from tests.conftest import clear_settings_and_generation_caches

    # A trusted Origin for the state-changing gate + the non-Secure cookie the
    # TestClient can carry, exactly like the shared auth_client fixture.
    monkeypatch.setenv("LEARNY_CSRF_TRUSTED_ORIGINS", TEST_ORIGIN)
    monkeypatch.setenv("LEARNY_SESSION_COOKIE_SECURE", "false")
    clear_settings_and_generation_caches()
    app = create_app()
    app.dependency_overrides[get_guest_sample_ask] = lambda: service
    set_sample_ask_limiter(
        InMemoryFixedWindowRateLimiter(max_attempts=max_attempts, window_seconds=86400)
    )
    return TestClient(app, headers={"Origin": TEST_ORIGIN})


def test_refuses_an_empty_or_oversized_question_before_any_spend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty (or whitespace-only) and over-ceiling questions answer 422 without
    the service ever seeing them; a question at the ceiling proceeds."""
    service = _RecordingService()
    # A generous window: the limiter counts every boundary request on purpose
    # (it protects the route, not the handler), and this test names validation.
    client = _client(service, monkeypatch, max_attempts=10)

    resp = client.post("/api/sample/ask", json={"question": ""})
    assert resp.status_code == 422, resp.text
    resp = client.post("/api/sample/ask", json={"question": "   "})
    assert resp.status_code == 422, resp.text

    long_question = "x" * (get_settings().guest_sample_question_max_chars + 1)
    resp = client.post("/api/sample/ask", json={"question": long_question})
    assert resp.status_code == 422, resp.text

    # All three refusals happened at the boundary: nothing reached the service,
    # so no retrieval, generation, or budget spend was possible.
    assert service.questions == []

    at_ceiling = "x" * get_settings().guest_sample_question_max_chars
    resp = client.post("/api/sample/ask", json={"question": at_ceiling})
    assert resp.status_code == 200, resp.text
    assert service.questions == [at_ceiling]


def test_the_visitors_language_rides_the_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The locale switcher's cookie (an anonymous visitor's only choice) picks
    the answer language; no cookie falls back to the browser's Accept-Language;
    neither present means English (``None``)."""
    service = _RecordingService()
    client = _client(service, monkeypatch)

    resp = client.post(
        "/api/sample/ask", json={"question": "hello"}, cookies={"learny_locale": "pt-BR"}
    )
    assert resp.status_code == 200, resp.text
    assert service.languages == ["pt-BR"]

    service2 = _RecordingService()
    client2 = _client(service2, monkeypatch)
    client2.post(
        "/api/sample/ask",
        json={"question": "hello"},
        headers={"Accept-Language": "pt-BR,en;q=0.8"},
    )
    assert service2.languages == ["pt-BR"]

    service3 = _RecordingService()
    client3 = _client(service3, monkeypatch)
    client3.post("/api/sample/ask", json={"question": "hello"})
    assert service3.languages == [None]


def test_rate_limits_guest_asks_per_client_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fourth ask inside the window answers 429 with ``Retry-After``; the
    key is the trusted client IP + route, so header tricks mint nothing and a
    refused request never reached the service."""
    service = _RecordingService()
    client = _client(service, monkeypatch)

    for _ in range(3):
        resp = client.post("/api/sample/ask", json={"question": "hello"})
        assert resp.status_code == 200, resp.text
    resp = client.post("/api/sample/ask", json={"question": "hello"})
    assert resp.status_code == 429, resp.text
    assert "Retry-After" in resp.headers
    assert len(service.questions) == 3


def test_guest_askes_the_sample_grounded_without_an_account_web(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Through the route: 200 with the grounded answer, citations, and the
    sample label; a port failure answers 502 with the generic body; a missing
    sample answers 503 with the honest copy."""
    evidence = _evidence()
    grounded = _RecordingService(
        result=_GuestAnswerStub(
            found=True,
            answer="Deception precedes every battle.",
            citations=[evidence],
            model="local-extractive",
        )
    )
    client = _client(grounded, monkeypatch)
    resp = client.post("/api/sample/ask", json={"question": "What is warfare based on?"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["found"] is True
    assert body["sample"] is True
    assert body["answer"] == "Deception precedes every battle."
    assert body["citations"][0]["chunk_id"] == str(evidence.chunk_id)
    assert body["citations"][0]["anchor"] == evidence.anchor

    broke = _RecordingService(error=AnswerGenerationFailed("Answer generation failed."))
    client = _client(broke, monkeypatch)
    resp = client.post("/api/sample/ask", json={"question": "hello"})
    assert resp.status_code == 502, resp.text
    from app.infrastructure.web.error_handlers import ANSWER_GENERATION_FAILED_DETAIL

    assert resp.json()["detail"] == ANSWER_GENERATION_FAILED_DETAIL

    unavailable = _RecordingService(error=SampleUnavailable(SAMPLE_UNAVAILABLE_COPY))
    client = _client(unavailable, monkeypatch)
    resp = client.post("/api/sample/ask", json={"question": "hello"})
    assert resp.status_code == 503, resp.text
    assert resp.json()["detail"] == SAMPLE_UNAVAILABLE_COPY


class _GuestAnswerStub:
    def __init__(self, *, found, answer, citations, model) -> None:
        self.found = found
        self.answer = answer
        self.citations = citations
        self.model = model
