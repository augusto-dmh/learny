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
ask-eligible. The cached FastAPI accessors expose the two chains.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from app.core.config import Settings
from app.infrastructure.answering import (
    AnthropicGenerationAdapter,
    ChainEntry,
    DeterministicGenerationAdapter,
    RoutingGenerationAdapter,
    build_generation_chain,
)
from app.infrastructure.providers import GenerationProfileSettings

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
    assert adapter._effort == "xhigh"


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
    from app.infrastructure.web.dependencies import build_budget

    monkeypatch.setenv("LEARNY_GENERATION_PROFILES", _TWO_PROFILES_JSON)
    get_settings.cache_clear()
    try:
        budget = build_budget(db_conn)
    finally:
        get_settings.cache_clear()

    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    assert budget.usage_micros(usage, "cheap") == 1_200_000  # $0.20 + $1.00 per M
    assert budget.usage_micros(usage, "primary") == 18_000_000  # $3.00 + $15.00 per M
    assert budget.usage_micros(usage) == 18_000_000  # no stamp is the primary catalog


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
