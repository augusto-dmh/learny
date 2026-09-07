"""RoutingGenerationAdapter — one ``GenerationPort`` over the profile chain.

The router implements the generation port itself, so the application services
keep calling the same seam and never learn routing exists (AD-338): all fallback
policy lives here, the port gains no members, and the only thing a caller sees
beyond today's contract is the serving profile's id stamped on the
:class:`~app.domain.entities.GeneratedAnswer` it gets back (ROUTE-08/AD-344) —
the one carrier the debit paths price from.

Policy (ROUTE-02 / AD-337), walked over the ordered chain:

- the first entry that can serve, serves;
- ``Timeout`` / ``ProviderUnavailable`` → the next entry;
- ``RateLimited`` → one same-entry retry, then the next entry;
- ``RequestRejected`` → only an entry whose adapter builds a **different**
  request shape (another kind) may be tried — the same shape would earn the
  same rejection;
- an exhausted chain re-raises the last translated error, so the application's
  ``AnswerGenerationFailed`` envelope is exactly today's (TAX-03); an
  unrecognized failure propagates unchanged, identity-preserved.

Imports stay inside infrastructure and SDK-free: this module depends on the
providers package (taxonomy + profile settings) and the domain only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from app.domain.entities import GeneratedAnswer
from app.infrastructure.providers import (
    ProviderUnavailable,
    RateLimited,
    RequestRejected,
    Timeout,
)

if TYPE_CHECKING:
    from app.domain.entities import Evidence, HistoryTurn
    from app.domain.ports import GenerationPort
    from app.infrastructure.providers.profiles import GenerationProfileSettings


@dataclass(frozen=True)
class ChainEntry:
    """One built sub-adapter together with the profile that configures it.

    The adapter is what serves; the profile carries what the router's policy and
    the attribution stamp need: the id, the adapter kind (the request-shape test
    a rejection cross is gated on), and the grounded-mode eligibility flags.
    """

    adapter: GenerationPort
    profile: GenerationProfileSettings


def _next_index(
    chain: tuple[ChainEntry, ...],
    index: int,
    error: Exception,
    retried: set[int],
) -> int | None:
    """Return the chain index the policy walks to after ``error``, or ``None``.

    ``None`` means the walk is over and ``error`` — by then the last translated
    failure — is re-raised as-is. A ``RateLimited`` entry is retried at most
    once per turn: ``retried`` carries the indices whose one retry was spent.
    """
    last = len(chain) - 1
    if isinstance(error, (Timeout, ProviderUnavailable)):
        return index + 1 if index < last else None
    if isinstance(error, RateLimited):
        if index not in retried:
            retried.add(index)
            return index
        return index + 1 if index < last else None
    if isinstance(error, RequestRejected):
        candidate = index + 1
        while candidate <= last:
            if chain[candidate].profile.kind != chain[index].profile.kind:
                return candidate
            candidate += 1
        return None
    return None  # unrecognized — propagate unchanged, no fail-over


class RoutingGenerationAdapter:
    """``GenerationPort`` over the ordered profile chain — the policy's only home.

    Built at the composition root from the settings-declared registry
    (``build_generation_chain``); ``model`` reads the primary profile's identity
    so the not-found short-circuit can name a model without any provider touch
    (QA-04). Buffered fallback walks the chain per the module policy and stamps
    whichever entry served onto the returned answer.
    """

    def __init__(self, chain: tuple[ChainEntry, ...]) -> None:
        if not chain:
            raise ValueError("a generation chain needs at least one profile")
        self._chain = chain

    @property
    def model(self) -> str:
        """The primary profile's model identity, readable without a call (QA-04)."""
        return self._chain[0].adapter.model

    def generate(
        self,
        *,
        message: str,
        mode: str,
        evidence: Sequence[Evidence],
        history: Sequence[HistoryTurn] = (),
        target_section_path: tuple[str, ...] | None = None,
        tutor_phase: str | None = None,
        hint_level: str | None = None,
    ) -> GeneratedAnswer:
        """Serve from the first entry that can, stamping the serving profile."""
        kwargs: dict[str, object] = {
            "message": message,
            "mode": mode,
            "evidence": evidence,
            "history": history,
            "target_section_path": target_section_path,
            "tutor_phase": tutor_phase,
            "hint_level": hint_level,
        }
        retried: set[int] = set()
        index = 0
        while True:
            entry = self._chain[index]
            try:
                answer = entry.adapter.generate(**kwargs)  # type: ignore[arg-type]
            except Exception as error:
                nxt = _next_index(self._chain, index, error, retried)
                if nxt is None:
                    raise
                index = nxt
                continue
            return replace(answer, profile_id=entry.profile.id)
