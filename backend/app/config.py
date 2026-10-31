"""Settings read from backend/.env (see .env.example)."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    clinic_name: str = "Demo Specialist Clinic"
    database_url: str = ""
    frontend_origin: str = "http://localhost:3000"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    @field_validator("database_url")
    @classmethod
    def default_database_url(cls, value: str) -> str:
        return value or f"sqlite:///{(BACKEND_DIR / 'clinic.db').as_posix()}"


settings = Settings()
