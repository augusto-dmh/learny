"""Daily AI spend budget (RFC-0007 Cycle F; design §Components, DailyBudget).

Framework-free check-and-debit over the ``ai_spend_days`` ledger. The
check-before-call assertion runs on every generation surface after authorization and
*before* the provider port is touched, so an exhausted day refuses with nothing spent
and nothing called; the debit runs after a successful call and records the usage the
adapter actually reported. This is the letter's ledger — a daily table plus integer
counters — not Cycle G's thinking-token ``SpendPort``.

The UTC day comes from the injected :class:`~app.domain.ports.Clock`, never from a
bare wall-clock read, so the day boundary is deterministic under tests and honest in
production (``Clock.now`` is timezone-aware UTC).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.application.errors import AiPaused, DailyBudgetExhausted
from app.domain.entities import TokenUsage
from app.domain.ports import AiSpendDayRepository, Clock

#: Budget kinds (design §Components). ``generation`` is a plain provider call with no
#: free-tier counter of its own; ``ask`` / ``teach_start`` carry the free-tier integer
#: counters; ``embed`` is an embedding-producing call. The honest copy is one class
#: for every kind: whichever cap trips first, the answer is come back tomorrow.
KIND_ASK = "ask"
KIND_TEACH_START = "teach_start"
KIND_GENERATION = "generation"
KIND_EMBED = "embed"

#: 1 USD expressed in micros — the ledger's unit, so accumulation stays integral.
MICROS_PER_USD = 1_000_000

#: The honest come-back-tomorrow copy (spec §Assumptions, "Honest copy"). One class
#: for every cap: naming which cap tripped, or what a call costs, would help a
#: farmer tune against the rails instead of telling a learner when to come back.
EXHAUSTED_COPY = (
    "You've reached today's AI limit. Your library and reviews still work, "
    "and the limit resets at 00:00 UTC."
)

#: The honest operator-pause copy (DOOR-12): the AI is off on purpose, and the
#: parts of the product that never call a provider are still fine.
PAUSED_COPY = "AI is paused right now. Your library and reviews still work."

#: Derived cache-price factors applied to the input price when a catalog does not
#: name its own (design §Tech Decisions — Anthropic Sonnet actuals). The profile
#: registry's legacy seed derives the same pair from the same factors; this copy
#: exists because the application layer cannot import the providers package.
_CACHE_READ_DEFAULT_FACTOR = 0.1
_CACHE_CREATION_DEFAULT_FACTOR = 1.25


class ServingProfile(Protocol):
    """What a debit needs from a resolved serving profile: its catalog key.

    Structural on purpose: the shared registry resolver the composition root
    wires returns the providers package's profile settings, and this layer
    depends on the ``id`` attribute alone — never on the concrete type.
    """

    id: str


def usd_to_micros(usd: float) -> int:
    """Convert an operator's USD amount to whole ledger micros (rounded)."""
    return int(round(usd * MICROS_PER_USD))


@dataclass(frozen=True)
class TokenPrices:
    """The operator's price catalog in USD micros per million tokens.

    The cache prices are profile-overridable; omitted, they take the derived
    defaults (read 0.1× input, creation 1.25× input — design §Tech Decisions),
    so the pre-registry global ``price_*`` pair keeps pricing honest for a
    cache-reporting adapter without new operator knobs. ``__post_init__`` fills
    the derived values once at construction; they are plain ints afterwards.
    """

    input_micros_per_million: int
    output_micros_per_million: int
    embed_micros_per_million: int
    cache_read_micros_per_million: int = -1  # derived 0.1 × input when omitted
    cache_creation_micros_per_million: int = -1  # derived 1.25 × input when omitted

    def __post_init__(self) -> None:
        if self.cache_read_micros_per_million < 0:
            object.__setattr__(
                self,
                "cache_read_micros_per_million",
                int(round(self.input_micros_per_million * _CACHE_READ_DEFAULT_FACTOR)),
            )
        if self.cache_creation_micros_per_million < 0:
            object.__setattr__(
                self,
                "cache_creation_micros_per_million",
                int(round(self.input_micros_per_million * _CACHE_CREATION_DEFAULT_FACTOR)),
            )


class DailyBudget:
    """Assert remaining daily budget before a provider call; debit after success.

    ``assert_generation`` reads the caller's ledger row for the current UTC day and
    raises :class:`~app.application.errors.DailyBudgetExhausted` when the day's spend
    is at or above the cap — the caller is refused before anything is retrieved,
    generated, or written. ``record`` adds a successful call's USD (usage × prices)
    to the day's row atomically; an adapter that reports no usage (the deterministic
    local ones) debits 0. A day with no row simply has not spent anything.
    """

    def __init__(
        self,
        *,
        repo: AiSpendDayRepository,
        clock: Clock,
        daily_cap_micros: int,
        prices: TokenPrices,
        ask_daily_cap: int,
        teach_start_daily_cap: int,
        ai_paused: bool = False,
        profile_catalogs: dict[str, TokenPrices] | None = None,
        resolve_serving_profile: Callable[[str | None], ServingProfile | None] | None = None,
    ) -> None:
        self._repo = repo
        self._clock = clock
        self._daily_cap_micros = daily_cap_micros
        self._prices = prices
        self._ask_daily_cap = ask_daily_cap
        self._teach_start_daily_cap = teach_start_daily_cap
        self._ai_paused = ai_paused
        self._profile_catalogs = profile_catalogs or {}
        self._resolve_serving_profile = resolve_serving_profile

    def assert_generation(self, user_id: UUID, *, kind: str) -> None:
        """Refuse the call unless the operator's pause and the caller's day allow it.

        The kill switch short-circuits *before* the ledger is read: a paused
        process refuses everything with the pause copy, whatever the caller has
        spent. Then the USD cap governs every kind and the free-tier integer caps
        govern their own kinds (``ask``: so many turns a day, ``teach_start``: so
        many session starts). Whichever cap trips first refuses with the same
        honest copy — a learner is never told which meter was the one.
        """
        if self._ai_paused:
            raise AiPaused(PAUSED_COPY)
        row = self._repo.get_for_day(user_id, self._clock.now().date())
        if row is None:
            return
        if row.usd_micros >= self._daily_cap_micros:
            raise DailyBudgetExhausted(EXHAUSTED_COPY)
        if kind == KIND_ASK and row.ask_count >= self._ask_daily_cap:
            raise DailyBudgetExhausted(EXHAUSTED_COPY)
        if kind == KIND_TEACH_START and row.teach_starts >= self._teach_start_daily_cap:
            raise DailyBudgetExhausted(EXHAUSTED_COPY)

    def usage_micros(self, usage: TokenUsage | None, profile_id: str | None = None) -> int:
        """Price one call's reported usage into ledger micros; absent usage is 0.

        Pricing uses the **serving profile's** catalog (PRICE-01): the stamp is
        resolved through the shared resolver the composition root wired — the
        providers package's ``resolve_serving_profile`` bound to the declared
        registry, so the stamp→profile-with-warning rule has one implementation —
        and the resolved profile's id selects the catalog wired for it. A stamp
        that names no declared profile resolves to the primary **with a warning**
        (the resolver's — never a silent misprice, PRICE-04) and prices at the
        primary catalog. No resolver wired is the single-catalog world a caller
        without stamps lives in: everything prices at ``prices``.
        """
        if usage is None:
            return 0
        prices = self._prices
        if self._resolve_serving_profile is not None:
            serving = self._resolve_serving_profile(profile_id)
            if serving is not None:
                catalog = self._profile_catalogs.get(serving.id)
                if catalog is not None:
                    prices = catalog
        return (
            usage.input_tokens * prices.input_micros_per_million
            + usage.output_tokens * prices.output_micros_per_million
            + usage.cache_read_input_tokens * prices.cache_read_micros_per_million
            + usage.cache_creation_input_tokens * prices.cache_creation_micros_per_million
        ) // 1_000_000

    def record(self, user_id: UUID, *, usd_micros: int, kind: str) -> None:
        """Add a successful call's USD and its counter to the caller's current day.

        ``ask`` and ``teach_start`` count even when the call cost 0 recorded USD
        (the deterministic local adapters) — the free-tier caps are call counts, not
        amounts. A ``generation``/``embed`` call that reports no usage writes
        nothing: an empty debit never mints a row.
        """
        asks = 1 if kind == KIND_ASK else 0
        teach_starts = 1 if kind == KIND_TEACH_START else 0
        if usd_micros == 0 and asks == 0 and teach_starts == 0:
            return
        self._repo.record(
            user_id,
            self._clock.now().date(),
            usd_micros=usd_micros,
            asks=asks,
            teach_starts=teach_starts,
        )
