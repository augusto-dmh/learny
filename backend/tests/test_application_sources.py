"""T5 gate — source application services + upload validation (unit, fake ports).

1:1 to the P1-Upload and P1-View spec ACs: every ``validate_source_upload``
reject with its ``kind``; ``CreateSource`` store-then-persist incl. the opaque
key shape and the storage-failure/no-row path; ``GetSource`` owner/non-owner/
missing → 404 semantics; ``ListSources`` delegation.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.application.errors import (
    InvalidSourceUpload,
    SourceNotFound,
    StorageUnavailable,
)
from app.application.identity import AuthorizeOwnership
from app.application.sources import CreateSource, GetSource, ListSources
from app.application.validation import validate_source_upload
from app.domain.entities import Source, User
from tests.fakes import (
    FailingStorage,
    FakeClock,
    FakeSourceRepository,
    FakeStorage,
)

EPUB_TYPE = "application/epub+zip"
DATA = b"PK\x03\x04 fake epub bytes"
MAX_BYTES = 1024


def _user(email: str = "reader@example.com") -> User:
    return User(id=uuid4(), email=email, created_at=datetime(2026, 7, 4, tzinfo=UTC))


def _valid_upload(**overrides):
    kwargs = {
        "title": "Meditations",
        "filename": "meditations.epub",
        "content_type": EPUB_TYPE,
        "byte_size": len(DATA),
        "max_bytes": MAX_BYTES,
    }
    kwargs.update(overrides)
    return kwargs


# ---- validate_source_upload ----------------------------------------------


def test_validate_accepts_valid_upload() -> None:
    # A well-formed upload returns without raising.
    assert validate_source_upload(**_valid_upload()) is None


def test_validate_rejects_non_epub_extension() -> None:
    with pytest.raises(InvalidSourceUpload) as exc:
        validate_source_upload(**_valid_upload(filename="book.txt"))
    assert exc.value.kind == "extension"


def test_validate_rejects_wrong_content_type() -> None:
    with pytest.raises(InvalidSourceUpload) as exc:
        validate_source_upload(**_valid_upload(content_type="application/pdf"))
    assert exc.value.kind == "content_type"


def test_validate_rejects_oversize_file() -> None:
    with pytest.raises(InvalidSourceUpload) as exc:
        validate_source_upload(**_valid_upload(byte_size=MAX_BYTES + 1))
    assert exc.value.kind == "size"


def test_validate_accepts_file_at_exact_max_bytes() -> None:
    # A file exactly at the cap is accepted; only bytes exceeding it reject.
    assert validate_source_upload(**_valid_upload(byte_size=MAX_BYTES)) is None


def test_validate_rejects_zero_byte_file() -> None:
    with pytest.raises(InvalidSourceUpload) as exc:
        validate_source_upload(**_valid_upload(byte_size=0))
    assert exc.value.kind == "empty"


def test_validate_rejects_whitespace_title() -> None:
    with pytest.raises(InvalidSourceUpload) as exc:
        validate_source_upload(**_valid_upload(title="   "))
    assert exc.value.kind == "title"


def test_validate_rejects_too_long_title() -> None:
    with pytest.raises(InvalidSourceUpload) as exc:
        validate_source_upload(**_valid_upload(title="x" * 501))
    assert exc.value.kind == "title"


# ---- validate_source_upload: PDF (ING-09) --------------------------------


PDF_TYPE = "application/pdf"


def test_validate_accepts_valid_pdf() -> None:
    # A well-formed PDF upload (extension + content type agree, within the PDF cap)
    # returns without raising.
    assert (
        validate_source_upload(
            title="Report",
            filename="report.pdf",
            content_type=PDF_TYPE,
            byte_size=len(DATA),
            max_bytes=1,
            pdf_max_bytes=MAX_BYTES,
        )
        is None
    )


def test_validate_rejects_pdf_extension_with_epub_content_type() -> None:
    # Spec edge case: a .pdf file uploaded as application/epub+zip is a mismatch.
    with pytest.raises(InvalidSourceUpload) as exc:
        validate_source_upload(
            title="Report",
            filename="report.pdf",
            content_type=EPUB_TYPE,
            byte_size=len(DATA),
            max_bytes=MAX_BYTES,
            pdf_max_bytes=MAX_BYTES,
        )
    assert exc.value.kind == "content_type"


def test_validate_rejects_epub_extension_with_pdf_content_type() -> None:
    # The mirror direction: an .epub file uploaded as application/pdf is a mismatch.
    with pytest.raises(InvalidSourceUpload) as exc:
        validate_source_upload(
            title="Meditations",
            filename="meditations.epub",
            content_type=PDF_TYPE,
            byte_size=len(DATA),
            max_bytes=MAX_BYTES,
            pdf_max_bytes=MAX_BYTES,
        )
    assert exc.value.kind == "content_type"


def test_validate_rejects_oversize_pdf_against_pdf_cap() -> None:
    with pytest.raises(InvalidSourceUpload) as exc:
        validate_source_upload(
            title="Report",
            filename="report.pdf",
            content_type=PDF_TYPE,
            byte_size=MAX_BYTES + 1,
            max_bytes=10 * MAX_BYTES,  # a large EPUB cap must not admit an oversize PDF
            pdf_max_bytes=MAX_BYTES,
        )
    assert exc.value.kind == "size"


def test_validate_pdf_uses_pdf_cap_not_epub_cap() -> None:
    # A PDF larger than the EPUB cap but within the PDF cap is accepted — proving
    # the size check keys off the format, not a single shared limit.
    assert (
        validate_source_upload(
            title="Report",
            filename="report.pdf",
            content_type=PDF_TYPE,
            byte_size=MAX_BYTES // 2,
            max_bytes=MAX_BYTES // 4,  # would reject if the EPUB cap were applied
            pdf_max_bytes=MAX_BYTES,
        )
        is None
    )


# ---- CreateSource ---------------------------------------------------------


def _create_source(sources, storage, *, source_id: UUID | None = None) -> CreateSource:
    fixed = source_id or uuid4()
    return CreateSource(
        sources=sources,
        storage=storage,
        clock=FakeClock(datetime(2026, 7, 4, 12, 0, 0, tzinfo=UTC)),
        ids=lambda: fixed,
        max_bytes=MAX_BYTES,
    )


def test_create_stores_bytes_then_persists_row() -> None:
    sources, storage = FakeSourceRepository(), FakeStorage()
    user = _user()
    source_id = uuid4()
    create = _create_source(sources, storage, source_id=source_id)

    result = create(
        user=user,
        title="Meditations",
        filename="meditations.epub",
        content_type=EPUB_TYPE,
        data=DATA,
    )

    assert result.id == source_id
    assert result.user_id == user.id
    assert result.status == "uploaded"
    assert result.byte_size == len(DATA)
    assert result.checksum == hashlib.sha256(DATA).hexdigest()
    assert result.created_at == result.updated_at
    # Bytes landed in storage under the persisted key, with the EPUB content-type.
    assert storage.objects[result.object_key] == DATA
    assert storage.put_calls == [(result.object_key, EPUB_TYPE)]
    # And the row is persisted (exactly once).
    assert sources.get_by_id(result.id) == result
    assert sources.add_calls == 1


def test_create_object_key_is_opaque_owner_partitioned() -> None:
    sources, storage = FakeSourceRepository(), FakeStorage()
    user = _user(email="secret.person@example.com")
    source_id = uuid4()
    create = _create_source(sources, storage, source_id=source_id)

    result = create(
        user=user,
        title="My Private Book",
        filename="private.epub",
        content_type=EPUB_TYPE,
        data=DATA,
    )

    assert result.object_key == f"sources/{user.id}/{source_id}.epub"
    assert user.email not in result.object_key
    assert "My Private Book" not in result.object_key


def test_create_pdf_stores_bytes_under_pdf_key() -> None:
    sources, storage = FakeSourceRepository(), FakeStorage()
    user = _user()
    source_id = uuid4()
    create = CreateSource(
        sources=sources,
        storage=storage,
        clock=FakeClock(datetime(2026, 7, 4, 12, 0, 0, tzinfo=UTC)),
        ids=lambda: source_id,
        max_bytes=MAX_BYTES,
        pdf_max_bytes=MAX_BYTES,
    )

    pdf_data = b"%PDF-1.7 fake but nonempty payload"
    result = create(
        user=user,
        title="Report",
        filename="report.pdf",
        content_type="application/pdf",
        data=pdf_data,
    )

    # The object key mirrors the PDF extension so parser dispatch stays consistent.
    assert result.object_key == f"sources/{user.id}/{source_id}.pdf"
    assert result.content_type == "application/pdf"
    assert storage.objects[result.object_key] == pdf_data
    assert storage.put_calls == [(result.object_key, "application/pdf")]


def test_create_pdf_uses_pdf_cap_not_epub_cap() -> None:
    # A PDF larger than the EPUB cap but within the PDF cap is stored (per-format
    # cap selection reaches storage, not just the pure validator).
    sources, storage = FakeSourceRepository(), FakeStorage()
    create = CreateSource(
        sources=sources,
        storage=storage,
        clock=FakeClock(datetime(2026, 7, 4, 12, 0, 0, tzinfo=UTC)),
        ids=uuid4,
        max_bytes=8,  # tiny EPUB cap
        pdf_max_bytes=64,  # roomier PDF cap
    )

    result = create(
        user=_user(),
        title="Report",
        filename="report.pdf",
        content_type="application/pdf",
        data=b"x" * 32,  # over the EPUB cap, under the PDF cap
    )

    assert result.byte_size == 32
    assert sources.add_calls == 1


def test_create_rejects_oversize_pdf_before_storage() -> None:
    sources, storage = FakeSourceRepository(), FakeStorage()
    create = CreateSource(
        sources=sources,
        storage=storage,
        clock=FakeClock(datetime(2026, 7, 4, 12, 0, 0, tzinfo=UTC)),
        ids=uuid4,
        max_bytes=8,
        pdf_max_bytes=16,
    )

    with pytest.raises(InvalidSourceUpload) as exc:
        create(
            user=_user(),
            title="Report",
            filename="report.pdf",
            content_type="application/pdf",
            data=b"x" * 17,  # over the PDF cap
        )

    assert exc.value.kind == "size"
    assert storage.put_calls == []
    assert sources.add_calls == 0


def test_create_rejects_invalid_before_touching_storage_or_repo() -> None:
    sources, storage = FakeSourceRepository(), FakeStorage()
    create = _create_source(sources, storage)

    with pytest.raises(InvalidSourceUpload) as exc:
        create(
            user=_user(),
            title="Meditations",
            filename="book.txt",
            content_type=EPUB_TYPE,
            data=DATA,
        )

    assert exc.value.kind == "extension"
    assert storage.put_calls == []
    assert sources.add_calls == 0


def test_create_storage_failure_raises_and_skips_persist() -> None:
    sources = FakeSourceRepository()
    create = _create_source(sources, FailingStorage())

    with pytest.raises(StorageUnavailable):
        create(
            user=_user(),
            title="Meditations",
            filename="meditations.epub",
            content_type=EPUB_TYPE,
            data=DATA,
        )

    # No row is persisted when the object store write fails (SRC-09).
    assert sources.add_calls == 0


# ---- GetSource ------------------------------------------------------------


def _stored_source(sources: FakeSourceRepository, owner: User) -> Source:
    now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=UTC)
    source = Source(
        id=uuid4(),
        user_id=owner.id,
        title="Meditations",
        filename="meditations.epub",
        content_type=EPUB_TYPE,
        byte_size=len(DATA),
        checksum=hashlib.sha256(DATA).hexdigest(),
        object_key=f"sources/{owner.id}/{uuid4()}.epub",
        status="uploaded",
        created_at=now,
        updated_at=now,
    )
    return sources.add(source)


def test_get_source_returns_entity_for_owner() -> None:
    sources = FakeSourceRepository()
    owner = _user()
    source = _stored_source(sources, owner)
    get = GetSource(sources=sources, authorize=AuthorizeOwnership())

    assert get(user=owner, source_id=source.id) == source


def test_get_source_hides_other_users_source_as_not_found() -> None:
    sources = FakeSourceRepository()
    owner = _user("owner@example.com")
    source = _stored_source(sources, owner)
    other = _user("intruder@example.com")
    get = GetSource(sources=sources, authorize=AuthorizeOwnership())

    with pytest.raises(SourceNotFound):
        get(user=other, source_id=source.id)


def test_get_source_missing_id_is_not_found() -> None:
    sources = FakeSourceRepository()
    get = GetSource(sources=sources, authorize=AuthorizeOwnership())

    with pytest.raises(SourceNotFound):
        get(user=_user(), source_id=uuid4())


# ---- ListSources ----------------------------------------------------------


def test_list_sources_delegates_to_owner_scoped_repo() -> None:
    sources = FakeSourceRepository()
    owner = _user("owner@example.com")
    other = _user("other@example.com")
    mine_a = _stored_source(sources, owner)
    mine_b = _stored_source(sources, owner)
    _stored_source(sources, other)
    list_sources = ListSources(sources=sources)

    result = list_sources(user=owner)

    assert {s.id for s in result} == {mine_a.id, mine_b.id}
