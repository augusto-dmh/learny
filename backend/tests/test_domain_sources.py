"""T1 gate — Source domain entity + SourceRepository port (unit).

Pure-domain checks: the entity carries every field the design lists, is
immutable like the other entities, and the repository port is a structural
(``runtime_checkable``) Protocol with exactly the three persistence methods.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.entities import Source
from app.domain.ports import SourceRepository


def _sample_source() -> Source:
    now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=UTC)
    return Source(
        id=uuid4(),
        user_id=uuid4(),
        title="Meditations",
        filename="meditations.epub",
        content_type="application/epub+zip",
        byte_size=123456,
        checksum="a" * 64,
        object_key="sources/00000000-0000-0000-0000-000000000000/abc.epub",
        status="uploaded",
        created_at=now,
        updated_at=now,
    )


def test_source_carries_expected_fields() -> None:
    source = _sample_source()

    assert source.title == "Meditations"
    assert source.filename == "meditations.epub"
    assert source.content_type == "application/epub+zip"
    assert source.byte_size == 123456
    assert source.checksum == "a" * 64
    assert source.object_key.startswith("sources/")
    assert source.status == "uploaded"
    assert source.created_at == source.updated_at


def test_source_is_frozen() -> None:
    source = _sample_source()
    with pytest.raises(FrozenInstanceError):
        source.title = "Tampered"  # type: ignore[misc]


def test_source_repository_is_runtime_checkable_protocol() -> None:
    class ConformingRepo:
        def add(self, source):  # noqa: ANN001, ANN201
            return source

        def list_by_user(self, user_id):  # noqa: ANN001, ANN201
            return []

        def get_by_id(self, source_id):  # noqa: ANN001, ANN201
            return None

        def set_status(self, source_id, status, updated_at):  # noqa: ANN001, ANN201
            return None

    class MissingMethodRepo:
        def add(self, source):  # noqa: ANN001, ANN201
            return source

    assert isinstance(ConformingRepo(), SourceRepository)
    assert not isinstance(MissingMethodRepo(), SourceRepository)
