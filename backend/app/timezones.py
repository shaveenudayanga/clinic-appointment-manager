"""Conversions between UTC (how times are stored) and clinic time (how people read them).

The clinic is in Australia/Sydney, which is UTC+10 in winter and UTC+11 during
daylight saving (first Sunday in October to first Sunday in April). zoneinfo
handles the switch, so nothing here hard-codes an offset.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

CLINIC_TZ = ZoneInfo("Australia/Sydney")


def now_utc() -> datetime:
    return datetime.now(UTC)


def to_utc(value: datetime) -> datetime:
    """Return `value` as an aware UTC datetime.

    A naive datetime is treated as clinic wall-clock time, e.g. 15:00 means
    3pm in Sydney. An aware datetime is simply converted.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=CLINIC_TZ)
    return value.astimezone(UTC)


def to_clinic(value: datetime) -> datetime:
    """Return an aware datetime in clinic time."""
    if value.tzinfo is None:
        raise ValueError("Expected a timezone-aware datetime")
    return value.astimezone(CLINIC_TZ)


def clinic_today(now: datetime) -> date:
    return to_clinic(now).date()


def clinic_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """UTC start (inclusive) and end (exclusive) of a calendar day in clinic time."""
    start = datetime.combine(day, time.min, CLINIC_TZ)
    end = datetime.combine(day + timedelta(days=1), time.min, CLINIC_TZ)
    return start.astimezone(UTC), end.astimezone(UTC)


def format_clinic(value: datetime) -> str:
    """Human-readable clinic time, e.g. 'Tue 3 Nov 15:00'. Avoids %-d, which Windows lacks."""
    local = to_clinic(value)
    return f"{local:%a} {local.day} {local:%b %H:%M}"
