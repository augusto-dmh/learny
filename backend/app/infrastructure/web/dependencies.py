"""HTTP composition root for the Identity module (task C1).

This module is the single place where concrete adapters (DB repositories, the
Argon2id hasher, the token generator, the system clock) are assembled into the
framework-free application services, and exposed to FastAPI routers as
dependencies. Keeping the wiring here preserves the layering boundary
(ADR-007/009): routers stay thin, and the application/domain layers never import
FastAPI or SQLAlchemy.

Transaction boundary: a request-scoped SQLAlchemy ``Connection`` is opened per
request inside a transaction. The connection is committed when the handler
returns normally and rolled back on any exception, so each request is an atomic
unit of work (the repositories themselves are transaction-agnostic, per B3).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Connection

from app.application.identity import (
    AuthenticateUser,
    AuthorizeOwnership,
    CurrentUser,
    Logout,
    RegisterUser,
)
from app.core.config import Settings, get_settings
from app.domain.entities import Session, User
from app.infrastructure.clock import SystemClock
from app.infrastructure.db.engine import get_engine
from app.infrastructure.db.repositories import (
    SqlAlchemyCredentialRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
)
from app.infrastructure.security.password_hasher import Argon2PasswordHasher
from app.infrastructure.security.tokens import SecretsTokenGenerator

# Process-wide singletons for the stateless adapters. The hasher in particular is
# expensive to construct (Argon2 parameter setup), so it is built once.
_hasher = Argon2PasswordHasher()
_tokens = SecretsTokenGenerator()
_clock = SystemClock()


def get_db_connection(request: Request) -> Iterator[Connection]:
    """Yield a request-scoped connection wrapped in a transaction.

    Commits on success, rolls back if the handler raised. Stored on
    ``request.state`` is unnecessary — each dependency consumer shares the same
    yielded connection because FastAPI caches dependency results per request.
    """
    engine = get_engine()
    conn = engine.connect()
    trans = conn.begin()
    try:
        yield conn
    except Exception:
        trans.rollback()
        raise
    else:
        trans.commit()
    finally:
        conn.close()


DbConnection = Annotated[Connection, Depends(get_db_connection)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_register_user(conn: DbConnection) -> RegisterUser:
    return RegisterUser(
        users=SqlAlchemyUserRepository(conn),
        credentials=SqlAlchemyCredentialRepository(conn),
        sessions=SqlAlchemySessionRepository(conn),
        hasher=_hasher,
        tokens=_tokens,
        clock=_clock,
    )


def get_authenticate_user(conn: DbConnection) -> AuthenticateUser:
    return AuthenticateUser(
        users=SqlAlchemyUserRepository(conn),
        credentials=SqlAlchemyCredentialRepository(conn),
        sessions=SqlAlchemySessionRepository(conn),
        hasher=_hasher,
        tokens=_tokens,
        clock=_clock,
    )


def get_logout(conn: DbConnection) -> Logout:
    return Logout(sessions=SqlAlchemySessionRepository(conn))


def get_current_user_service(conn: DbConnection) -> CurrentUser:
    return CurrentUser(
        users=SqlAlchemyUserRepository(conn),
        sessions=SqlAlchemySessionRepository(conn),
        clock=_clock,
    )


def get_authorize_ownership() -> AuthorizeOwnership:
    return AuthorizeOwnership()


def resolve_current(
    request: Request,
    settings: AppSettings,
    current_user: Annotated[CurrentUser, Depends(get_current_user_service)],
) -> tuple[User, Session]:
    """Resolve the session cookie to (user, session) or raise ``NotAuthenticated``.

    The cookie name is read from settings (``session_cookie_name``) rather than a
    literal ``Cookie`` alias, so the configured name stays authoritative. The
    global exception handler maps ``NotAuthenticated`` to HTTP 401.
    """
    session_token = request.cookies.get(settings.session_cookie_name)
    user, session = current_user(raw_token=session_token)
    return user, session


CurrentPrincipal = Annotated[tuple[User, Session], Depends(resolve_current)]


def get_current_session(principal: CurrentPrincipal) -> Session:
    """FastAPI dependency: the authenticated session row (401 if absent)."""
    return principal[1]


def get_authenticated_user(principal: CurrentPrincipal) -> User:
    """FastAPI dependency: the authenticated user (401 if absent)."""
    return principal[0]
