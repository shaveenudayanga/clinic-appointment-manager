"""Fake demo data. All names are invented; there is no real personal data here.

Appointments are placed relative to today so the app always has something to
show: the previous clinic day (completed, no-show, cancelled), the current or
next clinic day, and the clinic day after that.

Run `python -m app.seed` from backend/ to wipe and re-seed the database.
"""

from datetime import date, datetime, time, timedelta

from sqlmodel import Session, SQLModel, select

from app.db import create_tables, engine
from app.models import Appointment, AppointmentStatus, Patient, Practitioner
from app.rules import check_no_double_booking, next_clinic_day, previous_clinic_day
from app.timezones import CLINIC_TZ, clinic_today, now_utc, to_utc

# Provider numbers and MRNs are made up. Two pairs share a name on purpose,
# so the app has to tell people apart by id and show the identifier:
# - two "Dr Anika Silva", both cardiologists
# - two "Ruwan Perera", with the same date of birth
PRACTITIONERS = [
    # (provider number, name, specialty)
    ("000101AA", "Dr Anika Silva", "Cardiology"),
    ("000102AB", "Dr James Whitfield", "Dermatology"),
    ("000103AC", "Dr Mei Chen", "Endocrinology"),
    ("000104AD", "Dr Anika Silva", "Cardiology"),
]

PATIENTS = [
    # (MRN, name, date of birth)
    ("000123", "Ruwan Perera", date(1968, 4, 12)),
    ("000124", "Olivia Thompson", date(1985, 9, 3)),
    ("000125", "Liam O'Connor", date(1992, 1, 27)),
    ("000126", "Priya Raman", date(1979, 6, 18)),
    ("000127", "Noah Williams", date(2001, 11, 5)),
    ("000128", "Grace Nguyen", date(1958, 2, 14)),
    ("000129", "Ethan Brown", date(1990, 7, 30)),
    ("000130", "Chloe Martin", date(1974, 12, 9)),
    ("000131", "Lucas Fernando", date(1983, 3, 21)),
    ("000132", "Isla Robinson", date(1996, 8, 16)),
    ("000133", "Ruwan Perera", date(1968, 4, 12)),
]

# (day, practitioner index, patient index, start "HH:MM", minutes, status)
# day: -1 = previous clinic day, 0 = today or next clinic day, 1 = the clinic day after
APPOINTMENTS = [
    (-1, 0, 0, "09:00", 30, AppointmentStatus.COMPLETED),
    (-1, 0, 1, "09:30", 30, AppointmentStatus.NO_SHOW),
    (-1, 1, 2, "10:00", 45, AppointmentStatus.COMPLETED),
    (-1, 2, 3, "14:00", 60, AppointmentStatus.CANCELLED),
    (0, 0, 4, "09:00", 30, AppointmentStatus.BOOKED),
    (0, 0, 5, "09:30", 30, AppointmentStatus.BOOKED),  # touches the 09:00 slot, allowed
    (0, 0, 6, "10:30", 60, AppointmentStatus.BOOKED),
    (0, 0, 7, "14:00", 30, AppointmentStatus.CANCELLED),
    (0, 0, 8, "14:00", 30, AppointmentStatus.BOOKED),  # re-uses the cancelled slot
    (0, 0, 9, "16:00", 45, AppointmentStatus.BOOKED),
    (0, 1, 1, "08:30", 30, AppointmentStatus.BOOKED),
    (0, 1, 0, "11:00", 30, AppointmentStatus.BOOKED),
    (0, 1, 3, "13:00", 60, AppointmentStatus.BOOKED),
    (0, 2, 2, "10:00", 30, AppointmentStatus.BOOKED),
    (0, 2, 4, "15:00", 60, AppointmentStatus.BOOKED),
    (1, 0, 0, "11:00", 30, AppointmentStatus.BOOKED),
    (1, 0, 3, "13:30", 45, AppointmentStatus.BOOKED),
    (1, 1, 5, "09:00", 20, AppointmentStatus.BOOKED),
    (1, 2, 6, "08:00", 60, AppointmentStatus.BOOKED),
    (1, 2, 7, "17:00", 60, AppointmentStatus.BOOKED),
    # Same-name people: both Dr Silvas and both Ruwan Pereras are busy at the
    # same times without clashing, because they are different records.
    (0, 3, 10, "09:00", 30, AppointmentStatus.BOOKED),
    (0, 3, 0, "14:00", 30, AppointmentStatus.BOOKED),
    (1, 3, 10, "11:00", 30, AppointmentStatus.BOOKED),
]


def seed(session: Session, now: datetime) -> None:
    practitioners = [
        Practitioner(provider_number=num, full_name=name, specialty=spec)
        for num, name, spec in PRACTITIONERS
    ]
    patients = [Patient(mrn=mrn, full_name=name, date_of_birth=dob) for mrn, name, dob in PATIENTS]
    session.add_all(practitioners + patients)
    session.flush()  # assigns ids

    anchor = next_clinic_day(clinic_today(now))
    days = {
        -1: previous_clinic_day(anchor),
        0: anchor,
        1: next_clinic_day(anchor + timedelta(days=1)),
    }

    created: list[Appointment] = []
    for day, prac_i, pat_i, start, minutes, status in APPOINTMENTS:
        local_start = datetime.combine(days[day], time.fromisoformat(start))
        start_utc = to_utc(local_start)
        end_utc = to_utc(local_start + timedelta(minutes=minutes))
        practitioner, patient = practitioners[prac_i], patients[pat_i]
        appointment = Appointment(
            practitioner_id=practitioner.id,
            patient_id=patient.id,
            start_utc=start_utc,
            end_utc=end_utc,
            status=status,
        )
        # Seed data skips the "not in the past" rule but must never double-book.
        if status != AppointmentStatus.CANCELLED:
            check_no_double_booking(
                start_utc=start_utc,
                end_utc=end_utc,
                practitioner=practitioner,
                patient=patient,
                existing=created,
            )
        created.append(appointment)

    session.add_all(created)
    session.commit()


def seed_if_empty() -> None:
    """Used at app startup so a fresh clone works without a separate seed step."""
    create_tables()
    with Session(engine) as session:
        if session.exec(select(Practitioner)).first() is None:
            seed(session, now_utc())


def reset_and_seed() -> None:
    SQLModel.metadata.drop_all(engine)
    create_tables()
    with Session(engine) as session:
        seed(session, now_utc())


if __name__ == "__main__":
    reset_and_seed()
    print(f"Seeded {len(PRACTITIONERS)} practitioners, {len(PATIENTS)} patients and "
          f"{len(APPOINTMENTS)} appointments (clinic time zone: {CLINIC_TZ.key}).")
