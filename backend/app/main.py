"""FastAPI application. Run with: uvicorn app.main:app --reload (from backend/)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import router
from app.config import settings
from app.rules import BookingValidationError, DoubleBookingError
from app.seed import seed_if_empty
from app.services import NotFoundError


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


# Every error response has the same shape: {"detail": "<message for the user>"}.


@app.exception_handler(DoubleBookingError)
def handle_double_booking(_request: Request, exc: DoubleBookingError):
    return JSONResponse(status_code=409, content={"detail": exc.message})


@app.exception_handler(BookingValidationError)
def handle_booking_validation(_request: Request, exc: BookingValidationError):
    return JSONResponse(status_code=422, content={"detail": exc.message})


@app.exception_handler(NotFoundError)
def handle_not_found(_request: Request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": exc.message})


@app.exception_handler(RequestValidationError)
def handle_request_validation(_request: Request, exc: RequestValidationError):
    problems = []
    for error in exc.errors():
        field = ".".join(str(part) for part in error["loc"] if part != "body")
        problems.append(f"{field}: {error['msg']}" if field else error["msg"])
    return JSONResponse(status_code=422, content={"detail": "; ".join(problems)})
