"""Per-user generation chain wiring at the real conversations surface (live DB).

Exercises the composition seam where a learner's stored AI-profile choice meets
the Ask/Teach turn path, end to end through FastAPI against a real Postgres:

- A stored choice that names a declared profile leads that user's chain; a turn
  served from the resolved chain is shaped exactly like today's (same statuses,
  same view), and the lead is observable in the turn's model identity even on a
  not-found turn, where the port is never invoked and the port attribute is the
  report (HP-03).
- Two users with different choices in the same process resolve different leads;
  a user with nothing stored resolves the operator default chain object itself
  (HP-03; byte-identical serving to before the choice existed).
- A stale stored id — one the operator renamed or removed — serves the default
  chain and logs a warning; it never errors a turn.
- The selection-Explain chain stays house-routed: a stored choice moves nothing
  about an explain-origin turn (HP-04).
- Spend and rails are unchanged in mechanism on the per-user path: the served
  turn debits the caller's own day, and the daily rails refuse before anything
  is retrieved or generated (HP-05/HP-07).

Seeding mirrors ``test_web_conversations``: sources, corpus, and conversations
through the real repositories on the shared rolled-back ``db_conn``.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection
from sqlalchemy.exc import OperationalError

from app.domain.entities import (
    ANSWERED,
    MODE_ANSWER,
    AnswerStreamEvent,
    Conversation,
    CorpusSectionRecord,
    GeneratedAnswer,
    ParsedSection,
    SectionChunk,
    Source,
    User,
)
from app.infrastructure.db.repositories import (
    SqlAlchemyAiPreferenceRepository,
    SqlAlchemyAiSpendDayRepository,
    SqlAlchemyConversationRepository,
    SqlAlchemyCorpusRepository,
    SqlAlchemyEmbeddingIndexRepository,
    SqlAlchemySourceRepository,
)
from app.infrastructure.embeddings import DeterministicEmbeddingAdapter
from tests.conftest import TEST_PASSWORD, clear_settings_and_generation_caches, requires_db

pytestmark = requires_db

_PHOTO = "photosynthesis converts sunlight into chemical energy in green plants"
_SECTION_PATH = ("Biology",)
_ANCHOR = "bio.xhtml"
_DEFAULT_LEAD_MODEL = "local-extractive"

# A declared two-profile registry: "primary" (the operator default lead) and the
# economy tier, both deterministic local adapters so the suite stays offline.
# "scout" is the Anthropic-shaped profile whose *model identity* is distinct: its
# adapter builds lazily and is never invoked on these paths, so the declared
# model name is observable without a network.
_LOCAL_PROFILES_JSON = (
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
_SCOUT_PROFILES_JSON = (
    '[{"id": "primary", "kind": "local", "model": "m", "max_tokens": 1, '
    '"price_input_usd_per_million_tokens": 3.0, "price_output_usd_per_million_tokens": 15.0, '
    '"price_cache_read_usd_per_million_tokens": 0.3, '
    '"price_cache_creation_usd_per_million_tokens": 3.75, "grounding": "verified-spans", '
    '"ask_enabled": true, "teach_enabled": true},'
    '{"id": "scout", "kind": "anthropic", "model": "claude-scout-x", '
    '"api_key_env": "LEARNY_TEST_PROFILE_KEY", "max_tokens": 8, '
    '"price_input_usd_per_million_tokens": 1.0, "price_output_usd_per_million_tokens": 5.0, '
    '"price_cache_read_usd_per_million_tokens": 0.1, '
    '"price_cache_creation_usd_per_million_tokens": 1.25, "grounding": "verified-spans", '
    '"ask_enabled": true, "teach_enabled": true}]'
)


def _declare_registry(monkeypatch: pytest.MonkeyPatch, profiles_json: str) -> None:
    """Declare a registry for this test and reset the settings-derived chain caches."""
    monkeypatch.setenv("LEARNY_GENERATION_PROFILES", profiles_json)
    monkeypatch.setenv("LEARNY_TEST_PROFILE_KEY", "sk-ant-test")
    clear_settings_and_generation_caches()


def _register(client: TestClient, email: str) -> str:
    resp = client.post(
        "/api/auth/register", json={"email": email, "password": TEST_PASSWORD, "accepted_tos": True}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _csrf(client: TestClient) -> str:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200, resp.text
    return resp.json()["csrf_token"]


def _seed_source(db_conn: Connection, user_id: str) -> UUID:
    """An owned, ready source whose one section is corpus-built and embedded."""
    now = datetime.now(UTC)
    source_id = (
        SqlAlchemySourceRepository(db_conn)
        .add(
            Source(
                id=uuid4(),
                user_id=UUID(user_id),
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
        .id
    )
    SqlAlchemyCorpusRepository(db_conn).replace(
        source_id,
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
                    section_path=_SECTION_PATH,
                    anchor=_ANCHOR,
                    blocks=(),
                ),
                markdown="",
                chunks=(
                    SectionChunk(
                        index=0,
                        text=_PHOTO,
                        section_path=_SECTION_PATH,
                        anchor=_ANCHOR,
                        page_span=None,
                    ),
                ),
            ),
        ),
    )
    index = SqlAlchemyEmbeddingIndexRepository(db_conn)
    adapter = DeterministicEmbeddingAdapter()
    chunks = index.chunks_for_source(source_id)
    vectors = adapter.embed_documents([chunk.text for chunk in chunks])
    index.set_embeddings(
        list(zip((chunk.id for chunk in chunks), vectors, strict=True)), model=adapter.model
    )
    return source_id


def _seed_conversation(db_conn: Connection, source_id: UUID, *, scope: tuple[str, ...]) -> UUID:
    now = datetime.now(UTC)
    conversation = SqlAlchemyConversationRepository(db_conn).add(
        Conversation(
            id=uuid4(),
            source_id=source_id,
            title="A Book",
            scope_anchors=scope,
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
    return conversation.id


def _store_choice(db_conn: Connection, user_id: str, profile_id: str) -> None:
    SqlAlchemyAiPreferenceRepository(db_conn).upsert(UUID(user_id), profile_id)


def _post_turn(client: TestClient, conversation_id: UUID, csrf: str, **body: object):
    return client.post(
        f"/api/conversations/{conversation_id}/turns",
        json={"message": "photosynthesis sunlight energy", "mode": MODE_ANSWER, **body},
        headers={"X-CSRF-Token": csrf},
    )


# --- The turn is served from the user's resolved chain (HP-03) --------------------


def test_a_stored_choice_leads_the_users_turn_chain(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A choice naming a declared, eligible profile leads that user's chain, while
    a reader with nothing stored in the same process still serves the operator
    default lead. The scoped conversation sees no evidence for its dead anchor, so
    the turn takes the not-found outcome whose model identity is the chain lead's
    — the port is never touched, which is what makes the lead observable offline."""
    _declare_registry(monkeypatch, _SCOUT_PROFILES_JSON)
    client = auth_client

    chooser_id = _register(client, "chooser@example.com")
    chooser_csrf = _csrf(client)
    _store_choice(db_conn, chooser_id, "scout")
    chosen_conversation = _seed_conversation(
        db_conn, _seed_source(db_conn, chooser_id), scope=("missing.xhtml",)
    )

    plain_id = _register(client, "plain-reader@example.com")
    plain_csrf = _csrf(client)
    plain_conversation = _seed_conversation(
        db_conn, _seed_source(db_conn, plain_id), scope=("missing.xhtml",)
    )

    chosen = _post_turn(client, chosen_conversation, chooser_csrf)
    plain = _post_turn(client, plain_conversation, plain_csrf)

    assert chosen.status_code == 201, chosen.text
    assert plain.status_code == 201, plain.text
    assert chosen.json()["answer_status"] == "not_found_in_scope"
    # The chosen profile led the chooser's chain; the other reader got today's
    # operator default lead — same process, different leads.
    assert chosen.json()["model"] == "claude-scout-x"
    assert plain.json()["model"] == _DEFAULT_LEAD_MODEL


def test_a_stale_stored_choice_serves_the_default_chain(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An operator edit that removes a stored profile id must never break asking:
    the turn serves the operator default chain and one warning records the stale
    hint."""
    _declare_registry(monkeypatch, _SCOUT_PROFILES_JSON)
    client = auth_client

    user_id = _register(client, "stale-choice@example.com")
    csrf = _csrf(client)
    _store_choice(db_conn, user_id, "removed-profile")
    conversation = _seed_conversation(
        db_conn, _seed_source(db_conn, user_id), scope=("missing.xhtml",)
    )

    with caplog.at_level("WARNING"):
        resp = _post_turn(client, conversation, csrf)

    assert resp.status_code == 201, resp.text
    assert resp.json()["model"] == _DEFAULT_LEAD_MODEL  # the operator default lead
    assert any("removed-profile" in record.message for record in caplog.records)


# --- The seam itself: default object, choice-keyed cache, conservative failure ----


def _domain_user(user_id: str) -> User:
    return User(id=UUID(user_id), email=f"{user_id}@example.com", created_at=datetime.now(UTC))


def test_an_unset_choice_resolves_the_default_chain_object_itself(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.infrastructure.web import dependencies

    _declare_registry(monkeypatch, _LOCAL_PROFILES_JSON)
    default = dependencies.get_generation()

    resolved = dependencies.get_generation_for_user(db_conn, _domain_user(str(uuid4())), default)

    assert resolved is default  # byte-identical to the pre-choice wiring


def test_the_chain_cache_is_keyed_on_the_choice_never_the_user(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two learners who chose differently resolve chains with different leads in
    the same process; two who chose the same profile share the one cached chain —
    the key is the profile id, never the user or the row."""
    from app.infrastructure.answering import RoutingGenerationAdapter
    from app.infrastructure.db.repositories import SqlAlchemyUserRepository
    from app.infrastructure.web import dependencies

    _declare_registry(monkeypatch, _LOCAL_PROFILES_JSON)
    default = dependencies.get_generation()

    def _real_user() -> str:
        user = User(id=uuid4(), email=f"{uuid4()}@example.com", created_at=datetime.now(UTC))
        SqlAlchemyUserRepository(db_conn).add(user)
        return str(user.id)

    economy, other_economy, premium = (_real_user() for _ in range(3))
    prefs = SqlAlchemyAiPreferenceRepository(db_conn)
    prefs.upsert(UUID(economy), "cheap")
    prefs.upsert(UUID(other_economy), "cheap")
    prefs.upsert(UUID(premium), "primary")

    economy_chain = dependencies.get_generation_for_user(db_conn, _domain_user(economy), default)
    other_economy_chain = dependencies.get_generation_for_user(
        db_conn, _domain_user(other_economy), default
    )
    premium_chain = dependencies.get_generation_for_user(db_conn, _domain_user(premium), default)

    assert isinstance(economy_chain, RoutingGenerationAdapter)
    assert [entry.profile.id for entry in economy_chain._chain] == ["cheap", "primary"]
    assert [entry.profile.id for entry in premium_chain._chain] == ["primary", "cheap"]
    assert economy_chain is not premium_chain  # different choices, different leads
    assert economy_chain is other_economy_chain  # same choice, one shared chain


def test_a_preference_read_failure_propagates_instead_of_masking(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A preference read failure behaves like every sibling repository's failure on
    this connection: it propagates. Serving the operator default through the
    failure would mask a real outage behind a successful-looking turn."""
    from app.infrastructure.web import dependencies

    _declare_registry(monkeypatch, _LOCAL_PROFILES_JSON)

    class _ExplodingRepo:
        def __init__(self, _conn: Connection) -> None:
            pass

        def get_by_user(self, _user_id: UUID) -> None:
            raise OperationalError("SELECT", {}, Exception("database is down"))

    monkeypatch.setattr(dependencies, "SqlAlchemyAiPreferenceRepository", _ExplodingRepo)

    with pytest.raises(OperationalError):
        dependencies.get_generation_for_user(
            db_conn, _domain_user(str(uuid4())), dependencies.get_generation()
        )


# --- The Explain chain and the spend rails are unmoved (HP-04/HP-05/HP-07) --------


class _ExplainSpy:
    """A recording fake for the house-routed Explain chain (mirrors ``_ChainSpy``)."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0

    @property
    def model(self) -> str:
        return self.name

    def _answer(self, evidence: Sequence[object]) -> GeneratedAnswer:
        cited = (evidence[0].chunk_id,) if evidence else ()  # type: ignore[attr-defined]
        return GeneratedAnswer(
            text=f"served by {self.name}",
            cited_chunk_ids=cited,
            model=self.name,
            found=True,
        )

    def generate(self, *, evidence: Sequence[object], **_kwargs: object) -> GeneratedAnswer:  # noqa: ANN003
        self.calls += 1
        return self._answer(evidence)

    def generate_stream(  # noqa: ANN202, ANN003
        self, *, evidence: Sequence[object], **_kwargs: object
    ) -> Iterator[AnswerStreamEvent]:
        raise AssertionError("the buffered turns in this module never stream")


def test_the_explain_chain_stays_house_routed_despite_a_stored_choice(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.infrastructure.web.dependencies import get_explain_generation

    _declare_registry(monkeypatch, _LOCAL_PROFILES_JSON)
    client = auth_client
    spy = _ExplainSpy("explain-spy")
    client.app.dependency_overrides[get_explain_generation] = lambda: spy
    try:
        user_id = _register(client, "explain-keeper@example.com")
        csrf = _csrf(client)
        _store_choice(db_conn, user_id, "cheap")
        conversation = _seed_conversation(db_conn, _seed_source(db_conn, user_id), scope=())

        explained = _post_turn(client, conversation, csrf, origin="explain_selection")
        ordinary = _post_turn(client, conversation, csrf)
    finally:
        client.app.dependency_overrides.pop(get_explain_generation, None)

    # The marked turn was served by the house Explain chain (the stored choice did
    # not move it); the ordinary turn was served by the user's own chain.
    assert explained.status_code == 201, explained.text
    assert explained.json()["model"] == "explain-spy"
    assert ordinary.status_code == 201, ordinary.text
    assert ordinary.json()["answer_status"] == ANSWERED
    assert ordinary.json()["model"] == _DEFAULT_LEAD_MODEL
    assert spy.calls == 1  # the Explain chain served exactly the marked turn


def test_a_turn_served_from_the_user_chain_debits_the_callers_day(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The debit mechanism is untouched by whose chain served: the answered turn
    records the caller's own day — the ask counter counts even though the
    deterministic adapter reports no usage to price."""
    _declare_registry(monkeypatch, _LOCAL_PROFILES_JSON)
    client = auth_client

    user_id = _register(client, "debited-chooser@example.com")
    csrf = _csrf(client)
    _store_choice(db_conn, user_id, "cheap")
    conversation = _seed_conversation(db_conn, _seed_source(db_conn, user_id), scope=())

    resp = _post_turn(client, conversation, csrf)

    assert resp.status_code == 201, resp.text
    row = SqlAlchemyAiSpendDayRepository(db_conn).get_for_day(
        UUID(user_id), datetime.now(UTC).date()
    )
    assert row is not None
    assert row.ask_count == 1
    assert row.usd_micros == 0


def test_the_daily_rails_refuse_before_the_user_chain_serves(
    auth_client: TestClient,
    db_conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rails precede any port touch regardless of the resolved profile: with
    the day's cap spent, the chooser's turn is a 429 with the honest copy and the
    conversation (and its history) survive the refusal untouched."""
    _declare_registry(monkeypatch, _SCOUT_PROFILES_JSON)
    client = auth_client

    user_id = _register(client, "capped-chooser@example.com")
    csrf = _csrf(client)
    _store_choice(db_conn, user_id, "scout")
    conversation = _seed_conversation(db_conn, _seed_source(db_conn, user_id), scope=())

    SqlAlchemyAiSpendDayRepository(db_conn).record(
        UUID(user_id), datetime.now(UTC).date(), usd_micros=500_000
    )

    resp = _post_turn(client, conversation, csrf)

    assert resp.status_code == 429, resp.text
    assert "00:00 UTC" in resp.json()["detail"]
    still_there = client.get(
        f"/api/conversations/{conversation.id}", headers={"X-CSRF-Token": csrf}
    )
    assert still_there.status_code == 200, still_there.text
    assert still_there.json()["turns"] == []
