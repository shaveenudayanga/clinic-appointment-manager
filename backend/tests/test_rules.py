"""Tests for app/rules.py. No database: every rule is a pure function."""

from datetime import date, datetime

import pytest

from app.models import AppointmentStatus as Status
from app.rules import (
    BookingValidationError,
    DoubleBookingError,
    allowed_actions,
    check_can_cancel,
    check_can_edit,
    check_no_double_booking,
    find_possible_duplicates,
    is_clinic_day,
    next_clinic_day,
    normalise_name,
    overlaps,
    previous_clinic_day,
    validate_new_patient,
    validate_status,
    validate_times,
)
from tests.helpers import appointment, patient, practitioner, sydney

# "Now" for most tests: Monday 2 Nov 2026, 07:00 Sydney (before opening).
NOW = sydney("2026-11-02T07:00")

DR_SILVA = practitioner(1, "Dr Anika Silva", "000101AA")
DR_CHEN = practitioner(2, "Dr Mei Chen", "000103AC")
PERERA = patient(1, "Ruwan Perera", "000123")
NGUYEN = patient(2, "Grace Nguyen", "000128")

# Existing appointment: Dr Silva with Ruwan Perera, Tue 3 Nov 15:00-15:30.
EXISTING = appointment(100, DR_SILVA.id, PERERA.id, "2026-11-03T15:00", 30)


def book(start: str, end: str, prac=DR_SILVA, pat=PERERA, existing=(EXISTING,), exclude_id=None):
    check_no_double_booking(
        start_utc=sydney(start),
        end_utc=sydney(end),
        practitioner=prac,
        patient=pat,
        existing=list(existing),
        exclude_id=exclude_id,
    )


# --- overlaps() -------------------------------------------------------------


@pytest.mark.parametrize(
    "a, b, expected",
    [
        (("10:00", "10:30"), ("10:30", "11:00"), False),  # touching: a ends as b starts
        (("10:30", "11:00"), ("10:00", "10:30"), False),  # touching: b ends as a starts
        (("10:00", "10:30"), ("10:15", "10:45"), True),  # partial overlap at the end
        (("10:15", "10:45"), ("10:00", "10:30"), True),  # partial overlap at the start
        (("10:00", "11:00"), ("10:15", "10:30"), True),  # b inside a
        (("10:15", "10:30"), ("10:00", "11:00"), True),  # a inside b
        (("10:00", "10:30"), ("10:00", "10:30"), True),  # identical
        (("10:00", "10:30"), ("11:00", "11:30"), False),  # apart
    ],
)
def test_overlaps(a, b, expected):
    day = "2026-11-03T"
    assert overlaps(sydney(day + a[0]), sydney(day + a[1]), sydney(day + b[0]), sydney(day + b[1])) is expected


# --- check_no_double_booking(): practitioner --------------------------------


def test_practitioner_partial_overlap_is_blocked():
    with pytest.raises(DoubleBookingError) as err:
        book("2026-11-03T15:15", "2026-11-03T15:45", pat=NGUYEN)
    assert "Dr Anika Silva" in err.value.message
    assert "000101AA" in err.value.message
    assert "Tue 3 Nov 15:00 to 15:30" in err.value.message
    assert err.value.clash is EXISTING


def test_practitioner_overlap_does_not_reveal_other_patient():
    with pytest.raises(DoubleBookingError) as err:
        book("2026-11-03T15:00", "2026-11-03T15:30", pat=NGUYEN)
    assert "Perera" not in err.value.message


@pytest.mark.parametrize("start, end", [("14:30", "15:00"), ("15:30", "16:00")])
def test_practitioner_touching_edges_are_allowed(start, end):
    book(f"2026-11-03T{start}", f"2026-11-03T{end}", pat=NGUYEN)


# --- check_no_double_booking(): patient --------------------------------------


def test_patient_overlap_with_another_practitioner_is_blocked():
    with pytest.raises(DoubleBookingError) as err:
        book("2026-11-03T15:15", "2026-11-03T15:45", prac=DR_CHEN)
    assert "Ruwan Perera" in err.value.message
    assert "MRN 000123" in err.value.message


def test_patient_inside_existing_appointment_is_blocked():
    with pytest.raises(DoubleBookingError):
        book("2026-11-03T15:10", "2026-11-03T15:25", prac=DR_CHEN)


@pytest.mark.parametrize("start, end", [("14:30", "15:00"), ("15:30", "16:00")])
def test_patient_touching_edges_are_allowed(start, end):
    book(f"2026-11-03T{start}", f"2026-11-03T{end}", prac=DR_CHEN)


# --- check_no_double_booking(): statuses and edits ---------------------------


def test_cancelled_appointment_does_not_block():
    cancelled = appointment(101, DR_SILVA.id, PERERA.id, "2026-11-03T15:00", 30, Status.CANCELLED)
    book("2026-11-03T15:00", "2026-11-03T15:30", existing=[cancelled])


@pytest.mark.parametrize("status", [Status.BOOKED, Status.COMPLETED, Status.NO_SHOW])
def test_other_statuses_block(status):
    existing = appointment(101, DR_SILVA.id, PERERA.id, "2026-11-03T15:00", 30, status)
    with pytest.raises(DoubleBookingError):
        book("2026-11-03T15:00", "2026-11-03T15:30", pat=NGUYEN, existing=[existing])


def test_editing_an_appointment_does_not_clash_with_itself():
    book("2026-11-03T15:15", "2026-11-03T15:45", exclude_id=EXISTING.id)


def test_editing_still_clashes_with_other_appointments():
    other = appointment(101, DR_SILVA.id, NGUYEN.id, "2026-11-03T16:00", 30)
    with pytest.raises(DoubleBookingError):
        book("2026-11-03T15:45", "2026-11-03T16:15", existing=[EXISTING, other], exclude_id=EXISTING.id)


def test_different_people_at_the_same_time_are_fine():
    book("2026-11-03T15:00", "2026-11-03T15:30", prac=DR_CHEN, pat=NGUYEN)


def test_requires_saved_people():
    with pytest.raises(ValueError):
        book("2026-11-03T10:00", "2026-11-03T10:30", prac=practitioner(None, provider_number="000999AA"))


# --- Same-name people: identity is the id, never the name -------------------

OTHER_DR_SILVA = practitioner(3, "Dr Anika Silva", "000104AD")  # same name and specialty
OTHER_PERERA = patient(3, "Ruwan Perera", "000133")  # same name and date of birth


def test_same_name_people_are_really_the_same_except_id():
    assert (DR_SILVA.full_name, DR_SILVA.specialty) == (OTHER_DR_SILVA.full_name, OTHER_DR_SILVA.specialty)
    assert (PERERA.full_name, PERERA.date_of_birth) == (OTHER_PERERA.full_name, OTHER_PERERA.date_of_birth)


def test_same_name_practitioner_is_not_double_booked():
    # The other Dr Silva is free at 15:00 even though "Dr Silva" is busy.
    book("2026-11-03T15:00", "2026-11-03T15:30", prac=OTHER_DR_SILVA, pat=NGUYEN)


def test_same_name_patient_is_not_double_booked():
    # The other Ruwan Perera is free at 15:00 even though "Ruwan Perera" is busy.
    book("2026-11-03T15:00", "2026-11-03T15:30", prac=DR_CHEN, pat=OTHER_PERERA)


def test_clash_message_names_the_right_practitioner_by_provider_number():
    busy_other_silva = appointment(101, OTHER_DR_SILVA.id, NGUYEN.id, "2026-11-03T09:00", 30)
    with pytest.raises(DoubleBookingError) as err:
        book("2026-11-03T09:00", "2026-11-03T09:30", prac=OTHER_DR_SILVA, pat=PERERA,
             existing=[EXISTING, busy_other_silva])
    assert "000104AD" in err.value.message
    assert "000101AA" not in err.value.message


def test_clash_message_names_the_right_patient_by_mrn():
    busy_other_perera = appointment(101, DR_CHEN.id, OTHER_PERERA.id, "2026-11-03T09:00", 30)
    with pytest.raises(DoubleBookingError) as err:
        book("2026-11-03T09:00", "2026-11-03T09:30", prac=OTHER_DR_SILVA, pat=OTHER_PERERA,
             existing=[EXISTING, busy_other_perera])
    assert "MRN 000133" in err.value.message
    assert "MRN 000123" not in err.value.message


def test_date_of_birth_is_written_in_words():
    # Day first or month first can't be confused: no leading zero, month as a word.
    assert patient(9, "Kamal Silva", "000134").model_copy(update={"date_of_birth": date(1998, 1, 3)}).label == (
        "Kamal Silva (MRN 000134, DOB 3 Jan 1998)"
    )


def test_labels_include_identifier():
    assert PERERA.label == "Ruwan Perera (MRN 000123, DOB 12 Apr 1968)"
    assert DR_SILVA.label == "Dr Anika Silva (Cardiology, Provider No. 000101AA)"


# --- validate_times() --------------------------------------------------------


def times(start: str, end: str, now=NOW):
    validate_times(sydney(start), sydney(end), now)


def test_valid_appointment_passes():
    times("2026-11-03T10:00", "2026-11-03T10:30")


@pytest.mark.parametrize("end", ["2026-11-03T10:00", "2026-11-03T09:45"])
def test_end_must_be_after_start(end):
    with pytest.raises(BookingValidationError, match="End time must be after"):
        times("2026-11-03T10:00", end)


@pytest.mark.parametrize("end, ok", [("10:14", False), ("10:15", True), ("12:00", True), ("12:01", False)])
def test_length_between_15_and_120_minutes(end, ok):
    if ok:
        times("2026-11-03T10:00", f"2026-11-03T{end}")
    else:
        with pytest.raises(BookingValidationError, match="between 15 and 120 minutes"):
            times("2026-11-03T10:00", f"2026-11-03T{end}")


def test_past_start_is_rejected():
    now = sydney("2026-11-03T10:01")
    with pytest.raises(BookingValidationError, match="in the past"):
        times("2026-11-03T10:00", "2026-11-03T10:30", now=now)


def test_start_exactly_now_is_allowed():
    now = sydney("2026-11-03T10:00")
    times("2026-11-03T10:00", "2026-11-03T10:30", now=now)


@pytest.mark.parametrize("day", ["2026-11-07", "2026-11-08"])  # Saturday, Sunday
def test_weekends_are_rejected(day):
    with pytest.raises(BookingValidationError, match="Monday to Friday"):
        times(f"{day}T10:00", f"{day}T10:30")


@pytest.mark.parametrize(
    "start, end, ok",
    [
        ("08:00", "08:30", True),  # opening time
        ("17:30", "18:00", True),  # ends exactly at closing
        ("07:45", "08:15", False),  # starts before opening
        ("17:45", "18:15", False),  # runs past closing
        ("18:00", "18:30", False),  # after closing
    ],
)
def test_clinic_hours(start, end, ok):
    if ok:
        times(f"2026-11-03T{start}", f"2026-11-03T{end}")
    else:
        with pytest.raises(BookingValidationError, match="clinic hours"):
            times(f"2026-11-03T{start}", f"2026-11-03T{end}")


def test_monday_8am_sydney_is_sunday_in_utc_but_allowed():
    # Clinic hours are checked in Sydney time, not UTC.
    start = sydney("2026-11-09T08:00")
    assert start.weekday() == 6  # Sunday 21:00 UTC
    validate_times(start, sydney("2026-11-09T08:30"), NOW)


def test_clinic_hours_in_winter_time():
    # 16 June is AEST (UTC+10). 17:30-18:00 Sydney must still be accepted.
    winter_now = sydney("2026-06-15T07:00")
    times("2026-06-16T17:30", "2026-06-16T18:00", now=winter_now)
    with pytest.raises(BookingValidationError, match="clinic hours"):
        times("2026-06-16T07:30", "2026-06-16T08:00", now=winter_now)


def test_naive_datetimes_are_a_programming_error():
    with pytest.raises(ValueError):
        validate_times(datetime(2026, 11, 3, 10), datetime(2026, 11, 3, 10, 30), NOW)


# --- Status rules -----------------------------------------------------------


@pytest.mark.parametrize("status", [Status.COMPLETED, Status.NO_SHOW])
def test_outcome_status_not_allowed_before_start(status):
    with pytest.raises(BookingValidationError, match="after it has started"):
        validate_status(status, sydney("2026-11-03T10:00"), now_utc=sydney("2026-11-03T09:59"))


@pytest.mark.parametrize("status", [Status.COMPLETED, Status.NO_SHOW])
def test_outcome_status_allowed_once_started(status):
    validate_status(status, sydney("2026-11-03T10:00"), now_utc=sydney("2026-11-03T10:00"))


@pytest.mark.parametrize("status", [Status.BOOKED, Status.CANCELLED])
def test_booked_and_cancelled_allowed_for_future(status):
    validate_status(status, sydney("2026-11-03T10:00"), now_utc=NOW)


def test_cancelled_appointment_cannot_be_edited():
    with pytest.raises(BookingValidationError, match="cancelled"):
        check_can_edit(Status.CANCELLED)


@pytest.mark.parametrize("status", [Status.BOOKED, Status.COMPLETED, Status.NO_SHOW])
def test_other_appointments_can_be_edited(status):
    check_can_edit(status)


def test_booked_appointment_can_be_cancelled():
    check_can_cancel(Status.BOOKED)


@pytest.mark.parametrize("status", [Status.COMPLETED, Status.NO_SHOW, Status.CANCELLED])
def test_only_booked_appointments_can_be_cancelled(status):
    with pytest.raises(BookingValidationError, match="Only booked appointments can be cancelled") as err:
        check_can_cancel(status)
    assert err.value.field == "status"


# --- Clinic days -------------------------------------------------------------


@pytest.mark.parametrize(
    "day, expected",
    [
        (date(2026, 10, 31), date(2026, 11, 2)),  # Saturday -> Monday
        (date(2026, 11, 1), date(2026, 11, 2)),  # Sunday -> Monday
        (date(2026, 11, 4), date(2026, 11, 4)),  # Wednesday stays
    ],
)
def test_next_clinic_day(day, expected):
    assert next_clinic_day(day) == expected


@pytest.mark.parametrize(
    "day, expected",
    [
        (date(2026, 11, 2), date(2026, 10, 30)),  # Monday -> Friday
        (date(2026, 11, 3), date(2026, 11, 2)),  # Tuesday -> Monday
    ],
)
def test_previous_clinic_day(day, expected):
    assert previous_clinic_day(day) == expected


# --- Error fields -------------------------------------------------------------


@pytest.mark.parametrize(
    "start, end, field",
    [
        ("2026-11-03T10:00", "2026-11-03T09:45", "end"),  # end before start
        ("2026-11-03T10:00", "2026-11-03T12:30", "end"),  # too long
        ("2026-11-07T10:00", "2026-11-07T10:30", "start"),  # Saturday
        ("2026-11-03T07:45", "2026-11-03T08:15", "start"),  # before opening
        ("2026-11-03T17:45", "2026-11-03T18:15", "end"),  # finishes after closing
    ],
)
def test_time_errors_name_the_field(start, end, field):
    with pytest.raises(BookingValidationError) as err:
        times(start, end)
    assert err.value.field == field


def test_clash_errors_name_the_field():
    with pytest.raises(DoubleBookingError) as practitioner_err:
        book("2026-11-03T15:00", "2026-11-03T15:30", pat=NGUYEN)
    with pytest.raises(DoubleBookingError) as patient_err:
        book("2026-11-03T15:00", "2026-11-03T15:30", prac=DR_CHEN)
    assert practitioner_err.value.field == "practitioner_id"
    assert patient_err.value.field == "patient_id"


# --- allowed_actions() ----------------------------------------------------------

START = sydney("2026-11-03T10:00")


@pytest.mark.parametrize(
    "status, now, expected",
    [
        (Status.BOOKED, sydney("2026-11-03T09:59"), ["edit", "cancel"]),
        (Status.BOOKED, sydney("2026-11-03T10:00"), ["edit", "cancel", "complete", "no_show"]),
        (Status.COMPLETED, sydney("2026-11-03T11:00"), ["edit", "no_show"]),  # can't be cancelled
        (Status.NO_SHOW, sydney("2026-11-03T11:00"), ["edit", "complete"]),  # can't be cancelled
        (Status.CANCELLED, sydney("2026-11-03T11:00"), []),
    ],
)
def test_allowed_actions(status, now, expected):
    assert allowed_actions(status, START, now) == expected


# --- Patients --------------------------------------------------------------------


def test_normalise_name():
    assert normalise_name("  Ruwan   Perera ") == "Ruwan Perera"


def test_validate_new_patient():
    validate_new_patient("Kamal Silva", date(1990, 4, 3), today=date(2026, 11, 2))
    validate_new_patient("Baby Silva", date(2026, 11, 2), today=date(2026, 11, 2))  # born today
    with pytest.raises(BookingValidationError) as err:
        validate_new_patient("Kamal Silva", date(2026, 11, 3), today=date(2026, 11, 2))
    assert err.value.field == "date_of_birth"
    with pytest.raises(BookingValidationError) as err:
        validate_new_patient("   ", date(1990, 4, 3), today=date(2026, 11, 2))
    assert err.value.field == "full_name"


def test_possible_duplicates_match_name_and_birthday_ignoring_case_and_spacing():
    existing = [PERERA, OTHER_PERERA, NGUYEN]  # both Pereras share a birthday
    matches = find_possible_duplicates(" ruwan  PERERA ", PERERA.date_of_birth, existing)
    assert [p.mrn for p in matches] == ["000123", "000133"]


def test_same_name_different_birthday_is_not_a_possible_duplicate():
    assert find_possible_duplicates("Ruwan Perera", date(1970, 1, 1), [PERERA, OTHER_PERERA]) == []


def test_different_name_same_birthday_is_not_a_possible_duplicate():
    assert find_possible_duplicates("Ruwan Pereira", PERERA.date_of_birth, [PERERA]) == []


@pytest.mark.parametrize(
    "day, expected",
    [(date(2026, 11, 6), True), (date(2026, 11, 7), False), (date(2026, 11, 8), False)],
)
def test_is_clinic_day(day, expected):
    assert is_clinic_day(day) is expected
