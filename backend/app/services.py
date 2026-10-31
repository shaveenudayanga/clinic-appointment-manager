"""Appointment operations: load data, apply app/rules.py, save.

This module decides *when* each rule runs; rules.py decides *what* the rule
is. Nothing here re-implements a rule.
"""

from datetime import date, datetime

from sqlalchemy import and_, or_, text
from sqlmodel import Session, select

from app import rules
from app.models import Appointment, AppointmentStatus, Patient, Practitioner
from app.schemas import AppointmentCreate, AppointmentUpdate, PatientCreate
from app.timezones import clinic_day_bounds_utc, clinic_today, to_clinic, to_utc


class NotFoundError(Exception):
    def __init__(self, message: str, field: rules.ErrorField | None = None):
        super().__init__(message)
        self.message = message
        self.field = field


class PossibleDuplicateError(Exception):
    """A patient with the same name and date of birth already exists."""

    def __init__(self, matches: list[Patient]):
        super().__init__("possible duplicate")
        self.matches = matches
        count = "A patient" if len(matches) == 1 else f"{len(matches)} patients"
        self.message = f"{count} with this name and date of birth already exist{'s' if len(matches) == 1 else ''}."


def create_appointment(session: Session, data: AppointmentCreate, now: datetime) -> Appointment:
    _begin_write(session)
    practitioner = get_practitioner(session, data.practitioner_id)
    patient = get_patient(session, data.patient_id)
    start_utc, end_utc = to_utc(data.start), to_utc(data.end)

    rules.validate_times(start_utc, end_utc, now)
    rules.check_no_double_booking(
        start_utc=start_utc,
        end_utc=end_utc,
        practitioner=practitioner,
        patient=patient,
        existing=_appointments_near(session, practitioner.id, patient.id, start_utc, end_utc),
    )

    appointment = Appointment(
        practitioner_id=practitioner.id,
        patient_id=patient.id,
        start_utc=start_utc,
        end_utc=end_utc,
        notes=data.notes,
        created_at=now,
        updated_at=now,
    )
    session.add(appointment)
    session.commit()
    session.refresh(appointment)
    return appointment


def update_appointment(
    session: Session, appointment_id: int, data: AppointmentUpdate, now: datetime
) -> Appointment:
    _begin_write(session)
    appointment = get_appointment(session, appointment_id)
    rules.check_can_edit(appointment.status)

    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    practitioner = get_practitioner(session, changes.get("practitioner_id", appointment.practitioner_id))
    patient = get_patient(session, changes.get("patient_id", appointment.patient_id))
    start_utc = to_utc(changes["start"]) if "start" in changes else appointment.start_utc
    end_utc = to_utc(changes["end"]) if "end" in changes else appointment.end_utc
    status = changes.get("status", appointment.status)

    # Time rules (including "not in the past") apply only when the time moves,
    # so staff can still record the outcome of an appointment that has passed.
    if (start_utc, end_utc) != (appointment.start_utc, appointment.end_utc):
        rules.validate_times(start_utc, end_utc, now)
    if status == AppointmentStatus.CANCELLED:
        rules.check_can_cancel(appointment.status)
    rules.validate_status(status, start_utc, now)
    if status in rules.BLOCKING_STATUSES:
        rules.check_no_double_booking(
            start_utc=start_utc,
            end_utc=end_utc,
            practitioner=practitioner,
            patient=patient,
            existing=_appointments_near(session, practitioner.id, patient.id, start_utc, end_utc),
            exclude_id=appointment.id,
        )

    appointment.practitioner_id = practitioner.id
    appointment.patient_id = patient.id
    appointment.start_utc = start_utc
    appointment.end_utc = end_utc
    appointment.status = status
    appointment.notes = changes.get("notes", appointment.notes)
    appointment.updated_at = now
    session.add(appointment)
    session.commit()
    session.refresh(appointment)
    return appointment


def cancel_appointment(session: Session, appointment_id: int, now: datetime) -> Appointment:
    """Cancelling only changes the status; the record is kept."""
    return update_appointment(
        session, appointment_id, AppointmentUpdate(status=AppointmentStatus.CANCELLED), now
    )


def list_appointments_for_day(
    session: Session, day: date, practitioner_id: int | None = None
) -> list[Appointment]:
    """Appointments starting on `day` (a Sydney date), in time order. Includes cancelled ones."""
    day_start, day_end = clinic_day_bounds_utc(day)
    query = select(Appointment).where(Appointment.start_utc >= day_start, Appointment.start_utc < day_end)
    if practitioner_id is not None:
        query = query.where(Appointment.practitioner_id == practitioner_id)
    return list(session.exec(query.order_by(Appointment.start_utc, Appointment.id)))


def get_appointment(session: Session, appointment_id: int) -> Appointment:
    appointment = session.get(Appointment, appointment_id)
    if appointment is None:
        raise NotFoundError(f"Appointment {appointment_id} not found.")
    return appointment


def get_practitioner(session: Session, practitioner_id: int) -> Practitioner:
    practitioner = session.get(Practitioner, practitioner_id)
    if practitioner is None:
        raise NotFoundError(f"Practitioner {practitioner_id} not found.", "practitioner_id")
    return practitioner


def get_patient(session: Session, patient_id: int) -> Patient:
    patient = session.get(Patient, patient_id)
    if patient is None:
        raise NotFoundError(f"Patient {patient_id} not found.", "patient_id")
    return patient


def search_patients(session: Session, query: str, limit: int = 20) -> list[Patient]:
    """Find patients by name (every word must appear), MRN, or date of birth
    (3 Jan 1998, 03/01/1998 day first, or 1998-01-03). An empty query returns everyone, up to `limit`."""
    query = query.strip()
    statement = select(Patient)
    if query:
        by_name = and_(*[Patient.full_name.icontains(word, autoescape=True) for word in query.split()])
        alternatives = [by_name, Patient.mrn.contains(query, autoescape=True)]
        dob = _parse_date(query)
        if dob is not None:
            alternatives.append(Patient.date_of_birth == dob)
        statement = statement.where(or_(*alternatives))
    return list(session.exec(statement.order_by(Patient.full_name, Patient.id).limit(limit)))


def register_patient(session: Session, data: PatientCreate, now: datetime) -> Patient:
    """Create a patient with the next free MRN.

    If a patient with the same name and date of birth exists, raise
    PossibleDuplicateError unless the caller confirmed with allow_duplicate.
    """
    _begin_write(session)
    full_name = rules.normalise_name(data.full_name)
    rules.validate_new_patient(full_name, data.date_of_birth, clinic_today(now))

    if not data.allow_duplicate:
        same_birthday = session.exec(select(Patient).where(Patient.date_of_birth == data.date_of_birth))
        matches = rules.find_possible_duplicates(full_name, data.date_of_birth, same_birthday)
        if matches:
            raise PossibleDuplicateError(matches)

    patient = Patient(mrn=_next_mrn(session), full_name=full_name, date_of_birth=data.date_of_birth)
    session.add(patient)
    session.commit()
    session.refresh(patient)
    return patient


def _next_mrn(session: Session) -> str:
    """One more than the highest numeric MRN, as six digits."""
    numbers = [int(mrn) for mrn in session.exec(select(Patient.mrn)) if mrn.isdigit()]
    return f"{max(numbers, default=0) + 1:06d}"


def _parse_date(text_value: str) -> date | None:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text_value, fmt).date()
        except ValueError:
            pass
    return None


def _appointments_near(
    session: Session, practitioner_id: int, patient_id: int, start_utc: datetime, end_utc: datetime
) -> list[Appointment]:
    """All appointments for this practitioner or patient on the same clinic day(s).

    This is deliberately a superset of possible clashes; rules.py decides
    which of them actually clash (status and overlap).
    """
    window_start, _ = clinic_day_bounds_utc(to_clinic(start_utc).date())
    _, window_end = clinic_day_bounds_utc(to_clinic(end_utc).date())
    query = select(Appointment).where(
        or_(Appointment.practitioner_id == practitioner_id, Appointment.patient_id == patient_id),
        Appointment.start_utc < window_end,
        Appointment.end_utc > window_start,
    )
    return list(session.exec(query))


def _begin_write(session: Session) -> None:
    """Take SQLite's write lock before reading, so the clash check and the save
    happen together. Two simultaneous bookings for the same slot are then
    handled one after the other and the second one sees the first."""
    session.execute(text("BEGIN IMMEDIATE"))
