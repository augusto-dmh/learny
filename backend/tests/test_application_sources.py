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


def test_create_rejects_invalid_before_touching_storage_or_repo() -> None:
    sources, storage = FakeSourceRepository(), FakeStorage()
    create = _create_source(sources, storage)

    with pytest.raises(InvalidSourceUpload) as exc:
        create(
            user=_user(),
            title="Meditations",
            filename="book.pdf",
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
