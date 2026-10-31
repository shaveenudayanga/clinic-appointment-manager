"""Booking rules: every rule about when an appointment may exist lives here.

The functions are pure. They take the current time and any existing
appointments as arguments and never touch the database, so each rule can be
tested on its own. They raise BookingValidationError (the API returns 422) or
DoubleBookingError (the API returns 409) with a message fit to show a user and,
where it applies, the request field the problem is about.

All datetimes passed in must be timezone-aware. Times are compared in UTC and
converted to clinic time only for the opening-hours check and for messages.
"""

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from typing import Literal

from app.models import Appointment, AppointmentStatus, Patient, Practitioner
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


# Request fields an error can point at, so the form can show it in the right place.
ErrorField = Literal["practitioner_id", "patient_id", "start", "end", "status", "full_name", "date_of_birth"]


class BookingRuleError(Exception):
    """Base class for rule violations. `message` is safe to show to users."""

    def __init__(self, message: str, field: ErrorField | None = None):
        super().__init__(message)
        self.message = message
        self.field = field


class BookingValidationError(BookingRuleError):
    """The request is invalid on its own (bad times, bad status, bad patient details)."""


class DoubleBookingError(BookingRuleError):
    """The requested appointment clashes with an existing one."""

    def __init__(self, message: str, field: ErrorField, clash: Appointment):
        super().__init__(message, field)
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
        raise BookingValidationError("End time must be after the start time.", "end")

    duration = end_utc - start_utc
    if duration < MIN_DURATION or duration > MAX_DURATION:
        raise BookingValidationError(
            f"Appointments must be between {_minutes(MIN_DURATION)} and "
            f"{_minutes(MAX_DURATION)} minutes long (this one is {_minutes(duration)}).",
            "end",
        )

    if start_utc < now_utc:
        raise BookingValidationError("Appointments can't be booked in the past.", "start")

    local_start, local_end = to_clinic(start_utc), to_clinic(end_utc)
    if local_start.weekday() not in CLINIC_WEEKDAYS:
        raise BookingValidationError("The clinic is only open Monday to Friday.", "start")
    hours = f"{CLINIC_OPEN:%H:%M} to {CLINIC_CLOSE:%H:%M} (Sydney time)"
    if local_start.time() < CLINIC_OPEN or local_start.time() >= CLINIC_CLOSE:
        raise BookingValidationError(f"Appointments must be within clinic hours, {hours}.", "start")
    if local_start.date() != local_end.date() or local_end.time() > CLINIC_CLOSE:
        raise BookingValidationError(
            f"This appointment would finish after closing (clinic hours are {hours}).", "end"
        )


def check_no_double_booking(
    *,
    start_utc: datetime,
    end_utc: datetime,
    practitioner: Practitioner,
    patient: Patient,
    existing: Iterable[Appointment],
    exclude_id: int | None = None,
) -> None:
    """Raise DoubleBookingError if the practitioner OR the patient is already busy.

    People are matched by id only, never by name, because names are not
    unique. The message uses each person's label (name plus provider number
    or MRN) so it is clear who is busy.

    `existing` may contain any appointments (any status, any people); this
    function decides which ones matter. Pass `exclude_id` when editing so the
    appointment does not clash with itself.
    """
    _require_aware(start_utc, end_utc)
    if practitioner.id is None or patient.id is None:
        raise ValueError("Practitioner and patient must be saved (have ids) before checking clashes")

    for other in sorted(existing, key=lambda a: a.start_utc):
        if exclude_id is not None and other.id == exclude_id:
            continue
        if other.status not in BLOCKING_STATUSES:
            continue
        if not overlaps(start_utc, end_utc, other.start_utc, other.end_utc):
            continue

        when = f"from {format_clinic(other.start_utc)} to {to_clinic(other.end_utc):%H:%M}"
        if other.practitioner_id == practitioner.id:
            raise DoubleBookingError(
                f"{practitioner.label} already has an appointment {when}.", "practitioner_id", other
            )
        if other.patient_id == patient.id:
            raise DoubleBookingError(f"{patient.label} already has an appointment {when}.", "patient_id", other)


def check_can_edit(current_status: AppointmentStatus) -> None:
    """Cancelled appointments are final. To undo a cancellation, book again."""
    if current_status == AppointmentStatus.CANCELLED:
        raise BookingValidationError(
            "This appointment is cancelled and can't be changed. Please book a new one."
        )


def check_can_cancel(current_status: AppointmentStatus) -> None:
    """Only a booked appointment can be cancelled. A completed or no-show
    appointment records what happened and stays as it is."""
    if current_status != AppointmentStatus.BOOKED:
        raise BookingValidationError("Only booked appointments can be cancelled.", "status")


def validate_status(status: AppointmentStatus, start_utc: datetime, now_utc: datetime) -> None:
    """Completed and No-show can only be recorded once the appointment has started."""
    _require_aware(start_utc, now_utc)
    if status in OUTCOME_STATUSES and start_utc > now_utc:
        raise BookingValidationError(
            "An appointment can only be marked completed or no-show after it has started.", "status"
        )


def allowed_actions(status: AppointmentStatus, start_utc: datetime, now_utc: datetime) -> list[str]:
    """What staff may do with an appointment right now, worked out from the rules above.

    The frontend uses this to decide which buttons to show, so it never has to
    repeat a rule itself.
    """
    try:
        check_can_edit(status)
    except BookingValidationError:
        return []
    actions = ["edit"]
    try:
        check_can_cancel(status)
        actions.append("cancel")
    except BookingValidationError:
        pass
    for action, outcome in (("complete", AppointmentStatus.COMPLETED), ("no_show", AppointmentStatus.NO_SHOW)):
        if status == outcome:
            continue
        try:
            validate_status(outcome, start_utc, now_utc)
        except BookingValidationError:
            continue
        actions.append(action)
    return actions


# --- Patients -----------------------------------------------------------------


def normalise_name(name: str) -> str:
    """Trim and collapse spaces, e.g. '  Ruwan   Perera ' -> 'Ruwan Perera'."""
    return " ".join(name.split())


def validate_new_patient(full_name: str, date_of_birth: date, today: date) -> None:
    if not normalise_name(full_name):
        raise BookingValidationError("Please enter the patient's full name.", "full_name")
    if date_of_birth > today:
        raise BookingValidationError("Date of birth can't be in the future.", "date_of_birth")


def find_possible_duplicates(full_name: str, date_of_birth: date, existing: Iterable[Patient]) -> list[Patient]:
    """Existing patients with the same name (ignoring case and spacing) and date of birth.

    These may be the same person, so staff are asked before registering
    another record. They may also be different people, which is allowed.
    """
    wanted = normalise_name(full_name).casefold()
    return [
        p for p in existing
        if p.date_of_birth == date_of_birth and normalise_name(p.full_name).casefold() == wanted
    ]


# --- Clinic days --------------------------------------------------------------


def is_clinic_day(day: date) -> bool:
    return day.weekday() in CLINIC_WEEKDAYS


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
