"""Booking rules: every rule about when an appointment may exist lives here.

The functions are pure. They take the current time and any existing
appointments as arguments and never touch the database, so each rule can be
tested on its own. They raise BookingValidationError (the API returns 422) or
DoubleBookingError (the API returns 409) with a message fit to show a user.

All datetimes passed in must be timezone-aware. Times are compared in UTC and
converted to clinic time only for the opening-hours check and for messages.
"""

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta

from app.models import Appointment, AppointmentStatus
from app.timezones import format_clinic, to_clinic

# Clinic schedule (clinic local time)
CLINIC_OPEN = time(8, 0)
CLINIC_CLOSE = time(18, 0)
CLINIC_WEEKDAYS = {0, 1, 2, 3, 4}  # Monday to Friday

# Appointment length
MIN_DURATION = timedelta(minutes=15)
MAX_DURATION = timedelta(minutes=120)

# Statuses that occupy a time slot. Only a cancelled appointment frees its slot.
BLOCKING_STATUSES = {
    AppointmentStatus.BOOKED,
    AppointmentStatus.COMPLETED,
    AppointmentStatus.NO_SHOW,
}

# Statuses that describe something that already happened.
OUTCOME_STATUSES = {AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW}


class BookingRuleError(Exception):
    """Base class for rule violations. `message` is safe to show to users."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class BookingValidationError(BookingRuleError):
    """The requested appointment is invalid on its own (bad times, bad status)."""


class DoubleBookingError(BookingRuleError):
    """The requested appointment clashes with an existing one."""

    def __init__(self, message: str, clash: Appointment):
        super().__init__(message)
        self.clash = clash


def _require_aware(*values: datetime) -> None:
    for value in values:
        if value.tzinfo is None:
            raise ValueError("Booking rules need timezone-aware datetimes")


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """True if two time ranges share any time.

    Ranges are half-open [start, end), so one appointment ending at 10:00 and
    another starting at 10:00 do not overlap.
    """
    return a_start < b_end and b_start < a_end


def validate_times(start_utc: datetime, end_utc: datetime, now_utc: datetime) -> None:
    """Check that the time range is a bookable appointment."""
    _require_aware(start_utc, end_utc, now_utc)

    if end_utc <= start_utc:
        raise BookingValidationError("End time must be after the start time.")

    duration = end_utc - start_utc
    if duration < MIN_DURATION or duration > MAX_DURATION:
        raise BookingValidationError(
            f"Appointments must be between {_minutes(MIN_DURATION)} and "
            f"{_minutes(MAX_DURATION)} minutes long (this one is {_minutes(duration)})."
        )

    if start_utc < now_utc:
        raise BookingValidationError("Appointments can't be booked in the past.")

    local_start, local_end = to_clinic(start_utc), to_clinic(end_utc)
    if local_start.weekday() not in CLINIC_WEEKDAYS:
        raise BookingValidationError("The clinic is only open Monday to Friday.")
    if (
        local_start.date() != local_end.date()
        or local_start.time() < CLINIC_OPEN
        or local_end.time() > CLINIC_CLOSE
    ):
        raise BookingValidationError(
            f"Appointments must be within clinic hours, "
            f"{CLINIC_OPEN:%H:%M} to {CLINIC_CLOSE:%H:%M} (Sydney time)."
        )


def check_no_double_booking(
    *,
    start_utc: datetime,
    end_utc: datetime,
    practitioner_id: int,
    patient_id: int,
    existing: Iterable[Appointment],
    exclude_id: int | None = None,
    practitioner_name: str = "The practitioner",
    patient_name: str = "The patient",
) -> None:
    """Raise DoubleBookingError if the practitioner OR the patient is already busy.

    `existing` may contain any appointments (any status, any people); this
    function decides which ones matter. Pass `exclude_id` when editing so the
    appointment does not clash with itself.
    """
    _require_aware(start_utc, end_utc)

    for other in sorted(existing, key=lambda a: a.start_utc):
        if exclude_id is not None and other.id == exclude_id:
            continue
        if other.status not in BLOCKING_STATUSES:
            continue
        if not overlaps(start_utc, end_utc, other.start_utc, other.end_utc):
            continue

        when = f"from {format_clinic(other.start_utc)} to {to_clinic(other.end_utc):%H:%M}"
        if other.practitioner_id == practitioner_id:
            raise DoubleBookingError(f"{practitioner_name} already has an appointment {when}.", other)
        if other.patient_id == patient_id:
            raise DoubleBookingError(f"{patient_name} already has an appointment {when}.", other)


def check_can_edit(current_status: AppointmentStatus) -> None:
    """Cancelled appointments are final. To undo a cancellation, book again."""
    if current_status == AppointmentStatus.CANCELLED:
        raise BookingValidationError(
            "This appointment is cancelled and can't be changed. Please book a new one."
        )


def validate_status(status: AppointmentStatus, start_utc: datetime, now_utc: datetime) -> None:
    """Completed and No-show can only be recorded once the appointment has started."""
    _require_aware(start_utc, now_utc)
    if status in OUTCOME_STATUSES and start_utc > now_utc:
        raise BookingValidationError(
            "An appointment can only be marked completed or no-show after it has started."
        )


def next_clinic_day(day: date) -> date:
    """`day` itself if the clinic is open that weekday, otherwise the next open day."""
    while day.weekday() not in CLINIC_WEEKDAYS:
        day += timedelta(days=1)
    return day


def previous_clinic_day(day: date) -> date:
    """The last open day strictly before `day`."""
    day -= timedelta(days=1)
    while day.weekday() not in CLINIC_WEEKDAYS:
        day -= timedelta(days=1)
    return day


def _minutes(delta: timedelta) -> int:
    return int(delta.total_seconds() // 60)
