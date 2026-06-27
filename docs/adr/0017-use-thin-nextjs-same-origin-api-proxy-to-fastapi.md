# ADR-017: Use A Thin Next.js Same-Origin API Proxy To FastAPI

- **Date**: 2026-06-27
- **Status**: Accepted
- **Deciders**: Augusto, Codex
- **Tags**: architecture, frontend, backend, nextjs, fastapi, authentication, api

## Context and Problem Statement

ADR-004 selected FastAPI for the backend and React/Next.js for the frontend. ADR-015 selected backend-owned authentication with secure HTTP-only cookies. The frontend/API boundary now needs to define whether browser requests call FastAPI directly, go through Next.js server routes/proxying, or use a more formal backend-for-frontend layer.

The main concern is making browser authentication and session handling reliable without duplicating product logic or authorization rules in Next.js.

## Decision Drivers

- Browser authentication should use secure HTTP-only cookies and avoid browser-accessible bearer token storage.
- Cross-origin cookie, CORS, and CSRF complexity should be minimized.
- FastAPI should remain authoritative for authentication, authorization, product behavior, and user-owned resources.
- Next.js should support protected user-facing routes and frontend ergonomics without becoming a second backend domain.
- The boundary should work cleanly in local Docker Compose and VPS deployment.

## Considered Options

- Browser calls FastAPI directly.
- Next.js provides a thin same-origin API/proxy boundary to FastAPI.
- Next.js implements a strict backend-for-frontend layer with frontend-specific API models and orchestration.

## Decision Outcome

Chosen option: **Next.js provides a thin same-origin API/proxy boundary to FastAPI**, because it fits HTTP-only cookie authentication while preserving FastAPI as the authoritative backend.

The frontend/API boundary is:

1. Browser-facing requests should call same-origin Next.js routes or proxy paths.
2. Next.js forwards relevant API requests to FastAPI.
3. FastAPI owns registration, login, logout, session validation, authorization, product logic, ingestion status, retrieval, and teaching behavior.
4. Next.js may perform route-level authentication checks for user experience, but FastAPI must enforce authorization for every protected resource.
5. Next.js should not duplicate Learny domain logic, authorization policy, ingestion orchestration, retrieval behavior, or teaching-session state machines.
6. Avoid browser-accessible bearer tokens.

### Positive Consequences

- Same-origin browser requests reduce CORS and credential-handling complexity.
- The approach aligns with secure HTTP-only cookie auth.
- FastAPI remains the single authority for data ownership and authorization.
- Next.js can still provide ergonomic route protection and frontend-specific request shaping.
- The design can evolve into a richer BFF later if repeated frontend-specific orchestration pain appears.

### Negative Consequences

- Next.js must include some server-side route/proxy code.
- The project must ensure proxy code stays thin and does not accumulate business logic.
- Local and deployed routing must be configured carefully so cookies, origins, and internal service URLs behave consistently.
- CSRF, cookie attributes, and same-site behavior still need implementation-level design.

## Pros and Cons of the Options

### Thin same-origin Next.js API/proxy boundary ✅ Chosen

- ✅ Fits backend-owned HTTP-only cookie authentication.
- ✅ Keeps browser calls same-origin.
- ✅ Preserves FastAPI as the authoritative backend.
- ❌ Requires disciplined proxy boundaries to avoid duplicated backend logic.

### Browser calls FastAPI directly

- ✅ Fewer frontend server routes.
- ✅ Direct API topology is easy to understand.
- ❌ Cross-origin CORS, cookies, and credentials become more delicate.
- ❌ Can complicate local/deployed auth behavior between Next.js and FastAPI origins.

### Strict backend-for-frontend in Next.js

- ✅ Can create frontend-optimized API shapes.
- ✅ Useful if the frontend later needs substantial aggregation/orchestration.
- ❌ Too much structure for the MVP.
- ❌ Risks duplicating domain logic and authorization behavior outside FastAPI.

## References

- [ADR-004: Use Python, FastAPI, React, Next.js, And PostgreSQL For The Initial Stack](0004-python-fastapi-react-nextjs-postgresql-stack.md)
- [ADR-015: Use Backend-Owned Auth With HTTP-Only Cookies](0015-use-backend-owned-auth-with-http-only-cookies.md)
- Next.js Backend for Frontend guide: https://nextjs.org/docs/app/guides/backend-for-frontend
- Next.js Route Handlers: https://nextjs.org/docs/app/getting-started/route-handlers
- Next.js cookies API: https://nextjs.org/docs/app/api-reference/functions/cookies
- Next.js server function security guidance: https://nextjs.org/docs/app/api-reference/directives/use-server
- FastAPI CORS documentation: https://fastapi.tiangolo.com/tutorial/cors/
- FastAPI response cookies documentation: https://fastapi.tiangolo.com/advanced/response-cookies/
