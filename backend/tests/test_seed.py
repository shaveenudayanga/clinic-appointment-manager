"""The seed data must obey the booking rules and always land on clinic days."""

from datetime import UTC, date, datetime

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Appointment, AppointmentStatus, Patient, Practitioner
from app.rules import check_no_double_booking, validate_times
from app.seed import seed
from app.timezones import to_clinic


def seeded_session(now: datetime) -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    seed(session, now)
    return session


@pytest.mark.parametrize(
    "now, first_upcoming_day",
    [
        (datetime(2026, 10, 30, 23, 0, tzinfo=UTC), date(2026, 11, 2)),  # Saturday 10:00 Sydney -> Monday
        (datetime(2026, 11, 1, 23, 0, tzinfo=UTC), date(2026, 11, 2)),  # Monday 10:00 Sydney -> today
    ],
)
def test_upcoming_appointments_start_on_a_clinic_day(now, first_upcoming_day):
    session = seeded_session(now)
    booked = session.exec(select(Appointment).where(Appointment.status == AppointmentStatus.BOOKED)).all()
    assert min(to_clinic(a.start_utc).date() for a in booked) == first_upcoming_day


def test_seed_data_obeys_the_rules():
    session = seeded_session(datetime(2026, 10, 30, 23, 0, tzinfo=UTC))
    practitioners = {p.id: p for p in session.exec(select(Practitioner))}
    patients = {p.id: p for p in session.exec(select(Patient))}
    appointments = session.exec(select(Appointment)).all()
    long_ago = datetime(2000, 1, 1, tzinfo=UTC)

    for appt in appointments:
        validate_times(appt.start_utc, appt.end_utc, now_utc=long_ago)
        if appt.status != AppointmentStatus.CANCELLED:
            check_no_double_booking(
                start_utc=appt.start_utc,
                end_utc=appt.end_utc,
                practitioner=practitioners[appt.practitioner_id],
                patient=patients[appt.patient_id],
                existing=appointments,
                exclude_id=appt.id,
            )


def test_seed_contains_same_name_pairs_with_distinct_identifiers():
    session = seeded_session(datetime(2026, 10, 30, 23, 0, tzinfo=UTC))
    silvas = session.exec(select(Practitioner).where(Practitioner.full_name == "Dr Anika Silva")).all()
    pereras = session.exec(select(Patient).where(Patient.full_name == "Ruwan Perera")).all()
    assert len(silvas) == 2 and len({p.provider_number for p in silvas}) == 2
    assert len(pereras) == 2 and len({p.mrn for p in pereras}) == 2
    assert pereras[0].date_of_birth == pereras[1].date_of_birth
