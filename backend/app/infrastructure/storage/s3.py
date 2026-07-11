"""boto3 adapter implementing ``StoragePort`` against S3-compatible storage.

Points at MinIO locally and unchanged at AWS S3 / Cloudflare R2 (AD-011): the
S3 API is the provider-neutral contract. boto3 client and ``ClientError`` objects
are kept inside this module — the port only ever raises the Learny-owned
:class:`ObjectNotFound`, so provider details never cross into domain/application
(ADR-007/009). The bucket is created on first use so local boot needs no manual
setup.
"""

from __future__ import annotations

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

# S3 error codes that mean "the object (or its bucket) is not there".
_NOT_FOUND_CODES = frozenset({"NoSuchKey", "NoSuchBucket", "404"})


class ObjectNotFound(Exception):
    """Raised by :meth:`S3StorageAdapter.get_object` when the key has no object."""


class S3StorageAdapter:
    """``StoragePort`` backed by an S3-compatible bucket via boto3."""

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str,
    ) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            # Path-style addressing so a host like localhost/minio works.
            config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        self._bucket_ready = False

    def _ensure_bucket(self) -> None:
        """Create the bucket if missing; idempotent and cached per instance."""
        if self._bucket_ready:
            return
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)
        self._bucket_ready = True

    def put_object(self, key: str, data: bytes, *, content_type: str) -> None:
        self._ensure_bucket()
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    def get_object(self, key: str) -> bytes:
        self._ensure_bucket()
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in _NOT_FOUND_CODES:
                raise ObjectNotFound(key) from exc
            raise
        return response["Body"].read()
