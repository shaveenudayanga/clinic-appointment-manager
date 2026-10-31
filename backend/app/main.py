"""FastAPI application. Run with: uvicorn app.main:app --reload (from backend/)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import patient_read, router
from app.config import settings
from app.rules import BookingValidationError, DoubleBookingError
from app.seed import seed_if_empty
from app.services import NotFoundError, PossibleDuplicateError


@asynccontextmanager
async def lifespan(_app: FastAPI):
    seed_if_empty()  # a fresh clone works without a separate seed step
    yield


app = FastAPI(title="Clinic Appointments API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


# Every error response has the same shape:
# {"detail": "<message for the user>", "code": "<kind>", "field": "<request field or null>"}


def error(status: int, code: str, detail: str, field: str | None = None, **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail, "code": code, "field": field, **extra})


@app.exception_handler(DoubleBookingError)
def handle_double_booking(_request: Request, exc: DoubleBookingError):
    return error(409, "double_booking", exc.message, exc.field)


@app.exception_handler(BookingValidationError)
def handle_booking_validation(_request: Request, exc: BookingValidationError):
    return error(422, "invalid", exc.message, exc.field)


@app.exception_handler(NotFoundError)
def handle_not_found(_request: Request, exc: NotFoundError):
    return error(404, "not_found", exc.message, exc.field)


@app.exception_handler(PossibleDuplicateError)
def handle_possible_duplicate(_request: Request, exc: PossibleDuplicateError):
    matches = [patient_read(p).model_dump(mode="json") for p in exc.matches]
    return error(409, "possible_duplicate", exc.message, matches=matches)


@app.exception_handler(RequestValidationError)
def handle_request_validation(_request: Request, exc: RequestValidationError):
    problems, fields = [], []
    for err in exc.errors():
        field = ".".join(str(part) for part in err["loc"] if part not in ("body", "query", "path"))
        fields.append(field)
        problems.append(f"{field}: {err['msg']}" if field else err["msg"])
    return error(422, "invalid", "; ".join(problems), fields[0] if fields else None)
