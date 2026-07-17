"""D4 gate — genanki ``.apkg`` export (unit + route, live test DB for the route).

Pins QUIZ-22 at the adapter and route levels: ``build_apkg`` produces non-empty
valid-zip bytes; each note's GUID derives from ``(source_id, content_key)`` and is
stable across builds and across a regenerated item (so re-import updates in place);
cloze items reconstruct ``{{c1::answer}}`` from the blanked sentence; the citation
footnote carries the book title, section path, and any non-active status. The route
streams an octet-stream attachment for the owner, and 404s for an empty/missing/
non-owned source.
"""

from __future__ import annotations

import io
import sqlite3
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import genanki
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app.application.quiz_qc import CLOZE_BLANK, content_key
from app.domain.entities import QuizItem, QuizItemStatus, QuizItemType, Source
from app.infrastructure.db.repositories import (
    SqlAlchemyQuizItemRepository,
    SqlAlchemySourceRepository,
)
from app.infrastructure.export.anki import _note_for, build_apkg
from tests.conftest import TEST_PASSWORD, requires_db

_SOURCE_ID = UUID("11111111-1111-1111-1111-111111111111")


# --- builders ------------------------------------------------------------------


def _item(
    *,
    source_id: UUID = _SOURCE_ID,
    item_type: str = QuizItemType.FREE_RECALL,
    question: str = "What is the powerhouse of the cell?",
    answer: str = "Mitochondria",
    section_path: tuple[str, ...] = ("Part 1", "Cells"),
    status: str = QuizItemStatus.ACTIVE,
    item_id: UUID | None = None,
    anchor: str = "ch1.xhtml",
) -> QuizItem:
    now = datetime.now(UTC)
    return QuizItem(
        id=item_id or uuid4(),
        source_id=source_id,
        item_type=item_type,
        question=question,
        answer=answer,
        section_path=section_path,
        anchor=anchor,
        source_excerpt="The mitochondria is the powerhouse of the cell.",
        chunk_hash="c" * 64,
        content_key=content_key(item_type, question, answer),
        status=status,
        generation_meta={},
        created_at=now,
        updated_at=now,
    )


def _note_guids(apkg: bytes) -> list[str]:
    """Return the GUIDs of the notes inside an ``.apkg`` package."""
    with zipfile.ZipFile(io.BytesIO(apkg)) as archive:
        collection = archive.read("collection.anki2")
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "collection.anki2"
        db_path.write_bytes(collection)
        conn = sqlite3.connect(db_path)
        try:
            return [row[0] for row in conn.execute("SELECT guid FROM notes")]
        finally:
            conn.close()


# --- build_apkg bytes (QUIZ-22) -------------------------------------------------


def test_build_apkg_returns_nonempty_valid_zip() -> None:
    apkg = build_apkg([_item()], "A Book")

    assert len(apkg) > 0
    assert apkg[:2] == b"PK"  # zip local-file signature
    assert zipfile.is_zipfile(io.BytesIO(apkg))


def test_build_apkg_note_guid_matches_upsert_identity() -> None:
    item = _item()
    guids = _note_guids(build_apkg([item], "A Book"))

    assert guids == [genanki.guid_for(str(item.source_id), item.content_key)]


def test_build_apkg_guid_stable_across_builds() -> None:
    # Re-exporting the same items yields the same note GUID — Anki re-import updates
    # the note in place rather than duplicating it.
    item = _item()
    first = _note_guids(build_apkg([item], "A Book"))
    second = _note_guids(build_apkg([item], "A Book"))

    assert first == second


def test_guid_stable_across_regenerated_item() -> None:
    # Two items sharing (source_id, content_key) but differing in id/anchor/status
    # (a regenerated + reconciled item) map to the SAME note GUID (upsert identity).
    original = _item(item_id=uuid4(), anchor="old.xhtml", status=QuizItemStatus.ACTIVE)
    regenerated = _item(item_id=uuid4(), anchor="new.xhtml", status=QuizItemStatus.STALE)

    assert _note_for(original, "A Book").guid == _note_for(regenerated, "A Book").guid


# --- note shape (QUIZ-22) -------------------------------------------------------


def test_cloze_note_reconstructs_deletion() -> None:
    # A cloze item's blanked sentence becomes an Anki ``{{c1::answer}}`` deletion.
    question = f"The mitochondria is the {CLOZE_BLANK} of the cell."
    item = _item(item_type=QuizItemType.CLOZE, question=question, answer="powerhouse")

    note = _note_for(item, "A Book")

    text = note.fields[0]
    assert "{{c1::powerhouse}}" in text
    assert CLOZE_BLANK not in text


def test_free_recall_note_has_answer_and_citation_footnote() -> None:
    item = _item(section_path=("Part 1", "Cells"))
    note = _note_for(item, "A Book")

    front, back = note.fields
    assert front == item.question
    assert item.answer in back
    # Footnote: book title and the section path joined.
    assert "A Book" in back
    assert "Part 1" in back and "Cells" in back


def test_footnote_notes_non_active_status() -> None:
    stale = _item(status=QuizItemStatus.STALE)
    note = _note_for(stale, "A Book")
    assert "(status: stale)" in note.fields[1]


# --- export route (QUIZ-22) -----------------------------------------------------
# The unit tests above need no DB; the route tests below are gated per-test.


def _register(client: TestClient, email: str) -> str:
    resp = client.post("/api/auth/register", json={"email": email, "password": TEST_PASSWORD})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


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


@requires_db
def test_export_route_returns_apkg_attachment_for_owner(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(quiz_client, "export-ok@example.com")
    source_id = _persist_source(db_conn, user_id, title="My Book")
    SqlAlchemyQuizItemRepository(db_conn).upsert(_item(source_id=source_id), embedding=None)

    resp = quiz_client.get(f"/api/sources/{source_id}/quiz/export")

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/octet-stream"
    assert resp.headers["content-disposition"] == 'attachment; filename="My_Book.apkg"'
    assert zipfile.is_zipfile(io.BytesIO(resp.content))


def test_export_filename_strips_non_ascii_title_characters() -> None:
    """Accented characters (the real corpus has Portuguese titles) are stripped so the
    latin-1 Content-Disposition header can never carry a broken filename."""
    from app.infrastructure.web.quiz import _export_filename

    assert _export_filename("Memórias Póstumas de Brás Cubas") == (
        "Memrias_Pstumas_de_Brs_Cubas.apkg"
    )


def test_export_filename_falls_back_when_nothing_printable_remains() -> None:
    from app.infrastructure.web.quiz import _export_filename

    assert _export_filename("日本語の本") == "deck.apkg"
    assert _export_filename("   ") == "deck.apkg"


@requires_db
def test_export_route_empty_source_returns_404(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(quiz_client, "export-empty@example.com")
    source_id = _persist_source(db_conn, user_id)

    resp = quiz_client.get(f"/api/sources/{source_id}/quiz/export")

    assert resp.status_code == 404, resp.text


@requires_db
def test_export_route_missing_and_non_owned_return_404(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    owner_id = _register(quiz_client, "export-owner@example.com")
    source_id = _persist_source(db_conn, owner_id)
    SqlAlchemyQuizItemRepository(db_conn).upsert(_item(source_id=source_id), embedding=None)

    _register(quiz_client, "export-intruder@example.com")  # become a different user

    non_owned = quiz_client.get(f"/api/sources/{source_id}/quiz/export")
    missing = quiz_client.get(f"/api/sources/{uuid4()}/quiz/export")

    assert non_owned.status_code == 404, non_owned.text
    assert missing.status_code == 404, missing.text


@requires_db
def test_export_route_unauthenticated_returns_401(
    quiz_client: TestClient, db_conn: Connection
) -> None:
    user_id = _register(quiz_client, "export-401@example.com")
    source_id = _persist_source(db_conn, user_id)
    quiz_client.cookies.clear()
    resp = quiz_client.get(f"/api/sources/{source_id}/quiz/export")
    assert resp.status_code == 401, resp.text
