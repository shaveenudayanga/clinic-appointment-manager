"""Natural-language booking. Gemini is never called: every test uses a fake
parser with a fixed answer, or a fake client that records the request."""

import json
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from app.api import get_booking_parser
from app.config import settings
from app.main import app
from app.nl_booking import (
    EMPTY_MESSAGE,
    TIMEOUT_MESSAGE,
    UNAVAILABLE_MESSAGE,
    UNUSABLE_MESSAGE,
    GeminiParser,
    ParsedBooking,
    PromptContext,
    build_instructions,
    match_people,
    name_words,
)
from tests.helpers import patient, practitioner, sydney
from tests.test_api import client, clock  # noqa: F401  (fixtures: in-memory DB with same-name people)

SENTENCE = "Book Mr Perera with Dr Silva next Tuesday at 3pm for 30 minutes"


def reply(**fields) -> str:
    base = dict(patient_name=None, practitioner_name=None, date=None, start_time=None, duration_minutes=None, notes=None)
    return json.dumps({**base, **fields})


class FakeParser:
    """Stands in for Gemini: returns a fixed reply (or raises) and records what it was asked."""

    def __init__(self, answer: str = "", error: Exception | None = None):
        self.answer, self.error, self.calls = answer, error, []

    def __call__(self, text, context):
        self.calls.append((text, context))
        if self.error:
            raise self.error
        return self.answer


@pytest.fixture
def use_parser():
    def install(parser):
        app.dependency_overrides[get_booking_parser] = lambda: parser
        return parser

    yield install
    app.dependency_overrides.pop(get_booking_parser, None)


def parse(client, text=SENTENCE):
    return client.post("/api/appointments/parse", json={"text": text})


# --- Names: several matches are all returned, none are reported, never a guess ---


def test_unique_names_are_matched(client, use_parser):
    use_parser(FakeParser(reply(patient_name="Grace Nguyen", practitioner_name="Dr Mei Chen")))
    body = parse(client, "Book Grace Nguyen with Dr Mei Chen").json()
    assert [p["mrn"] for p in body["patient"]["matches"]] == ["000128"]
    assert [p["provider_number"] for p in body["practitioner"]["matches"]] == ["000103AC"]


def test_ambiguous_names_return_every_match(client, use_parser):
    use_parser(FakeParser(reply(patient_name="Mr Perera", practitioner_name="Dr Silva")))
    body = parse(client).json()
    assert body["patient"]["query"] == "Mr Perera"
    assert [p["label"] for p in body["patient"]["matches"]] == [
        "Ruwan Perera (MRN 000123, DOB 12/04/1968)",
        "Ruwan Perera (MRN 000133, DOB 12/04/1968)",
    ]
    assert body["practitioner"]["query"] == "Dr Silva"
    assert [p["provider_number"] for p in body["practitioner"]["matches"]] == ["000101AA", "000104AD"]


def test_unknown_names_return_no_matches(client, use_parser):
    use_parser(FakeParser(reply(patient_name="Mr Kamal Fernando", practitioner_name="Dr Smith")))
    body = parse(client).json()
    assert body["patient"] == {"query": "Mr Kamal Fernando", "matches": []}
    assert body["practitioner"] == {"query": "Dr Smith", "matches": []}


def test_names_not_in_the_sentence_are_null(client, use_parser):
    use_parser(FakeParser(reply(date="2026-11-03", start_time="15:00")))
    body = parse(client, "Tuesday at 3pm").json()
    assert body["patient"] is None and body["practitioner"] is None


def test_a_partial_name_is_not_a_match():
    people = [patient(1, "Ruwan Perera", "000123")]
    assert match_people("Pere", people, lambda p: p.mrn) == []


def test_match_ignores_titles_case_and_order():
    people = [patient(1, "Ruwan Perera", "000123"), patient(2, "Grace Nguyen", "000128")]
    assert [p.mrn for p in match_people("mr PERERA ruwan", people, lambda p: p.mrn)] == ["000123"]


def test_match_by_mrn_or_provider_number():
    assert [p.mrn for p in match_people("000128", [patient(1), patient(2, mrn="000128")], lambda p: p.mrn)] == ["000128"]
    doctors = [practitioner(1, provider_number="000101AA"), practitioner(2, provider_number="000104AD")]
    assert [p.id for p in match_people("000104ad", doctors, lambda p: p.provider_number)] == [2]


def test_a_title_alone_matches_nobody():
    assert match_people("Dr", [practitioner(1)], lambda p: p.provider_number) == []
    assert name_words("Dr. Anika  Silva") == ["anika", "silva"]


# --- Dates: the model is told today's date and the clinic time zone ---------------


def test_next_tuesday_resolves_from_the_date_given_to_the_model(client, use_parser):
    # Monday 2 Nov 07:00 Sydney. The fake answers as the model should: Tuesday 3 Nov, 15:00.
    fake = use_parser(FakeParser(reply(patient_name="Mr Perera", practitioner_name="Dr Silva",
                                       date="2026-11-03", start_time="15:00", duration_minutes=30)))
    body = parse(client).json()
    assert (body["date"], body["start"], body["duration_minutes"]) == ("2026-11-03", "15:00", 30)

    text, context = fake.calls[0]
    assert text == SENTENCE
    assert context == PromptContext(today=date(2026, 11, 2), weekday="Monday", time="07:00", timezone="Australia/Sydney")


def test_today_is_the_clinic_date_not_the_utc_date():
    # 14:30 UTC on Monday 2 Nov is 01:30 on Tuesday 3 Nov in Sydney.
    context = PromptContext.at(datetime(2026, 11, 2, 14, 30, tzinfo=UTC))
    assert (context.today, context.weekday, context.time) == (date(2026, 11, 3), "Tuesday", "01:30")


def test_instructions_include_date_weekday_and_time_zone():
    text = build_instructions(PromptContext(date(2026, 11, 2), "Monday", "07:00", "Australia/Sydney"))
    assert "Monday 2026-11-02" in text and "Australia/Sydney" in text and "07:00" in text


# --- Privacy: only the sentence and the date context are sent ----------------------


def test_gemini_request_contains_only_the_sentence_and_date_context(client, use_parser):
    calls = []
    fake_client = SimpleNamespace(interactions=SimpleNamespace(
        create=lambda **kwargs: calls.append(kwargs) or SimpleNamespace(output_text=reply(patient_name="Mr Perera"))
    ))
    use_parser(GeminiParser(api_key="unused", model="test-model", client=fake_client))
    parse(client)

    request = calls[0]
    assert request["input"] == SENTENCE
    assert request["model"] == "test-model"
    assert request["store"] is False
    assert request["generation_config"] == {"temperature": 0}
    assert request["response_format"]["mime_type"] == "application/json"
    assert request["timeout"] == 15
    sent = json.dumps(request)
    for private in ("Ruwan", "Nguyen", "000123", "000128", "000101AA", "1968"):  # records in the test database
        assert private not in sent


# --- Untrusted output: anything that doesn't fit is rejected -------------------------


@pytest.mark.parametrize(
    "answer",
    [
        "not json",
        "",
        reply(start_time="3pm"),  # not HH:MM
        reply(start_time="25:00"),
        reply(date="next Tuesday"),  # not a date
        reply(duration_minutes="thirty"),
        reply(duration_minutes=-5),
        reply(patient_name="x" * 101),
        reply(patient_name="Mr Perera", appointment_id=7),  # unexpected field
        json.dumps(["Mr Perera"]),
    ],
)
def test_unusable_replies_are_rejected_with_a_plain_message(client, use_parser, answer):
    use_parser(FakeParser(answer))
    response = parse(client)
    assert response.status_code == 502
    assert response.json() == {"detail": UNUSABLE_MESSAGE, "code": "nl_failed", "field": None}


def test_a_reply_with_nothing_useful_is_reported(client, use_parser):
    use_parser(FakeParser(reply()))
    assert parse(client, "hello").json()["detail"] == EMPTY_MESSAGE


def test_timeout_gives_a_plain_message(client, use_parser):
    use_parser(FakeParser(error=TimeoutError()))
    response = parse(client)
    assert (response.status_code, response.json()["detail"]) == (502, TIMEOUT_MESSAGE)


def test_service_error_gives_a_plain_message(client, use_parser):
    use_parser(FakeParser(error=RuntimeError("quota exceeded")))
    response = parse(client)
    assert (response.status_code, response.json()["detail"]) == (502, UNAVAILABLE_MESSAGE)


def test_strict_model_accepts_a_good_reply():
    parsed = ParsedBooking.model_validate_json(reply(patient_name="  Mr Perera ", start_time="09:05", date="2026-11-03"))
    assert (parsed.patient_name, parsed.start_time, parsed.date) == ("Mr Perera", "09:05", date(2026, 11, 3))


# --- Never saves; hidden without a key ------------------------------------------------


def test_parsing_never_creates_an_appointment(client, use_parser):
    use_parser(FakeParser(reply(patient_name="Grace Nguyen", practitioner_name="Dr Mei Chen",
                                date="2026-11-03", start_time="15:00", duration_minutes=30)))
    assert parse(client).status_code == 200
    assert client.get("/api/appointments", params={"date": "2026-11-03"}).json() == []


def test_without_an_api_key_the_feature_is_off(client, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    assert client.get("/api/clinic").json()["nl_booking"] is False
    response = parse(client)
    assert response.status_code == 404
    assert response.json()["code"] == "nl_disabled"
    assert client.get("/api/practitioners").status_code == 200  # the rest still works


@pytest.mark.parametrize("text", ["", "x" * 301])
def test_sentence_length_is_checked(client, use_parser, text):
    use_parser(FakeParser(reply(patient_name="Mr Perera")))
    response = parse(client, text)
    assert response.status_code == 422
    assert response.json()["field"] == "text"


def test_real_sdk_sends_only_the_sentence_and_date_context():
    """Runs the real google-genai SDK against a fake HTTP transport (no network),
    to check the exact request body that would go to Google."""
    import httpx
    from google import genai
    from google.genai import types

    seen = {}

    def transport(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["body"] = str(request.url), json.loads(request.content)
        text = reply(patient_name="Mr Perera")
        return httpx.Response(200, json={"id": "t", "status": "completed",
                                         "steps": [{"type": "model_output", "content": [{"type": "text", "text": text}]}]})

    sdk = genai.Client(api_key="test-key", http_options=types.HttpOptions(
        httpx_client=httpx.Client(transport=httpx.MockTransport(transport))))
    raw = GeminiParser("test-key", "gemini-3.5-flash-lite", client=sdk)(SENTENCE, PromptContext.at(sydney("2026-11-02T07:00")))

    assert ParsedBooking.model_validate_json(raw).patient_name == "Mr Perera"
    assert seen["url"].endswith("/v1beta/interactions")
    body = seen["body"]
    assert sorted(body) == ["generation_config", "input", "model", "response_format", "store", "system_instruction"]
    assert body["input"] == SENTENCE
    assert body["store"] is False
    assert "Monday 2026-11-02" in body["system_instruction"]
