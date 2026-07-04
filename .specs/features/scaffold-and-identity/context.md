# Context — Cycle 1 Discuss Decisions

User decisions resolving the spec's gray areas. These feed Design directly.

## AD-006 (GA-1) — Password hashing + session model

**Decision:** Argon2id password hashing (via `pwdlib` or `argon2-cffi`) + server-side **opaque** session tokens stored in PostgreSQL.

**Why:** OWASP-preferred hash; keeps PostgreSQL the durable source of truth (TDD Identity authoritative state); enables instant logout/revocation; avoids a broad auth framework (ADR-009). Verify exact library versions at install time (passlib is unmaintained — prefer pwdlib).

**Implications:**
- `sessions` table holds opaque token (hashed at rest), user_id, expiry, created/last-seen.
- Session cookie carries only the opaque token; server resolves it to the session row each authenticated request.

## AD-007 (GA-2) — CSRF strategy

**Decision:** `SameSite=Lax` + `Secure` + `HttpOnly` session cookie (outer perimeter), `Origin`/`Referer` check, and a **session-bound (synchronizer) CSRF token** validated in a request header on every state-changing request.

**Why:** We are already stateful and already load the session row per request, so a synchronizer token is essentially free and strictly stronger than double-submit (immune to the cookie-injection class); no second cookie, no HMAC; explicit/auditable, matching the project's security posture (ADR-003). Revisit only if DB sessions are ever dropped for stateless JWTs (then signed double-submit).

**Implications:**
- CSRF token generated at session creation, stored on/with the session row, surfaced to the SPA (e.g., via `/api/auth/me` or a dedicated read).
- Next.js proxy forwards the CSRF header through unchanged.
- No state changes via GET.

## AD-008 (GA-3) — S3-compatible object storage

**Decision:** Self-hosted **MinIO** in Docker Compose for both local and the first VPS.

**Why:** Maximum local/prod parity, no external dependency or cost now, fits ADR-008 (Compose on a VPS); the ADR-007 storage port keeps a later swap to a managed provider (R2/B2/S3/Spaces) low-cost. Trade-off accepted: we own backups/durability on the VPS.

**Implications:**
- This cycle only needs MinIO to **boot** as part of `docker compose up` (uploads land in TDD Phase 3).
- A Learny storage port is defined; the MinIO adapter can be minimal/stubbed this cycle.
