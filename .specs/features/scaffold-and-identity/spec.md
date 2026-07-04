# Spec — Cycle 1: Scaffold + Identity Foundation

Maps to TDD-001 Implementation Plan **Phase 1 (Repository scaffold)** and **Phase 2 (Identity foundation)**.
Locked constraints: ADR-004, ADR-006, ADR-007, ADR-008, ADR-009, ADR-012, ADR-013, ADR-014, ADR-015, ADR-017 and TDD-001.

## Goal

A runnable skeleton (`docker compose up`) for all MVP services, plus a complete email/password identity
foundation: users can register, log in, see who they are, and log out, end-to-end through the same-origin
Next.js proxy to FastAPI, with secure HTTP-only cookie sessions and per-user ownership enforcement primitives.

## Out of Scope (deferred to later cycles)

Source upload, ingestion, corpus, retrieval, Q&A, teaching sessions, golden fixtures, production/VPS hardening
(TDD Phases 3–10). File-upload constraints are deferred with sources; only auth-input validation is in scope.

## Functional Requirements

### Scaffold (TDD Phase 1)

- **FR-SCAF-001** — `docker compose up` starts: FastAPI API, Next.js web, PostgreSQL+pgvector, Redis, a Celery worker, and an S3-compatible object-storage service.
- **FR-SCAF-002** — API and worker expose liveness/health checks; compose reports healthy.
- **FR-SCAF-003** — Backend layout enforces ADR-007/009 boundaries: domain / application / infrastructure (adapters), with provider SDKs behind ports. No SDK or framework objects in domain.
- **FR-SCAF-004** — Next.js app exists with a thin same-origin API route/proxy boundary to FastAPI (ADR-017); proxy owns no domain logic.
- **FR-SCAF-005** — Test harness runs for backend (pytest) and frontend; a trivial test passes in CI-style invocation.
- **FR-SCAF-006** — Database schema migration tooling is wired and can create the identity tables.

### Identity (TDD Phase 2 — Module: Identity And Access)

- **FR-AUTH-001** — `POST /api/auth/register`: create email/password account and start an authenticated session. (TDD API Contract)
- **FR-AUTH-002** — `POST /api/auth/login`: validate credentials and start an authenticated session.
- **FR-AUTH-003** — `POST /api/auth/logout`: end the authenticated session.
- **FR-AUTH-004** — `GET /api/auth/me`: return authenticated user summary; 401 when unauthenticated.
- **FR-AUTH-005** — Passwords are hashed (never stored plaintext); hashing via the library chosen in AD-006.
- **FR-AUTH-006** — Sessions are FastAPI-owned and carried by a secure HTTP-only cookie; PostgreSQL is the durable source of truth for session/credential state (TDD Identity authoritative state).
- **FR-AUTH-007** — Browser auth calls route through the same-origin Next.js proxy; Next route protection is UX-only, not the security boundary (TDD Security).
- **FR-AUTH-008** — An ownership/authorization primitive exists so every protected endpoint enforces authentication and user-ownership; a non-owner is denied (TDD: "every user-owned resource query scoped by ownership").
- **FR-AUTH-009** — Auth endpoints (register/login) expose rate-limit hooks (conservative defaults acceptable) (TDD Abuse And Rate Limits).
- **FR-AUTH-010** — Registration/login validate input (email format, password policy).

## Non-Functional / Security Requirements (TDD Security Considerations)

- **NFR-SEC-001** — State-changing browser requests are protected by the CSRF strategy chosen in AD-007.
- **NFR-SEC-002** — Cookie attributes (Secure, HttpOnly, SameSite, path) are explicitly defined for local and future VPS.
- **NFR-SEC-003** — Secrets/provider credentials stay server-side; never exposed to browser JS.
- **NFR-SEC-004** — Logs redact passwords, session tokens, and secrets by default.
- **NFR-SEC-005** — Cross-user access is impossible: tests prove user A cannot read user B's owned resource via the FR-AUTH-008 primitive.

## Gray Areas → resolved in Discuss (context.md)

- **GA-1 (→ AD-006)** — password-hashing / session library for FastAPI.
- **GA-2 (→ AD-007)** — CSRF strategy compatible with same-origin proxy + HTTP-only cookies.
- **GA-3 (→ AD-008)** — concrete S3-compatible object-storage provider for local + first VPS.

## Acceptance Criteria (spec-anchored, drive tests)

- **AC-1** — `docker compose up` brings all six services to healthy; API and worker health checks return success. (FR-SCAF-001/002)
- **AC-2** — A new user registers via the Next.js proxy and receives an HTTP-only session cookie; no token is readable by browser JS. (FR-AUTH-001/006/007, NFR-SEC-002/003)
- **AC-3** — Registered user logs in, calls `/api/auth/me` and gets their summary; after logout `/api/auth/me` returns 401. (FR-AUTH-002/003/004)
- **AC-4** — Stored password is a verifiable hash, never the plaintext. (FR-AUTH-005)
- **AC-5** — A state-changing request without a valid CSRF token is rejected. (NFR-SEC-001)
- **AC-6** — User A cannot access a resource owned by user B through the ownership primitive. (FR-AUTH-008, NFR-SEC-005)
- **AC-7** — Repeated rapid login/register attempts hit the rate-limit hook. (FR-AUTH-009)
- **AC-8** — Logs of an auth flow contain no plaintext password, session token, or secret. (NFR-SEC-004)
