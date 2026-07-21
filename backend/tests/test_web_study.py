"""Study + continue-reading routers (integration, live test DB).

Exercises ``GET /api/study/days`` and ``GET /api/reading/continue`` end-to-end through
FastAPI's ``TestClient`` against a real Postgres, asserting the spec ACs at the route
level:

- ``GET /api/study/days`` — owner → 200 window rows + ``studied_last_14``; ``window``
  bounds 7..365 (else 422); another user's rows never appear (HOME-15); a read persists
  nothing (I-4); no session → 401 (HOME-11/12).
- ``GET /api/reading/continue`` — owner with a position → 200 hero (title + chapter +
  percent); no positions → 200 ``null``; another user's position never returned (HOME-04);
  no session → 401 (HOME-01/02).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, func, select

from app.domain.entities import CorpusSectionRecord, ParsedSection, Source
from app.infrastructure.db.metadata import study_days
from app.infrastructure.db.repositories import (
    SqlAlchemyCorpusRepository,
    SqlAlchemyReadingPositionRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyStudyDayRepository,
)
from tests.conftest import TEST_ORIGIN, requires_db

pytestmark = requires_db


# --- Fixtures ------------------------------------------------------------------


@pytest.fixture
def study_client(db_conn: Connection, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """A ``TestClient`` for the study routes, isolated to a rolled-back txn.

    Mirrors ``reading_client`` (shared ``db_conn``, non-Secure cookie, trusted Origin,
    generous limiter). Both study reads are single-request GETs, so no UoW override.
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


# --- Auth / seeding helpers ----------------------------------------------------


def _register(client: TestClient, email: str) -> str:
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _seed_study_days(db_conn: Connection, user_id: str, days: list[date]) -> None:
    repo = SqlAlchemyStudyDayRepository(db_conn)
    for d in days:
        repo.record(UUID(user_id), d, reviews=1)


def _persist_source(db_conn: Connection, user_id: str, *, title: str = "A Book") -> UUID:
    now = datetime.now(UTC)
    source = Source(
        id=uuid4(),
        user_id=UUID(user_id),
        title=title,
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


def _record(position, depth, anchor, markdown) -> CorpusSectionRecord:  # noqa: ANN001
    return CorpusSectionRecord(
        section=ParsedSection(
            position=position,
            title=f"Chapter {position}",
            depth=depth,
            section_path=(f"Chapter {position}",),
            anchor=anchor,
            blocks=(),
            anchor_aliases=(),
        ),
        markdown=markdown,
        chunks=(),
    )


def _seed_book(db_conn: Connection, source_id: UUID) -> None:
    SqlAlchemyCorpusRepository(db_conn).replace(
        source_id,
        title="A Book",
        authors=(),
        language="en",
        schema_version=1,
        sections=[
            _record(0, 0, "c1", "a b c"),
            _record(1, 1, "c1s1", "d e"),
            _record(2, 0, "c2", "f"),
        ],
    )


def _seed_position(
    db_conn: Connection, user_id: str, source_id: UUID, anchor: str, *, percent: str
) -> datetime:
    when = datetime.now(UTC)
    SqlAlchemyReadingPositionRepository(db_conn).upsert(
        UUID(user_id), source_id, anchor=anchor, percent=Decimal(percent), updated_at=when
    )
    return when


# --- GET /api/study/days -------------------------------------------------------


def test_study_days_returns_window_rows_and_studied_last_14(
    study_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(study_client, "study-days@example.com")
    today = datetime.now(UTC).date()
    # Two days inside the 14-day window and one 20 days ago (inside the 84 window but
    # outside the 14).
    _seed_study_days(
        db_conn,
        user_id,
        [today, today - timedelta(days=2), today - timedelta(days=20)],
    )

    resp = study_client.get("/api/study/days")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"days", "studied_last_14"}
    assert [d["day"] for d in body["days"]] == [
        (today - timedelta(days=20)).isoformat(),
        (today - timedelta(days=2)).isoformat(),
        today.isoformat(),
    ]
    assert body["days"][-1] == {
        "day": today.isoformat(),
        "reviews_count": 1,
        "reading_updates": 0,
    }
    # Only the two days within the last 14 count; the 20-days-ago one does not.
    assert body["studied_last_14"] == 2


@pytest.mark.parametrize("window", [6, 0, 366, 400])
def test_study_days_out_of_range_window_returns_422(
    study_client: TestClient, db_conn: Connection, window: int
) -> None:
    _register(study_client, f"study-w{window}@example.com")
    resp = study_client.get("/api/study/days", params={"window": window})
    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize("window", [7, 84, 365])
def test_study_days_in_range_window_is_accepted(
    study_client: TestClient, db_conn: Connection, window: int
) -> None:
    _register(study_client, f"study-ok-w{window}@example.com")
    resp = study_client.get("/api/study/days", params={"window": window})
    assert resp.status_code == 200, resp.text


def test_study_days_never_returns_another_users_rows(
    study_client: TestClient, db_conn: Connection
) -> None:
    # HOME-15 / I-5: seed another user's study day, then become a fresh caller — the
    # other user's row must never appear.
    other_id = _register(study_client, "study-other@example.com")
    today = datetime.now(UTC).date()
    _seed_study_days(db_conn, other_id, [today, today - timedelta(days=1)])

    caller_id = _register(study_client, "study-caller@example.com")  # switch session
    _seed_study_days(db_conn, caller_id, [today])

    resp = study_client.get("/api/study/days")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [d["day"] for d in body["days"]] == [today.isoformat()]
    assert body["studied_last_14"] == 1


def test_study_days_empty_for_a_new_user(
    study_client: TestClient, db_conn: Connection
) -> None:
    _register(study_client, "study-empty@example.com")
    resp = study_client.get("/api/study/days")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"days": [], "studied_last_14": 0}


def test_study_days_read_persists_nothing(
    study_client: TestClient, db_conn: Connection
) -> None:
    # I-4: studied_last_14 is derived at read time — a GET creates no rows and is stable.
    user_id = _register(study_client, "study-noderive@example.com")
    today = datetime.now(UTC).date()
    _seed_study_days(db_conn, user_id, [today, today - timedelta(days=1)])
    before = db_conn.execute(
        select(func.count()).select_from(study_days).where(
            study_days.c.user_id == UUID(user_id)
        )
    ).scalar_one()

    first = study_client.get("/api/study/days")
    second = study_client.get("/api/study/days")

    after = db_conn.execute(
        select(func.count()).select_from(study_days).where(
            study_days.c.user_id == UUID(user_id)
        )
    ).scalar_one()
    assert first.json() == second.json()  # stable, recomputed identically
    assert before == after == 2  # the reads wrote nothing


def test_study_days_requires_authentication(
    study_client: TestClient, db_conn: Connection
) -> None:
    study_client.cookies.clear()
    resp = study_client.get("/api/study/days")
    assert resp.status_code == 401, resp.text


# --- GET /api/reading/continue -------------------------------------------------


def test_continue_returns_the_hero_with_resolved_chapter(
    study_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(study_client, "continue-ok@example.com")
    source_id = _persist_source(db_conn, user_id, title="The Book")
    _seed_book(db_conn, source_id)
    when = _seed_position(db_conn, user_id, source_id, "c1s1", percent="30.00")

    resp = study_client.get("/api/reading/continue")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {
        "source_id",
        "source_title",
        "chapter_title",
        "percent",
        "updated_at",
    }
    assert body["source_id"] == str(source_id)
    assert body["source_title"] == "The Book"
    # c1s1 (position 1, depth 1) belongs to the first chapter, titled "Chapter 0".
    assert body["chapter_title"] == "Chapter 0"
    assert body["percent"] == 30.0
    assert datetime.fromisoformat(body["updated_at"]) == when


def test_continue_returns_null_without_a_position(
    study_client: TestClient, db_conn: Connection
) -> None:
    _register(study_client, "continue-none@example.com")
    resp = study_client.get("/api/reading/continue")
    assert resp.status_code == 200, resp.text
    assert resp.json() is None


def test_continue_never_returns_another_users_position(
    study_client: TestClient, db_conn: Connection
) -> None:
    # HOME-04: the other user's (more recent) position must never surface for the caller.
    other_id = _register(study_client, "continue-other@example.com")
    other_source = _persist_source(db_conn, other_id, title="Other Book")
    _seed_book(db_conn, other_source)
    _seed_position(db_conn, other_id, other_source, "c1", percent="10.00")

    caller_id = _register(study_client, "continue-caller@example.com")  # switch session
    caller_source = _persist_source(db_conn, caller_id, title="Caller Book")
    _seed_book(db_conn, caller_source)
    _seed_position(db_conn, caller_id, caller_source, "c2", percent="90.00")

    resp = study_client.get("/api/reading/continue")

    assert resp.status_code == 200, resp.text
    assert resp.json()["source_id"] == str(caller_source)
    assert resp.json()["source_title"] == "Caller Book"


def test_continue_requires_authentication(
    study_client: TestClient, db_conn: Connection
) -> None:
    study_client.cookies.clear()
    resp = study_client.get("/api/reading/continue")
    assert resp.status_code == 401, resp.text
