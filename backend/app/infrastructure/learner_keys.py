"""Whether learner provider keys are on, and access to them (ADR-0033).

One gate for both process assemblies: the API composition root and the worker
tasks. The feature is on only when a KEK is configured AND at least one
declared profile binds a provider AND the hosted lock is not engaged (a
deployment that declares itself hosted without the explicit opt-in). Off, this
returns ``None`` and no credential row is ever read. On, it hands back the
credential repository together with the providers the registry offers, so a
caller can never read a key for a provider no profile binds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from app.infrastructure.db.provider_credentials import SqlAlchemyProviderCredentialRepository
from app.infrastructure.providers import offered_providers
from app.infrastructure.security.secrets_envelope import SecretsEnvelope

if TYPE_CHECKING:
    from sqlalchemy import Connection

    from app.core.config import Settings
    from app.domain.entities import ProviderCredential
    from app.infrastructure.providers import GenerationProfileSettings


def envelope_from_settings(settings: Settings) -> SecretsEnvelope | None:
    """The envelope over the configured KEKs, or ``None`` when no KEK is set."""
    keks = settings.secrets_keks()
    if keks is None:
        return None
    current, previous = keks
    return SecretsEnvelope(current, previous)


@dataclass(frozen=True)
class LearnerKeyAccess:
    """The credential repository, limited to the providers this instance offers."""

    repo: SqlAlchemyProviderCredentialRepository
    offered: tuple[str, ...]

    def credential(self, user_id: UUID, provider: str) -> ProviderCredential | None:
        """The learner's usable credential for an offered ``provider``, else ``None``."""
        if provider not in self.offered:
            return None
        return self.repo.get(user_id, provider)


def learner_key_access(
    conn: Connection,
    envelope: SecretsEnvelope | None,
    profiles: tuple[GenerationProfileSettings, ...],
    *,
    hosted_lock: bool = False,
) -> LearnerKeyAccess | None:
    """Access to learner keys on ``conn``, or ``None`` when the feature is off.

    ``profiles`` is the declared registry. The API passes its resolved registry
    and the worker the declared list; they offer the same providers, because
    resolution only adds the legacy seed when nothing is declared, and the seed
    never binds a provider.

    ``hosted_lock`` is the hosted-instance gate: a deployment that declares
    itself hosted and has not taken the explicit opt-in reads as feature-off
    here — the one gate both assemblies resolve key access through, so no
    credential row is read anywhere (API routes and worker tasks alike).
    """
    if hosted_lock:
        return None
    offered = offered_providers(profiles)
    if envelope is None or not offered:
        return None
    return LearnerKeyAccess(
        repo=SqlAlchemyProviderCredentialRepository(conn, envelope), offered=offered
    )
