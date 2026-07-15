"""T4 gate — S3StorageAdapter against MinIO (integration, skip-if-unavailable).

Runs when an S3-compatible endpoint is reachable (local MinIO by default); skips
cleanly otherwise. Each run uses a unique throwaway bucket that is emptied and
dropped on teardown so runs don't accumulate state.
"""

from __future__ import annotations

import io
import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError

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
    except (ClientError, BotoCoreError, StorageUnavailable) as exc:
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
    """boto3-client stub raising a configured error from selected operations."""

    def __init__(
        self,
        *,
        head_bucket: Exception | None = None,
        create_bucket: Exception | None = None,
        get_object: Exception | None = None,
        put_object: Exception | None = None,
    ) -> None:
        self._faults = {
            "head_bucket": head_bucket,
            "create_bucket": create_bucket,
            "get_object": get_object,
            "put_object": put_object,
        }
        self.calls: list[str] = []

    def _op(self, name: str) -> dict:
        self.calls.append(name)
        error = self._faults[name]
        if error is not None:
            raise error
        if name == "get_object":
            return {"Body": io.BytesIO(b"stub-object-bytes")}
        return {}

    def head_bucket(self, **_kwargs) -> dict:  # noqa: ANN003
        return self._op("head_bucket")

    def create_bucket(self, **_kwargs) -> dict:  # noqa: ANN003
        return self._op("create_bucket")

    def get_object(self, **_kwargs) -> dict:  # noqa: ANN003
        return self._op("get_object")

    def put_object(self, **_kwargs) -> dict:  # noqa: ANN003
        return self._op("put_object")


def _adapter_with(**faults: Exception) -> S3StorageAdapter:
    adapter = S3StorageAdapter(
        endpoint=ENDPOINT,
        access_key=ACCESS_KEY,
        secret_key=SECRET_KEY,
        bucket="learny-test-faults",
        region=REGION,
    )
    adapter._client = _FaultingClient(**faults)  # noqa: SLF001 — unit-level stub
    return adapter


def _unreachable_endpoint_error() -> EndpointConnectionError:
    # The exact fault the first containerized ingestion hit (QA finding F2).
    return EndpointConnectionError(endpoint_url=ENDPOINT)


def test_get_transient_client_error_raises_storage_unavailable() -> None:
    """Non-missing-object S3 faults surface as the Learny-owned error.

    The port contract keeps vendor exception types inside this adapter, so
    callers (the ingestion step's retry classification) never import botocore.
    """
    error = ClientError({"Error": {"Code": "SlowDown", "Message": "slow"}}, "GetObject")

    with pytest.raises(StorageUnavailable):
        _adapter_with(get_object=error).get_object("sources/a-book.epub")


def test_get_botocore_error_raises_storage_unavailable() -> None:
    with pytest.raises(StorageUnavailable):
        _adapter_with(get_object=BotoCoreError()).get_object("sources/a-book.epub")


def test_get_missing_key_still_raises_object_not_found() -> None:
    error = ClientError({"Error": {"Code": "NoSuchKey", "Message": "gone"}}, "GetObject")

    with pytest.raises(ObjectNotFound):
        _adapter_with(get_object=error).get_object("sources/a-book.epub")


def test_get_with_unreachable_endpoint_raises_storage_unavailable() -> None:
    # FND-03: the fault escapes from bucket-ensure, before get_object itself runs.
    with pytest.raises(StorageUnavailable):
        _adapter_with(head_bucket=_unreachable_endpoint_error()).get_object(
            "sources/a-book.epub"
        )


def test_put_with_unreachable_endpoint_raises_storage_unavailable() -> None:
    # FND-04: bucket-ensure fault during upload.
    with pytest.raises(StorageUnavailable):
        _adapter_with(head_bucket=_unreachable_endpoint_error()).put_object(
            "sources/a-book.epub", b"bytes", content_type="application/epub+zip"
        )


def test_put_botocore_error_raises_storage_unavailable() -> None:
    with pytest.raises(StorageUnavailable):
        _adapter_with(put_object=BotoCoreError()).put_object(
            "sources/a-book.epub", b"bytes", content_type="application/epub+zip"
        )


def test_put_transient_client_error_raises_storage_unavailable() -> None:
    error = ClientError({"Error": {"Code": "SlowDown", "Message": "slow"}}, "PutObject")

    with pytest.raises(StorageUnavailable):
        _adapter_with(put_object=error).put_object(
            "sources/a-book.epub", b"bytes", content_type="application/epub+zip"
        )


def test_bucket_create_failure_raises_storage_unavailable() -> None:
    # head_bucket says "missing" (ClientError), then create_bucket itself fails.
    missing = ClientError({"Error": {"Code": "404", "Message": "no bucket"}}, "HeadBucket")

    with pytest.raises(StorageUnavailable):
        _adapter_with(
            head_bucket=missing, create_bucket=_unreachable_endpoint_error()
        ).get_object("sources/a-book.epub")


def test_missing_bucket_is_created_and_the_operation_proceeds() -> None:
    # head_bucket says "missing", create_bucket succeeds → the original
    # operation completes against the freshly created bucket.
    missing = ClientError({"Error": {"Code": "404", "Message": "no bucket"}}, "HeadBucket")
    adapter = _adapter_with(head_bucket=missing)

    assert adapter.get_object("sources/a-book.epub") == b"stub-object-bytes"
    assert "create_bucket" in adapter._client.calls  # noqa: SLF001 — unit-level stub
