"""``SqlAlchemyLocalePreferenceRepository`` against a live Postgres."""

from __future__ import annotations

import uuid

from sqlalchemy import Connection, text

from app.infrastructure.db.repositories import SqlAlchemyLocalePreferenceRepository
from tests.conftest import requires_db

pytestmark = requires_db


def _user(conn: Connection) -> uuid.UUID:
    user_id = uuid.uuid4()
    conn.execute(
        text("INSERT INTO users (id, email) VALUES (:id, :email)"),
        {"id": user_id, "email": f"{user_id}@example.test"},
    )
    return user_id


def test_a_second_upsert_replaces_the_first_and_leaves_one_row(db_conn: Connection) -> None:
    repo = SqlAlchemyLocalePreferenceRepository(db_conn)
    user_id = _user(db_conn)

    repo.upsert(user_id, "pt-BR")
    replaced = repo.upsert(user_id, "en")

    assert replaced.locale == "en"
    stored = repo.get_by_user(user_id)
    assert stored is not None and stored.locale == "en"
    count = db_conn.execute(
        text("SELECT count(*) FROM user_locale_preferences WHERE user_id = :uid"),
        {"uid": user_id},
    ).scalar_one()
    assert count == 1


def test_delete_reports_whether_a_row_existed(db_conn: Connection) -> None:
    repo = SqlAlchemyLocalePreferenceRepository(db_conn)
    user_id = _user(db_conn)
    repo.upsert(user_id, "pt-BR")

    assert repo.delete(user_id) is True
    assert repo.get_by_user(user_id) is None
    assert repo.delete(user_id) is False


def test_the_choice_belongs_to_its_user_only(db_conn: Connection) -> None:
    repo = SqlAlchemyLocalePreferenceRepository(db_conn)
    mine, theirs = _user(db_conn), _user(db_conn)
    repo.upsert(mine, "pt-BR")
    repo.upsert(theirs, "en")

    repo.delete(mine)

    assert repo.get_by_user(mine) is None
    survivor = repo.get_by_user(theirs)
    assert survivor is not None and survivor.locale == "en"


def test_deleting_the_user_removes_the_preference(db_conn: Connection) -> None:
    repo = SqlAlchemyLocalePreferenceRepository(db_conn)
    user_id = _user(db_conn)
    repo.upsert(user_id, "pt-BR")

    db_conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})

    assert repo.get_by_user(user_id) is None
    remaining = db_conn.execute(
        text("SELECT count(*) FROM user_locale_preferences WHERE user_id = :uid"),
        {"uid": user_id},
    ).scalar_one()
    assert remaining == 0


def test_an_unsupported_stored_value_is_returned_as_stored(db_conn: Connection) -> None:
    """The repository never judges the value; the web boundary treats it as unset."""
    repo = SqlAlchemyLocalePreferenceRepository(db_conn)
    user_id = _user(db_conn)
    repo.upsert(user_id, "fr")

    stored = repo.get_by_user(user_id)
    assert stored is not None and stored.locale == "fr"
