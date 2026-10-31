"""Two simultaneous bookings for the same slot: exactly one must win."""

import threading
import time
from datetime import date

from sqlmodel import Session, SQLModel, create_engine

from app import rules, services
from app.models import Patient, Practitioner
from app.schemas import AppointmentCreate
from tests.helpers import sydney


def test_simultaneous_bookings_cannot_both_succeed(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'race.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Practitioner(provider_number="000101AA", full_name="Dr Anika Silva", specialty="Cardiology"))
        session.add(Patient(mrn="000123", full_name="Ruwan Perera", date_of_birth=date(1968, 4, 12)))
        session.add(Patient(mrn="000128", full_name="Grace Nguyen", date_of_birth=date(1958, 2, 14)))
        session.commit()

    # Slow down the clash check so both requests are "in flight" at once.
    original_check = rules.check_no_double_booking

    def slow_check(**kwargs):
        time.sleep(0.3)
        return original_check(**kwargs)

    monkeypatch.setattr(rules, "check_no_double_booking", slow_check)

    results: list[str] = []

    def attempt(patient_id: int):
        data = AppointmentCreate(
            practitioner_id=1, patient_id=patient_id, start="2026-11-03T15:00", end="2026-11-03T15:30"
        )
        with Session(engine) as session:
            try:
                services.create_appointment(session, data, now=sydney("2026-11-02T07:00"))
                results.append("booked")
            except rules.DoubleBookingError:
                results.append("clash")

    threads = [threading.Thread(target=attempt, args=(patient_id,)) for patient_id in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == ["booked", "clash"]
