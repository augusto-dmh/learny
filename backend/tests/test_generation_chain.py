"""Generation chain composition — registry → routing adapter (ROUTE-01/05/06).

``build_generation_chain`` is the composition root's one seam from the
settings-declared profile registry to the routing adapter: profiles resolve
(validated, legacy-seeded) through the registry, each builds its sub-adapter,
and the ordered chain is wrapped so the application keeps calling one
``GenerationPort``. A default deployment (nothing declared) gets the
single-entry legacy chain — today's behavior, byte for byte (ROUTE-06); a
malformed registry or missing key env fails fast here at composition instead of
per request (ROUTE-05); and the selection-Explain ordering (AD-345) leads with
the profile ``generation_explain_profile`` names when it is declared and
ask-eligible. The cached FastAPI accessors expose the two chains. The first
economy profile (ECON-04/AD-336) ships declared-in-docs but inert: nothing is
declared by default, the shipped example carries it ask/teach-ineligible, and a
chain built from exactly that declaration refuses grounded turns honest with
zero adapter calls.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.core.config import Settings
from app.domain.entities import MODE_ANSWER, MODE_TEACH, Evidence, GeneratedAnswer
from app.infrastructure.answering import (
    AnthropicGenerationAdapter,
    ChainEntry,
    DeterministicGenerationAdapter,
    OpenAICompatibleGenerationAdapter,
    RoutingGenerationAdapter,
    build_generation_chain,
    build_user_generation_chain,
)
from app.infrastructure.providers import GenerationProfileSettings, Timeout

_PROFILE = {
    "id": "primary",
    "kind": "local",
    "model": "local-extractive",
    "max_tokens": 1024,
    "price_input_usd_per_million_tokens": 3.0,
    "price_output_usd_per_million_tokens": 15.0,
    "price_cache_read_usd_per_million_tokens": 0.3,
    "price_cache_creation_usd_per_million_tokens": 3.75,
    "grounding": "verified-spans",
    "ask_enabled": True,
    "teach_enabled": True,
}


def _profile(**overrides: object) -> GenerationProfileSettings:
    return GenerationProfileSettings(**{**_PROFILE, **overrides})  # type: ignore[arg-type]


# The declared two-profile registry exactly as an operator's env would carry it:
# "primary" at list prices, "cheap" at economy prices, ask-eligible and (for
# "cheap") teach-ineligible. Both the chain-accessor and budget-wiring tests
# declare the registry through ``LEARNY_GENERATION_PROFILES``.
_TWO_PROFILES_JSON = (
    '[{"id": "primary", "kind": "local", "model": "m", "max_tokens": 1, '
    '"price_input_usd_per_million_tokens": 3.0, "price_output_usd_per_million_tokens": 15.0, '
    '"price_cache_read_usd_per_million_tokens": 0.3, '
    '"price_cache_creation_usd_per_million_tokens": 3.75, "grounding": "verified-spans", '
    '"ask_enabled": true, "teach_enabled": true},'
    '{"id": "cheap", "kind": "local", "model": "m", "max_tokens": 1, '
    '"price_input_usd_per_million_tokens": 0.2, "price_output_usd_per_million_tokens": 1.0, '
    '"price_cache_read_usd_per_million_tokens": 0.02, '
    '"price_cache_creation_usd_per_million_tokens": 0.25, "grounding": "verified-spans", '
    '"ask_enabled": true, "teach_enabled": false}]'
)


def _chain_ids(chain: RoutingGenerationAdapter) -> list[str]:
    return [entry.profile.id for entry in chain._chain]


# --- ROUTE-06: the undeclared registry is today's single-adapter behavior ---------


def test_default_settings_build_the_single_entry_legacy_chain() -> None:
    settings = Settings(_env_file=None)

    chain = build_generation_chain(settings)

    assert isinstance(chain, RoutingGenerationAdapter)
    assert _chain_ids(chain) == ["default"]
    assert isinstance(chain._chain[0].adapter, DeterministicGenerationAdapter)
    # The model identity the not-found short-circuit reports is today's.
    assert chain.model == "local-extractive"


def test_an_anthropic_legacy_seed_builds_the_claude_adapter_from_legacy_settings() -> None:
    settings = Settings(
        _env_file=None,
        generation_provider="anthropic",
        anthropic_api_key="sk-ant-test",
        generation_model="claude-sonnet-4-6",
        generation_effort="xhigh",
        generation_max_tokens=2048,
    )

    chain = build_generation_chain(settings)

    adapter = chain._chain[0].adapter
    assert isinstance(adapter, AnthropicGenerationAdapter)
    assert adapter.model == "claude-sonnet-4-6"
    assert adapter._max_tokens == 2048
    # The legacy single effort seeds BOTH modes (COST-01/AD-342 equivalence): one
    # knob yesterday, one value on both modes today, until a registry is declared.
    assert (adapter._effort_ask, adapter._effort_teach) == ("xhigh", "xhigh")


def test_a_profile_feeds_its_per_mode_effort_values_to_the_sub_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # COST-01/AD-339: the profile's per-mode values reach the adapter constructor —
    # ask and teach may differ — so a turn's effort is the serving profile's value
    # for that turn's mode, never a global setting read.
    monkeypatch.setenv("LEARNY_TEST_PROFILE_KEY", "sk-ant-test")
    settings = Settings(
        _env_file=None,
        generation_profiles=[
            _profile(
                id="scout",
                kind="anthropic",
                api_key_env="LEARNY_TEST_PROFILE_KEY",
                effort_ask="low",
                effort_teach="high",
            ),
        ],
    )

    chain = build_generation_chain(settings)

    adapter = chain._chain[0].adapter
    assert isinstance(adapter, AnthropicGenerationAdapter)
    assert (adapter._effort_ask, adapter._effort_teach) == ("low", "high")


# --- ROUTE-01/05: the declared registry builds in order and fails fast ------------


def test_a_declared_registry_builds_the_router_over_every_profile_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LEARNY_TEST_PROFILE_KEY", "sk-ant-test")
    settings = Settings(
        _env_file=None,
        generation_profiles=[
            _profile(id="primary", kind="local"),
            _profile(id="scout", kind="anthropic", api_key_env="LEARNY_TEST_PROFILE_KEY"),
        ],
    )

    chain = build_generation_chain(settings)

    assert _chain_ids(chain) == ["primary", "scout"]
    assert isinstance(chain._chain[0].adapter, DeterministicGenerationAdapter)
    assert isinstance(chain._chain[1].adapter, AnthropicGenerationAdapter)


def test_a_missing_key_env_fails_the_composition_with_an_actionable_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LEARNY_TEST_PROFILE_KEY", raising=False)
    settings = Settings(
        _env_file=None,
        generation_profiles=[
            _profile(id="scout", kind="anthropic", api_key_env="LEARNY_TEST_PROFILE_KEY"),
        ],
    )

    with pytest.raises(ValueError, match="LEARNY_TEST_PROFILE_KEY"):
        build_generation_chain(settings)


def test_an_empty_registry_is_rejected() -> None:
    # The resolver never returns an empty registry (the legacy seed fills it),
    # so an empty chain at the router is a construction error, not a state.
    with pytest.raises(ValueError, match="at least one profile"):
        RoutingGenerationAdapter(())


# --- AD-345: the selection-Explain ordering ----------------------------------------


def test_the_explain_chain_leads_with_the_named_explain_profile() -> None:
    settings = Settings(
        _env_file=None,
        generation_profiles=[_profile(id="primary"), _profile(id="cheap")],
        generation_explain_profile="cheap",
    )

    assert _chain_ids(build_generation_chain(settings, explain=True)) == ["cheap", "primary"]
    # The normal chain is untouched: primary first.
    assert _chain_ids(build_generation_chain(settings)) == ["primary", "cheap"]


def test_an_unset_or_ineligible_explain_name_keeps_the_primary_first() -> None:
    settings = Settings(
        _env_file=None,
        generation_profiles=[_profile(id="primary"), _profile(id="quiet", ask_enabled=False)],
    )
    assert settings.generation_explain_profile == ""

    # Unset → primary first.
    assert _chain_ids(build_generation_chain(settings, explain=True)) == ["primary", "quiet"]

    # A name nothing declares → primary first.
    unnamed = settings.model_copy(update={"generation_explain_profile": "ghost"})
    assert _chain_ids(build_generation_chain(unnamed, explain=True)) == ["primary", "quiet"]

    # A name that is not ask-eligible cannot lead an ask chain → primary first.
    ineligible = settings.model_copy(update={"generation_explain_profile": "quiet"})
    assert _chain_ids(build_generation_chain(ineligible, explain=True)) == ["primary", "quiet"]


# --- COST-04 composed: the explain lead's transport failure fails over --------------


class _FailingLead:
    """A ``GenerationPort`` double for the cheap explain lead: every call fails."""

    def __init__(self, error: Exception) -> None:
        self._error = error
        self.calls = 0

    @property
    def model(self) -> str:
        return "cheap-model"

    def generate(self, **_kwargs: object) -> GeneratedAnswer:  # noqa: ANN003 — port kwargs
        self.calls += 1
        raise self._error

    def generate_stream(self, **_kwargs: object) -> object:  # noqa: ANN003, ANN202
        self.calls += 1
        raise self._error


class _AttemptRecorder:
    """Wraps a real adapter, writing down the attempt order the composition walks."""

    def __init__(
        self, name: str, inner: DeterministicGenerationAdapter, attempted: list[str]
    ) -> None:
        self._name = name
        self._inner = inner
        self._attempted = attempted

    @property
    def model(self) -> str:
        return self._inner.model

    def generate(self, **kwargs: object) -> object:  # noqa: ANN003 — port kwargs
        self._attempted.append(self._name)
        return self._inner.generate(**kwargs)  # type: ignore[arg-type]

    def generate_stream(self, **kwargs: object) -> object:  # noqa: ANN003
        self._attempted.append(self._name)
        return self._inner.generate_stream(**kwargs)  # type: ignore[arg-type]


def test_an_explain_lead_transport_failure_fails_over_to_the_ask_primary() -> None:
    """COST-04's fallback leg, composed end to end.

    The halves live in different suites — the routing policy tests fail a
    scripted entry over (ROUTE-02), and the AD-345 tests above order the explain
    chain ``["cheap", "primary"]``. This one walks the composed chain: the cheap
    lead raises a transport-class error, the router fails over, and the Ask
    primary serves the turn and takes the attribution stamp. Both adapters are
    attempted, in order, each exactly once (a ``Timeout`` earns no retry).
    """
    evidence = [
        Evidence(
            chunk_id=uuid4(),
            source_id=uuid4(),
            section_path=("Biology",),
            anchor="bio.xhtml",
            page_span=None,
            snippet="photosynthesis converts sunlight into chemical energy",
            score=0.5,
        )
    ]
    settings = Settings(
        _env_file=None,
        generation_profiles=[_profile(id="primary"), _profile(id="cheap")],
        generation_explain_profile="cheap",
    )
    chain = build_generation_chain(settings, explain=True)
    assert _chain_ids(chain) == ["cheap", "primary"]  # the premise: the cheap lead serves first

    attempted: list[str] = []
    router = RoutingGenerationAdapter(
        (
            ChainEntry(
                adapter=_AttemptRecorder(
                    "cheap", _FailingLead(Timeout("the cheap lead is down")), attempted
                ),
                profile=chain._chain[0].profile,
            ),
            ChainEntry(
                adapter=_AttemptRecorder("primary", chain._chain[1].adapter, attempted),
                profile=chain._chain[1].profile,
            ),
        )
    )

    answer = router.generate(mode=MODE_ANSWER, message="why?", evidence=evidence)

    assert attempted == ["cheap", "primary"]  # both attempted, in order, once each
    assert answer.profile_id == "primary"  # the Ask primary served and is billed for it
    assert answer.model == "local-extractive"
    assert answer.found
    assert "photosynthesis" in answer.text


# --- The cached FastAPI accessors expose the two chains (AD-345) --------------------


def test_the_generation_accessors_build_the_normal_and_explain_chains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import get_settings
    from app.infrastructure.web import dependencies

    monkeypatch.setenv("LEARNY_GENERATION_PROFILES", _TWO_PROFILES_JSON)
    monkeypatch.setenv("LEARNY_GENERATION_EXPLAIN_PROFILE", "cheap")
    get_settings.cache_clear()
    dependencies.get_generation.cache_clear()
    dependencies.get_explain_generation.cache_clear()
    try:
        normal = dependencies.get_generation()
        explain = dependencies.get_explain_generation()

        assert _chain_ids(normal) == ["primary", "cheap"]
        assert _chain_ids(explain) == ["cheap", "primary"]
        # Cached like get_settings: one chain per process, not per request.
        assert dependencies.get_generation() is normal
        assert dependencies.get_explain_generation() is explain
    finally:
        get_settings.cache_clear()
        dependencies.get_generation.cache_clear()
        dependencies.get_explain_generation.cache_clear()


# --- AD-344: the request budget carries every declared profile's catalog -----------


@pytest.mark.requires_db
def test_the_request_budget_prices_a_stamp_from_the_declared_profiles_catalog(
    db_conn,  # noqa: ANN001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The composition root wires each declared profile's prices into the budget.

    A router-stamped result must debit at the catalog of the profile that served
    it (AD-344/PRICE-01) — here proven through the very ``build_budget`` the
    request path uses, not a hand-built budget: the cheap profile's usage prices
    cheap, the primary's prices primary, and no stamp is the primary catalog.
    """
    from app.core.config import get_settings
    from app.domain.entities import TokenUsage
    from app.infrastructure.web import dependencies
    from app.infrastructure.web.dependencies import build_budget

    monkeypatch.setenv("LEARNY_GENERATION_PROFILES", _TWO_PROFILES_JSON)
    get_settings.cache_clear()
    dependencies._generation_profiles.cache_clear()
    dependencies._profile_catalogs.cache_clear()
    dependencies._serving_profile_resolver.cache_clear()
    try:
        budget = build_budget(db_conn)
    finally:
        get_settings.cache_clear()
        dependencies._generation_profiles.cache_clear()
        dependencies._profile_catalogs.cache_clear()
        dependencies._serving_profile_resolver.cache_clear()

    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    assert budget.usage_micros(usage, "cheap") == 1_200_000  # $0.20 + $1.00 per M
    assert budget.usage_micros(usage, "primary") == 18_000_000  # $3.00 + $15.00 per M
    assert budget.usage_micros(usage) == 18_000_000  # no stamp is the primary catalog


def test_build_budget_resolves_the_registry_once_across_two_builds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The catalogs path is memoized per process (the zero-arg accessor pattern).

    Settings are a singleton, so a second ``build_budget`` must re-resolve and
    re-validate nothing: the counting wrapper around the registry resolver fires
    exactly once, and both budgets still price from the declared catalogs.
    """
    from app.core.config import get_settings
    from app.domain.entities import TokenUsage
    from app.infrastructure.web import dependencies
    from app.infrastructure.web.dependencies import build_budget

    calls = 0
    real_resolve = dependencies.resolve_generation_profiles

    def counting_resolve(settings: Settings) -> tuple:
        nonlocal calls
        calls += 1
        return real_resolve(settings)

    monkeypatch.setattr(dependencies, "resolve_generation_profiles", counting_resolve)
    monkeypatch.setenv("LEARNY_GENERATION_PROFILES", _TWO_PROFILES_JSON)
    get_settings.cache_clear()
    dependencies._generation_profiles.cache_clear()
    dependencies._profile_catalogs.cache_clear()
    dependencies._serving_profile_resolver.cache_clear()
    try:
        first = build_budget(None)  # the repo only holds the connection; no DB touch
        second = build_budget(None)
    finally:
        get_settings.cache_clear()
        dependencies._generation_profiles.cache_clear()
        dependencies._profile_catalogs.cache_clear()
        dependencies._serving_profile_resolver.cache_clear()

    assert calls == 1  # resolved once per process, not once per request
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    assert first.usage_micros(usage, "cheap") == second.usage_micros(usage, "cheap") == 1_200_000


# --- ROUTE-07: the rails fire before any chain entry, whatever serves --------------


class _CountingGeneration:
    """A deterministic adapter that counts the calls the chain makes through it."""

    def __init__(self) -> None:
        self._inner = DeterministicGenerationAdapter()
        self.calls = 0

    @property
    def model(self) -> str:
        return self._inner.model

    def generate(self, **kwargs: object) -> object:
        self.calls += 1
        return self._inner.generate(**kwargs)  # type: ignore[arg-type]

    def generate_stream(self, **kwargs: object) -> object:
        self.calls += 1
        return self._inner.generate_stream(**kwargs)  # type: ignore[arg-type]


@pytest.fixture
def generation_chain_client(auth_client, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN001, ANN201
    """The app with ``get_generation`` overridden by a two-entry counting router.

    The entries' call counts are the rails' sensor: whatever a request does, the
    chain may only be reached after every rail has passed.
    """
    from app.infrastructure.web.dependencies import get_generation

    first = _CountingGeneration()
    second = _CountingGeneration()
    router = RoutingGenerationAdapter(
        (
            ChainEntry(adapter=first, profile=_profile(id="primary")),
            ChainEntry(adapter=second, profile=_profile(id="fallback")),
        )
    )
    auth_client.app.dependency_overrides[get_generation] = lambda: router
    try:
        yield auth_client, first, second
    finally:
        auth_client.app.dependency_overrides.pop(get_generation, None)


def _seed_turn_world(client, db_conn, email: str) -> tuple[UUID, UUID, str]:
    """A registered reader with an owned, ready, embedded source.

    Returns ``(source_id, conversation_id, csrf)``.
    """
    from datetime import UTC, datetime
    from uuid import UUID, uuid4

    from app.domain.entities import (
        Conversation,
        CorpusSectionRecord,
        ParsedSection,
        SectionChunk,
        Source,
    )
    from app.infrastructure.db.repositories import (
        SqlAlchemyConversationRepository,
        SqlAlchemyCorpusRepository,
        SqlAlchemyEmbeddingIndexRepository,
        SqlAlchemySourceRepository,
    )
    from app.infrastructure.embeddings import DeterministicEmbeddingAdapter
    from tests.conftest import TEST_PASSWORD

    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": TEST_PASSWORD, "accepted_tos": True},
    )
    assert resp.status_code == 201, resp.text
    user_id = UUID(resp.json()["id"])
    csrf = client.get("/api/auth/me").json()["csrf_token"]

    now = datetime.now(UTC)
    source = SqlAlchemySourceRepository(db_conn).add(
        Source(
            id=uuid4(),
            user_id=user_id,
            title="A Book",
            filename="a-book.epub",
            content_type="application/epub+zip",
            byte_size=1024,
            checksum="d" * 64,
            object_key=f"sources/{user_id}/{uuid4()}.epub",
            status="ready",
            created_at=now,
            updated_at=now,
        )
    )
    chunk = SectionChunk(
        index=0,
        text="photosynthesis converts sunlight into chemical energy in green plants",
        section_path=("Biology",),
        anchor="bio.xhtml",
        page_span=None,
    )
    SqlAlchemyCorpusRepository(db_conn).replace(
        source.id,
        title="A Book",
        authors=("Author",),
        language="en",
        schema_version=1,
        sections=(
            CorpusSectionRecord(
                section=ParsedSection(
                    position=0,
                    title="Biology",
                    depth=0,
                    section_path=("Biology",),
                    anchor="bio.xhtml",
                    blocks=(),
                ),
                markdown="",
                chunks=(chunk,),
            ),
        ),
    )
    index = SqlAlchemyEmbeddingIndexRepository(db_conn)
    adapter = DeterministicEmbeddingAdapter()
    chunks = index.chunks_for_source(source.id)
    vectors = adapter.embed_documents([c.text for c in chunks])
    index.set_embeddings(
        list(zip((c.id for c in chunks), vectors, strict=True)), model=adapter.model
    )
    conversation = SqlAlchemyConversationRepository(db_conn).add(
        Conversation(
            id=uuid4(),
            source_id=source.id,
            title="A Book",
            scope_anchors=(),
            include_notes=False,
            target_anchor=None,
            target_section_path=None,
            target_title=None,
            tutor_phase=None,
            hint_level=None,
            tutor_check_text=None,
            created_at=now,
            updated_at=now,
        )
    )
    return source.id, conversation.id, csrf


@pytest.mark.requires_db
def test_the_rate_limit_fires_before_any_chain_entry(
    generation_chain_client,
    db_conn,  # noqa: ANN001
) -> None:
    """Three turns reach the chain; the throttled fourth reaches none of it (ROUTE-07)."""
    from app.infrastructure.web.rate_limit import (
        InMemoryFixedWindowRateLimiter,
        get_rate_limiter,
        set_rate_limiter,
    )

    client, first, second = generation_chain_client
    _, conversation_id, csrf = _seed_turn_world(client, db_conn, "chain-rails@example.com")

    previous = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=3, window_seconds=300))
    try:
        for _ in range(3):
            resp = client.post(
                f"/api/conversations/{conversation_id}/turns",
                json={"message": "photosynthesis sunlight energy", "mode": "answer"},
                headers={"X-CSRF-Token": csrf},
            )
            assert resp.status_code == 201, resp.text
        reached = first.calls + second.calls

        throttled = client.post(
            f"/api/conversations/{conversation_id}/turns",
            json={"message": "photosynthesis sunlight energy", "mode": "answer"},
            headers={"X-CSRF-Token": csrf},
        )
    finally:
        set_rate_limiter(previous)

    # The unthrottled turns really did reach the chain (the premise), and the
    # throttled one was refused by the user-keyed rail before either entry —
    # whatever profile would have served it — was consulted.
    assert reached == 3
    assert throttled.status_code == 429, throttled.text
    assert first.calls + second.calls == 3


# --- ECON-04/AD-336: the economy profile ships declared-in-docs, inert in code -----


def test_the_economy_profile_is_not_in_the_shipped_defaults() -> None:
    # Inertness, half one (AD-343): nothing ships declared. The default
    # deployment's registry is the legacy single profile (the ROUTE-06 tests
    # above, unmodified); the economy profile exists only where an operator
    # declares it, and the shipped example declares it grounded-ineligible.
    assert Settings(_env_file=None).generation_profiles == []


def test_the_shipped_env_example_declares_the_economy_profile_inert() -> None:
    """Inertness, half two: the shipped declaration artifact itself (ECON-04).

    The example registry in ``backend/.env.example`` is commented out (nothing
    is declared by default) and carries the first economy profile —
    Fireworks-US-hosted GLM — Ask-ineligible, Teach-ineligible, prompt-cited,
    with its price pair and its key env-var name: exactly the declaration an
    operator flips after a green nightly to promote it. The example must also
    stay internally consistent with the shipped accessors: the profile
    ``LEARNY_GENERATION_EXPLAIN_PROFILE`` names exists and is ask-eligible, so
    the documented example actually leads the explain chain if declared.
    """
    example = Path(__file__).resolve().parents[1] / ".env.example"
    declared: str | None = None
    explain_name: str | None = None
    for line in example.read_text(encoding="utf-8").splitlines():
        if line.startswith("# LEARNY_GENERATION_PROFILES="):
            declared = line.removeprefix("# LEARNY_GENERATION_PROFILES=")
        elif line.startswith("# LEARNY_GENERATION_EXPLAIN_PROFILE="):
            explain_name = line.removeprefix("# LEARNY_GENERATION_EXPLAIN_PROFILE=").strip()
    assert declared is not None  # the example ships a registry declaration
    profiles = [GenerationProfileSettings(**item) for item in json.loads(declared)]
    economy = next(profile for profile in profiles if profile.id == "economy-glm")
    assert economy.kind == "openai-compatible"
    assert economy.ask_enabled is False
    assert economy.teach_enabled is False
    assert economy.grounding == "prompt-cited"
    assert economy.price_input_usd_per_million_tokens == 0.22
    assert economy.price_output_usd_per_million_tokens == 0.75
    assert economy.api_key_env == "LEARNY_FIREWORKS_API_KEY"
    assert economy.base_url != ""

    named = next(profile for profile in profiles if profile.id == explain_name)
    assert named.ask_enabled is True


def test_the_declared_economy_chain_builds_and_refuses_ask_turns_with_zero_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Inertness, half three (AD-343): a chain built from exactly the shipped
    # economy declaration builds fine but refuses every grounded turn honest —
    # the application's existing error envelope — before any adapter is
    # touched. The lazy client is the zero-calls sensor: it is only built on
    # first use, and it never is.
    monkeypatch.setenv("LEARNY_FIREWORKS_API_KEY", "fw-test")
    settings = Settings(
        _env_file=None,
        generation_profiles=[
            _profile(
                id="economy-glm",
                kind="openai-compatible",
                model="zai-org/glm-5.3-flash",
                api_key_env="LEARNY_FIREWORKS_API_KEY",
                base_url="https://api.fireworks.ai/inference/v1",
                grounding="prompt-cited",
                ask_enabled=False,
                teach_enabled=False,
            ),
        ],
    )

    chain = build_generation_chain(settings)

    adapter = chain._chain[0].adapter
    assert isinstance(adapter, OpenAICompatibleGenerationAdapter)
    assert chain.model == "zai-org/glm-5.3-flash"

    with pytest.raises(RuntimeError, match="no generation profile is enabled"):
        chain.generate(mode=MODE_ANSWER, message="q", evidence=[])
    with pytest.raises(RuntimeError, match="no generation profile is enabled"):
        chain.generate(mode=MODE_TEACH, message="q", evidence=[])

    assert adapter._client is None


def test_an_openai_compatible_profile_builds_the_compat_adapter_from_its_declaration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The kind the economy profile names must actually build (ROUTE-01): the
    # declared model, host base_url, token budget, and per-mode effort values
    # are the ones the sub-adapter carries (the effort values accepted, never
    # sent — ECON-05 is the adapter's own contract).
    monkeypatch.setenv("LEARNY_FIREWORKS_API_KEY", "fw-test")
    settings = Settings(
        _env_file=None,
        generation_profiles=[
            _profile(
                id="economy-glm",
                kind="openai-compatible",
                model="zai-org/glm-5.3-flash",
                api_key_env="LEARNY_FIREWORKS_API_KEY",
                base_url="https://api.fireworks.ai/inference/v1",
                max_tokens=2048,
                grounding="prompt-cited",
                effort_ask="low",
                effort_teach="high",
            ),
        ],
    )

    chain = build_generation_chain(settings)
    adapter = chain._chain[0].adapter

    assert isinstance(adapter, OpenAICompatibleGenerationAdapter)
    assert adapter.model == "zai-org/glm-5.3-flash"
    assert adapter._base_url == "https://api.fireworks.ai/inference/v1"
    assert adapter._max_tokens == 2048
    assert (adapter._effort_ask, adapter._effort_teach) == ("low", "high")


# --- Per-user resolution: the stored choice leads, the registry follows -----------
#
# The learner's choice among house profiles is a reorder with fail-over preserved,
# never a hard pin: the chosen profile stands first, the rest of the registry keeps
# registry order (deduped), and unset / unknown / mode-ineligible choices collapse
# to exactly today's operator default chain. The selection-Explain chain and the
# quiz/card adapters are house-routed always — no preference reaches them.


def test_an_unset_choice_builds_the_operator_default_chain() -> None:
    settings = Settings(
        _env_file=None, generation_profiles=[_profile(id="primary"), _profile(id="cheap")]
    )

    assert _chain_ids(build_user_generation_chain(settings, None)) == ["primary", "cheap"]

    # The default deployment (legacy seed only) is unchanged too: an unset choice
    # there is today's single-entry chain byte for byte.
    assert _chain_ids(build_user_generation_chain(Settings(_env_file=None), None)) == ["default"]


def test_a_stored_choice_leads_and_the_registry_follows_deduped() -> None:
    settings = Settings(
        _env_file=None, generation_profiles=[_profile(id="primary"), _profile(id="cheap")]
    )

    assert _chain_ids(build_user_generation_chain(settings, "cheap")) == [
        "cheap",
        "primary",
    ]
    # Choosing the registry lead is the same order as the default chain.
    assert _chain_ids(build_user_generation_chain(settings, "primary")) == [
        "primary",
        "cheap",
    ]
    # Choosing the legacy seed in a legacy deployment resolves to itself.
    assert _chain_ids(build_user_generation_chain(Settings(_env_file=None), "default")) == [
        "default"
    ]


def test_an_unknown_stored_choice_falls_back_to_the_default_chain_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A stale id is a hint, not a correctness invariant: the operator may have
    renamed or removed the profile, so the turn serves the default chain and one
    warning records the miss — it never errors the learner's asking."""
    settings = Settings(
        _env_file=None, generation_profiles=[_profile(id="primary"), _profile(id="cheap")]
    )

    with caplog.at_level(logging.WARNING, logger="app.infrastructure.answering"):
        chain = build_user_generation_chain(settings, "removed-profile")

    assert _chain_ids(chain) == ["primary", "cheap"]
    assert any("removed-profile" in record.message for record in caplog.records)


def test_a_mode_ineligible_choice_is_not_prefiltered_the_router_walk_decides() -> None:
    """Eligibility has one authority — the router's per-mode walk. The chosen
    profile keeps its lead in the chain even when it cannot serve the mode (no
    build-time filtering that could drift from the router), and the walk simply
    falls through to the registry remainder, which is today's ineligible-lead
    behavior."""
    evidence = [
        Evidence(
            chunk_id=uuid4(),
            source_id=uuid4(),
            section_path=("Biology",),
            anchor="bio.xhtml",
            page_span=None,
            snippet="photosynthesis converts sunlight into chemical energy",
            score=0.5,
        )
    ]
    settings = Settings(
        _env_file=None,
        generation_profiles=[_profile(id="quiet", ask_enabled=False), _profile(id="primary")],
    )

    chain = build_user_generation_chain(settings, "quiet")
    assert _chain_ids(chain) == ["quiet", "primary"]

    answer = chain.generate(mode=MODE_ANSWER, message="why?", evidence=evidence)
    assert answer.profile_id == "primary"  # the walk skipped the ask-ineligible lead


def test_a_chosen_lead_that_fails_serves_the_rest_in_todays_fail_over_shape() -> None:
    """Reorder composes with the router unchanged: a transport failure on the
    chosen lead fails over to the registry remainder, the answer is shaped exactly
    like today's fail-over answers, and the profile that actually served takes the
    stamp (so the debit resolves its catalog)."""
    evidence = [
        Evidence(
            chunk_id=uuid4(),
            source_id=uuid4(),
            section_path=("Biology",),
            anchor="bio.xhtml",
            page_span=None,
            snippet="photosynthesis converts sunlight into chemical energy",
            score=0.5,
        )
    ]
    settings = Settings(
        _env_file=None, generation_profiles=[_profile(id="primary"), _profile(id="cheap")]
    )
    chain = build_user_generation_chain(settings, "cheap")
    assert _chain_ids(chain) == ["cheap", "primary"]  # premise: the choice leads

    attempted: list[str] = []
    router = RoutingGenerationAdapter(
        (
            ChainEntry(
                adapter=_AttemptRecorder(
                    "cheap", _FailingLead(Timeout("the chosen lead is down")), attempted
                ),
                profile=chain._chain[0].profile,
            ),
            ChainEntry(
                adapter=_AttemptRecorder("primary", chain._chain[1].adapter, attempted),
                profile=chain._chain[1].profile,
            ),
        )
    )

    answer = router.generate(mode=MODE_ANSWER, message="why?", evidence=evidence)

    assert attempted == ["cheap", "primary"]
    assert answer.profile_id == "primary"
    assert answer.found and "photosynthesis" in answer.text


# --- The composition seam: per-profile caching with the choice always per user -----


def _declare_two_profile_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEARNY_GENERATION_PROFILES", _TWO_PROFILES_JSON)


def test_unset_choice_serves_the_default_chain_object_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A user with no stored choice resolves the operator default chain object —
    behavior byte-identical to before per-user resolution existed, and (unlike a
    rebuilt chain) not even a second adapter set."""
    from app.infrastructure.web import dependencies

    _declare_two_profile_registry(monkeypatch)
    dependencies.clear_generation_chain_caches()

    sentinel = dependencies.get_generation()
    assert dependencies._resolve_user_chain(None, sentinel) is sentinel


def test_two_users_with_different_choices_resolve_different_leads_in_one_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cache is keyed per chosen profile id, never per user object and never
    shared: two learners who chose differently resolve chains with different leads
    in the same process, and the same choice re-resolves to the one cached chain."""
    from app.infrastructure.web import dependencies

    _declare_two_profile_registry(monkeypatch)
    dependencies.clear_generation_chain_caches()

    sentinel = dependencies.get_generation()
    cheap = dependencies._resolve_user_chain("cheap", sentinel)
    primary = dependencies._resolve_user_chain("primary", sentinel)

    assert cheap is not primary
    assert _chain_ids(cheap) == ["cheap", "primary"]
    assert _chain_ids(primary) == ["primary", "cheap"]
    # One chain per profile id per process: repeat resolutions reuse it.
    assert dependencies._resolve_user_chain("cheap", sentinel) is cheap
    assert dependencies._resolve_user_chain("primary", sentinel) is primary


def test_clear_generation_chain_caches_drops_the_per_user_chains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The test hook that clears ``get_settings`` also drops the per-user chain
    cache — a redeclared registry must never keep serving chains built from the
    previous one."""
    from app.infrastructure.web import dependencies

    _declare_two_profile_registry(monkeypatch)
    dependencies.clear_generation_chain_caches()
    sentinel = dependencies.get_generation()
    cheap = dependencies._resolve_user_chain("cheap", sentinel)

    dependencies.clear_generation_chain_caches()

    assert dependencies._resolve_user_chain("cheap", dependencies.get_generation()) is not cheap


def test_the_explain_and_card_adapters_never_gain_a_preference_parameter() -> None:
    """The selection-Explain chain and the quiz/card adapters are house-routed
    always: their composition seams accept no user/profile/preference input, so no
    stored choice can reach them through wiring drift."""
    import inspect

    from app.infrastructure.quiz import build_quiz_adapter
    from app.infrastructure.web import dependencies

    assert inspect.signature(dependencies.get_explain_generation).parameters == {}
    assert list(inspect.signature(build_quiz_adapter).parameters) == ["settings", "provider"]
    assert inspect.signature(dependencies.get_card_generation).parameters == {}
