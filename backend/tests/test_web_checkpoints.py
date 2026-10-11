"""Checkpoint routes over HTTP: payload shapes, statuses and once-only steps.

Runs the assembled app (``quiz_client``: every router, a rolled-back shared
connection, a generous in-memory limiter) against Postgres. Explain-back uses the
default deterministic Explain chain unless a test overrides it.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, func, select

from app.domain.entities import User
from app.infrastructure.db.metadata import (
    checkpoint_attempts,
    quiz_items,
    review_log,
    section_checkpoints,
)
from app.infrastructure.db.repositories import SqlAlchemyAiSpendDayRepository
from tests.checkpoint_seed import ANCHOR, CHUNKS, add_card, add_corpus, add_source, add_user
from tests.conftest import TEST_PASSWORD, requires_db

pytestmark = requires_db

# Whole words only: "passage" is the point of the feedback, "pass" would be a verdict.
_GRADE_WORDS = re.compile(
    r"\b(score[sd]?|grade[sd]?|percent|correct|incorrect|pass(ed)?|fail(ed)?)\b|%",
    re.IGNORECASE,
)


def _login(client: TestClient, email: str | None = None) -> tuple[User, str]:
    email = email or f"{uuid4()}@example.test"
    resp = client.post(
        "/api/auth/register", json={"email": email, "password": TEST_PASSWORD, "accepted_tos": True}
    )
    assert resp.status_code == 201, resp.text
    me = client.get("/api/auth/me").json()
    return User(id=UUID(resp.json()["id"]), email=email, created_at=datetime.now(UTC)), me[
        "csrf_token"
    ]


def _book(client: TestClient, db_conn: Connection) -> tuple[User, str, UUID]:
    user, csrf = _login(client)
    source_id = add_source(db_conn, user.id)
    add_corpus(db_conn, source_id)
    return user, csrf, source_id


def _create(client: TestClient, source_id: object, csrf: str | None, **body):
    headers = {} if csrf is None else {"X-CSRF-Token": csrf}
    return client.post(
        f"/api/sources/{source_id}/checkpoints",
        json={"anchor": ANCHOR, "prediction": None, **body},
        headers=headers,
    )


def _post(client: TestClient, attempt_id: object, step: str, csrf: str | None, body=None):
    headers = {} if csrf is None else {"X-CSRF-Token": csrf}
    return client.post(f"/api/checkpoint-attempts/{attempt_id}/{step}", json=body, headers=headers)


def _attempts(resp) -> list[dict]:
    assert resp.status_code == 201, resp.text
    return resp.json()["attempts"]


def _checkpoint_count(db_conn: Connection) -> int:
    return db_conn.execute(select(func.count()).select_from(section_checkpoints)).scalar_one()


# --- create ----------------------------------------------------------------------


def test_create_payload_carries_no_answers(quiz_client: TestClient, db_conn: Connection) -> None:
    _, csrf, source_id = _book(quiz_client, db_conn)
    card = add_card(db_conn, source_id, answer="A distinctive secret answer")

    resp = _create(quiz_client, source_id, csrf, prediction=3)

    assert resp.status_code == 201, resp.text
    raw = resp.text
    assert "A distinctive secret answer" not in raw
    for chunk in CHUNKS:
        assert chunk not in raw
    body = resp.json()
    for key in ("answer", "source_excerpt", "passage"):
        assert key not in json.dumps(body)
    assert [a["kind"] for a in body["attempts"]] == ["recall", "explain"]
    assert body["attempts"][0]["question"] == card.question
    assert set(body["attempts"][0]) == {"attempt_id", "kind", "question"}


def test_create_404_cases_persist_nothing(quiz_client: TestClient, db_conn: Connection) -> None:
    _, csrf, source_id = _book(quiz_client, db_conn)
    stranger = add_user(db_conn)
    foreign = add_source(db_conn, stranger.id)
    add_corpus(db_conn, foreign)
    before = _checkpoint_count(db_conn)

    missing = _create(quiz_client, uuid4(), csrf)
    not_mine = _create(quiz_client, foreign, csrf)
    no_section = _create(quiz_client, source_id, csrf, anchor="nowhere.xhtml")

    assert [missing.status_code, not_mine.status_code, no_section.status_code] == [404, 404, 404]
    assert missing.json() == not_mine.json()
    assert _checkpoint_count(db_conn) == before


def test_create_on_shared_sample_returns_201(quiz_client: TestClient, db_conn: Connection) -> None:
    _, csrf = _login(quiz_client)
    operator = add_user(db_conn)
    sample = add_source(db_conn, operator.id, is_sample=True)
    add_corpus(db_conn, sample)

    resp = _create(quiz_client, sample, csrf)

    assert resp.status_code == 201, resp.text


def test_new_routes_require_session_and_csrf(quiz_client: TestClient, db_conn: Connection) -> None:
    _, csrf, source_id = _book(quiz_client, db_conn)
    add_card(db_conn, source_id)
    attempts = _attempts(_create(quiz_client, source_id, csrf))
    recall_id = attempts[0]["attempt_id"]
    before = _checkpoint_count(db_conn)

    without_csrf = [
        _create(quiz_client, source_id, None).status_code,
        _post(
            quiz_client, recall_id, "response", None, {"response": "", "confidence": 1}
        ).status_code,
        _post(quiz_client, attempts[1]["attempt_id"], "reveal", None).status_code,
        _post(quiz_client, recall_id, "grade", None, {"rating": 3}).status_code,
    ]
    quiz_client.cookies.clear()
    without_session = [
        _create(quiz_client, source_id, csrf).status_code,
        _post(
            quiz_client, recall_id, "response", csrf, {"response": "", "confidence": 1}
        ).status_code,
        _post(quiz_client, attempts[1]["attempt_id"], "reveal", csrf).status_code,
        _post(quiz_client, recall_id, "grade", csrf, {"rating": 3}).status_code,
    ]

    assert without_csrf == [403, 403, 403, 403]
    assert without_session == [401, 401, 401, 401]
    assert _checkpoint_count(db_conn) == before
    stamps = db_conn.execute(
        select(checkpoint_attempts.c.responded_at, checkpoint_attempts.c.revealed_at).where(
            checkpoint_attempts.c.id.in_([UUID(recall_id), UUID(attempts[1]["attempt_id"])])
        )
    ).all()
    assert [tuple(s) for s in stamps] == [(None, None), (None, None)]


# --- respond ---------------------------------------------------------------------


def test_recall_response_reveals_answer_after_storing(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    _, csrf, source_id = _book(quiz_client, db_conn)
    card = add_card(db_conn, source_id, answer="Eighteen operations")
    attempt_id = _attempts(_create(quiz_client, source_id, csrf))[0]["attempt_id"]

    resp = _post(quiz_client, attempt_id, "response", csrf, {"response": "", "confidence": 2})

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "answer": "Eighteen operations",
        "source_excerpt": card.source_excerpt,
        "anchor": ANCHOR,
        "section_path": list(card.section_path),
    }
    stored = db_conn.execute(
        select(checkpoint_attempts.c.response, checkpoint_attempts.c.confidence).where(
            checkpoint_attempts.c.id == UUID(attempt_id)
        )
    ).one()
    assert tuple(stored) == ("", 2)


def test_second_response_is_409_and_keeps_first(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    _, csrf, source_id = _book(quiz_client, db_conn)
    add_card(db_conn, source_id)
    attempt_id = _attempts(_create(quiz_client, source_id, csrf))[0]["attempt_id"]
    first = _post(quiz_client, attempt_id, "response", csrf, {"response": "one", "confidence": 1})
    assert first.status_code == 200

    second = _post(quiz_client, attempt_id, "response", csrf, {"response": "two", "confidence": 3})

    assert second.status_code == 409
    stored = db_conn.execute(
        select(checkpoint_attempts.c.response, checkpoint_attempts.c.confidence).where(
            checkpoint_attempts.c.id == UUID(attempt_id)
        )
    ).one()
    assert tuple(stored) == ("one", 1)


@pytest.mark.parametrize(
    "body",
    [
        {"response": "x"},
        {"response": "x", "confidence": 0},
        {"response": "x", "confidence": 4},
        {"response": "x" * 4001, "confidence": 2},
    ],
)
def test_response_validation_422(quiz_client: TestClient, db_conn: Connection, body: dict) -> None:
    _, csrf, source_id = _book(quiz_client, db_conn)
    add_card(db_conn, source_id)
    attempt_id = _attempts(_create(quiz_client, source_id, csrf))[0]["attempt_id"]

    resp = _post(quiz_client, attempt_id, "response", csrf, body)

    assert resp.status_code == 422
    responded = db_conn.execute(
        select(checkpoint_attempts.c.responded_at).where(
            checkpoint_attempts.c.id == UUID(attempt_id)
        )
    ).scalar_one()
    assert responded is None


def test_attempt_routes_404_for_foreign_and_missing(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    _, csrf_a, source_id = _book(quiz_client, db_conn)
    add_card(db_conn, source_id)
    attempts = _attempts(_create(quiz_client, source_id, csrf_a))
    quiz_client.cookies.clear()
    _, csrf_b = _login(quiz_client)

    bodies: dict[str, set[str]] = {"response": set(), "reveal": set(), "grade": set()}
    for attempt_id in (attempts[0]["attempt_id"], attempts[1]["attempt_id"], str(uuid4())):
        responses = {
            "response": _post(
                quiz_client, attempt_id, "response", csrf_b, {"response": "", "confidence": 1}
            ),
            "reveal": _post(quiz_client, attempt_id, "reveal", csrf_b),
            "grade": _post(quiz_client, attempt_id, "grade", csrf_b, {"rating": 3}),
        }
        assert [r.status_code for r in responses.values()] == [404, 404, 404]
        for step, resp in responses.items():
            bodies[step].add(resp.text)
    # A foreign attempt and a missing one are indistinguishable on every route.
    assert [len(texts) for texts in bodies.values()] == [1, 1, 1]


# --- grade -----------------------------------------------------------------------


def _log_count(db_conn: Connection) -> int:
    return db_conn.execute(select(func.count()).select_from(review_log)).scalar_one()


def test_grade_before_response_is_409(quiz_client: TestClient, db_conn: Connection) -> None:
    _, csrf, source_id = _book(quiz_client, db_conn)
    add_card(db_conn, source_id)
    attempt_id = _attempts(_create(quiz_client, source_id, csrf))[0]["attempt_id"]
    before = _log_count(db_conn)

    resp = _post(quiz_client, attempt_id, "grade", csrf, {"rating": 3})

    assert resp.status_code == 409
    assert _log_count(db_conn) == before


def test_second_grade_is_409_one_log_row(quiz_client: TestClient, db_conn: Connection) -> None:
    _, csrf, source_id = _book(quiz_client, db_conn)
    card = add_card(db_conn, source_id)
    attempt_id = _attempts(_create(quiz_client, source_id, csrf))[0]["attempt_id"]
    _post(quiz_client, attempt_id, "response", csrf, {"response": "", "confidence": 2})

    first = _post(quiz_client, attempt_id, "grade", csrf, {"rating": 3})
    second = _post(quiz_client, attempt_id, "grade", csrf, {"rating": 1})

    assert first.status_code == 200, first.text
    assert set(first.json()) == {"quiz_item_id", "due", "state"}
    assert second.status_code == 409
    rows = db_conn.execute(
        select(review_log.c.rating).where(review_log.c.quiz_item_id == card.id)
    ).all()
    assert [r.rating for r in rows] == [3]


@pytest.mark.parametrize("rating,expected", [(1, 200), (3, 200), (4, 422), (0, 422)])
def test_explain_grade_rating_bounds(
    quiz_client: TestClient, db_conn: Connection, rating: int, expected: int
) -> None:
    _, csrf, source_id = _book(quiz_client, db_conn)
    attempt_id = _attempts(_create(quiz_client, source_id, csrf))[0]["attempt_id"]
    _post(quiz_client, attempt_id, "response", csrf, {"response": "", "confidence": 2})
    before = _log_count(db_conn)

    resp = _post(quiz_client, attempt_id, "grade", csrf, {"rating": rating})

    assert resp.status_code == expected, resp.text
    assert _log_count(db_conn) == before + (1 if expected == 200 else 0)


# --- explain feedback ------------------------------------------------------------


def test_explain_payload_keys_have_no_score(quiz_client: TestClient, db_conn: Connection) -> None:
    _, csrf, source_id = _book(quiz_client, db_conn)
    attempt_id = _attempts(_create(quiz_client, source_id, csrf))[0]["attempt_id"]

    resp = _post(
        quiz_client,
        attempt_id,
        "response",
        csrf,
        {"response": "Workers specialise and grow dexterous.", "confidence": 2},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"feedback", "citations"}
    assert body["citations"]
    for citation in body["citations"]:
        assert set(citation) == {"anchor", "section_path", "quote"}
    assert _GRADE_WORDS.search(body["feedback"]) is None


def _spend_to_cap(db_conn: Connection, user: User) -> None:
    SqlAlchemyAiSpendDayRepository(db_conn).record(
        user.id, datetime.now(UTC).date(), usd_micros=10_000_000
    )


def test_explain_budget_exhausted_429_paused_503(
    quiz_client: TestClient, db_conn: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.conftest import clear_settings_and_generation_caches

    user, csrf, source_id = _book(quiz_client, db_conn)
    exhausted_id = _attempts(_create(quiz_client, source_id, csrf))[0]["attempt_id"]
    paused_id = _attempts(_create(quiz_client, source_id, csrf))[0]["attempt_id"]
    body = {"response": "Workers specialise.", "confidence": 2}

    _spend_to_cap(db_conn, user)
    exhausted = _post(quiz_client, exhausted_id, "response", csrf, body)
    monkeypatch.setenv("LEARNY_AI_KILL_SWITCH", "true")
    clear_settings_and_generation_caches()
    paused = _post(quiz_client, paused_id, "response", csrf, body)

    assert exhausted.status_code == 429
    assert paused.status_code == 503
    stamps = db_conn.execute(
        select(checkpoint_attempts.c.responded_at).where(
            checkpoint_attempts.c.id.in_([UUID(exhausted_id), UUID(paused_id)])
        )
    ).all()
    assert [s.responded_at for s in stamps] == [None, None]


# --- reveal ----------------------------------------------------------------------


def test_reveal_stamps_and_returns_first_chunk(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    _, csrf, source_id = _book(quiz_client, db_conn)
    attempt_id = _attempts(_create(quiz_client, source_id, csrf))[0]["attempt_id"]

    resp = _post(quiz_client, attempt_id, "reveal", csrf)

    assert resp.status_code == 200, resp.text
    assert resp.json()["passage"] == CHUNKS[0]
    revealed = db_conn.execute(
        select(checkpoint_attempts.c.revealed_at).where(
            checkpoint_attempts.c.id == UUID(attempt_id)
        )
    ).scalar_one()
    assert revealed is not None


def test_reveal_409_on_recall_or_after_response(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    _, csrf, source_id = _book(quiz_client, db_conn)
    add_card(db_conn, source_id)
    recall_id, explain_id = (
        a["attempt_id"] for a in _attempts(_create(quiz_client, source_id, csrf))
    )
    _post(quiz_client, explain_id, "response", csrf, {"response": "", "confidence": 1})

    on_recall = _post(quiz_client, recall_id, "reveal", csrf)
    after_response = _post(quiz_client, explain_id, "reveal", csrf)

    assert (on_recall.status_code, after_response.status_code) == (409, 409)
    stamps = db_conn.execute(
        select(checkpoint_attempts.c.revealed_at).where(
            checkpoint_attempts.c.id.in_([UUID(recall_id), UUID(explain_id)])
        )
    ).all()
    assert [s.revealed_at for s in stamps] == [None, None]


@pytest.mark.parametrize(
    "body",
    [
        {"anchor": ANCHOR, "prediction": 0},
        {"anchor": ANCHOR, "prediction": 4},
        {"anchor": "", "prediction": None},
    ],
)
def test_create_validation_422(quiz_client: TestClient, db_conn: Connection, body: dict) -> None:
    _, csrf, source_id = _book(quiz_client, db_conn)
    before = _checkpoint_count(db_conn)

    resp = quiz_client.post(
        f"/api/sources/{source_id}/checkpoints", json=body, headers={"X-CSRF-Token": csrf}
    )

    assert resp.status_code == 422
    assert _checkpoint_count(db_conn) == before


@pytest.mark.parametrize("rating,expected", [(4, 200), (5, 422)])
def test_recall_grade_rating_bounds(
    quiz_client: TestClient, db_conn: Connection, rating: int, expected: int
) -> None:
    _, csrf, source_id = _book(quiz_client, db_conn)
    card = add_card(db_conn, source_id)
    attempt_id = _attempts(_create(quiz_client, source_id, csrf))[0]["attempt_id"]
    _post(quiz_client, attempt_id, "response", csrf, {"response": "", "confidence": 3})

    resp = _post(quiz_client, attempt_id, "grade", csrf, {"rating": rating})

    assert resp.status_code == expected, resp.text
    rows = db_conn.execute(
        select(review_log.c.rating).where(review_log.c.quiz_item_id == card.id)
    ).all()
    assert [r.rating for r in rows] == ([rating] if expected == 200 else [])


def test_grade_refuses_a_client_assisted_field(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    # Assistance is the server's call: a revealed explanation cannot be graded as
    # unaided by a client that says so.
    _, csrf, source_id = _book(quiz_client, db_conn)
    attempt_id = _attempts(_create(quiz_client, source_id, csrf))[0]["attempt_id"]
    _post(quiz_client, attempt_id, "reveal", csrf)
    _post(quiz_client, attempt_id, "response", csrf, {"response": "", "confidence": 3})
    before = _log_count(db_conn)

    resp = _post(quiz_client, attempt_id, "grade", csrf, {"rating": 3, "assisted": False})

    assert resp.status_code == 422
    assert _log_count(db_conn) == before


def test_grade_on_a_deleted_card_is_404_and_leaves_the_attempt_ungraded(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    # The grade claim stamps the attempt before the card is resolved; a card deleted
    # since the response must roll that stamp back, so the attempt is not left graded
    # with no review behind it.
    _, csrf, source_id = _book(quiz_client, db_conn)
    card = add_card(db_conn, source_id)
    attempt_id = _attempts(_create(quiz_client, source_id, csrf))[0]["attempt_id"]
    _post(quiz_client, attempt_id, "response", csrf, {"response": "", "confidence": 2})
    db_conn.execute(quiz_items.delete().where(quiz_items.c.id == card.id))
    before = _log_count(db_conn)

    resp = _post(quiz_client, attempt_id, "grade", csrf, {"rating": 3})

    assert resp.status_code == 404, resp.text
    graded = db_conn.execute(
        select(checkpoint_attempts.c.graded_at).where(checkpoint_attempts.c.id == UUID(attempt_id))
    ).scalar_one()
    assert graded is None
    assert _log_count(db_conn) == before
