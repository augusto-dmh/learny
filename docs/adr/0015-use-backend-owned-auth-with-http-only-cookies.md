# ADR-015: Use Backend-Owned Auth With HTTP-Only Cookies

- **Date**: 2026-06-27
- **Status**: Accepted
- **Deciders**: Augusto, Codex
- **Tags**: architecture, authentication, security, fastapi, nextjs, sessions

## Context and Problem Statement

ADR-012 established that Learny should support email/password accounts from the MVP. The next decision is how browser authentication should be shaped between the FastAPI backend and the Next.js frontend.

Learny needs authenticated access to user-owned sources, corpus records, retrieval results, and teaching sessions. The implementation should fit a first-party web app while avoiding unnecessary exposure of long-lived credentials to browser JavaScript.

## Decision Drivers

- User-owned source files, corpus records, and teaching sessions require reliable authorization.
- The browser should not store bearer tokens in localStorage or other JavaScript-accessible durable storage.
- FastAPI should remain the authority for authentication and resource authorization.
- The approach should work with Next.js protected routes and API calls.
- Exact auth libraries, session storage, CSRF approach, and cookie settings need implementation-level design.

## Considered Options

- Backend-owned auth with secure HTTP-only cookies.
- Backend-owned auth with bearer JWT in frontend storage.
- External auth framework/service from the start.
- OAuth-first authentication.

## Decision Outcome

Chosen option: **Backend-owned auth with secure HTTP-only cookies**, because it fits Learny as a first-party web application and keeps credential/session authority with the backend that owns authorization decisions.

The authentication implementation direction is:

1. FastAPI owns registration, login, logout, session validation, and authenticated API access.
2. Browser authentication uses secure HTTP-only cookies rather than JavaScript-accessible bearer token storage.
3. Next.js treats authentication state as server/backend-verified state and protects user-facing routes accordingly.
4. FastAPI enforces authorization for user-owned resources regardless of frontend route checks.
5. Do not choose the exact auth library, session persistence mechanism, cookie attributes, CSRF strategy, password reset flow, or email verification flow in this ADR.

### Positive Consequences

- Avoids storing bearer tokens in browser-accessible storage.
- Keeps authentication and authorization close to the backend data model.
- Supports a first-party web app without introducing external identity-provider complexity.
- Gives Next.js a clear route-protection model while preserving backend enforcement.
- Leaves room for later OAuth or invite-only flows on top of the same account foundation.

### Negative Consequences

- Cookie, CSRF, CORS, and same-site behavior need careful implementation design.
- FastAPI must implement account/session lifecycle and security details.
- Next.js and FastAPI integration must be tested across local and deployed origins.
- Password reset, email verification, rate limiting, and account abuse protection remain follow-up work.

## Pros and Cons of the Options

### Backend-owned auth with secure HTTP-only cookies ✅ Chosen

- ✅ Good fit for a first-party browser application.
- ✅ Reduces exposure of tokens to browser JavaScript.
- ✅ Keeps backend authorization authoritative.
- ❌ Requires careful cookie/CSRF/CORS design.

### Backend-owned auth with bearer JWT in frontend storage

- ✅ Common API pattern.
- ✅ Simple to attach to API requests.
- ❌ Browser-accessible token storage increases security risk.
- ❌ Encourages frontend-managed auth state to drift from backend authorization.

### External auth framework/service from the start

- ✅ Can accelerate auth features.
- ✅ May provide polished account-management flows.
- ❌ Adds provider/framework coupling before the MVP needs it.
- ❌ Can complicate local Docker Compose and self-hosted VPS deployment.

### OAuth-first authentication

- ✅ Useful later for user convenience.
- ❌ Already out of MVP scope.
- ❌ Adds provider setup and callback complexity before core product behavior is proven.

## References

- [ADR-004: Use Python, FastAPI, React, Next.js, And PostgreSQL For The Initial Stack](0004-python-fastapi-react-nextjs-postgresql-stack.md)
- [ADR-012: Use Email And Password Accounts From The MVP](0012-use-email-password-accounts-from-mvp.md)
- FastAPI official documentation via Context7: `/fastapi/fastapi`
- Next.js official documentation via Context7: `/vercel/next.js`
