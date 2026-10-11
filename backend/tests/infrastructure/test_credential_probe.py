"""The key test probe at its own layer (ADR-0033).

The probe lists models with the learner's key, on the host the bound profile
serves from, and maps the outcome onto ``rejected``, ``rate_limited`` and
``unavailable``. The SDK clients are replaced by recording fakes, so no
provider is called.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.infrastructure.answering import probe as probe_module
from app.infrastructure.answering.probe import ProbeOutcome, probe_key
from app.infrastructure.providers import GenerationProfileSettings
from app.infrastructure.providers.errors import (
    ProviderUnavailable,
    RateLimited,
    RequestRejected,
    Timeout,
)

_KEY = "sk-proj-probe-learner-key-PPPPPPPPPPPPPPPP"


def _profile(**overrides: Any) -> GenerationProfileSettings:  # noqa: ANN401
    fields: dict[str, Any] = {
        "id": "byok",
        "kind": "openai-compatible",
        "model": "gpt-x",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "max_tokens": 64,
        "price_input_usd_per_million_tokens": 1.0,
        "price_output_usd_per_million_tokens": 1.0,
        "price_cache_read_usd_per_million_tokens": 0.1,
        "price_cache_creation_usd_per_million_tokens": 1.25,
        "grounding": "prompt-cited",
        "ask_enabled": True,
        "teach_enabled": True,
        "user_key_provider": "gemini",
    }
    fields.update(overrides)
    return GenerationProfileSettings(**fields)


class _Client:
    """A fake SDK client: records its construction and its model-list calls."""

    built: list[_Client] = []
    fail_with: BaseException | None = None

    def __init__(self, **kwargs: Any) -> None:  # noqa: ANN401
        self.kwargs = kwargs
        self.listed: list[dict[str, Any]] = []
        self.closed = False
        self.models = self
        _Client.built.append(self)

    def list(self, **kwargs: Any) -> list[str]:  # noqa: ANN401
        self.listed.append(kwargs)
        if _Client.fail_with is not None:
            raise _Client.fail_with
        return []

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def clients(monkeypatch: pytest.MonkeyPatch) -> list[_Client]:
    import anthropic
    import openai

    _Client.built = []
    _Client.fail_with = None
    monkeypatch.setattr(openai, "OpenAI", _Client)
    monkeypatch.setattr(anthropic, "Anthropic", _Client)
    return _Client.built


def test_lists_models_with_profile_host(clients: list[_Client]) -> None:
    outcome = probe_key(_profile(), _KEY)

    assert outcome == ProbeOutcome(ok=True)
    (client,) = clients
    assert client.kwargs["api_key"] == _KEY
    assert client.kwargs["base_url"] == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert client.kwargs["max_retries"] == 0
    assert client.listed == [{}]
    assert client.closed is True


def test_an_openai_profile_without_a_base_url_uses_the_sdk_default_host(
    clients: list[_Client],
) -> None:
    probe_key(_profile(base_url="", user_key_provider="openai"), _KEY)

    assert clients[0].kwargs["base_url"] is None


def test_an_anthropic_profile_lists_models_on_the_native_host(clients: list[_Client]) -> None:
    key = "sk-ant-api03-probe-learner-key-PPPPPPPPPPPP"
    outcome = probe_key(_profile(kind="anthropic", base_url="", user_key_provider="anthropic"), key)

    assert outcome.ok is True
    (client,) = clients
    assert client.kwargs["api_key"] == key
    assert "base_url" not in client.kwargs
    assert client.listed == [{"limit": 1}]


class _StatusError(Exception):
    """An SDK-shaped failure carrying an HTTP status, as the SDKs' errors do."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"request with {_KEY} failed")
        self.status_code = status_code


@pytest.mark.parametrize(
    ("status", "reason"),
    [(401, "rejected"), (403, "rejected"), (429, "rate_limited"), (500, "unavailable")],
)
def test_sdk_status_failures_map_onto_reasons(
    status: int, reason: str, clients: list[_Client]
) -> None:
    _Client.fail_with = _StatusError(status)

    assert probe_key(_profile(), _KEY) == ProbeOutcome(ok=False, reason=reason)
    assert clients[0].closed is True


@pytest.mark.parametrize(
    ("raised", "reason"),
    [
        (RequestRejected("401"), "rejected"),
        (RateLimited("429"), "rate_limited"),
        (Timeout("slow"), "unavailable"),
        (ProviderUnavailable("down"), "unavailable"),
        (RuntimeError(f"unexpected, quoting {_KEY}"), "unavailable"),
    ],
)
def test_taxonomy_failures_map_onto_reasons(
    raised: BaseException, reason: str, caplog: pytest.LogCaptureFixture
) -> None:
    def _lister(api_key: str, base_url: str) -> None:
        raise raised

    outcome = probe_key(_profile(), _KEY, listers={"openai-compatible": _lister})

    assert outcome == ProbeOutcome(ok=False, reason=reason)
    assert _KEY not in caplog.text


def test_every_bindable_kind_has_a_lister() -> None:
    assert set(probe_module.MODEL_LISTERS) == {"anthropic", "openai-compatible"}
