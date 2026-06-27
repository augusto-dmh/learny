# ADR-013: Use S3-Compatible Object Storage For Uploaded Sources

- **Date**: 2026-06-27
- **Status**: Accepted
- **Deciders**: Augusto, Codex
- **Tags**: architecture, storage, uploads, s3, object-storage, files

## Context and Problem Statement

Learny's MVP needs users to upload EPUB source files for ingestion. Future versions may support PDF, DOCX, HTML, scans, and other source materials. These files should be preserved as original source artifacts while derived corpus records, chunks, embeddings, citations, and session data live in PostgreSQL.

The storage question is whether uploaded source files should live on a local filesystem volume, in S3-compatible object storage, as database blobs, or in a local MinIO service from the start.

## Decision Drivers

- Source files should be stored separately from relational product and corpus metadata.
- The storage model should work for local development, VPS deployment, and later managed/cloud deployment.
- The application should avoid assuming local filesystem paths as durable source identifiers.
- Original files need backup, migration, and future reprocessing support.
- Storage implementation details should sit behind a Learny-owned storage port.

## Considered Options

- Local filesystem volume first.
- S3-compatible object storage from the start.
- Database blobs.
- Local MinIO in Docker from the start.

## Decision Outcome

Chosen option: **S3-compatible object storage from the start**, because it gives Learny a production-shaped file storage model for uploaded sources without tying the application to one provider.

The storage direction is:

1. Store uploaded source files in S3-compatible object storage.
2. Store source metadata, ownership, ingestion status, corpus links, and object keys in PostgreSQL.
3. Access files through a Learny-owned storage port rather than direct provider SDK calls from domain logic.
4. Keep the concrete provider undecided in this ADR.
5. Allow MinIO, AWS S3, Cloudflare R2, or another S3-compatible provider to satisfy the storage port in different environments.
6. Do not store source files as database blobs.

### Positive Consequences

- The first implementation uses production-like object storage semantics.
- Original source files can be reprocessed without depending on local server paths.
- The same application storage contract can work locally, on a VPS, and later in managed/cloud environments.
- PostgreSQL remains focused on metadata, corpus structure, retrieval data, and product state.
- Moving between S3-compatible providers remains possible.

### Negative Consequences

- The MVP has more infrastructure than local filesystem storage.
- Local development and Docker Compose need an object-storage service or configured external bucket.
- Backups, lifecycle rules, credentials, bucket policy, and object naming need explicit design.
- S3-compatible providers are similar but not always identical; adapter tests are needed.

## Pros and Cons of the Options

### S3-compatible object storage from the start ✅ Chosen

- ✅ Production-shaped storage model.
- ✅ Works across local MinIO, AWS S3, Cloudflare R2, and similar providers.
- ✅ Keeps original files separate from relational metadata.
- ❌ Adds service/configuration complexity to the MVP.

### Local filesystem volume first

- ✅ Simplest Docker Compose/VPS setup.
- ✅ Easy to inspect files during development.
- ❌ Encourages local path assumptions.
- ❌ Backup, migration, and later object-storage transition need more care.

### Database blobs

- ✅ Strong transactional consistency with metadata.
- ❌ Poor fit for growing source files and object lifecycle management.
- ❌ Makes database backups heavier and file serving less flexible.

### Local MinIO in Docker from the start

- ✅ Gives S3-compatible semantics in local/VPS Docker Compose.
- ✅ Useful implementation option for the accepted direction.
- ❌ It is one implementation choice, not the storage architecture itself.
- ❌ Adds another service to operate if used in production-like deployments.

## References

- [ADR-008: Use Docker Compose On A VPS For The First Production-Like Deploy](0008-use-docker-compose-vps-for-first-production-like-deploy.md)
- [ADR-011: Support EPUB First For Initial Ingestion](0011-support-epub-first-for-initial-ingestion.md)
- Amazon S3 official documentation via Context7: `/websites/aws_amazon_s3`
- MinIO official documentation via Context7: `/minio/docs`
