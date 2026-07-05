# ADR-018: Use Direct Multipart Upload Through FastAPI For MVP Source Uploads

- **Date**: 2026-07-04
- **Status**: Accepted
- **Deciders**: Augusto, Claude
- **Tags**: architecture, storage, uploads, s3, object-storage, fastapi, epub

## Context and Problem Statement

Learny's MVP lets authenticated users upload EPUB source files, which are stored
in S3-compatible object storage (ADR-013) while metadata, ownership, and object
keys live in PostgreSQL. TDD-001's Phase 3 (Source storage) leaves the upload
transport deliberately open: the backend either *"returns an upload path or
accepts a file upload according to the selected implementation."* This ADR
selects that transport for the first source-storage implementation.

The question is how the file bytes travel from the browser into object storage:
straight through the FastAPI backend, or directly from the browser to storage
via a pre-authorized URL. Both paths end with the same durable outcome — the
original file in S3-compatible storage and a `sources` row in PostgreSQL — and
both sit behind the existing Learny-owned `StoragePort`. They differ in who
streams the bytes, how many round-trips the upload takes, and how upload state is
reconciled.

## Decision Drivers

- EPUB is the only supported format for the MVP (ADR-011); EPUBs are typically
  1–20 MB and rarely exceed ~50 MB.
- File validation (extension, content type, size) must be enforceable and not
  bypassable (TDD-001 security: upload constraints).
- The upload path should be simple to build, test, and review for the first
  source slice; PRs are kept small and reviewable.
- Storage details must stay behind the Learny-owned `StoragePort` so the
  transport choice does not leak provider specifics into domain logic (ADR-007).
- The choice should not foreclose a more scalable transport later if larger
  formats (e.g. image-heavy PDFs) are added.

## Considered Options

- Direct multipart upload through FastAPI.
- Presigned S3 PUT URL (browser uploads directly to object storage).

## Decision Outcome

Chosen option: **Direct multipart upload through FastAPI**, because at MVP EPUB
sizes the bytes streaming through the backend costs nothing meaningful, and it
avoids a two-phase upload state machine the product does not yet need.

The upload direction is:

1. The browser sends the `.epub` file in a single `POST /api/sources`
   multipart request (through the same-origin Next.js proxy, ADR-017).
2. FastAPI validates the file (extension, content type, size cap) before
   persisting anything — because the bytes pass through the backend, validation
   cannot be bypassed.
3. FastAPI writes the bytes to object storage via `StoragePort.put_object` under
   an opaque object key (no user email or source title, per TDD-001 data
   protection), then inserts the `sources` row as a single unit of work.
4. No new `StoragePort` method is introduced; the existing
   `put_object`/`get_object` contract is sufficient.
5. Source rows have a single post-upload state for this cycle
   (`uploaded`); ingestion states are added in Phase 4.

### Positive Consequences

- One endpoint, one request, one atomic outcome: the file lands and the row is
  created, or nothing persists — no orphaned "pending upload" rows to reconcile.
- Validation is authoritative because the file physically transits the backend.
- Reuses the existing `StoragePort` with no new surface.
- Smaller, faster-to-review first slice for the source-storage cycle.

### Negative Consequences

- The file occupies a FastAPI request worker for the duration of the upload;
  acceptable at EPUB sizes but not for very large files.
- The backend host carries the upload bandwidth and memory rather than
  offloading it to object storage.
- If large formats are added later, this transport will need revisiting (see
  below).

### Revisit Trigger — Presigned Upload As The Deferred Alternative

The presigned S3 PUT URL flow (browser uploads bytes directly to storage; the
backend issues a signed URL and later confirms completion) remains the preferred
upgrade path and should be captured in a follow-up ADR when any of these hold:

- A source format materially larger than EPUB is accepted (e.g. large,
  image-heavy PDFs), such that streaming through FastAPI ties up request workers.
- Upload volume or file size begins to pressure API host memory/bandwidth.
- A resumable or client-parallel upload experience becomes a product goal.

Because uploads already sit behind `StoragePort`, moving to presigned URLs is an
additive change (a `presign_put` port method plus a create → upload → confirm
state machine) rather than a rewrite. This ADR intentionally does not adopt that
complexity now.

## Pros and Cons of the Options

### Direct multipart upload through FastAPI ✅ Chosen

- ✅ Simplest path: one request, existing port, no new methods.
- ✅ Validation cannot be bypassed — bytes transit the backend.
- ✅ Atomic: file store and row insert succeed or fail together; no orphan state.
- ✅ Fine for MVP EPUB sizes (no parsing happens in-request; that is Phase 4).
- ❌ Ties up a request worker and backend bandwidth per upload.
- ❌ Does not scale to very large files.

### Presigned S3 PUT URL

- ✅ Scales to large files; backend never streams the bytes.
- ✅ Lower API host memory/bandwidth; storage does the heavy lifting.
- ✅ Enables resumable/direct-to-storage upload experiences.
- ❌ Adds a `presign_put` port method and provider-specific implementation.
- ❌ Introduces a `pending_upload` → `uploaded` state machine and orphan cleanup.
- ❌ Three round-trips plus a confirm endpoint — more to build, test, and review.
- ❌ Validation is harder because the file skips backend inspection mid-flight.

## References

- [ADR-007: Use Learny-Owned Ports For AI Provider Integration](0007-use-learny-owned-ports-for-ai-provider-integration.md)
- [ADR-011: Support EPUB First For Initial Ingestion](0011-support-epub-first-for-initial-ingestion.md)
- [ADR-013: Use S3-Compatible Object Storage For Uploaded Sources](0013-use-s3-compatible-object-storage-for-uploaded-sources.md)
- [ADR-017: Use A Thin Next.js Same-Origin API Proxy To FastAPI](0017-use-thin-nextjs-same-origin-api-proxy-to-fastapi.md)
- [TDD-001: MVP Architecture](../tdd/0001-mvp-architecture.md) — Phase 3 (Source storage); Open Question on upload transport
