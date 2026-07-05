# Context — Source Storage Decisions

Decisions resolving this cycle's gray areas, settled with the user before Design
(the Discuss phase was pre-empted because the two material forks were decided in
planning). These feed Design directly. Architecture-level decisions are recorded
durably in ADR-018; this file captures the cycle-local framing and implications.

## AD-009 (D-1) — Upload transport: direct multipart through FastAPI

**Decision:** The browser POSTs the EPUB in a single multipart request; FastAPI
validates and streams the bytes to object storage via the existing
`StoragePort.put_object`, then persists the `sources` row. **Presigned
direct-to-storage upload is deferred** (ADR-018), to be revisited only when a
materially larger format (e.g. image-heavy PDFs) or host-bandwidth pressure
appears.

**Why:** EPUBs are typically 1–20 MB (rarely > 50 MB), so streaming through the
backend is cheap; a one-request, single-state flow avoids a `pending → uploaded`
state machine and orphan-reconciliation the product does not yet need; reuses the
`StoragePort` with no new method. Full rationale + revisit triggers in ADR-018.

**Implications:**
- One endpoint (`POST /api/sources`), one atomic outcome; no confirm step, no `pending_upload` state.
- Validation is authoritative because the bytes transit the backend.
- `StoragePort` is unchanged (`put_object`/`get_object`).

## AD-010 (D-2) — PR scope: full vertical slice

**Decision:** This cycle ships backend (sources API + storage adapter + migration
+ tests) **and** frontend (`/sources` list + upload screen + same-origin proxy
routes + tests) in one PR.

**Why:** Matches Cycle 1's end-to-end cadence and delivers a feature the user can
actually exercise in the browser, not just via curl.

**Implications:**
- Frontend proxy routes under `frontend/app/api/sources/**` forward cookie + CSRF, per ADR-017.
- `/sources` page is a UX convenience; FastAPI remains the security boundary.

## AD-011 (D-3) — Storage SDK: boto3 behind the port

**Decision:** Implement the `StoragePort` adapter with **`boto3`** (S3 API)
pointed at MinIO locally, rather than the MinIO-specific client.

**Why:** The S3 API is the provider-neutral contract; boto3 works unchanged
against MinIO, AWS S3, Cloudflare R2, etc., preserving the ADR-013/AD-008
swap-provider property. The adapter stays behind `StoragePort` so boto3 objects
never leak inward (ADR-007/009).

**Implications:**
- New settings: endpoint URL, access key, secret key, bucket, region — env-only.
- Adapter ensures the bucket exists on first use (idempotent), so local boot needs no manual bucket creation.

## Gap-2 closure — ownership enforcement

Sources are the first user-owned resource, so this cycle wires the Cycle-1
`AuthorizeOwnership` primitive to real endpoints (list scoped by owner; single-
read denies non-owners). Cross-user / missing reads return `404` (no existence
disclosure) rather than `403` — see spec Assumptions.
