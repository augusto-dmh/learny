"""The learner key never surfaces: an end-to-end canary run (live DB, ADR-0033).

A canary key goes through the whole lifecycle: add, test, an Ask turn, a failed
Explain turn, a note card suggestion, a deck (begin, poll, settle), a KEK
rotation, a replace and a delete. Every channel the plan names is captured and
scanned for it: every line the Learny log handler emitted (all loggers, DEBUG,
JSON format), every API response body, the strings of the exceptions the
system raises, every Celery task argument, and the ``repr`` of credential
entities and built adapters.

The fakes stand in for the provider SDKs and behave the way a careless SDK
might: they log the key in a request-header dump and quote it in an exception.
So the canary really reaches the log channel, and the run proves the masking
catches it rather than proving nothing was ever written. The negative control
writes the canary through an unmasked handler and asserts the same scanner
reports it.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.core.logging import SensitiveDataFilter, configure_logging
from app.domain.entities import (
    AnswerStreamEvent,
    GeneratedAnswer,
    QuizDeckHandle,
    QuizDeckResult,
    QuizGenerationJob,
    QuizJobStatus,
    SuggestResult,
    TokenUsage,
    User,
)
from app.infrastructure.db.provider_credentials import SqlAlchemyProviderCredentialRepository
from app.infrastructure.db.repositories import SqlAlchemyQuizJobRepository
from app.infrastructure.providers.errors import RequestRejected
from app.infrastructure.security.secrets_envelope import SealedSecretError, SecretsEnvelope
from tests.conftest import clear_settings_and_generation_caches, requires_db
from tests.test_web_byok_cards import _highlight
from tests.test_web_cards import cards_client  # noqa: F401 — a fixture
from tests.test_web_user_generation import _post_turn, _seed_conversation, _seed_source
from tests.worker.test_quiz_deck_pinning import FakeSelf

pytestmark = requires_db

_KEK_1 = os.urandom(32)
_KEK_2 = os.urandom(32)
_SDK_LOGGER = logging.getLogger("anthropic._base_client")

_HOUSE = {
    "id": "house",
    "kind": "local",
    "model": "local-extractive",
    "max_tokens": 64,
    "price_input_usd_per_million_tokens": 3.0,
    "price_output_usd_per_million_tokens": 15.0,
    "price_cache_read_usd_per_million_tokens": 0.3,
    "price_cache_creation_usd_per_million_tokens": 3.75,
    "grounding": "verified-spans",
    "ask_enabled": True,
    "teach_enabled": True,
}
_BYOK = {
    **_HOUSE,
    "id": "byok-claude",
    "kind": "anthropic",
    "model": "claude-byok",
    "user_key_provider": "anthropic",
}


def _canary(tag: str) -> str:
    return f"{_PREFIX}{tag}-{secrets.token_hex(16)}"


_PREFIX = "sk-ant-api03-"


def scan(channels: dict[str, list[str]], canaries: tuple[str, ...]) -> list[tuple[str, int]]:
    """Every (channel, index) whose text holds any 12-character run of a canary's secret part.

    The shared provider prefix is public, so only runs inside the part after it count.
    """
    secrets_only = [c.removeprefix(_PREFIX) for c in canaries]
    fragments = {s[start : start + 12] for s in secrets_only for start in range(len(s) - 11)}
    hits = []
    for name, texts in channels.items():
        for index, text in enumerate(texts):
            if any(fragment in text for fragment in fragments):
                hits.append((name, index))
    return hits


class _SdkAuthError(Exception):
    """What a careless SDK raises: the rejected key quoted in the message."""


class _GenerationFake:
    """Stands in for ``AnthropicGenerationAdapter``; logs and raises like a leaky SDK."""

    fail = False

    def __init__(self, *, api_key: str, model: str, max_tokens: int, **_: object) -> None:
        self._api_key = api_key
        self.model = model

    def generate(self, *, evidence: Any, **_: object) -> GeneratedAnswer:  # noqa: ANN401
        _SDK_LOGGER.debug("Request options: %s", {"headers": {"x-api-key": self._api_key}})
        if _GenerationFake.fail:
            try:
                raise _SdkAuthError(f"invalid x-api-key: {self._api_key}")
            except _SdkAuthError as exc:
                _SDK_LOGGER.warning("provider call failed", exc_info=True)
                raise RequestRejected("the provider rejected the request (401)") from exc
        return GeneratedAnswer(
            text="served",
            cited_chunk_ids=(evidence[0].chunk_id,) if evidence else (),
            model=self.model,
            found=True,
            usage=TokenUsage(input_tokens=10, output_tokens=10),
        )

    def generate_stream(self, **_: object) -> Iterator[AnswerStreamEvent]:
        raise AssertionError("buffered turns only")


class _QuizFake:
    """Stands in for ``AnthropicQuizAdapter``; logs its key in a header dump."""

    def __init__(self, *, api_key: str, model: str, max_tokens: int) -> None:
        self._api_key = api_key
        self.model = model

    #: Collects across instances: the begin's inline collect and the poll's.
    collects = 0

    def _dump(self) -> None:
        _SDK_LOGGER.debug("Request headers: x-api-key=%s", self._api_key)

    def suggest_note_cards(self, note_body: str, context: str, limit: int) -> SuggestResult:
        self._dump()
        return SuggestResult(candidates=())

    def begin_deck(self, sections: Any) -> QuizDeckHandle:  # noqa: ANN401
        self._dump()
        return QuizDeckHandle(provider="anthropic", batch_id="batch-canary")

    def collect_deck(self, handle: QuizDeckHandle) -> QuizDeckResult | None:
        self._dump()
        _QuizFake.collects += 1
        return None if _QuizFake.collects == 1 else QuizDeckResult(candidates=(), errors=())


class _ProbeClient:
    """Stands in for ``anthropic.Anthropic`` in the real probe: the key is rejected."""

    def __init__(self, *, api_key: str, **_: object) -> None:
        self._api_key = api_key
        self.models = self

    def list(self, **_: object) -> None:
        error = _SdkAuthError(f"401 invalid x-api-key {self._api_key}")
        error.status_code = 401  # type: ignore[attr-defined]
        raise error

    def close(self) -> None:
        pass


@contextmanager
def _learny_log_capture() -> Iterator[io.StringIO]:
    """Everything the Learny handler emits, all loggers at DEBUG, JSON lines."""
    configure_logging(level=logging.DEBUG, log_format="json")
    root = logging.getLogger()
    handler = next(h for h in root.handlers if getattr(h, "_learny", False))
    buffer = io.StringIO()
    previous = handler.setStream(buffer)
    try:
        yield buffer
    finally:
        handler.setStream(previous)
        configure_logging(level=logging.INFO, log_format="human")


class _SharedEngine:
    """The worker's engine, bound to the test's one rolled-back transaction."""

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    @contextmanager
    def begin(self) -> Iterator[Connection]:
        with self._conn.begin_nested():
            yield self._conn

    connect = begin


def _set_kek(monkeypatch: pytest.MonkeyPatch, current: bytes, previous: bytes | None) -> None:
    monkeypatch.setenv("LEARNY_SECRETS_KEK", base64.b64encode(current).decode())
    if previous is None:
        monkeypatch.delenv("LEARNY_SECRETS_KEK_PREVIOUS", raising=False)
    else:
        monkeypatch.setenv("LEARNY_SECRETS_KEK_PREVIOUS", base64.b64encode(previous).decode())
    clear_settings_and_generation_caches()


def test_canary_never_surfaces(
    cards_client: TestClient,  # noqa: F811
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import anthropic

    import app.cli.rotate_secrets_kek as rotation
    import app.infrastructure.answering as answering
    import app.infrastructure.quiz.learner as learner
    from app.infrastructure.answering import build_user_keyed_adapter
    from app.infrastructure.providers import GenerationProfileSettings
    from app.infrastructure.quiz.learner import build_user_keyed_quiz_adapter
    from app.infrastructure.web import dependencies
    from app.infrastructure.worker.enqueuer import CeleryNoteIndexEnqueuer, CeleryQuizDeckEnqueuer
    from app.worker.tasks import generate_quiz_deck, poll_quiz_deck

    canary, replacement = _canary("CANARY"), _canary("REPLACED")
    real_generation_adapter = answering.AnthropicGenerationAdapter
    real_quiz_adapter = learner.AnthropicQuizAdapter
    monkeypatch.setenv("LEARNY_GENERATION_PROFILES", json.dumps([_HOUSE, _BYOK]))
    _set_kek(monkeypatch, _KEK_1, None)
    monkeypatch.setattr(answering, "AnthropicGenerationAdapter", _GenerationFake)
    monkeypatch.setattr(learner, "AnthropicQuizAdapter", _QuizFake)
    monkeypatch.setattr(anthropic, "Anthropic", _ProbeClient)
    monkeypatch.setattr("app.worker.tasks.get_engine", lambda: _SharedEngine(db_conn))
    monkeypatch.setattr(rotation, "_uow", lambda: _SharedEngine(db_conn).begin())
    _GenerationFake.fail = False
    _QuizFake.collects = 0

    responses: list[str] = []
    exceptions: list[str] = []
    celery_args: list[str] = []
    reprs: list[str] = []

    def _capture_task(*args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        celery_args.append(json.dumps({"args": args, "kwargs": kwargs}, default=str))

    with _learny_log_capture() as logs:
        learner_ctx = _highlight(cards_client, db_conn, "canary@example.com")
        user_id, csrf = UUID(learner_ctx["user_id"]), learner_ctx["csrf"]
        headers = {"X-CSRF-Token": csrf}
        conversation = _seed_conversation(db_conn, _seed_source(db_conn, str(user_id)), scope=())

        def _call(resp: Any) -> Any:  # noqa: ANN401
            responses.append(resp.text)
            return resp

        # add, list, test (the real probe; the fake SDK rejects and quotes the key)
        assert (
            _call(
                cards_client.put(
                    "/api/me/provider-keys/anthropic", json={"api_key": canary}, headers=headers
                )
            ).status_code
            == 200
        )
        _call(cards_client.get("/api/me/provider-keys"))
        tested = _call(cards_client.post("/api/me/provider-keys/anthropic/test", headers=headers))
        assert tested.json() == {"ok": False, "reason": "rejected"}

        # an Ask turn on the key, then an Explain turn whose provider call fails
        assert _call(_post_turn(cards_client, conversation, csrf)).status_code == 201
        _GenerationFake.fail = True
        failed = _call(_post_turn(cards_client, conversation, csrf, origin="explain_selection"))
        assert failed.status_code == 502
        _GenerationFake.fail = False

        # a note card suggestion on the key
        assert (
            _call(
                cards_client.post(
                    f"/api/notes/{learner_ctx['note_id']}/cards/suggest", headers=headers
                )
            ).status_code
            == 200
        )

        # a deck: begin (pending), poll (still pending), poll (done)
        job_id = uuid4()
        now = datetime.now(UTC)
        SqlAlchemyQuizJobRepository(db_conn).add(
            QuizGenerationJob(
                id=job_id,
                source_id=learner_ctx["source_id"],
                status=QuizJobStatus.QUEUED,
                attempts=0,
                generated_count=0,
                discarded_count=0,
                failed_sections=0,
                last_error=None,
                created_at=now,
                updated_at=now,
            )
        )
        deadline = (now + timedelta(hours=1)).isoformat()
        with (
            patch("app.worker.tasks.generate_quiz_deck.apply_async", side_effect=_capture_task),
            patch("app.worker.tasks.refresh_note_cards.apply_async", side_effect=_capture_task),
        ):
            # What the web layer enqueues for this learner: ids only.
            CeleryQuizDeckEnqueuer().enqueue_quiz_deck(
                source_id=learner_ctx["source_id"], job_id=job_id
            )
            CeleryNoteIndexEnqueuer().enqueue_refresh_cards(UUID(learner_ctx["note_id"]))
        with patch("app.worker.tasks.poll_quiz_deck.apply_async", side_effect=_capture_task):
            generate_quiz_deck.run.__func__(FakeSelf(), str(learner_ctx["source_id"]), str(job_id))
            handle = json.loads(celery_args[-1])["kwargs"]["args"][1]
            poll_quiz_deck.run.__func__(FakeSelf(), str(job_id), handle, deadline)
        assert SqlAlchemyQuizJobRepository(db_conn).get_by_id(job_id).status == (
            QuizJobStatus.SUCCEEDED
        )

        # rotate the KEK, then serve a turn under the rotated wrap
        _set_kek(monkeypatch, _KEK_2, _KEK_1)
        assert rotation.main([]) in (0, 1)  # 1 only for other tests' rows under other KEKs
        assert _call(_post_turn(cards_client, conversation, csrf)).status_code == 201

        # reprs of what holds or wraps the key
        repo = SqlAlchemyProviderCredentialRepository(db_conn, SecretsEnvelope(_KEK_2, (_KEK_1,)))
        credential = repo.get(user_id, "anthropic")
        assert credential is not None
        assert repo.reveal(credential) == canary  # the canary really is what is stored
        settings = dependencies.get_settings()
        profile = GenerationProfileSettings(**_BYOK)
        monkeypatch.setattr(answering, "AnthropicGenerationAdapter", real_generation_adapter)
        monkeypatch.setattr(learner, "AnthropicQuizAdapter", real_quiz_adapter)
        reprs += [
            repr(credential),
            repr(repo),
            repr(
                dependencies.get_learner_credentials(
                    db_conn, User(id=user_id, email="canary@example.com", created_at=now)
                )
            ),
            repr(build_user_keyed_adapter(profile, settings, canary)),
            repr(build_user_keyed_quiz_adapter(settings, canary, credential_id=credential.id)),
            repr(dependencies._user_adapters),
            repr(dependencies._user_quiz_adapters),
        ]

        # exceptions the system raises around a key
        for attempt in (
            lambda: repo.replace(user_id, "anthropic", canary + " "),
            lambda: SecretsEnvelope(_KEK_2).open(
                SecretsEnvelope(_KEK_2).seal(canary, user_id=user_id, provider="anthropic"),
                user_id=uuid4(),
                provider="anthropic",
            ),
        ):
            with pytest.raises((ValueError, SealedSecretError)) as raised:
                attempt()
            exceptions += [str(raised.value), repr(raised.value)]

        # replace, then delete
        assert (
            _call(
                cards_client.put(
                    "/api/me/provider-keys/anthropic",
                    json={"api_key": replacement},
                    headers=headers,
                )
            ).status_code
            == 200
        )
        assert (
            _call(
                cards_client.delete("/api/me/provider-keys/anthropic", headers=headers)
            ).status_code
            == 204
        )
        _call(cards_client.get("/api/me/provider-keys"))

    captured = capsys.readouterr()
    emitted = logs.getvalue()
    channels = {
        "logs": emitted.splitlines(),
        "stdio": [captured.out, captured.err],
        "responses": responses,
        "exceptions": exceptions,
        "celery": celery_args,
        "reprs": reprs,
    }
    assert scan(channels, (canary, replacement)) == []
    # The canary did reach the log channel (the fakes dump and quote it): what the
    # scan proves is that it was masked on the way out, not that nothing was logged.
    assert emitted.count("***KEY-REDACTED***") >= 5
    assert len(celery_args) == 3


def test_scanner_catches_deliberate_leak() -> None:
    """The negative control: the canary through an unmasked path is reported."""
    canary = _canary("LEAK")
    logger = logging.getLogger("app.tests.deliberate_leak")
    raw = io.StringIO()
    raw_handler = logging.StreamHandler(raw)  # no filter, plain formatter
    logger.addHandler(raw_handler)
    try:
        with _learny_log_capture() as masked:
            logger.warning("SDK said: invalid x-api-key %s", canary)
            root = logging.getLogger()
            handler = next(h for h in root.handlers if getattr(h, "_learny", False))
            # Strip the Learny handler of its masking: the same scanner must see it.
            unmasked = [f for f in handler.filters if isinstance(f, SensitiveDataFilter)]
            for f in unmasked:
                handler.removeFilter(f)
            for f in [f for f in root.filters if isinstance(f, SensitiveDataFilter)]:
                root.removeFilter(f)
            formatter = handler.formatter
            handler.setFormatter(logging.Formatter("%(message)s"))
            try:
                logger.warning("SDK said: invalid x-api-key %s", canary)
            finally:
                handler.setFormatter(formatter)
                for f in unmasked:
                    handler.addFilter(f)
                root.addFilter(SensitiveDataFilter())
    finally:
        logger.removeHandler(raw_handler)

    masked_lines = masked.getvalue().splitlines()
    assert len(masked_lines) == 2
    assert scan({"learny": masked_lines[:1]}, (canary,)) == []  # masked while on
    assert scan({"learny": masked_lines[1:]}, (canary,)) == [("learny", 0)]
    # A handler on the emitting logger runs before the record propagates to the
    # masking handler: it is an unmasked path, and the scanner reports it.
    assert scan({"raw": raw.getvalue().splitlines()}, (canary,)) == [("raw", 0), ("raw", 1)]


def test_kek_canary_never_reaches_the_account_surface(
    cards_client: TestClient,  # noqa: F811
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No response of the whole account surface ever carries the configured KEK.

    The canary KEK is set the way an operator sets it; every user-facing route the
    keys section can touch is then driven — list, save (malformed and valid),
    test, delete, the budget put, the profile choice, and the account read — and
    every response body is scanned for the KEK in its three spellable forms.
    """
    import base64

    from app.infrastructure.answering.probe import ProbeOutcome
    from app.infrastructure.web.provider_keys import get_key_probe

    canary_kek = secrets.token_bytes(32)
    monkeypatch.setenv("LEARNY_GENERATION_PROFILES", json.dumps([_HOUSE, _BYOK]))
    _set_kek(monkeypatch, canary_kek, None)

    class _OkProbe:
        def __call__(self, profile: Any, api_key: str) -> ProbeOutcome:  # noqa: ANN401
            return ProbeOutcome(ok=True)

    cards_client.app.dependency_overrides[get_key_probe] = lambda: _OkProbe()
    try:
        learner_ctx = _highlight(cards_client, db_conn, "kek-canary@example.com")
        user_id, csrf = UUID(learner_ctx["user_id"]), learner_ctx["csrf"]
        headers = {"X-CSRF-Token": csrf}

        def _call(resp: Any) -> Any:  # noqa: ANN401
            responses.append(resp.text)
            return resp

        responses: list[str] = []
        canary_key = _canary("KEKCANARY")
        # list (feature on, nothing stored), a malformed save, a valid save, test,
        # delete, the budget put, the profile choice, and the account read.
        _call(cards_client.get("/api/me/provider-keys"))
        malformed = cards_client.put(
            "/api/me/provider-keys/anthropic", json={"api_key": "short"}, headers=headers
        )
        assert malformed.status_code == 422, malformed.text
        assert (
            _call(
                cards_client.put(
                    "/api/me/provider-keys/anthropic", json={"api_key": canary_key}, headers=headers
                )
            ).status_code
            == 200
        )
        tested = _call(cards_client.post("/api/me/provider-keys/anthropic/test", headers=headers))
        assert tested.json() == {"ok": True, "reason": None}
        budgeted = _call(
            cards_client.put(
                "/api/me/provider-keys/budget",
                json={"monthly_budget_usd": 25},
                headers=headers,
            )
        )
        assert budgeted.status_code == 200, budgeted.text
        chosen = _call(
            cards_client.put("/api/me/ai-profile", json={"profile_id": "house"}, headers=headers)
        )
        assert chosen.status_code == 200, chosen.text
        _call(cards_client.get("/api/auth/me"))
        assert (
            _call(
                cards_client.delete("/api/me/provider-keys/anthropic", headers=headers)
            ).status_code
            == 204
        )
        _call(cards_client.get("/api/me/provider-keys"))
        assert user_id  # the learner context is real; the scan below is the point
    finally:
        cards_client.app.dependency_overrides.pop(get_key_probe, None)

    spellings = [
        base64.b64encode(canary_kek).decode(),
        base64.b64encode(canary_kek).decode().rstrip("="),
        canary_kek.hex(),
        canary_kek.hex().upper(),
    ]
    for spelling in spellings:
        for index, body in enumerate(responses):
            assert spelling not in body, ("response", index, spelling)
