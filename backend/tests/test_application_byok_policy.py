"""The learner-side BYOK policy at its own layer (deterministic fakes, no DB).

The soft monthly budget and the per-corpus prompt ceiling are scoped to calls
the learner's own key would serve, decided before any provider call, and
recorded only from what a successful call actually reported. The ledger scope,
the ceiling's settings values, the budget lifecycle, and the pricing rule are
pinned here — the web boundary (which status each refusal answers, and that no
refusal falls over to a house key) is proven beside the routes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.application.budget import DailyBudget, TokenPrices
from app.application.byok import BUDGET_COPY, ByokPolicy
from app.application.errors import ByokBudgetExhausted, ByokCorpusLimitExhausted
from app.domain.entities import TokenUsage
from tests.fakes import (
    FakeAiSpendDayRepository,
    FakeByokCorpusRepository,
    FakeByokMonthRepository,
    FakeByokSettingsStore,
    FakeClock,
)

_NOW = datetime(2026, 10, 15, 12, 0, 0, tzinfo=UTC)
_MONTH = "2026-10"
_USER = UUID("aaaaaaaa-0000-0000-0000-000000000001")
_OTHER = UUID("aaaaaaaa-0000-0000-0000-000000000002")
_SOURCE = uuid4()
_OTHER_SOURCE = uuid4()

_PRICES = TokenPrices(
    input_micros_per_million=1_000_000,  # $1 / million input
    output_micros_per_million=2_000_000,  # $2 / million output
    embed_micros_per_million=0,
)


def _estimate(usage: TokenUsage | None, profile_id: str | None = None) -> int:
    """The stand-in estimate: the same arithmetic the budget's rule performs."""
    if usage is None:
        return 0
    return (
        usage.input_tokens * _PRICES.input_micros_per_million
        + usage.output_tokens * _PRICES.output_micros_per_million
    ) // 1_000_000


def _policy(
    *,
    corpus_cap: int = 100_000,
    budget: int | None = None,
    months: FakeByokMonthRepository | None = None,
    corpus: FakeByokCorpusRepository | None = None,
    clock: FakeClock | None = None,
) -> tuple[ByokPolicy, FakeByokMonthRepository, FakeByokCorpusRepository]:
    months = months or FakeByokMonthRepository()
    corpus = corpus or FakeByokCorpusRepository()
    policy = ByokPolicy(
        months=months,
        corpus=corpus,
        settings=FakeByokSettingsStore(budget),
        clock=clock or FakeClock(_NOW),
        corpus_cap_tokens=corpus_cap,
        estimate=_estimate,
    )
    return policy, months, corpus


# --- the corpus ledger's scope -------------------------------------------------------


def test_corpus_ledger_scope() -> None:
    """The ceiling counts this learner's user-keyed prompt tokens on this source this month."""
    policy, months, corpus = _policy(corpus_cap=10_000)
    usage = TokenUsage(input_tokens=6_000, output_tokens=100)

    policy.record_turn(_USER, user_keyed=True, source_id=_SOURCE, usage=usage, profile_id="p1")
    policy.record_turn(_USER, user_keyed=True, source_id=_SOURCE, usage=usage, profile_id="p1")

    row = corpus.get_for_month(_USER, _SOURCE, _MONTH)
    assert row is not None and row.input_tokens == 12_000  # both calls, this book
    assert corpus.get_for_month(_USER, _SOURCE, "2026-09") is None  # another month
    assert corpus.get_for_month(_USER, _OTHER_SOURCE, _MONTH) is None  # another book
    assert corpus.get_for_month(_OTHER, _SOURCE, _MONTH) is None  # another learner


def test_house_served_calls_never_reach_the_ledgers() -> None:
    """A call the learner's key does not serve records nothing, whatever it reported."""
    policy, months, corpus = _policy()

    policy.record_turn(_USER, user_keyed=False, source_id=_SOURCE, usage=None, profile_id="p1")
    policy.record_turn(
        _USER,
        user_keyed=False,
        source_id=_SOURCE,
        usage=TokenUsage(input_tokens=50_000, output_tokens=5_000),
        profile_id="p1",
    )
    policy.assert_turn(_USER, user_keyed=False, source_id=_SOURCE)

    assert months.record_calls == []
    assert corpus.record_calls == []
    assert months.get_for_month(_USER, _MONTH) is None


# --- the ceiling ---------------------------------------------------------------------


def test_ceiling_refuses_at_and_above_the_cap() -> None:
    """A source at the month's ceiling refuses the next user-keyed turn on it."""
    policy, _months, _corpus = _policy(corpus_cap=10_000)
    policy.record_turn(
        _USER,
        user_keyed=True,
        source_id=_SOURCE,
        usage=TokenUsage(input_tokens=10_000, output_tokens=1),
        profile_id="p1",
    )

    with pytest.raises(ByokCorpusLimitExhausted) as refused:
        policy.assert_turn(_USER, user_keyed=True, source_id=_SOURCE)
    assert refused.value.code == "byok_corpus_limit"
    assert "monthly" in str(refused.value)

    # A different book of the same learner is unaffected, and a covered month
    # under the cap passes.
    policy.assert_turn(_USER, user_keyed=True, source_id=_OTHER_SOURCE)


def test_cap_zero_disables() -> None:
    policy, _months, corpus = _policy(corpus_cap=0)
    policy.record_turn(
        _USER,
        user_keyed=True,
        source_id=_SOURCE,
        usage=TokenUsage(input_tokens=9_999_999, output_tokens=1),
        profile_id="p1",
    )

    policy.assert_turn(_USER, user_keyed=True, source_id=_SOURCE)  # no refusal: disabled
    assert corpus.get_for_month(_USER, _SOURCE, _MONTH) is not None


def test_negative_cap_is_a_programming_error() -> None:
    with pytest.raises(ValueError):
        _policy(corpus_cap=-1)


def test_absent_source_record_serves_forever_under_the_cap() -> None:
    """A month with no row has seen nothing: the first user-keyed turn always passes."""
    policy, _months, _corpus = _policy(corpus_cap=10_000)

    policy.assert_turn(_USER, user_keyed=True, source_id=_SOURCE)


# --- the soft monthly budget ---------------------------------------------------------


def test_budget_trips_at_the_months_cost() -> None:
    policy, _months, _corpus = _policy(corpus_cap=0, budget=1_000_000)
    policy.record_turn(
        _USER,
        user_keyed=True,
        source_id=_SOURCE,
        # 400k input x $1/M + 300k output x $2/M = exactly the $1 budget
        usage=TokenUsage(input_tokens=400_000, output_tokens=300_000),
        profile_id="p1",
    )

    with pytest.raises(ByokBudgetExhausted) as refused:
        policy.assert_turn(_USER, user_keyed=True, source_id=_SOURCE)
    assert refused.value.code == "byok_budget"
    assert "own monthly" in str(refused.value)
    assert "Account" in str(refused.value)
    assert str(refused.value) == BUDGET_COPY


def test_no_budget_set_never_refuses() -> None:
    policy, _months, _corpus = _policy(budget=None)
    policy.record_turn(
        _USER,
        user_keyed=True,
        source_id=None,
        usage=TokenUsage(input_tokens=10**9, output_tokens=10**9),
        profile_id="p1",
    )

    policy.assert_turn(_USER, user_keyed=True, source_id=_SOURCE)


def test_raised_budget_serves_next() -> None:
    """What makes the budget soft: raise or clear it, and the next request serves."""
    settings = FakeByokSettingsStore(1_000_000)
    policy, _months, _corpus = _policy(corpus_cap=0, budget=1_000_000)
    policy._settings = settings  # noqa: SLF001 — the lifecycle under test is the stored value
    policy.record_turn(
        _USER,
        user_keyed=True,
        source_id=_SOURCE,
        usage=TokenUsage(input_tokens=400_000, output_tokens=300_000),
        profile_id="p1",
    )
    with pytest.raises(ByokBudgetExhausted):
        policy.assert_turn(_USER, user_keyed=True, source_id=_SOURCE)

    settings.set_budget(_USER, 2_000_000)
    policy.assert_turn(_USER, user_keyed=True, source_id=_SOURCE)

    settings.set_budget(_USER, None)
    policy.assert_turn(_USER, user_keyed=True, source_id=_SOURCE)


# --- the recorded estimate -----------------------------------------------------------


def test_recorded_estimate_matches_the_house_pricing_rule() -> None:
    """The learner's ledger debits the same number the house rule prices: one catalog.

    The budget wired here has no profile resolver, so both the house debit and
    the learner's estimate read the primary catalog — the point is that
    ``estimate_micros`` and the recorded cost agree to the micro.
    """
    clock = FakeClock(_NOW)
    months = FakeByokMonthRepository()
    budget = DailyBudget(
        repo=FakeAiSpendDayRepository(),
        clock=clock,
        daily_cap_micros=10**9,
        prices=_PRICES,
        ask_daily_cap=10,
        teach_start_daily_cap=10,
    )
    policy = ByokPolicy(
        months=months,
        corpus=FakeByokCorpusRepository(),
        settings=FakeByokSettingsStore(None),
        clock=clock,
        corpus_cap_tokens=0,
        estimate=budget.estimate_micros,
    )
    usage = TokenUsage(input_tokens=1_500_000, output_tokens=250_000)

    policy.record_turn(_USER, user_keyed=True, source_id=None, usage=usage, profile_id=None)

    row = months.get_for_month(_USER, _MONTH)
    assert row is not None
    assert row.cost_usd_micros == budget.estimate_micros(usage, None)
    # 1.5M input x $1/M + 250k output x $2/M = 2.0 USD, in micros
    assert row.cost_usd_micros == 2_000_000
    assert (row.input_tokens, row.output_tokens) == (1_500_000, 250_000)


def test_no_reported_usage_records_nothing() -> None:
    policy, months, corpus = _policy()

    policy.record_turn(_USER, user_keyed=True, source_id=_SOURCE, usage=None, profile_id="p1")

    assert months.record_calls == []
    assert corpus.record_calls == []
    assert months.get_for_month(_USER, _MONTH) is None


# --- the month boundary and the account view -----------------------------------------


def test_month_usage_reads_zeros_for_a_quiet_month() -> None:
    policy, _months, _corpus = _policy()

    period, tokens_in, tokens_out, cost = policy.month_usage(_USER)

    assert (period, tokens_in, tokens_out, cost) == (_MONTH, 0, 0, 0)


def test_stored_budget_reads_none_while_unset() -> None:
    policy, _months, _corpus = _policy(budget=None)

    assert policy.stored_budget(_USER) is None


# --- the monthly ledger's accumulation -----------------------------------------------


def test_monthly_ledger_accumulates() -> None:
    """Every user-keyed call kind lands in the same month row, incrementing it.

    Turns, card suggestions, and deck passes all record through ``record_turn``:
    the month row accumulates each call's reported tokens and estimated cost
    (the upsert-increment makes the order and the batching irrelevant), and the
    per-source rows accumulate the input tokens of the calls that targeted them.
    A house-served call records nothing at all.
    """
    policy, months, corpus = _policy(corpus_cap=1_000_000)

    # An ask turn and a card suggestion on the same book, then a deck pass on
    # another, then a house-served call that must vanish.
    policy.record_turn(
        _USER,
        user_keyed=True,
        source_id=_SOURCE,
        usage=TokenUsage(input_tokens=10_000, output_tokens=2_000),
        profile_id="p1",
    )
    policy.record_turn(
        _USER,
        user_keyed=True,
        source_id=_SOURCE,
        usage=TokenUsage(input_tokens=5_000, output_tokens=1_000),
        profile_id="p1",
    )
    policy.record_turn(
        _USER,
        user_keyed=True,
        source_id=_OTHER_SOURCE,
        usage=TokenUsage(input_tokens=100_000, output_tokens=50_000),
        profile_id=None,
    )
    policy.record_turn(
        _USER,
        user_keyed=False,
        source_id=_SOURCE,
        usage=TokenUsage(input_tokens=999_999, output_tokens=999_999),
        profile_id=None,
    )

    month = months.get_for_month(_USER, _MONTH)
    assert month is not None
    assert (month.input_tokens, month.output_tokens) == (115_000, 53_000)
    # 10k+5k in x $1/M + 2k+1k out x $2/M + 100k in x $1/M + 50k out x $2/M
    # = 0.015 + 0.006 + 0.1 + 0.1 USD = 221_000 micros.
    assert month.cost_usd_micros == 221_000

    this_book = corpus.get_for_month(_USER, _SOURCE, _MONTH)
    other_book = corpus.get_for_month(_USER, _OTHER_SOURCE, _MONTH)
    assert this_book is not None and this_book.input_tokens == 15_000
    assert other_book is not None and other_book.input_tokens == 100_000

    # The account view reads the same row back.
    assert policy.month_usage(_USER) == (_MONTH, 115_000, 53_000, 221_000)
