"""B4 gate — identity application services with fake ports.

Covers register/login/logout/current-user happy + failure paths, uniform login
failure (no enumeration), credential rehash-on-login, and the ownership
authorize allow/deny primitive (FR-AUTH-008).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.application.activation import RecordActivation
from app.application.errors import (
    AccountDeleteFailed,
    EmailAlreadyExists,
    InvalidCredentials,
    InviteRequired,
    NotAuthenticated,
    NotAuthorized,
    ValidationError,
)
from app.application.media import media_object_key
from app.application.identity import (
    SESSION_TOUCH_INTERVAL,
    AuthenticateUser,
    AuthorizeOwnership,
    CurrentUser,
    DeleteAccount,
    Logout,
    RegisterUser,
)
from app.application.validation import SAMPLE_OPERATOR_EMAIL
from app.domain.entities import CorpusSectionRecord, ParsedSection, Source, User
from tests.fakes import (
    FakeActivationEventRepository,
    FakeClock,
    FakeCorpusRepository,
    FakeCredentialRepository,
    FakeInviteRepository,
    FakePasswordHasher,
    FakeSessionRepository,
    FakeSourceRepository,
    FakeStorage,
    FakeUserRepository,
    SequentialTokenGenerator,
    UnavailableStorage,
)

VALID_PASSWORD = "correct horse battery"  # >= 12 chars


@pytest.fixture
def ports():
    return {
        "users": FakeUserRepository(),
        "credentials": FakeCredentialRepository(),
        "sessions": FakeSessionRepository(),
        "hasher": FakePasswordHasher(),
        "tokens": SequentialTokenGenerator(),
        "clock": FakeClock(),
    }


def _record(ports) -> RecordActivation:  # noqa: ANN001
    return RecordActivation(
        activations=FakeActivationEventRepository(),
        clock=ports["clock"],
    )


def _register(ports, email="user@example.com", password=VALID_PASSWORD):  # noqa: ANN001
    return RegisterUser(**ports, record_activation=_record(ports))(email=email, password=password)


# ---- RegisterUser ---------------------------------------------------------


def test_register_creates_user_credential_and_session(ports) -> None:
    result = _register(ports)
    assert result.user.email == "user@example.com"
    # Password is hashed, not stored plaintext.
    cred = ports["credentials"].get_by_user_id(result.user.id)
    assert cred is not None and cred.password_hash == f"hash::{VALID_PASSWORD}"
    # Session issued with a raw token + a distinct CSRF token.
    assert result.issued.raw_token == "token-1"
    assert result.issued.session.csrf_token == "token-2"


def test_register_normalizes_email(ports) -> None:
    result = _register(ports, email="  USER@Example.COM ")
    assert result.user.email == "user@example.com"


def test_register_rejects_duplicate_email(ports) -> None:
    _register(ports)
    with pytest.raises(EmailAlreadyExists):
        _register(ports)


def test_register_rejects_bad_email(ports) -> None:
    with pytest.raises(ValidationError):
        _register(ports, email="not-an-email")


def test_register_rejects_sample_operator_email(ports) -> None:
    with pytest.raises(ValidationError):
        _register(ports, email=SAMPLE_OPERATOR_EMAIL)


def test_register_rejects_weak_password(ports) -> None:
    with pytest.raises(ValidationError):
        _register(ports, password="short")


# ---- RegisterUser disposable + ToS rails (DOOR-23/24/25) -------------------


def test_register_rejects_listed_disposable_domain(ports) -> None:
    with pytest.raises(ValidationError):
        _register(ports, email="throwaway@mailinator.com")
    assert ports["users"].get_by_email("throwaway@mailinator.com") is None


def test_register_rejecting_disposable_matches_malformed_email_copy(ports) -> None:
    # The generic-copy rule (DOOR-23): the disposable refusal is the *same*
    # message a malformed address raises — no hint that disposability fired.
    with pytest.raises(ValidationError) as disposable:
        _register(ports, email="throwaway@mailinator.com")
    with pytest.raises(ValidationError) as malformed:
        _register(ports, email="not-an-email")
    assert str(disposable.value) == str(malformed.value) == "Invalid email address."


def test_register_allows_documented_alias_domains(ports) -> None:
    # duck.com is a documented privacy alias, never rejected as disposable (DOOR-24).
    result = _register(ports, email="reader@duck.com")
    assert result.user.email == "reader@duck.com"


def test_register_rejects_missing_tos(ports) -> None:
    with pytest.raises(ValidationError):
        RegisterUser(**ports, record_activation=_record(ports))(
            email="noservice@example.com", password=VALID_PASSWORD, accepted_tos=False
        )
    assert ports["users"].get_by_email("noservice@example.com") is None
    assert ports["sessions"].get_by_raw_token("token-1") is None


def test_register_stamps_accepted_tos_at(ports) -> None:
    result = _register(ports)
    assert result.user.accepted_tos_at == ports["clock"].now()


# ---- RegisterUser invite gate (DOOR-20/21/22/26) ---------------------------


def _register_gated(
    ports,  # noqa: ANN001
    invites: FakeInviteRepository,
    email="invited@example.com",
    password=VALID_PASSWORD,
    invite_code="letmein",
):
    return RegisterUser(**ports, record_activation=_record(ports), invites=invites)(
        email=email, password=password, invite_code=invite_code
    )


def test_register_with_valid_invite_consumes_exactly_one_use(ports) -> None:
    invites = FakeInviteRepository(codes={"letmein": 2})
    result = _register_gated(ports, invites)

    # One use burned, the other still there; the invited register still mints
    # its session immediately (DOOR-21 / AD-327).
    assert invites.consumed == ["letmein"]
    assert invites.remaining_uses("letmein") == 1
    assert result.issued.raw_token == "token-1"
    assert ports["users"].get_by_email("invited@example.com") is not None


def test_register_without_invite_code_is_refused_when_gated(ports) -> None:
    invites = FakeInviteRepository(codes={"letmein": 1})
    with pytest.raises(InviteRequired):
        _register_gated(ports, invites, invite_code=None)

    # No user row and no session survive a rejected register (DOOR-20).
    assert ports["users"].get_by_email("invited@example.com") is None
    assert ports["sessions"].get_by_raw_token("token-1") is None
    assert invites.consumed == []


def test_register_with_unknown_code_is_refused_and_burns_nothing(ports) -> None:
    invites = FakeInviteRepository(codes={"letmein": 1})
    with pytest.raises(InviteRequired):
        _register_gated(ports, invites, invite_code="not-a-code")

    assert ports["users"].get_by_email("invited@example.com") is None
    assert ports["sessions"].get_by_raw_token("token-1") is None
    assert invites.consumed == []
    assert invites.remaining_uses("letmein") == 1


def test_register_with_exhausted_code_is_refused(ports) -> None:
    invites = FakeInviteRepository(codes={"spent": 0})
    with pytest.raises(InviteRequired):
        _register_gated(ports, invites, invite_code="spent")

    assert ports["users"].get_by_email("invited@example.com") is None
    assert ports["sessions"].get_by_raw_token("token-1") is None


def test_register_with_expired_code_is_refused(ports) -> None:
    # The code expired one minute before the clock's "now".
    invites = FakeInviteRepository(
        codes={"stale": 3},
        expires_at={"stale": ports["clock"].now() - timedelta(minutes=1)},
    )
    with pytest.raises(InviteRequired):
        _register_gated(ports, invites, invite_code="stale")

    assert ports["users"].get_by_email("invited@example.com") is None
    assert ports["sessions"].get_by_raw_token("token-1") is None
    assert invites.remaining_uses("stale") == 3


def test_register_ignores_invite_code_when_no_gate_is_wired(ports) -> None:
    # Flag off (the default wiring passes no gate): a code in the body changes
    # nothing and a register without one still works (DOOR-26).
    result = RegisterUser(**ports, record_activation=_record(ports))(
        email="ungated@example.com", password=VALID_PASSWORD
    )
    assert result.user.email == "ungated@example.com"
    assert result.issued.raw_token == "token-1"


# ---- AuthenticateUser -----------------------------------------------------


def test_login_succeeds_with_correct_password(ports) -> None:
    _register(ports)
    result = AuthenticateUser(**ports)(email="user@example.com", password=VALID_PASSWORD)
    assert result.user.email == "user@example.com"
    assert result.issued.raw_token  # a session was started


def test_login_wrong_password_is_invalid_credentials(ports) -> None:
    _register(ports)
    with pytest.raises(InvalidCredentials):
        AuthenticateUser(**ports)(email="user@example.com", password="wrong-password-xx")


def test_login_unknown_email_is_invalid_credentials(ports) -> None:
    # Uniform failure: same error type whether or not the email exists.
    with pytest.raises(InvalidCredentials):
        AuthenticateUser(**ports)(email="ghost@example.com", password=VALID_PASSWORD)


def test_login_rehashes_when_params_outdated(ports) -> None:
    registered = _register(ports)
    registration_time = registered.user.created_at
    # Advance time so a rehash writes a distinguishable ``updated_at``.
    ports["clock"].advance(timedelta(minutes=5))
    ports["hasher"] = FakePasswordHasher(needs_rehash=True)

    AuthenticateUser(**ports)(email="user@example.com", password=VALID_PASSWORD)

    cred = ports["credentials"].get_by_user_id(registered.user.id)
    # The upgrade branch actually ran: ``updated_at`` moved to "now", which only
    # happens when ``credentials.update()`` is invoked on the rehash path. A
    # bare "credential still present" assertion would pass even if it never ran.
    assert cred is not None
    assert cred.updated_at == ports["clock"].now()
    assert cred.updated_at != registration_time


# ---- Logout ---------------------------------------------------------------


def test_logout_revokes_session(ports) -> None:
    result = _register(ports)
    Logout(sessions=ports["sessions"])(session_id=result.issued.session.id)
    assert ports["sessions"].get_by_raw_token(result.issued.raw_token) is None


# ---- CurrentUser ----------------------------------------------------------


def test_current_user_resolves_token(ports) -> None:
    result = _register(ports)
    user, session = CurrentUser(
        users=ports["users"], sessions=ports["sessions"], clock=ports["clock"]
    )(raw_token=result.issued.raw_token)
    assert user.id == result.user.id
    assert session.id == result.issued.session.id


def test_current_user_skips_touch_within_interval(ports) -> None:
    result = _register(ports)
    original_last_seen = result.issued.session.last_seen_at
    # Advance less than the touch interval: the read must NOT write last_seen_at.
    ports["clock"].advance(SESSION_TOUCH_INTERVAL - timedelta(seconds=1))
    CurrentUser(users=ports["users"], sessions=ports["sessions"], clock=ports["clock"])(
        raw_token=result.issued.raw_token
    )
    stored = ports["sessions"].get_by_raw_token(result.issued.raw_token)
    assert stored.last_seen_at == original_last_seen


def test_current_user_touches_once_interval_elapsed(ports) -> None:
    result = _register(ports)
    # Advance past the touch interval: the read refreshes last_seen_at to now.
    ports["clock"].advance(SESSION_TOUCH_INTERVAL + timedelta(seconds=1))
    CurrentUser(users=ports["users"], sessions=ports["sessions"], clock=ports["clock"])(
        raw_token=result.issued.raw_token
    )
    stored = ports["sessions"].get_by_raw_token(result.issued.raw_token)
    assert stored.last_seen_at == ports["clock"].now()


def test_current_user_no_token_is_unauthenticated(ports) -> None:
    with pytest.raises(NotAuthenticated):
        CurrentUser(users=ports["users"], sessions=ports["sessions"], clock=ports["clock"])(
            raw_token=None
        )


def test_current_user_unknown_token_is_unauthenticated(ports) -> None:
    with pytest.raises(NotAuthenticated):
        CurrentUser(users=ports["users"], sessions=ports["sessions"], clock=ports["clock"])(
            raw_token="nope"
        )


def test_current_user_expired_token_is_unauthenticated_and_revoked(ports) -> None:
    clock = FakeClock()
    ports["clock"] = clock
    # Short-lived session so we can expire it deterministically.
    result = RegisterUser(
        **ports, record_activation=_record(ports), session_ttl=timedelta(minutes=5)
    )(email="user@example.com", password=VALID_PASSWORD)
    clock.advance(timedelta(minutes=10))
    with pytest.raises(NotAuthenticated):
        CurrentUser(users=ports["users"], sessions=ports["sessions"], clock=clock)(
            raw_token=result.issued.raw_token
        )
    # Expired session revoked on resolution.
    assert ports["sessions"].get_by_raw_token(result.issued.raw_token) is None


# ---- AuthorizeOwnership ---------------------------------------------------


def test_authorize_allows_owner() -> None:
    user = User(id=uuid4(), email="o@example.com", created_at=FakeClock().now())
    authorize = AuthorizeOwnership()
    authorize(user=user, owner_id=user.id)  # no raise
    assert authorize.is_owner(user=user, owner_id=user.id) is True


def test_authorize_denies_non_owner() -> None:
    user = User(id=uuid4(), email="a@example.com", created_at=FakeClock().now())
    other_owner = uuid4()
    authorize = AuthorizeOwnership()
    with pytest.raises(NotAuthorized):
        authorize(user=user, owner_id=other_owner)
    assert authorize.is_owner(user=user, owner_id=other_owner) is False


# ---- DeleteAccount (DOOR-30..33) -------------------------------------------


def _source(user_id: UUID, *, is_sample: bool = False) -> Source:
    now = datetime(2026, 9, 6, tzinfo=UTC)
    return Source(
        id=uuid4(),
        user_id=user_id,
        title="A Book",
        filename="a.epub",
        content_type="application/epub+zip",
        byte_size=10,
        checksum="a" * 64,
        object_key=f"sources/{user_id}/{uuid4()}.epub",
        status="ready",
        created_at=now,
        updated_at=now,
        is_sample=is_sample,
    )


def _corpus_with_media(source: Source, digests: list[str]) -> FakeCorpusRepository:
    """A corpus whose single section references the given media digests."""
    markdown = " ".join(f"![fig](/api/sources/{source.id}/media/{digest})" for digest in digests)
    corpus = FakeCorpusRepository()
    corpus.replace(
        source.id,
        title=None,
        authors=[],
        language=None,
        schema_version=1,
        sections=(
            CorpusSectionRecord(
                section=ParsedSection(
                    position=0,
                    title="S",
                    depth=0,
                    section_path=("S",),
                    anchor="s.xhtml",
                    blocks=(),
                ),
                markdown=markdown,
                chunks=(),
            ),
        ),
    )
    return corpus


def _delete_account(ports, *, sources, corpus, storage):  # noqa: ANN001
    return DeleteAccount(users=ports["users"], sources=sources, corpus=corpus, storage=storage)


def test_delete_account_removes_owned_objects_then_the_user(ports) -> None:
    result = _register(ports)
    sources = FakeSourceRepository()
    source = _source(result.user.id)
    sources.add(source)
    storage = FakeStorage()
    storage.put_object(source.object_key, b"book-bytes", content_type="application/epub+zip")

    _delete_account(ports, sources=sources, corpus=FakeCorpusRepository(), storage=storage)(
        user=result.user
    )

    # The user row is gone. (Child-row cascades are Postgres semantics, covered
    # against the real DB at the web layer — DOOR-31.)
    assert ports["users"].get_by_id(result.user.id) is None
    # The derived object key was deleted from storage.
    assert source.object_key not in storage.objects


def test_delete_account_deletes_media_keys_derived_from_corpus_markdown(ports) -> None:
    result = _register(ports)
    sources = FakeSourceRepository()
    source = _source(result.user.id)
    sources.add(source)
    # The same figure digest referenced twice must yield exactly one delete.
    repeated, other = "b" * 64, "c" * 64
    corpus = _corpus_with_media(source, [repeated, repeated, other])
    storage = FakeStorage()
    # Expected keys come from the ONE shared builder the deletion path itself
    # uses — if the shapes ever drift, this test cannot pass by accident.
    media_keys = [
        media_object_key(user_id=result.user.id, source_id=source.id, digest=digest)
        for digest in (repeated, other)
    ]
    for key in [source.object_key, *media_keys]:
        storage.put_object(key, b"bytes", content_type="image/webp")

    _delete_account(ports, sources=sources, corpus=corpus, storage=storage)(user=result.user)

    assert source.object_key not in storage.objects
    for key in media_keys:
        assert key not in storage.objects
    # Deduplicated: each derived key was deleted exactly once.
    assert sorted(storage.deleted_keys) == sorted([source.object_key, *media_keys])


def test_delete_account_never_touches_sample_or_foreign_keys(ports) -> None:
    owner = _register(ports)
    other = _register(ports, email="other@example.com")
    sources = FakeSourceRepository()
    owned = _source(owner.user.id)
    foreign = _source(other.user.id)
    sample = _source(other.user.id, is_sample=True)  # visible to `owner`, not owned
    for source in (owned, foreign, sample):
        sources.add(source)
    storage = FakeStorage()
    for source in (owned, foreign, sample):
        storage.put_object(source.object_key, b"bytes", content_type="application/epub+zip")

    _delete_account(ports, sources=sources, corpus=FakeCorpusRepository(), storage=storage)(
        user=owner.user
    )

    assert ports["users"].get_by_id(owner.user.id) is None
    assert ports["users"].get_by_id(other.user.id) is not None
    assert owned.object_key not in storage.objects
    # DOOR-33: only keys derived from the caller's owned sources are deleted —
    # the shared sample and the other user's file survive untouched.
    assert sample.object_key in storage.objects
    assert foreign.object_key in storage.objects


def test_storage_failure_leaves_the_user_row(ports) -> None:
    result = _register(ports)
    sources = FakeSourceRepository()
    source = _source(result.user.id)
    sources.add(source)  # an owned key so a storage delete is actually attempted

    with pytest.raises(AccountDeleteFailed):
        _delete_account(
            ports,
            sources=sources,
            corpus=FakeCorpusRepository(),
            storage=UnavailableStorage(),
        )(user=result.user)

    # Fail closed: the account is fully intact after the failed erase.
    assert ports["users"].get_by_id(result.user.id) is not None


def test_partial_storage_failure_deletes_no_user_row(ports) -> None:
    from app.application.errors import StorageUnavailable

    class _OutageAfterFirstDelete(FakeStorage):
        """Deletes the first object, then the outage hits."""

        def __init__(self, inner: FakeStorage) -> None:
            self._inner = inner
            self.deletes = 0

        def put_object(self, key: str, data: bytes, *, content_type: str) -> None:
            self._inner.put_object(key, data, content_type=content_type)

        def get_object(self, key: str) -> bytes:
            return self._inner.get_object(key)

        def delete_object(self, key: str) -> None:
            self.deletes += 1
            if self.deletes > 1:
                raise StorageUnavailable("storage down mid-delete")
            self._inner.delete_object(key)

    result = _register(ports)
    sources = FakeSourceRepository()
    first, second = _source(result.user.id), _source(result.user.id)
    sources.add(first)
    sources.add(second)
    storage = FakeStorage()
    for source in (first, second):
        storage.put_object(source.object_key, b"bytes", content_type="application/epub+zip")

    with pytest.raises(AccountDeleteFailed):
        _delete_account(
            ports,
            sources=sources,
            corpus=FakeCorpusRepository(),
            storage=_OutageAfterFirstDelete(storage),
        )(user=result.user)

    # The first object may already be gone (deletes are idempotent on retry),
    # but the fail-closed guarantee holds: the user row survives.
    assert first.object_key not in storage.objects
    assert second.object_key in storage.objects
    assert ports["users"].get_by_id(result.user.id) is not None
