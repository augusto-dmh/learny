# ADR-012: Use Email And Password Accounts From The MVP

- **Date**: 2026-06-27
- **Status**: Accepted
- **Deciders**: Augusto, Codex
- **Tags**: product, authentication, authorization, users, mvp

## Context and Problem Statement

Learny is intended to support repeated daily use by multiple people. The first MVP includes document ingestion, cited Q&A, and teaching sessions, all of which need ownership boundaries for uploaded sources, processed corpus data, sessions, and future notes or memory.

The question is whether the first implementation should avoid authentication, start with local/admin-only use, use email/password accounts, use OAuth/social login, or restrict access through invite-only accounts.

## Decision Drivers

- Source uploads, corpus data, teaching sessions, and future notes need clear user ownership.
- Multi-user behavior should be modeled from the beginning instead of retrofitted later.
- The MVP should avoid unnecessary third-party identity-provider complexity.
- Authorization checks should be designed early to avoid insecure direct object access.
- The chosen account model should support later invite-only, OAuth, organizations, or sharing features.

## Considered Options

- Single-user local/admin mode first.
- Email/password accounts from the start.
- OAuth/social login first.
- Invite-only multi-user.

## Decision Outcome

Chosen option: **Email/password accounts from the start**, because it gives Learny a simple real multi-user foundation without adding OAuth/social-provider complexity to the MVP.

The authentication scope is:

1. Support user registration, login, logout, and authenticated API access in the MVP.
2. Associate uploaded sources, processed corpus records, retrieval indexes, and teaching sessions with an owning user.
3. Enforce authorization on user-owned resources from the first implementation.
4. Keep the implementation compatible with later invite-only registration, OAuth/social login, organizations, and sharing.
5. Do not choose the exact auth library, token/session format, cookie strategy, password hashing implementation, or email verification flow in this ADR.

### Positive Consequences

- Learny can model ownership, permissions, and user-specific learning data correctly from the start.
- MVP behavior matches the multi-user product direction.
- The first implementation avoids dependency on external identity providers.
- Future notes, memory, sharing, and organization features have a clean account foundation.

### Negative Consequences

- Authentication and authorization work must be implemented before or alongside the first user-facing workflows.
- Password reset, email verification, abuse protection, and account security details will need follow-up design.
- The project must test authorization carefully across uploads, corpus records, sessions, and generated outputs.
- Email/password auth carries security responsibilities that single-user mode would avoid.

## Pros and Cons of the Options

### Email/password accounts from the start ✅ Chosen

- ✅ Establishes real multi-user ownership early.
- ✅ Avoids OAuth/social-provider complexity in the MVP.
- ✅ Supports future invite-only, organization, sharing, and memory features.
- ❌ Requires authentication, authorization, and account-security work immediately.

### Single-user local/admin mode first

- ✅ Fastest path to local prototype behavior.
- ✅ Avoids auth work initially.
- ❌ Conflicts with Learny's multi-user product direction.
- ❌ Delays ownership and authorization modeling until data already exists.

### OAuth/social login first

- ✅ Convenient for users later.
- ✅ Avoids storing passwords if implemented through a trusted provider.
- ❌ Adds provider setup, callback flows, account linking, and deployment configuration before the MVP needs it.
- ❌ Can distract from the core ingestion and teaching workflow.

### Invite-only multi-user

- ✅ Good private beta shape.
- ✅ Keeps access controlled while preserving multi-user modeling.
- ❌ Adds invitation lifecycle and admin flows before they are necessary.
- ❌ Can be layered on top of email/password accounts later.

## References

- [ADR-004: Use Python, FastAPI, React, Next.js, And PostgreSQL For The Initial Stack](0004-python-fastapi-react-nextjs-postgresql-stack.md)
- [ADR-010: Scope The First MVP To Ingestion, Cited Q&A, And Teaching Sessions](0010-scope-first-mvp-to-ingestion-cited-qa-and-teaching-sessions.md)
- FastAPI official documentation via Context7: `/fastapi/fastapi`
- Next.js official documentation via Context7: `/vercel/next.js`
