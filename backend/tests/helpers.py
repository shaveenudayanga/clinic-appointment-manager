"""Small builders so tests read like the rules they check."""

from datetime import date, datetime, timedelta

from app.models import Appointment, AppointmentStatus, Patient, Practitioner
from app.timezones import to_utc


def sydney(value: str) -> datetime:
    """'2026-11-03T15:00' in Sydney time, as aware UTC."""
    return to_utc(datetime.fromisoformat(value))


def practitioner(id: int, name: str = "Dr Anika Silva", provider_number: str | None = None) -> Practitioner:
    return Practitioner(
        id=id,
        full_name=name,
        specialty="Cardiology",
        provider_number=provider_number or f"{id:06d}AA",
    )


def patient(id: int, name: str = "Ruwan Perera", mrn: str | None = None) -> Patient:
    return Patient(id=id, full_name=name, date_of_birth=date(1968, 4, 12), mrn=mrn or f"{id:06d}")


def appointment(
    id: int,
    practitioner_id: int,
    patient_id: int,
    start: str,
    minutes: int = 30,
    status: AppointmentStatus = AppointmentStatus.BOOKED,
) -> Appointment:
    start_utc = sydney(start)
    return Appointment(
        id=id,
        practitioner_id=practitioner_id,
        patient_id=patient_id,
        start_utc=start_utc,
        end_utc=start_utc + timedelta(minutes=minutes),
        status=status,
    )
