"""The documented local generation profile, proven through the real composition.

An operator declares an ``openai-compatible`` generation profile whose
``base_url`` names a local runtime (Ollama ``http://localhost:11434/v1``, LM
Studio ``http://localhost:1234/v1``) and whose ``api_key_env`` carries the
placeholder key convention keyless runtimes accept. These tests drive the real
registry → ``build_generation_chain`` composition with the ``openai`` module
stubbed out of ``sys.modules`` — a deterministic fake transport, no socket:

- an ask turn is served through the declared base_url, and the prompt-cited
  contract holds: the reply's ``[^n]`` markers resolve to evidence chunk ids;
- an unreachable local runtime surfaces as the Learny taxonomy
  ``ProviderUnavailable`` (retryable), never a raw SDK exception.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from uuid import uuid4

import httpx
import openai as openai_sdk
import pytest
from openai import APIConnectionError

from app.core.config import Settings
from app.domain.entities import MODE_ANSWER, Evidence
from app.infrastructure.answering import build_generation_chain
from app.infrastructure.providers.errors import ProviderUnavailable
from app.infrastructure.providers.profiles import GenerationProfileSettings

_PROFILE_ID = "local-ollama"
_MODEL = "qwen3:8b"
_BASE_URL = "http://localhost:11434/v1"
_KEY_ENV = "LEARNY_TEST_LOCAL_RUNTIME_KEY"


def _settings() -> Settings:
    """One declared openai-compatible profile: the documented operator profile."""
    profile = GenerationProfileSettings(
        id=_PROFILE_ID,
        kind="openai-compatible",
        model=_MODEL,
        base_url=_BASE_URL,
        api_key_env=_KEY_ENV,
        max_tokens=2048,
        price_input_usd_per_million_tokens=0.0,
        price_output_usd_per_million_tokens=0.0,
        price_cache_read_usd_per_million_tokens=0.0,
        price_cache_creation_usd_per_million_tokens=0.0,
        grounding="prompt-cited",
        ask_enabled=True,
        teach_enabled=True,
    )
    return Settings(_env_file=None, generation_profiles=[profile])


class _RecordingCompletions:
    """The ``chat.completions`` resource: records calls, serves one outcome."""

    def __init__(self, outcome: object) -> None:
        self._outcome = outcome
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


class _FakeOpenAIModule:
    """Stands in for the ``openai`` module inside the adapter's lazy import.

    The constructor records its kwargs — proving the request carries the
    profile's base_url — and the real SDK's exception types ride along so the
    adapter's transport translation keeps classifying on them.
    """

    def __init__(self, outcome: object) -> None:
        self._outcome = outcome
        self.built_with: list[dict[str, object]] = []
        self.clients: list[SimpleNamespace] = []
        self.APIConnectionError = openai_sdk.APIConnectionError
        self.APITimeoutError = openai_sdk.APITimeoutError

    def OpenAI(self, **kwargs: object) -> SimpleNamespace:
        self.built_with.append(kwargs)
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=_RecordingCompletions(self._outcome))
        )
        self.clients.append(client)
        return client

    def chat_calls(self) -> list[dict[str, object]]:
        """Every ``chat.completions.create`` call the served client recorded."""
        return self.clients[-1].chat.completions.calls


def _stub_openai(monkeypatch: pytest.MonkeyPatch, outcome: object) -> _FakeOpenAIModule:
    fake = _FakeOpenAIModule(outcome)
    monkeypatch.setitem(sys.modules, "openai", fake)
    return fake


def _evidence() -> Evidence:
    return Evidence(
        chunk_id=uuid4(),
        source_id=uuid4(),
        section_path=("Chapter 1",),
        anchor="chap1.xhtml",
        page_span=None,
        snippet="Ocean tides rise and fall because the moon's gravity pulls seawater.",
        score=1.0,
    )


def test_serves_ask_turn_through_declared_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # AC 1: the declared compat profile serves a prompt-cited ask turn through
    # its base_url — real registry, real chain, fake transport.
    monkeypatch.setenv(_KEY_ENV, "ollama")
    evidence = _evidence()
    reply = "The moon's gravity pulls the seawater [^1]."
    fake = _stub_openai(
        monkeypatch,
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))]),
    )

    chain = build_generation_chain(_settings())
    answer = chain.generate(mode=MODE_ANSWER, message="Why do tides rise?", evidence=[evidence])

    # The client was built for the profile's host, and the request names the
    # profile's model.
    assert fake.built_with == [{"api_key": "ollama", "base_url": _BASE_URL}]
    assert fake.chat_calls() and fake.chat_calls()[0]["model"] == _MODEL
    # The prompt-cited contract: the marker resolves to the evidence chunk id.
    assert answer.found is True
    assert answer.cited_chunk_ids == (evidence.chunk_id,)
    assert answer.text == reply


def test_unreachable_runtime_raises_provider_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # AC 2: an unreachable local runtime raises the Learny taxonomy error the
    # router retries across — never a raw SDK exception.
    monkeypatch.setenv(_KEY_ENV, "ollama")
    request = httpx.Request("POST", f"{_BASE_URL}/chat/completions")
    _stub_openai(monkeypatch, APIConnectionError(request=request))

    chain = build_generation_chain(_settings())

    with pytest.raises(ProviderUnavailable):
        chain.generate(mode=MODE_ANSWER, message="Why do tides rise?", evidence=[_evidence()])
