"""Profile-priced debits — cache pricing and stamp resolution (PRICE-01/02/04).

Pure pricing units behind :meth:`DailyBudget.usage_micros`: a successful call's
usage is multiplied into the **serving profile's** catalog (PRICE-01), cache
read/creation tokens are priced at the profile's cache prices and their absence
changes nothing (PRICE-02), and a stamp that names no declared profile falls back
to the primary catalog with a warning instead of mispricing silently (PRICE-04).
"""

from __future__ import annotations

import logging

import pytest

from app.application.budget import DailyBudget, TokenPrices
from app.domain.entities import TokenUsage
from app.infrastructure.providers import (
    GenerationProfileSettings,
    resolve_serving_profile,
)
from tests.fakes import FakeAiSpendDayRepository, FakeClock

#: Two catalogs whose prices differ enough that the same usage can never alias:
#: an economy profile (~$0.20/$1.00 with its own cache pair) and the premium
#: default pair with the derived cache prices (0.1×/1.25× input).
_ECONOMY_PRICES = TokenPrices(
    input_micros_per_million=200_000,
    output_micros_per_million=1_000_000,
    embed_micros_per_million=0,
    cache_read_micros_per_million=20_000,
    cache_creation_micros_per_million=300_000,
)
_PREMIUM_PRICES = TokenPrices(
    input_micros_per_million=1_000_000,
    output_micros_per_million=5_000_000,
    embed_micros_per_million=0,
)

#: A cache-bearing call: 900 in / 400 out / 10k cache-read / 2k cache-creation.
_USAGE = TokenUsage(
    input_tokens=900,
    output_tokens=400,
    cache_read_input_tokens=10_000,
    cache_creation_input_tokens=2_000,
)


def _budget(**kwargs: object) -> DailyBudget:
    return DailyBudget(
        repo=FakeAiSpendDayRepository(),  # pricing never touches the ledger
        clock=FakeClock(None),  # pricing never reads the clock
        daily_cap_micros=1_000_000,
        prices=_PREMIUM_PRICES,
        ask_daily_cap=8,
        teach_start_daily_cap=1,
        **kwargs,  # type: ignore[arg-type]
    )


# --- PRICE-01: the serving profile's catalog prices the call ----------------------


def test_the_same_usage_prices_differently_through_two_profile_catalogs() -> None:
    budget = _budget(profile_catalogs={"economy": _ECONOMY_PRICES})

    economy = budget.usage_micros(_USAGE, profile_id="economy")
    premium = budget.usage_micros(_USAGE, profile_id="primary")

    # Hand-checked: 900×200k + 400×1M + 10k×20k + 2k×300k micros = 1380;
    # 900×1M + 400×5M + 10k×100k + 2k×1.25M = 6400. Not merely unequal —
    # each equals its own catalog's arithmetic.
    assert economy == 1380
    assert premium == 6400


# --- PRICE-02: cache tokens are priced, their absence changes nothing ------------


def test_cache_fields_are_priced_at_the_catalog_cache_prices() -> None:
    economy_only = _budget(profile_catalogs={"economy": _ECONOMY_PRICES})

    with_cache = economy_only.usage_micros(_USAGE, profile_id="economy")
    without_cache = economy_only.usage_micros(
        TokenUsage(input_tokens=900, output_tokens=400), profile_id="economy"
    )

    # The cache increment is exactly the cache terms: 10k×20k + 2k×300k micros.
    assert with_cache - without_cache == 800


def test_usage_without_cache_fields_debits_input_and_output_only() -> None:
    budget = _budget()

    legacy_shaped = budget.usage_micros(TokenUsage(input_tokens=1500, output_tokens=300))

    # 1500×1M + 300×5M micros = 3000 — the exact debit the pre-cache formula
    # produced, so the derived cache prices never move a cache-free call.
    assert legacy_shaped == 3000


def test_a_profile_may_override_the_derived_cache_prices() -> None:
    overridden = TokenPrices(
        input_micros_per_million=1_000_000,
        output_micros_per_million=2_000_000,
        embed_micros_per_million=0,
        cache_read_micros_per_million=50_000,
        cache_creation_micros_per_million=2_000_000,
    )
    budget = _budget(profile_catalogs={"p": overridden})

    micros = budget.usage_micros(TokenUsage(cache_read_input_tokens=1_000_000), profile_id="p")

    assert micros == 50_000  # the override, not the 0.1× default (100_000)


def test_omitted_cache_prices_derive_from_the_input_price() -> None:
    prices = TokenPrices(
        input_micros_per_million=3_000_000,
        output_micros_per_million=15_000_000,
        embed_micros_per_million=0,
    )

    # $3/MTok input → $0.30 read, $3.75 creation: the design's derived pair.
    assert prices.cache_read_micros_per_million == 300_000
    assert prices.cache_creation_micros_per_million == 3_750_000


# --- PRICE-04: an unresolvable stamp is never a silent misprice ------------------


def test_an_unknown_stamp_falls_back_to_the_primary_catalog_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    budget = _budget(profile_catalogs={"economy": _ECONOMY_PRICES})

    with caplog.at_level(logging.WARNING, logger="app.application.budget"):
        micros = budget.usage_micros(_USAGE, profile_id="ghost")

    assert micros == 6400  # the primary catalog's arithmetic, not the economy's
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "ghost" in warnings[0].getMessage()


def test_a_missing_stamp_prices_at_the_primary_without_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    budget = _budget(profile_catalogs={"economy": _ECONOMY_PRICES})

    with caplog.at_level(logging.WARNING, logger="app.application.budget"):
        micros = budget.usage_micros(_USAGE)

    assert micros == 6400
    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


def test_absent_usage_debits_zero_whatever_the_stamp() -> None:
    budget = _budget(profile_catalogs={"economy": _ECONOMY_PRICES})

    assert budget.usage_micros(None) == 0
    assert budget.usage_micros(None, profile_id="economy") == 0


# --- Registry-level resolution helper (AD-344) ------------------------------------


def _profile(id: str, model: str) -> GenerationProfileSettings:
    return GenerationProfileSettings(
        id=id,
        kind="anthropic",
        model=model,
        api_key_env="LEARNY_TEST_PROFILE_KEY",
        max_tokens=4096,
        price_input_usd_per_million_tokens=3.0,
        price_output_usd_per_million_tokens=15.0,
        price_cache_read_usd_per_million_tokens=0.3,
        price_cache_creation_usd_per_million_tokens=3.75,
        grounding="verified-spans",
        ask_enabled=True,
        teach_enabled=True,
    )


def test_resolution_returns_the_stamped_profile_exactly() -> None:
    primary = _profile("primary", "claude-sonnet-5")
    explain = _profile("explain", "claude-haiku-4-5")

    # Two profiles sharing the provider stay unambiguous: the stamp decides.
    resolved = resolve_serving_profile((primary, explain), "explain")

    assert resolved is explain


def test_resolution_without_a_stamp_returns_the_primary() -> None:
    primary = _profile("primary", "claude-sonnet-5")

    assert resolve_serving_profile((primary,), None) is primary


def test_resolution_of_an_unknown_stamp_returns_primary_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    primary = _profile("primary", "claude-sonnet-5")

    with caplog.at_level(logging.WARNING, logger="app.infrastructure.providers.profiles"):
        resolved = resolve_serving_profile((primary,), "ghost")

    assert resolved is primary
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "ghost" in warnings[0].getMessage() and "primary" in warnings[0].getMessage()


def test_resolution_of_an_empty_registry_returns_none() -> None:
    assert resolve_serving_profile((), None) is None
