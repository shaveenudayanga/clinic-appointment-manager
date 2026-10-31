"""HTTP routes. Thin: parse input, call services, shape output."""

from datetime import date, datetime

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app import rules, services
from app.config import settings
from app.db import get_session
from app.models import Appointment, Patient, Practitioner
from app.schemas import (
    AppointmentCreate,
    AppointmentRead,
    AppointmentUpdate,
    ClinicInfo,
    PatientRead,
    PractitionerRead,
)
from app.timezones import CLINIC_TZ, clinic_today, now_utc, to_clinic

router = APIRouter(prefix="/api")


def get_now() -> datetime:
    """The current time. A dependency so tests can freeze the clock."""
    return now_utc()


def to_read(appointment: Appointment) -> AppointmentRead:
    return AppointmentRead(
        id=appointment.id,
        practitioner=PractitionerRead(**appointment.practitioner.model_dump(), label=appointment.practitioner.label),
        patient=PatientRead(**appointment.patient.model_dump(), label=appointment.patient.label),
        start_utc=appointment.start_utc,
        end_utc=appointment.end_utc,
        start_local=to_clinic(appointment.start_utc),
        end_local=to_clinic(appointment.end_utc),
        status=appointment.status,
        notes=appointment.notes,
        created_at=appointment.created_at,
        updated_at=appointment.updated_at,
    )


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/clinic", response_model=ClinicInfo)
def clinic_info(now: datetime = Depends(get_now)) -> ClinicInfo:
    today = clinic_today(now)
    return ClinicInfo(
        timezone=CLINIC_TZ.key,
        today=today,
        default_date=rules.next_clinic_day(today),
        opens=f"{rules.CLINIC_OPEN:%H:%M}",
        closes=f"{rules.CLINIC_CLOSE:%H:%M}",
        min_minutes=int(rules.MIN_DURATION.total_seconds() // 60),
        max_minutes=int(rules.MAX_DURATION.total_seconds() // 60),
        nl_booking=bool(settings.gemini_api_key),
    )


@router.get("/practitioners", response_model=list[PractitionerRead])
def list_practitioners(session: Session = Depends(get_session)):
    practitioners = session.exec(select(Practitioner).order_by(Practitioner.full_name, Practitioner.id))
    return [PractitionerRead(**p.model_dump(), label=p.label) for p in practitioners]


@router.get("/patients", response_model=list[PatientRead])
def list_patients(session: Session = Depends(get_session)):
    patients = session.exec(select(Patient).order_by(Patient.full_name, Patient.id))
    return [PatientRead(**p.model_dump(), label=p.label) for p in patients]


@router.get("/appointments", response_model=list[AppointmentRead])
def list_appointments(
    date: date,
    practitioner_id: int | None = None,
    session: Session = Depends(get_session),
):
    """Appointments starting on `date` (a Sydney date), in time order, including cancelled ones."""
    return [to_read(a) for a in services.list_appointments_for_day(session, date, practitioner_id)]


@router.get("/appointments/{appointment_id}", response_model=AppointmentRead)
def get_appointment(appointment_id: int, session: Session = Depends(get_session)):
    return to_read(services.get_appointment(session, appointment_id))


@router.post("/appointments", response_model=AppointmentRead, status_code=201)
def create_appointment(
    data: AppointmentCreate,
    session: Session = Depends(get_session),
    now: datetime = Depends(get_now),
):
    return to_read(services.create_appointment(session, data, now))


@router.patch("/appointments/{appointment_id}", response_model=AppointmentRead)
def update_appointment(
    appointment_id: int,
    data: AppointmentUpdate,
    session: Session = Depends(get_session),
    now: datetime = Depends(get_now),
):
    return to_read(services.update_appointment(session, appointment_id, data, now))


@router.post("/appointments/{appointment_id}/cancel", response_model=AppointmentRead)
def cancel_appointment(
    appointment_id: int,
    session: Session = Depends(get_session),
    now: datetime = Depends(get_now),
):
    return to_read(services.cancel_appointment(session, appointment_id, now))
