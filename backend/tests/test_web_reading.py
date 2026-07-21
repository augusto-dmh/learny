"""A6 gate — reader router (integration, live test DB).

Exercises the chapter-flow and reading-position endpoints end-to-end through FastAPI's
``TestClient`` against a real Postgres, asserting the spec ACs at the route level:

- ``GET /api/sources/{id}/chapter`` — owned anchor → 200 chapter (shape + sections +
  embedded position); alias anchor → 200 canonical chapter; unknown anchor / non-owner /
  missing source → identical 404; no ``anchor`` → resume (stored chapter, else first).
- ``PUT /api/sources/{id}/reading-position`` — owner → 200 stored view (canonical anchor
  + server percent); alias write stores canonical; bad anchor → 404 and nothing stored;
  no session → 401; missing CSRF / untrusted Origin → 403 (RD-01/02/08/09).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, select

from app.application.study import local_day
from app.domain.entities import (
    CorpusSectionRecord,
    ParsedSection,
    Source,
)
from app.infrastructure.db.metadata import reading_positions, study_days
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemySourceRepository,
)
from tests.conftest import TEST_ORIGIN, requires_db

pytestmark = requires_db


# --- Fixtures ------------------------------------------------------------------


@pytest.fixture
def reading_client(db_conn: Connection, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """A ``TestClient`` for the reader routes, isolated to a rolled-back txn.

    Mirrors ``notes_client`` (shared ``db_conn``, non-Secure cookie, trusted Origin,
    generous limiter). Every reader path is one atomic request, so no UoW override.
    """
    from app.core.config import get_settings
    from app.infrastructure.web.dependencies import get_db_connection
    from app.infrastructure.web.rate_limit import (
        InMemoryFixedWindowRateLimiter,
        get_rate_limiter,
        set_rate_limiter,
    )
    from app.main import create_app

    monkeypatch.setenv("LEARNY_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("LEARNY_CSRF_TRUSTED_ORIGINS", TEST_ORIGIN)
    get_settings.cache_clear()

    previous_limiter = get_rate_limiter()
    set_rate_limiter(InMemoryFixedWindowRateLimiter(max_attempts=1000))

    app = create_app()

    def _override() -> Iterator[Connection]:
        yield db_conn

    app.dependency_overrides[get_db_connection] = _override
    with TestClient(app, headers={"Origin": TEST_ORIGIN}) as c:
        yield c
    app.dependency_overrides.clear()
    set_rate_limiter(previous_limiter)
    get_settings.cache_clear()


# --- Auth / request helpers ----------------------------------------------------


def _register(client: TestClient, email: str) -> str:
    resp = client.post(
        "/api/auth/register", json={"email": email, "password": "correct horse battery staple"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _csrf(client: TestClient) -> str:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200, resp.text
    return resp.json()["csrf_token"]


def _put_position(
    client: TestClient,
    source_id: object,
    anchor: str,
    *,
    csrf: str | None,
    origin: str | None = None,
):
    headers: dict[str, str] = {}
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    if origin is not None:
        headers["Origin"] = origin
    return client.put(
        f"/api/sources/{source_id}/reading-position", json={"anchor": anchor}, headers=headers
    )


# --- Seeding -------------------------------------------------------------------


def _persist_source(db_conn: Connection, user_id: str) -> UUID:
    now = datetime.now(UTC)
    source = Source(
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
    return SqlAlchemySourceRepository(db_conn).add(source).id


def _record(position, depth, anchor, markdown, aliases=()) -> CorpusSectionRecord:  # noqa: ANN001
    return CorpusSectionRecord(
        section=ParsedSection(
            position=position,
            title=f"Section {position}",
            depth=depth,
            section_path=(f"Section {position}",),
            anchor=anchor,
            blocks=(),
            anchor_aliases=tuple(aliases),
        ),
        markdown=markdown,
        chunks=(),
    )


def _seed_book(db_conn: Connection, source_id: UUID) -> None:
    """Two chapters (depths 0,1,0,1), word counts 3,2,1,4; "c2" aliased "old-c2"."""
    SqlAlchemyCorpusRepository(db_conn).replace(
        source_id,
        title="A Book",
        authors=(),
        language="en",
        schema_version=1,
        sections=[
            _record(0, 0, "c1", "a b c"),
            _record(1, 1, "c1s1", "d e"),
            _record(2, 0, "c2", "f", aliases=("old-c2",)),
            _record(3, 1, "c2s1", "g h i j"),
        ],
    )


# --- GET chapter ---------------------------------------------------------------


def test_get_chapter_returns_200_with_shape_and_sections(
    reading_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(reading_client, "chapter-ok@example.com")
    source_id = _persist_source(db_conn, user_id)
    _seed_book(db_conn, source_id)

    resp = reading_client.get(f"/api/sources/{source_id}/chapter", params={"anchor": "c1s1"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {
        "chapter_title",
        "chapter_anchor",
        "chapter_index",
        "chapter_count",
        "prev_anchor",
        "next_anchor",
        "words_before_chapter",
        "chapter_word_count",
        "total_word_count",
        "sections",
        "reading_position",
    }
    assert body["chapter_index"] == 0
    assert body["chapter_count"] == 2
    assert body["chapter_anchor"] == "c1"
    assert body["prev_anchor"] is None
    assert body["next_anchor"] == "c2"
    assert body["words_before_chapter"] == 0
    assert body["chapter_word_count"] == 5
    assert body["total_word_count"] == 10
    assert [s["anchor"] for s in body["sections"]] == ["c1", "c1s1"]
    assert body["sections"][0]["word_count"] == 3
    assert body["sections"][0]["markdown"] == "a b c"
    assert body["reading_position"] is None


def test_get_chapter_alias_anchor_returns_canonical_chapter(
    reading_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(reading_client, "chapter-alias@example.com")
    source_id = _persist_source(db_conn, user_id)
    _seed_book(db_conn, source_id)

    resp = reading_client.get(f"/api/sources/{source_id}/chapter", params={"anchor": "old-c2"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["chapter_anchor"] == "c2"
    assert resp.json()["chapter_index"] == 1


def test_get_chapter_unknown_anchor_and_non_owner_return_identical_404(
    reading_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(reading_client, "chapter-owner@example.com")
    source_id = _persist_source(db_conn, user_id)
    _seed_book(db_conn, source_id)

    unknown = reading_client.get(
        f"/api/sources/{source_id}/chapter", params={"anchor": "missing"}
    )

    _register(reading_client, "chapter-intruder@example.com")  # become a different user
    non_owned = reading_client.get(
        f"/api/sources/{source_id}/chapter", params={"anchor": "c1"}
    )
    missing = reading_client.get(f"/api/sources/{uuid4()}/chapter", params={"anchor": "c1"})

    assert unknown.status_code == 404, unknown.text
    assert non_owned.status_code == 404, non_owned.text
    assert missing.status_code == 404, missing.text
    # No existence disclosure: a valid-but-unowned anchor and a missing source match.
    assert non_owned.json() == missing.json()


def test_get_chapter_no_anchor_resumes_first_chapter_without_stored_position(
    reading_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(reading_client, "chapter-resume-first@example.com")
    source_id = _persist_source(db_conn, user_id)
    _seed_book(db_conn, source_id)

    resp = reading_client.get(f"/api/sources/{source_id}/chapter")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["chapter_index"] == 0
    assert body["reading_position"] is None


def test_get_chapter_no_anchor_resumes_stored_position_chapter(
    reading_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(reading_client, "chapter-resume-stored@example.com")
    csrf = _csrf(reading_client)
    source_id = _persist_source(db_conn, user_id)
    _seed_book(db_conn, source_id)
    # Store a position in chapter 2 via the PUT route, then resume with no anchor.
    assert _put_position(reading_client, source_id, "c2", csrf=csrf).status_code == 200

    resp = reading_client.get(f"/api/sources/{source_id}/chapter")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["chapter_index"] == 1
    assert body["reading_position"]["anchor"] == "c2"
    assert body["reading_position"]["percent"] == 50.0


# --- PUT reading-position ------------------------------------------------------


def test_put_reading_position_returns_stored_view_with_server_percent(
    reading_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(reading_client, "rp-ok@example.com")
    csrf = _csrf(reading_client)
    source_id = _persist_source(db_conn, user_id)
    _seed_book(db_conn, source_id)

    resp = _put_position(reading_client, source_id, "c1s1", csrf=csrf)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"anchor", "percent", "updated_at"}
    assert body["anchor"] == "c1s1"
    # percent = words before row 1 (3) / total (10) * 100 = 30.0 (server-computed).
    assert body["percent"] == 30.0


def test_put_reading_position_alias_stores_canonical(
    reading_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(reading_client, "rp-alias@example.com")
    csrf = _csrf(reading_client)
    source_id = _persist_source(db_conn, user_id)
    _seed_book(db_conn, source_id)

    resp = _put_position(reading_client, source_id, "old-c2", csrf=csrf)

    assert resp.status_code == 200, resp.text
    assert resp.json()["anchor"] == "c2"
    # The persisted row carries the canonical anchor, not the alias.
    stored = db_conn.execute(
        select(reading_positions.c.anchor).where(
            reading_positions.c.source_id == source_id
        )
    ).scalar_one()
    assert stored == "c2"


def test_put_reading_position_bad_anchor_404s_and_stores_nothing(
    reading_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(reading_client, "rp-badanchor@example.com")
    csrf = _csrf(reading_client)
    source_id = _persist_source(db_conn, user_id)
    _seed_book(db_conn, source_id)

    resp = _put_position(reading_client, source_id, "missing", csrf=csrf)

    assert resp.status_code == 404, resp.text
    count = db_conn.execute(
        select(reading_positions.c.anchor).where(
            reading_positions.c.source_id == source_id
        )
    ).all()
    assert count == []


def test_put_reading_position_non_owner_returns_404(
    reading_client: TestClient, db_conn: Connection
) -> None:
    owner_id = _register(reading_client, "rp-owner@example.com")
    source_id = _persist_source(db_conn, owner_id)
    _seed_book(db_conn, source_id)

    _register(reading_client, "rp-intruder@example.com")
    csrf = _csrf(reading_client)
    resp = _put_position(reading_client, source_id, "c1", csrf=csrf)
    assert resp.status_code == 404, resp.text


def test_put_reading_position_missing_csrf_returns_403(
    reading_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(reading_client, "rp-csrf@example.com")
    source_id = _persist_source(db_conn, user_id)
    _seed_book(db_conn, source_id)
    resp = _put_position(reading_client, source_id, "c1", csrf=None)
    assert resp.status_code == 403, resp.text


def test_put_reading_position_untrusted_origin_returns_403(
    reading_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(reading_client, "rp-origin@example.com")
    csrf = _csrf(reading_client)
    source_id = _persist_source(db_conn, user_id)
    _seed_book(db_conn, source_id)
    resp = _put_position(
        reading_client, source_id, "c1", csrf=csrf, origin="http://evil.example.com"
    )
    assert resp.status_code == 403, resp.text


def test_put_reading_position_unauthenticated_returns_401(
    reading_client: TestClient, db_conn: Connection
) -> None:
    reading_client.cookies.clear()
    resp = _put_position(reading_client, uuid4(), "c1", csrf="whatever")
    assert resp.status_code == 401, resp.text


# --- study-day rollup + client timezone (HOME-08/09, I-6) ----------------------


def test_put_reading_position_credits_a_reading_study_day(
    reading_client: TestClient, db_conn: Connection
) -> None:
    # HOME-08/09: a saved position with the client-timezone header credits exactly one
    # study day with reading_updates=1 (and no review credit).
    user_id = _register(reading_client, "rp-study@example.com")
    csrf = _csrf(reading_client)
    source_id = _persist_source(db_conn, user_id)
    _seed_book(db_conn, source_id)

    resp = reading_client.put(
        f"/api/sources/{source_id}/reading-position",
        json={"anchor": "c1s1"},
        headers={"X-CSRF-Token": csrf, "X-Client-Timezone": "America/Sao_Paulo"},
    )

    assert resp.status_code == 200, resp.text
    rows = db_conn.execute(
        select(study_days.c.reviews_count, study_days.c.reading_updates).where(
            study_days.c.user_id == UUID(user_id)
        )
    ).all()
    assert [(r.reviews_count, r.reading_updates) for r in rows] == [(0, 1)]


def test_put_reading_position_garbage_timezone_succeeds_and_credits_utc_day(
    reading_client: TestClient, db_conn: Connection
) -> None:
    # HOME-09: a garbage zone must not 4xx/5xx; the position is stored and the study day
    # is credited on the UTC date.
    user_id = _register(reading_client, "rp-badtz@example.com")
    csrf = _csrf(reading_client)
    source_id = _persist_source(db_conn, user_id)
    _seed_book(db_conn, source_id)

    before = datetime.now(UTC)
    resp = reading_client.put(
        f"/api/sources/{source_id}/reading-position",
        json={"anchor": "c1s1"},
        headers={"X-CSRF-Token": csrf, "X-Client-Timezone": "Mars/Olympus"},
    )
    after = datetime.now(UTC)

    assert resp.status_code == 200, resp.text
    row = db_conn.execute(
        select(study_days.c.day, study_days.c.reading_updates).where(
            study_days.c.user_id == UUID(user_id)
        )
    ).one()
    assert row.reading_updates == 1
    assert row.day in {local_day(before, None), local_day(after, None)}


def test_put_reading_position_body_is_unchanged_by_the_timezone_header(
    reading_client: TestClient, db_conn: Connection
) -> None:
    # I-6: the client-timezone header is additive — it changes no response field. The
    # body schema and its header-independent values (anchor, server percent) are the same
    # whether or not it is sent. (updated_at is the server clock and advances per write,
    # so it is deliberately not compared.)
    user_id = _register(reading_client, "rp-i6@example.com")
    csrf = _csrf(reading_client)
    source_id = _persist_source(db_conn, user_id)
    _seed_book(db_conn, source_id)

    without = _put_position(reading_client, source_id, "c1s1", csrf=csrf)
    with_header = reading_client.put(
        f"/api/sources/{source_id}/reading-position",
        json={"anchor": "c1s1"},
        headers={"X-CSRF-Token": csrf, "X-Client-Timezone": "Asia/Tokyo"},
    )

    assert without.status_code == 200, without.text
    assert with_header.status_code == 200, with_header.text
    assert set(without.json()) == set(with_header.json()) == {
        "anchor",
        "percent",
        "updated_at",
    }
    assert without.json()["anchor"] == with_header.json()["anchor"] == "c1s1"
    assert without.json()["percent"] == with_header.json()["percent"] == 30.0
