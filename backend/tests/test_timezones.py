"""Tests for UTC <-> Australia/Sydney conversion, including daylight saving."""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from app.timezones import clinic_day_bounds_utc, clinic_today, format_clinic, to_clinic, to_utc


def test_summer_time_is_utc_plus_11():
    # November is AEDT.
    assert to_utc(datetime(2026, 11, 3, 15, 0)) == datetime(2026, 11, 3, 4, 0, tzinfo=UTC)


def test_winter_time_is_utc_plus_10():
    # June is AEST.
    assert to_utc(datetime(2026, 6, 16, 15, 0)) == datetime(2026, 6, 16, 5, 0, tzinfo=UTC)


def test_aware_input_is_converted_not_reinterpreted():
    perth_noon = datetime(2026, 11, 3, 12, 0, tzinfo=timezone(timedelta(hours=8)))
    assert to_utc(perth_noon) == datetime(2026, 11, 3, 4, 0, tzinfo=UTC)


def test_round_trip_back_to_clinic_time():
    local = to_clinic(to_utc(datetime(2026, 11, 3, 15, 0)))
    assert (local.hour, local.minute, local.utcoffset()) == (15, 0, timedelta(hours=11))


def test_to_clinic_rejects_naive():
    with pytest.raises(ValueError):
        to_clinic(datetime(2026, 11, 3, 15, 0))


def test_clinic_today_can_differ_from_utc_date():
    # 14:00 UTC on 2 Nov is 01:00 on 3 Nov in Sydney.
    assert clinic_today(datetime(2026, 11, 2, 14, 0, tzinfo=UTC)) == date(2026, 11, 3)


def test_day_bounds_in_summer():
    start, end = clinic_day_bounds_utc(date(2026, 11, 3))
    assert start == datetime(2026, 11, 2, 13, 0, tzinfo=UTC)
    assert end == datetime(2026, 11, 3, 13, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "day, hours",
    [
        (date(2026, 10, 4), 23),  # daylight saving starts: clocks go forward
        (date(2026, 4, 5), 25),  # daylight saving ends: clocks go back
        (date(2026, 11, 3), 24),
    ],
)
def test_day_bounds_across_daylight_saving_changes(day, hours):
    start, end = clinic_day_bounds_utc(day)
    assert end - start == timedelta(hours=hours)


def test_format_clinic():
    assert format_clinic(datetime(2026, 11, 3, 4, 0, tzinfo=UTC)) == "Tue 3 Nov 15:00"
