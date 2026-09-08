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
- ``RateLimited`` → one same-entry retry after a bounded backoff, then the next
  entry — the backoff is the provider's ``retry_after`` hint when it reports
  one (capped so a turn's latency stays bounded), or the router's default wait
  when it does not; an immediate re-entry would just re-earn the 429;
- ``RequestRejected`` → only an entry whose adapter builds a **different**
  request shape (another kind) may be tried — the same shape would earn the
  same rejection;
- an exhausted chain re-raises the last translated error, so the application's
  ``AnswerGenerationFailed`` envelope is exactly today's (TAX-03); an
  unrecognized failure propagates unchanged, identity-preserved.

A grounded mode routes only over entries enabled for it (ask/teach flags,
ROUTE-03): an empty eligible chain raises before any provider is touched, the
honest failure the application already maps to its error envelope. Streams obey
the same policy but may fail over only **before the first delta** (ROUTE-04):
once a delta is out the stream commits, and a post-delta error surfaces exactly
as a single adapter's would — no rewind, no second ``AnswerCompleted``. The
not-found completion is an outcome, not a failure: it is forwarded stamped and
terminal, so the sentinel can never ride a fail-over into a silently better
answer.

Imports stay inside infrastructure and SDK-free: this module depends on the
providers package (taxonomy + profile settings) and the domain only.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from app.domain.entities import (
    MODE_ANSWER,
    MODE_TEACH,
    AnswerCompleted,
    AnswerStreamEvent,
    GeneratedAnswer,
)
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


#: The ceiling on the wait before a same-entry retry, whatever the provider's
#: ``retry_after`` hint says: the cap is the turn's latency bound (ROUTE-02).
_RATE_RETRY_CAP_S = 5.0


def _backoff_seconds(error: RateLimited, default: float) -> float:
    """The bounded wait before the throttled entry is re-entered (ROUTE-02).

    The provider's own ``retry_after`` hint wins when an adapter carried one —
    a near-immediate retry would just re-earn the 429 — capped at
    :data:`_RATE_RETRY_CAP_S` so a provider asking for minutes cannot hold a
    reader's turn hostage. Without a hint, the router's default backoff applies.
    """
    if error.retry_after is None:
        return default
    return min(error.retry_after, _RATE_RETRY_CAP_S)


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


def _eligible_entries(chain: tuple[ChainEntry, ...], mode: str) -> tuple[ChainEntry, ...]:
    """The entries enabled for ``mode``'s grounded path, in chain order (ROUTE-03).

    Ask turns route only over ``ask_enabled`` profiles, teach turns only over
    ``teach_enabled`` ones — the application's teach carve-outs sit above this
    and are unchanged. An unknown mode is a programming error, not a routing
    decision, and raises.
    """
    if mode == MODE_TEACH:
        return tuple(entry for entry in chain if entry.profile.teach_enabled)
    if mode == MODE_ANSWER:
        return tuple(entry for entry in chain if entry.profile.ask_enabled)
    raise ValueError(f"unknown conversation mode: {mode!r}")


class RoutingGenerationAdapter:
    """``GenerationPort`` over the ordered profile chain — the policy's only home.

    Built at the composition root from the settings-declared registry
    (``build_generation_chain``); ``model`` reads the primary profile's identity
    so the not-found short-circuit can name a model without any provider touch
    (QA-04). Buffered fallback walks the chain per the module policy and stamps
    whichever entry served onto the returned answer. ``rate_retry_delay`` is the
    default backoff before a same-entry retry when the provider reported no
    ``retry_after`` hint — injectable so tests stay offline (the cap on the hint
    is not negotiable; the default is a composition choice).
    """

    def __init__(self, chain: tuple[ChainEntry, ...], *, rate_retry_delay: float = 1.0) -> None:
        if not chain:
            raise ValueError("a generation chain needs at least one profile")
        self._chain = chain
        self._rate_retry_delay = rate_retry_delay

    @property
    def model(self) -> str:
        """The primary profile's model identity, readable without a call (QA-04)."""
        return self._chain[0].adapter.model

    def _require_eligible(self, mode: str) -> tuple[ChainEntry, ...]:
        """The mode-eligible chain, or the honest empty-chain failure (ROUTE-03).

        A mode with no eligible profile raises before any provider is touched:
        the application maps the raise to its existing
        ``AnswerGenerationFailed`` envelope, so the turn fails honest instead of
        being silently served by a degraded profile.
        """
        eligible = _eligible_entries(self._chain, mode)
        if not eligible:
            raise RuntimeError(
                f"no generation profile is enabled for mode '{mode}': "
                "the turn fails honest rather than silently degrading"
            )
        return eligible

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
        """Serve from the first eligible entry that can, stamping the serving profile."""
        kwargs: dict[str, object] = {
            "message": message,
            "mode": mode,
            "evidence": evidence,
            "history": history,
            "target_section_path": target_section_path,
            "tutor_phase": tutor_phase,
            "hint_level": hint_level,
        }
        eligible = self._require_eligible(mode)
        retried: set[int] = set()
        index = 0
        while True:
            entry = eligible[index]
            try:
                answer = entry.adapter.generate(**kwargs)  # type: ignore[arg-type]
            except Exception as error:
                nxt = _next_index(eligible, index, error, retried)
                if nxt is None:
                    raise
                if nxt == index and isinstance(error, RateLimited):
                    # The only same-entry re-entry is the RateLimited retry:
                    # wait the bounded backoff first, or the retry re-earns
                    # the 429 it is meant to survive.
                    time.sleep(_backoff_seconds(error, self._rate_retry_delay))
                index = nxt
                continue
            return replace(answer, profile_id=entry.profile.id)

    def generate_stream(
        self,
        *,
        message: str,
        mode: str,
        evidence: Sequence[Evidence],
        history: Sequence[HistoryTurn] = (),
        target_section_path: tuple[str, ...] | None = None,
        tutor_phase: str | None = None,
        hint_level: str | None = None,
    ) -> Iterator[AnswerStreamEvent]:
        """Stream from the first eligible entry that can; commit at the first delta.

        The pre-delta window obeys the buffered policy exactly, so a candidate
        that fails before speaking costs the reader nothing. Once a delta is out
        the stream is committed (ROUTE-04): any error propagates immediately and
        unchanged — the consumer's exactly-one-terminal contract is never broken
        by a fail-over. The completed event's answer carries the serving
        profile's stamp (AD-344), and closing this iterator early closes the
        candidate's stream, so a client disconnect cancels the underlying
        generation.
        """
        eligible = self._require_eligible(mode)
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
            entry = eligible[index]
            stream = entry.adapter.generate_stream(**kwargs)  # type: ignore[arg-type]
            committed = False
            try:
                for event in stream:
                    committed = True  # anything emitted commits the stream
                    if isinstance(event, AnswerCompleted):
                        yield AnswerCompleted(
                            answer=replace(event.answer, profile_id=entry.profile.id)
                        )
                    else:
                        yield event
                return
            except Exception as error:
                if committed:
                    raise
                nxt = _next_index(eligible, index, error, retried)
                if nxt is None:
                    raise
                if nxt == index and isinstance(error, RateLimited):
                    # Pre-delta the stream obeys the buffered policy exactly,
                    # backoff included.
                    time.sleep(_backoff_seconds(error, self._rate_retry_delay))
                index = nxt
            finally:
                close = getattr(stream, "close", None)
                if close is not None:
                    close()
