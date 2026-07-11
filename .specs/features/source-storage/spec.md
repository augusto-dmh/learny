# Source Storage Specification

TDD-001 Phase 3 (Source storage). Cycle: `source-storage`. Closes STATE.md Gap-2
(wire `AuthorizeOwnership` to the first user-owned resource).

## Problem Statement

Learny users have accounts (Cycle 1) but no way to bring their own material in.
Before ingestion, retrieval, or teaching can exist, an authenticated user must be
able to upload an EPUB and have Learny durably record the original file plus its
metadata under that user's ownership. This is the first user-owned resource, so
it also establishes the ownership-enforcement pattern every later resource reuses.

## Goals

- [ ] An authenticated user can upload an EPUB and receive a persisted, owned source record (create).
- [ ] An authenticated user can list and inspect only their own sources (read + ownership enforcement).
- [ ] Original file bytes land in S3-compatible object storage via a Learny-owned `StoragePort`; PostgreSQL owns metadata, ownership, checksum, and the object key.
- [ ] Invalid uploads (wrong type/extension, oversize, missing title) are rejected before anything is persisted.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
| ------- | ------ |
| EPUB parsing / canonical corpus / chunks / embeddings | TDD Phase 5+; this cycle only stores the original file + metadata |
| Ingestion trigger endpoint (`POST /api/sources/{id}/ingestion`) and ingestion status | TDD Phase 4; sources land in a single `uploaded` state this cycle |
| PDF / DOCX / other formats | Deferred by ADR-011 (EPUB first) |
| Presigned-URL / direct-to-storage upload | Deferred by ADR-018; direct multipart through FastAPI for MVP |
| Source deletion, update, re-upload, versioning | Not MVP (TDD: account/data lifecycle deferred); schema must not preclude it |
| Content-based deduplication (same file uploaded twice) | Not MVP; each upload is a distinct source (checksum stored for future use) |
| Separate `source_files` table (multi-file sources) | MVP source = exactly one EPUB file; file attributes inline on `sources` |
| Orphaned-object garbage collection | Future; failed-insert orphans are opaque and left for later GC (see SRC-09) |

---

## Assumptions & Open Questions

Every ambiguity is resolved or recorded here — nothing is left silently unclear.

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --------------------- | -------------- | --------- | ---------- |
| Upload transport | Direct multipart through FastAPI | Settled in ADR-018; EPUB sizes make streaming through the backend cheap; avoids a two-phase state machine | y (user) |
| PR scope | Full vertical slice (backend + frontend) | Settled with user; matches Cycle 1 cadence, delivers an exercisable feature | y (user) |
| Storage SDK | `boto3` behind `StoragePort` | S3-generic → provider-swappable per ADR-013/AD-008 (MinIO local, S3/R2 later) | y (user) |
| Cross-user / missing source read | `404` when the source is not the caller's or does not exist; `403` reserved for authenticated-but-forbidden where existence is already known | Avoids existence disclosure/enumeration of other users' source IDs (TDD data protection) | n (default) |
| Max upload size | `LEARNY_EPUB_MAX_BYTES` default `52428800` (50 MiB) | EPUBs rarely exceed this; conservative cap protects the request worker | n (default) |
| Title source | Required client-supplied `title` field (multipart), non-empty, ≤ 500 chars | EPUB metadata-title extraction belongs to ingestion (Phase 5); do not parse here | n (default) |
| Store-then-persist ordering | `put_object` first, then INSERT within the request transaction | Keeps validation authoritative and avoids a visible row pointing at absent bytes; a failed INSERT leaves only an opaque orphan object (SRC-09) | n (default) |
| Object key shape | `sources/{user_id}/{uuid}.epub` | Opaque, owner-partitioned, no email/title (TDD data protection) | n (default) |
| Single `uploaded` status | One post-upload state this cycle | Ingestion states arrive in Phase 4; column exists so Phase 4 is additive | n (default) |

**Open questions:** none — all resolved or logged above.

---

## User Stories

### P1: Upload an EPUB source ⭐ MVP

**User Story**: As an authenticated user, I want to upload an EPUB file with a title so that Learny durably stores my source and I can build on it later.

**Why P1**: Nothing downstream (ingestion, Q&A, teaching) can exist without an owned, stored source. This is the entry point of the whole product.

**Acceptance Criteria**:

1. WHEN an authenticated user POSTs a valid `.epub` file plus a non-empty title to `/api/sources` THEN the system SHALL store the bytes in object storage under an opaque owner-partitioned key, persist a `sources` row owned by that user (status `uploaded`, with filename, content_type, byte_size, sha256 checksum, object_key), and return `201` with a secret-free source summary (id, title, filename, byte_size, status, created_at).
2. WHEN the uploaded file's extension is not `.epub` OR its content-type is not `application/epub+zip` THEN the system SHALL reject with `415` (unsupported media type) and persist nothing (no row, no stored object).
3. WHEN the uploaded file exceeds `LEARNY_EPUB_MAX_BYTES` THEN the system SHALL reject with `413` (payload too large) and persist nothing.
4. WHEN the request omits a title or the title is empty/whitespace or exceeds 500 characters THEN the system SHALL reject with `422` and persist nothing.
5. WHEN an unauthenticated caller POSTs to `/api/sources` THEN the system SHALL reject with `401` and persist nothing.
6. WHEN an authenticated POST arrives without a valid CSRF token OR from an untrusted origin THEN the system SHALL reject with `403` and persist nothing (reusing the Cycle-1 CSRF/origin guards).
7. WHEN the persisted object key is generated THEN it SHALL NOT contain the user's email or the source title, and SHALL be unique.

**Independent Test**: Register/login, POST a small valid EPUB with a title, assert `201` + summary; assert a `sources` row and a stored object exist. Repeat with a `.txt` file → `415`; oversize → `413`; missing title → `422`; no cookie → `401`.

---

### P1: List my sources ⭐ MVP

**User Story**: As an authenticated user, I want to list my uploaded sources so that I can see what I've brought into Learny.

**Why P1**: Uploads are useless if the user can't see them; also the primary screen of the vertical slice.

**Acceptance Criteria**:

1. WHEN an authenticated user GETs `/api/sources` THEN the system SHALL return `200` with an array of that user's source summaries, most-recent first, and SHALL NOT include any other user's sources.
2. WHEN a user with no sources GETs `/api/sources` THEN the system SHALL return `200` with an empty array.
3. WHEN an unauthenticated caller GETs `/api/sources` THEN the system SHALL reject with `401`.

**Independent Test**: User A uploads two sources, user B uploads one; A's `GET /api/sources` returns exactly A's two (newest first); a fresh user's list is `[]`.

---

### P1: View a single source ⭐ MVP

**User Story**: As an authenticated user, I want to open one of my sources so that I can inspect its metadata and status.

**Why P1**: Completes the read side and is where per-resource ownership enforcement (Gap-2) is exercised.

**Acceptance Criteria**:

1. WHEN an authenticated user GETs `/api/sources/{id}` for a source they own THEN the system SHALL return `200` with that source's summary.
2. WHEN an authenticated user GETs `/api/sources/{id}` for a source owned by another user THEN the system SHALL return `404` and SHALL NOT reveal that the source exists.
3. WHEN an authenticated user GETs `/api/sources/{id}` for an id that does not exist THEN the system SHALL return `404`.
4. WHEN an authenticated user GETs `/api/sources/{id}` with a malformed (non-UUID) id THEN the system SHALL return `422`.

**Independent Test**: A owns source S; `A GET /api/sources/S` → `200`; `B GET /api/sources/S` → `404`; `A GET /api/sources/<random-uuid>` → `404`.

---

### P1: Sources screen in the web app ⭐ MVP

**User Story**: As a user in the browser, I want a page to upload an EPUB and see my sources so that I can use the feature without the API directly.

**Why P1**: The chosen scope is a full vertical slice; the feature must be exercisable end-to-end through Next.js.

**Acceptance Criteria**:

1. WHEN an authenticated user visits `/sources` THEN the page SHALL fetch and render their sources through the same-origin Next.js proxy (never calling FastAPI cross-origin), showing an empty-state when there are none.
2. WHEN the user selects an `.epub` file, enters a title, and submits THEN the page SHALL POST it through the same-origin proxy (forwarding the session cookie and CSRF token) and, on success, show the new source in the list.
3. WHEN the API rejects an upload (e.g. `415`/`413`/`422`) THEN the page SHALL surface an error message and SHALL NOT add a source to the list.
4. WHEN an unauthenticated visitor loads `/sources` THEN the page SHALL redirect to `/login` (UX only; FastAPI remains the security boundary).

**Independent Test**: With a logged-in session, load `/sources` (empty state), upload an EPUB, see it appear; upload a `.txt`, see an error and no new row; logged-out visit redirects to `/login`.

---

## Edge Cases

- WHEN object storage is unavailable at upload time (put fails) THEN the system SHALL return `502`/`503`, persist no `sources` row, and log the failure with `user_id` (no secrets).
- WHEN the object is stored but the subsequent INSERT fails THEN the request transaction SHALL roll back the row and the response SHALL be `5xx`; the orphaned object is opaque and acceptable, left for future GC (no user-visible corruption, no metadata leak).
- WHEN the same file is uploaded twice THEN the system SHALL create two independent sources with distinct object keys (no dedup this cycle).
- WHEN the multipart request has no file part THEN the system SHALL return `422` and persist nothing.
- WHEN an empty (zero-byte) file is uploaded THEN the system SHALL reject with `422` (not a valid EPUB payload).

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| -------------- | ----- | ----- | ------ |
| SRC-01 | P1 Upload | Design | ✅ Verified |
| SRC-02 | P1 Upload (file type/ext validation) | Design | ✅ Verified |
| SRC-03 | P1 Upload (size cap) | Design | ✅ Verified |
| SRC-04 | P1 Upload (title validation) | Design | ✅ Verified |
| SRC-05 | P1 Upload (auth + CSRF/origin + rate-limit) | Design | ✅ Verified |
| SRC-06 | P1 Upload (opaque owner-partitioned object key via StoragePort) | Design | ✅ Verified |
| SRC-07 | boto3 S3/MinIO adapter implements StoragePort; bucket ensured | Design | ✅ Verified |
| SRC-08 | P1 List (owner-scoped, newest-first, empty ok) | Design | ✅ Verified |
| SRC-09 | P1 View (ownership enforcement → 404; storage/DB failure handling) | Design | ✅ Verified |
| SRC-10 | Observability: source lifecycle logs with ids, no secrets | Design | ✅ Verified |
| SRC-11 | P1 Web `/sources` list + upload via same-origin proxy | Design | ✅ Verified |
| SRC-12 | Migration 0002 creates `sources` table (FK, index, unique key) | Design | ✅ Verified |

**ID format:** `SRC-[NUMBER]`
**Status values:** Pending → In Design → In Tasks → Implementing → Verified
**Coverage:** 12 total, 0 mapped to tasks yet (mapped in tasks.md).

---

## Success Criteria

- [ ] A logged-in user can upload an EPUB and see it in their list, end to end through the web app.
- [ ] Every `/api/sources*` endpoint denies unauthenticated access; every read is owner-scoped and cross-user access yields `404`.
- [ ] Invalid uploads (type, size, title, empty) are rejected with the specified status and leave zero persisted state.
- [ ] Object keys carry no email/title; PostgreSQL holds metadata + checksum + object key; bytes live in MinIO via `StoragePort`.
- [ ] Backend and frontend test suites cover the ACs (including cross-user `404` and each validation reject) and are green; ruff clean.
