"""Idempotent shared-sample seed: operator, object, source, templates, then enqueue.

Commit the durable row first, then enqueue, then compensate on broker failure
(AD-016). Application code never imports Celery; this module is a composition
root. Tests inject synthetic bytes into ``SeedSample`` and do not run this CLI.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from uuid import uuid4

from app.application.ingestion import RunIngestion
from app.application.sample import SampleOperatorReserved, SeedSample
from app.core.config import get_settings
from app.infrastructure.clock import SystemClock
from app.infrastructure.db.engine import get_engine
from app.infrastructure.db.repositories import (
    SqlAlchemyCredentialRepository,
    SqlAlchemyIngestionEventRepository,
    SqlAlchemyIngestionJobRepository,
    SqlAlchemyQuizItemRepository,
    SqlAlchemySourceRepository,
    SqlAlchemyUserRepository,
)
from app.infrastructure.scheduling import build_scheduling_adapter
from app.infrastructure.storage.s3 import S3StorageAdapter
from app.infrastructure.worker.enqueuer import CeleryIngestionEnqueuer
from app.infrastructure.worker.steps import NoOpIngestionStep

logger = logging.getLogger(__name__)

_ENQUEUE_FAILURE_ERROR = "Failed to enqueue ingestion task."
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _storage() -> S3StorageAdapter:
    settings = get_settings()
    return S3StorageAdapter(
        endpoint=settings.storage_endpoint,
        access_key=settings.storage_access_key,
        secret_key=settings.storage_secret_key,
        bucket=settings.storage_bucket,
        region=settings.storage_region,
    )


def _resolve_epub(override: Path | None) -> Path:
    chosen = override if override is not None else get_settings().sample_epub_path
    if not chosen.is_absolute():
        chosen = _BACKEND_ROOT / chosen
    return chosen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the shared sample book once.")
    parser.add_argument("--epub", type=Path, default=None)
    args = parser.parse_args(argv)
    epub_path = _resolve_epub(args.epub)
    if not epub_path.is_file():
        print(f"sample epub not found: {epub_path}", file=sys.stderr)
        return 2

    epub_bytes = epub_path.read_bytes()
    engine = get_engine()
    clock = SystemClock()
    settings = get_settings()
    storage = _storage()

    try:
        with engine.begin() as conn:
            seed = SeedSample(
                users=SqlAlchemyUserRepository(conn),
                credentials=SqlAlchemyCredentialRepository(conn),
                sources=SqlAlchemySourceRepository(conn),
                storage=storage,
                jobs=SqlAlchemyIngestionJobRepository(conn),
                events=SqlAlchemyIngestionEventRepository(conn),
                items=SqlAlchemyQuizItemRepository(conn),
                scheduling=build_scheduling_adapter(settings),
                clock=clock,
                ids=uuid4,
                epub_bytes=epub_bytes,
            )
            source, job = seed.persist()
            source_id = source.id
            content_type = source.content_type
            job_id = None if job is None else job.id
    except SampleOperatorReserved:
        print("seed failed: sample operator email is already registered", file=sys.stderr)
        return 1

    if job_id is None:
        return 0

    try:
        CeleryIngestionEnqueuer().enqueue_ingestion(
            source_id=source_id, job_id=job_id, content_type=content_type
        )
    except Exception:
        with engine.begin() as conn:
            RunIngestion(
                sources=SqlAlchemySourceRepository(conn),
                jobs=SqlAlchemyIngestionJobRepository(conn),
                events=SqlAlchemyIngestionEventRepository(conn),
                step=NoOpIngestionStep(),
                clock=clock,
                ids=uuid4,
                max_attempts=settings.ingestion_max_attempts,
            ).fail(job_id, _ENQUEUE_FAILURE_ERROR)
        logger.warning(
            "sample seed enqueue failed",
            extra={"source_id": str(source_id), "job_id": str(job_id)},
        )
        print("seed failed: could not enqueue ingestion", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
