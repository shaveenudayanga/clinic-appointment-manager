"""API tests: the HTTP layer applies the rules and returns clear errors.

Each test gets a fresh in-memory database with a few people, including a
same-name pair of practitioners and of patients, and a frozen clock.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api import get_now
from app.config import settings
from app.db import get_session
from app.main import app
from app.models import Patient, Practitioner
from tests.helpers import sydney

MONDAY_7AM = sydney("2026-11-02T07:00")
SATURDAY_10AM = sydney("2026-10-31T10:00")

# ids are assigned in this order
SILVA, OTHER_SILVA, CHEN = 1, 2, 3
PERERA, OTHER_PERERA, NGUYEN = 1, 2, 3


@pytest.fixture
def clock():
    return {"now": MONDAY_7AM}


@pytest.fixture
def client(clock):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            Practitioner(provider_number="000101AA", full_name="Dr Anika Silva", specialty="Cardiology"),
            Practitioner(provider_number="000104AD", full_name="Dr Anika Silva", specialty="Cardiology"),
            Practitioner(provider_number="000103AC", full_name="Dr Mei Chen", specialty="Endocrinology"),
            Patient(mrn="000123", full_name="Ruwan Perera", date_of_birth=date(1968, 4, 12)),
            Patient(mrn="000133", full_name="Ruwan Perera", date_of_birth=date(1968, 4, 12)),
            Patient(mrn="000128", full_name="Grace Nguyen", date_of_birth=date(1958, 2, 14)),
        ])
        session.commit()

    def session_override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_now] = lambda: clock["now"]
    # Not used as a context manager, so the startup seed does not touch the real database.
    yield TestClient(app)
    app.dependency_overrides.clear()


def book(client, start="2026-11-03T15:00", end="2026-11-03T15:30", practitioner=SILVA, patient=PERERA, **extra):
    body = {"practitioner_id": practitioner, "patient_id": patient, "start": start, "end": end, **extra}
    return client.post("/api/appointments", json=body)


# --- Basics ------------------------------------------------------------------


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_clinic_info_on_a_weekday(client, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    info = client.get("/api/clinic").json()
    assert info == {
        "name": "Demo Specialist Clinic",
        "timezone": "Australia/Sydney",
        "now_local": "2026-11-02T07:00:00+11:00",
        "today": "2026-11-02",
        "default_date": "2026-11-02",
        "opens": "08:00",
        "closes": "18:00",
        "min_minutes": 15,
        "max_minutes": 120,
        "nl_booking": False,
        "selected_date": "2026-11-02",
        "is_open": True,
        "previous_date": "2026-10-30",
        "next_date": "2026-11-03",
    }


@pytest.mark.parametrize(
    "selected, is_open, previous, next_",
    [
        ("2026-11-06", True, "2026-11-05", "2026-11-09"),  # Friday: next is Monday
        ("2026-11-07", False, "2026-11-06", "2026-11-09"),  # Saturday: closed
        ("2026-11-09", True, "2026-11-06", "2026-11-10"),  # Monday: previous is Friday
    ],
)
def test_clinic_info_for_a_chosen_date(client, selected, is_open, previous, next_):
    info = client.get("/api/clinic", params={"date": selected}).json()
    assert (info["selected_date"], info["is_open"], info["previous_date"], info["next_date"]) == (
        selected, is_open, previous, next_,
    )


def test_clinic_default_date_skips_the_weekend(client, clock):
    clock["now"] = SATURDAY_10AM
    info = client.get("/api/clinic").json()
    assert (info["today"], info["default_date"]) == ("2026-10-31", "2026-11-02")


def test_nl_booking_flag_follows_api_key(client, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    assert client.get("/api/clinic").json()["nl_booking"] is True


def test_people_lists_include_same_name_records_with_labels(client):
    practitioners = client.get("/api/practitioners").json()
    patients = client.get("/api/patients").json()
    silvas = [p for p in practitioners if p["full_name"] == "Dr Anika Silva"]
    pereras = [p for p in patients if p["full_name"] == "Ruwan Perera"]
    assert [p["label"] for p in silvas] == [
        "Dr Anika Silva (Cardiology, Provider No. 000101AA)",
        "Dr Anika Silva (Cardiology, Provider No. 000104AD)",
    ]
    assert [p["label"] for p in pereras] == [
        "Ruwan Perera (MRN 000123, DOB 12/04/1968)",
        "Ruwan Perera (MRN 000133, DOB 12/04/1968)",
    ]


# --- Create ------------------------------------------------------------------


def test_create_returns_utc_and_sydney_times(client):
    response = book(client, notes="Follow-up")
    assert response.status_code == 201
    body = response.json()
    assert body["start_utc"] == "2026-11-03T04:00:00Z"
    assert body["start_local"] == "2026-11-03T15:00:00+11:00"
    assert body["end_local"] == "2026-11-03T15:30:00+11:00"
    assert body["status"] == "booked"
    assert body["notes"] == "Follow-up"
    assert body["practitioner"]["provider_number"] == "000101AA"
    assert body["patient"]["label"] == "Ruwan Perera (MRN 000123, DOB 12/04/1968)"


def test_create_accepts_a_time_with_an_offset(client):
    body = book(client, start="2026-11-03T04:00:00Z", end="2026-11-03T04:30:00Z").json()
    assert body["start_local"] == "2026-11-03T15:00:00+11:00"


def test_practitioner_double_booking_returns_409(client):
    book(client)
    response = book(client, start="2026-11-03T15:15", end="2026-11-03T15:45", patient=NGUYEN)
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Dr Anika Silva (Cardiology, Provider No. 000101AA) already has an appointment "
        "from Tue 3 Nov 15:00 to 15:30."
    )


def test_patient_double_booking_returns_409(client):
    book(client)
    response = book(client, start="2026-11-03T15:15", end="2026-11-03T15:45", practitioner=CHEN)
    assert response.status_code == 409
    assert "Ruwan Perera (MRN 000123" in response.json()["detail"]


def test_same_name_people_can_be_booked_at_the_same_time(client):
    assert book(client).status_code == 201
    assert book(client, practitioner=OTHER_SILVA, patient=OTHER_PERERA).status_code == 201


def test_touching_appointments_are_allowed(client):
    book(client)
    assert book(client, start="2026-11-03T15:30", end="2026-11-03T16:00", patient=NGUYEN).status_code == 201


@pytest.mark.parametrize(
    "start, end, message",
    [
        ("2026-11-02T06:00", "2026-11-02T06:30", "in the past"),
        ("2026-11-07T10:00", "2026-11-07T10:30", "Monday to Friday"),
        ("2026-11-03T17:45", "2026-11-03T18:15", "clinic hours"),
        ("2026-11-03T10:00", "2026-11-03T10:10", "between 15 and 120 minutes"),
        ("2026-11-03T10:00", "2026-11-03T09:30", "End time must be after"),
    ],
)
def test_invalid_times_return_422_with_message(client, start, end, message):
    response = book(client, start=start, end=end)
    assert response.status_code == 422
    assert message in response.json()["detail"]


def test_unknown_practitioner_returns_404(client):
    response = book(client, practitioner=99)
    assert response.status_code == 404
    assert response.json()["detail"] == "Practitioner 99 not found."


def test_malformed_body_returns_readable_422(client):
    response = client.post("/api/appointments", json={"practitioner_id": SILVA, "patient_id": PERERA})
    assert response.status_code == 422
    assert response.json()["detail"] == "start: Field required; end: Field required"


# --- Cancel ------------------------------------------------------------------


def test_cancel_keeps_the_record_and_frees_the_slot(client):
    appointment_id = book(client).json()["id"]
    response = client.post(f"/api/appointments/{appointment_id}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert client.get(f"/api/appointments/{appointment_id}").json()["status"] == "cancelled"
    assert book(client, patient=NGUYEN).status_code == 201


def test_cancelled_appointment_cannot_be_changed(client):
    appointment_id = book(client).json()["id"]
    client.post(f"/api/appointments/{appointment_id}/cancel")
    for response in (
        client.post(f"/api/appointments/{appointment_id}/cancel"),
        client.patch(f"/api/appointments/{appointment_id}", json={"notes": "x"}),
        client.patch(f"/api/appointments/{appointment_id}", json={"status": "booked"}),
    ):
        assert response.status_code == 422
        assert "cancelled" in response.json()["detail"]


# --- Edit --------------------------------------------------------------------


def test_edit_can_overlap_its_own_old_time(client):
    appointment_id = book(client).json()["id"]
    response = client.patch(
        f"/api/appointments/{appointment_id}", json={"start": "2026-11-03T15:15", "end": "2026-11-03T15:45"}
    )
    assert response.status_code == 200
    assert response.json()["start_local"] == "2026-11-03T15:15:00+11:00"


def test_edit_into_another_appointment_returns_409(client):
    book(client)
    other_id = book(client, start="2026-11-03T16:00", end="2026-11-03T16:30", patient=NGUYEN).json()["id"]
    response = client.patch(f"/api/appointments/{other_id}", json={"start": "2026-11-03T15:15"})
    assert response.status_code == 409


def test_edit_changing_patient_checks_the_new_patient(client):
    book(client, practitioner=CHEN, patient=NGUYEN)
    appointment_id = book(client).json()["id"]
    response = client.patch(f"/api/appointments/{appointment_id}", json={"patient_id": NGUYEN})
    assert response.status_code == 409
    assert "Grace Nguyen (MRN 000128" in response.json()["detail"]


def test_edit_runs_time_validation(client):
    appointment_id = book(client).json()["id"]
    response = client.patch(f"/api/appointments/{appointment_id}", json={"end": "2026-11-03T18:30"})
    assert response.status_code == 422


def test_outcome_status_only_after_start(client, clock):
    appointment_id = book(client).json()["id"]
    early = client.patch(f"/api/appointments/{appointment_id}", json={"status": "completed"})
    assert early.status_code == 422

    clock["now"] = sydney("2026-11-03T15:40")  # the appointment is now in the past
    for status in ("no_show", "completed"):
        response = client.patch(f"/api/appointments/{appointment_id}", json={"status": status})
        assert response.status_code == 200
        assert response.json()["status"] == status


def test_past_appointment_cannot_be_moved(client, clock):
    appointment_id = book(client).json()["id"]
    clock["now"] = sydney("2026-11-03T16:00")
    response = client.patch(f"/api/appointments/{appointment_id}", json={"start": "2026-11-03T15:05"})
    assert response.status_code == 422
    assert "in the past" in response.json()["detail"]


def test_get_unknown_appointment_returns_404(client):
    assert client.get("/api/appointments/999").status_code == 404


# --- Day view ----------------------------------------------------------------


def test_day_view_is_sorted_and_filtered_by_sydney_date(client):
    book(client, start="2026-11-03T15:00", end="2026-11-03T15:30")
    book(client, start="2026-11-03T08:00", end="2026-11-03T08:30", patient=NGUYEN)  # Mon 21:00 UTC
    book(client, start="2026-11-03T10:00", end="2026-11-03T10:30", practitioner=OTHER_SILVA)
    book(client, start="2026-11-04T09:00", end="2026-11-04T09:30")
    cancelled_id = book(client, start="2026-11-03T12:00", end="2026-11-03T12:30").json()["id"]
    client.post(f"/api/appointments/{cancelled_id}/cancel")

    rows = client.get("/api/appointments", params={"date": "2026-11-03", "practitioner_id": SILVA}).json()

    assert [(r["start_local"][11:16], r["status"]) for r in rows] == [
        ("08:00", "booked"),
        ("12:00", "cancelled"),
        ("15:00", "booked"),
    ]
    assert all(r["practitioner"]["id"] == SILVA for r in rows)


def test_day_view_requires_a_date(client):
    assert client.get("/api/appointments").status_code == 422


# --- Errors point at the field they are about --------------------------------


@pytest.mark.parametrize(
    "kwargs, field",
    [
        ({"start": "2026-11-02T06:00", "end": "2026-11-02T06:30"}, "start"),  # past
        ({"start": "2026-11-03T07:30", "end": "2026-11-03T08:00"}, "start"),  # before opening
        ({"start": "2026-11-03T17:45", "end": "2026-11-03T18:15"}, "end"),  # finishes after closing
        ({"start": "2026-11-03T10:00", "end": "2026-11-03T10:10"}, "end"),  # too short
        ({"practitioner": 99}, "practitioner_id"),
        ({"patient": 99}, "patient_id"),
    ],
)
def test_errors_name_the_field(client, kwargs, field):
    body = book(client, **kwargs).json()
    assert body["field"] == field
    assert body["detail"]


def test_clash_errors_name_the_field(client):
    book(client)
    practitioner_clash = book(client, patient=NGUYEN).json()
    patient_clash = book(client, practitioner=CHEN).json()
    assert (practitioner_clash["code"], practitioner_clash["field"]) == ("double_booking", "practitioner_id")
    assert (patient_clash["code"], patient_clash["field"]) == ("double_booking", "patient_id")


def test_malformed_body_names_the_first_field(client):
    body = client.post("/api/appointments", json={"practitioner_id": SILVA, "patient_id": PERERA}).json()
    assert (body["code"], body["field"]) == ("invalid", "start")


# --- Allowed actions -----------------------------------------------------------


def test_allowed_actions_follow_the_rules(client, clock):
    appointment_id = book(client).json()["id"]
    assert client.get(f"/api/appointments/{appointment_id}").json()["allowed_actions"] == ["edit", "cancel"]

    clock["now"] = sydney("2026-11-03T15:05")
    assert client.get(f"/api/appointments/{appointment_id}").json()["allowed_actions"] == [
        "edit", "cancel", "complete", "no_show",
    ]

    completed = client.patch(f"/api/appointments/{appointment_id}", json={"status": "completed"}).json()
    assert completed["allowed_actions"] == ["edit", "cancel", "no_show"]

    cancelled = client.post(f"/api/appointments/{appointment_id}/cancel").json()
    assert cancelled["allowed_actions"] == []


# --- Patient search ------------------------------------------------------------


def search(client, q):
    return [p["mrn"] for p in client.get("/api/patients", params={"q": q}).json()]


def test_search_by_name_returns_every_same_name_patient(client):
    assert search(client, "perera") == ["000123", "000133"]
    assert search(client, "ruwan PERERA") == ["000123", "000133"]
    assert search(client, "perera ruwan") == ["000123", "000133"]  # word order doesn't matter


def test_search_by_mrn(client):
    assert search(client, "000128") == ["000128"]


@pytest.mark.parametrize("q", ["12/04/1968", "1968-04-12"])
def test_search_by_date_of_birth(client, q):
    assert search(client, q) == ["000123", "000133"]


def test_search_with_no_match_is_empty(client):
    assert search(client, "kamal silva") == []


def test_search_treats_wildcards_literally(client):
    assert search(client, "%") == []


def test_empty_search_lists_everyone(client):
    assert len(search(client, "")) == 3


# --- Patient registration ------------------------------------------------------


def register(client, full_name="Kamal Silva", date_of_birth="1990-04-03", **extra):
    return client.post("/api/patients", json={"full_name": full_name, "date_of_birth": date_of_birth, **extra})


def test_register_assigns_the_next_mrn(client):
    response = register(client)
    assert response.status_code == 201
    assert response.json() == {
        "id": 4,
        "mrn": "000134",
        "full_name": "Kamal Silva",
        "date_of_birth": "1990-04-03",
        "label": "Kamal Silva (MRN 000134, DOB 03/04/1990)",
    }
    assert register(client, full_name="Asha Silva").json()["mrn"] == "000135"


def test_register_tidies_spacing_in_the_name(client):
    assert register(client, full_name="  Kamal   Silva ").json()["full_name"] == "Kamal Silva"


def test_register_same_name_and_birthday_returns_matches(client):
    response = register(client, full_name="ruwan  perera", date_of_birth="1968-04-12")
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "possible_duplicate"
    assert body["detail"] == "2 patients with this name and date of birth already exist."
    assert [m["label"] for m in body["matches"]] == [
        "Ruwan Perera (MRN 000123, DOB 12/04/1968)",
        "Ruwan Perera (MRN 000133, DOB 12/04/1968)",
    ]
    assert search(client, "perera") == ["000123", "000133"]  # nothing was saved


def test_register_anyway_creates_a_new_patient(client):
    response = register(client, full_name="Ruwan Perera", date_of_birth="1968-04-12", allow_duplicate=True)
    assert response.status_code == 201
    assert response.json()["mrn"] == "000134"
    assert search(client, "perera") == ["000123", "000133", "000134"]


def test_same_name_different_birthday_is_not_a_duplicate(client):
    assert register(client, full_name="Ruwan Perera", date_of_birth="1970-01-01").status_code == 201


def test_register_rejects_future_birth_date(client):
    body = register(client, date_of_birth="2026-11-03").json()
    assert (body["field"], body["detail"]) == ("date_of_birth", "Date of birth can't be in the future.")


def test_register_rejects_blank_name(client):
    body = register(client, full_name="   ").json()
    assert body["field"] == "full_name"
