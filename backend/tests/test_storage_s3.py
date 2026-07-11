"""T4 gate — S3StorageAdapter against MinIO (integration, skip-if-unavailable).

Runs when an S3-compatible endpoint is reachable (local MinIO by default); skips
cleanly otherwise. Each run uses a unique throwaway bucket that is emptied and
dropped on teardown so runs don't accumulate state.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from app.application.errors import StorageUnavailable
from app.infrastructure.storage.s3 import ObjectNotFound, S3StorageAdapter

ENDPOINT = os.environ.get("LEARNY_STORAGE_ENDPOINT", "http://localhost:9000")
ACCESS_KEY = os.environ.get("LEARNY_STORAGE_ACCESS_KEY", "learny")
SECRET_KEY = os.environ.get("LEARNY_STORAGE_SECRET_KEY", "learny-dev-secret")
REGION = os.environ.get("LEARNY_STORAGE_REGION", "us-east-1")


@pytest.fixture
def storage() -> Iterator[S3StorageAdapter]:
    bucket = f"learny-test-{uuid4().hex}"
    adapter = S3StorageAdapter(
        endpoint=ENDPOINT,
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        bucket=bucket,
        region=REGION,
    )
    try:
        adapter._ensure_bucket()
    except (ClientError, BotoCoreError) as exc:
        pytest.skip(f"S3-compatible storage not reachable at {ENDPOINT}: {exc}")

    try:
        yield adapter
    finally:
        client = adapter._client
        listing = client.list_objects_v2(Bucket=bucket)
        for obj in listing.get("Contents", []):
            client.delete_object(Bucket=bucket, Key=obj["Key"])
        client.delete_bucket(Bucket=bucket)


def test_put_get_roundtrip(storage: S3StorageAdapter) -> None:
    key = "sources/user/book.epub"
    payload = b"EPUB-bytes-\x00\x01\x02"

    storage.put_object(key, payload, content_type="application/epub+zip")

    assert storage.get_object(key) == payload


def test_ensure_bucket_is_idempotent(storage: S3StorageAdapter) -> None:
    # The fixture already created the bucket. Clear the per-instance cache so
    # the call actually re-checks the live (existing) bucket and must not try to
    # re-create it or raise.
    storage._bucket_ready = False
    storage._ensure_bucket()

    storage.put_object("a.epub", b"a", content_type="application/epub+zip")
    storage.put_object("b.epub", b"b", content_type="application/epub+zip")

    assert storage.get_object("a.epub") == b"a"
    assert storage.get_object("b.epub") == b"b"


def test_get_missing_key_raises_object_not_found(storage: S3StorageAdapter) -> None:
    with pytest.raises(ObjectNotFound):
        storage.get_object("sources/user/does-not-exist.epub")


class _FaultingClient:
    """boto3-client stub: bucket exists, get_object raises the configured error."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    def head_bucket(self, **_kwargs) -> dict:  # noqa: ANN003
        return {}

    def get_object(self, **_kwargs) -> dict:  # noqa: ANN003
        raise self._error


def _adapter_with(error: Exception) -> S3StorageAdapter:
    adapter = S3StorageAdapter(
        endpoint=ENDPOINT,
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        bucket="learny-test-faults",
        region=REGION,
    )
    adapter._client = _FaultingClient(error)  # noqa: SLF001 — unit-level stub
    return adapter


def test_get_transient_client_error_raises_storage_unavailable() -> None:
    """Non-missing-object S3 faults surface as the Learny-owned error.

    The port contract keeps vendor exception types inside this adapter, so
    callers (the ingestion step's retry classification) never import botocore.
    """
    error = ClientError({"Error": {"Code": "SlowDown", "Message": "slow"}}, "GetObject")

    with pytest.raises(StorageUnavailable):
        _adapter_with(error).get_object("sources/a-book.epub")


def test_get_botocore_error_raises_storage_unavailable() -> None:
    with pytest.raises(StorageUnavailable):
        _adapter_with(BotoCoreError()).get_object("sources/a-book.epub")


def test_get_missing_key_still_raises_object_not_found() -> None:
    error = ClientError({"Error": {"Code": "NoSuchKey", "Message": "gone"}}, "GetObject")

    with pytest.raises(ObjectNotFound):
        _adapter_with(error).get_object("sources/a-book.epub")
