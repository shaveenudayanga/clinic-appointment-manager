"""Request and response shapes for the API.

Request times (`start`, `end`) are Sydney wall-clock times without an offset,
e.g. "2026-11-03T15:00". A time with an offset (e.g. "...Z") is also accepted
and converted. Responses give both UTC and Sydney times with explicit offsets.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models import AppointmentStatus


class PractitionerRead(BaseModel):
    id: int
    provider_number: str
    full_name: str
    specialty: str
    label: str


class PatientRead(BaseModel):
    id: int
    mrn: str
    full_name: str
    date_of_birth: date
    label: str


class PatientCreate(BaseModel):
    full_name: str = Field(max_length=100)
    date_of_birth: date
    allow_duplicate: bool = Field(
        default=False,
        description="Register even if a patient with the same name and date of birth exists",
    )


class AppointmentCreate(BaseModel):
    practitioner_id: int
    patient_id: int
    start: datetime = Field(description="Sydney time, e.g. 2026-11-03T15:00")
    end: datetime = Field(description="Sydney time, e.g. 2026-11-03T15:30")
    notes: str = Field(default="", max_length=500)


class AppointmentUpdate(BaseModel):
    """Only the fields sent are changed. Sending null for a field is the same as leaving it out."""

    practitioner_id: int | None = None
    patient_id: int | None = None
    start: datetime | None = Field(default=None, description="Sydney time")
    end: datetime | None = Field(default=None, description="Sydney time")
    notes: str | None = Field(default=None, max_length=500)
    status: AppointmentStatus | None = None


class AppointmentRead(BaseModel):
    id: int
    practitioner: PractitionerRead
    patient: PatientRead
    start_utc: datetime
    end_utc: datetime
    start_local: datetime
    end_local: datetime
    status: AppointmentStatus
    allowed_actions: list[str] = Field(description="Any of: edit, cancel, complete, no_show")
    notes: str
    created_at: datetime
    updated_at: datetime


class ClinicInfo(BaseModel):
    name: str
    timezone: str
    today: date
    default_date: date = Field(description="Today if the clinic is open, otherwise the next clinic day")
    opens: str
    closes: str
    min_minutes: int
    max_minutes: int
    nl_booking: bool
    # About the requested date (or default_date if none was given)
    selected_date: date
    is_open: bool
    previous_date: date = Field(description="The clinic day before selected_date")
    next_date: date = Field(description="The clinic day after selected_date")
