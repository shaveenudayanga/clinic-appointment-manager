"""Database tables."""

from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import DateTime, Index
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, Relationship, SQLModel


class UTCDateTime(TypeDecorator):
    """Stores aware datetimes as naive UTC (SQLite has no time zones) and reads them back as aware UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Refusing to store a naive datetime; convert it to UTC first")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=UTC) if value is not None else None


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AppointmentStatus(StrEnum):
    BOOKED = "booked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


# Names are not unique: two people can share a name (and a patient's date of
# birth). The id is the only identity used by the database and the API. The
# provider number / MRN is a unique human-readable identifier shown next to
# the name so staff can tell people apart.


class Practitioner(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    provider_number: str = Field(unique=True, index=True)
    full_name: str
    specialty: str

    @property
    def label(self) -> str:
        return f"{self.full_name} ({self.specialty}, Provider No. {self.provider_number})"


class Patient(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    mrn: str = Field(unique=True, index=True)  # medical record number
    full_name: str
    date_of_birth: date

    @property
    def label(self) -> str:
        return f"{self.full_name} (MRN {self.mrn}, DOB {self.date_of_birth:%d/%m/%Y})"


class Appointment(SQLModel, table=True):
    __table_args__ = (
        Index("ix_appointment_practitioner_start", "practitioner_id", "start_utc"),
        Index("ix_appointment_patient_start", "patient_id", "start_utc"),
    )

    id: int | None = Field(default=None, primary_key=True)
    practitioner_id: int = Field(foreign_key="practitioner.id")
    patient_id: int = Field(foreign_key="patient.id")
    start_utc: datetime = Field(sa_type=UTCDateTime, nullable=False)
    end_utc: datetime = Field(sa_type=UTCDateTime, nullable=False)
    status: AppointmentStatus = Field(default=AppointmentStatus.BOOKED)
    notes: str = ""
    created_at: datetime = Field(default_factory=_utc_now, sa_type=UTCDateTime, nullable=False)
    updated_at: datetime = Field(default_factory=_utc_now, sa_type=UTCDateTime, nullable=False)

    practitioner: Practitioner = Relationship()
    patient: Patient = Relationship()
