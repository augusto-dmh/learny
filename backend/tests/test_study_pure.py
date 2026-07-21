"""Day-boundary helper (pure unit, no DB).

``local_day`` maps a UTC instant to the user-local calendar date (HOME-09 / I-3):

- a valid IANA zone shifts the date forward or backward across the local midnight;
- the current UTC offset (including DST) is applied, not a fixed offset;
- a missing, empty, or invalid zone degrades silently to the UTC date — never raises.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.application.dates import local_day


def test_valid_zone_east_of_utc_can_advance_the_date() -> None:
    # 23:30 UTC is already the next calendar day in Tokyo (+09:00).
    now = datetime(2026, 7, 21, 23, 30, tzinfo=UTC)
    assert local_day(now, "Asia/Tokyo") == date(2026, 7, 22)


def test_valid_zone_west_of_utc_can_roll_the_date_back() -> None:
    # 02:00 UTC is still the previous calendar day in Los Angeles (-07:00 in July).
    now = datetime(2026, 7, 21, 2, 0, tzinfo=UTC)
    assert local_day(now, "America/Los_Angeles") == date(2026, 7, 20)


def test_dst_offset_is_applied_not_a_fixed_standard_offset() -> None:
    # At 07:30 UTC, Los Angeles in July is DST (-07:00) → 00:30 local → the 21st.
    # A fixed standard offset (-08:00) would wrongly yield 23:30 on the 20th, so this
    # discriminates DST-aware resolution.
    now = datetime(2026, 7, 21, 7, 30, tzinfo=UTC)
    assert local_day(now, "America/Los_Angeles") == date(2026, 7, 21)


def test_none_zone_falls_back_to_utc_date() -> None:
    now = datetime(2026, 7, 21, 23, 30, tzinfo=UTC)
    assert local_day(now, None) == date(2026, 7, 21)


def test_empty_zone_falls_back_to_utc_date() -> None:
    now = datetime(2026, 7, 21, 23, 30, tzinfo=UTC)
    assert local_day(now, "") == date(2026, 7, 21)


def test_garbage_zone_falls_back_to_utc_date_without_raising() -> None:
    now = datetime(2026, 7, 21, 23, 30, tzinfo=UTC)
    assert local_day(now, "Mars/Olympus") == date(2026, 7, 21)


def test_path_injection_zone_falls_back_to_utc_date() -> None:
    # A path-like value raises ValueError inside zoneinfo, not ZoneInfoNotFoundError —
    # both must be swallowed into the UTC fallback.
    now = datetime(2026, 7, 21, 23, 30, tzinfo=UTC)
    assert local_day(now, "../../etc/passwd") == date(2026, 7, 21)
