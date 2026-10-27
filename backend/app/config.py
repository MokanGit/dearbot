from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal, Optional
import os


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App General
    APP_NAME: str = "DearBot"
    ENV: str = "development"
    DEBUG: bool = True
    BASE_URL: str = "http://localhost:3000"
    API_BASE_URL: str = "http://localhost:8000"

    # Candidate Profile
    CANDIDATE_NAME: str = "Sample Candidate"
    CANDIDATE_HEADLINE: str = "Technology and Product Leader"
    CANDIDATE_SUMMARY: str = (
        "A fictional sample profile for local development. Replace this text and the "
        "sample evidence documents before creating a real application."
    )
    CANDIDATE_CONTACT_LINE: str = "candidate@example.com | linkedin.com/in/example"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./backend/data/cv.db"

    # Google Workspace / Drive Ingestion
    GOOGLE_DRIVE_FOLDER_ID: str = ""
    GOOGLE_CV_TEMPLATE_DOC_ID: str = ""
    GOOGLE_CREDENTIALS_FILE: Optional[str] = "backend/credentials.json"
    GOOGLE_SERVICE_ACCOUNT_FILE: Optional[str] = "backend/service_account.json"
    LOCAL_SYNC_DIR: str = "backend/data/synced_docs"
    GENERATED_CVS_DIR: str = "backend/data/generated_cvs"

    # LLM providers. Model names are runtime configuration, not product identity.
    LLM_PROVIDER: str = "mock"  # "gemini", "openai", "mock"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.6-flash"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-5.4-mini"

    # Rate Limiting & Concurrency Quotas (supports shared Wi-Fi / presentation sessions)
    MAX_QUESTIONS_PER_MINUTE_PER_IP: int = 30
    MAX_QUESTIONS_PER_HOUR_PER_IP: int = 180
    MAX_VIEWS_PER_MINUTE_PER_IP: int = 180
    MAX_VIEWS_PER_HOUR_PER_IP: int = 1000
    MAX_QUESTIONS_PER_APPLICATION: int = 300

    # Admin authentication. Disabled is permitted only for development and tests.
    AUTH_MODE: Literal["disabled", "entra"] = "disabled"
    ENTRA_TENANT_ID: str = ""
    ENTRA_CLIENT_ID: str = ""
    ENTRA_AUDIENCE: str = ""
    ENTRA_REQUIRED_SCOPE: str = "admin.access"
    ADMIN_ALLOWED_OBJECT_IDS: list[str] = []

    # HTTP boundary configuration
    CORS_ORIGINS: str = "http://localhost:3000"
    ALLOWED_HOSTS: str = "localhost,127.0.0.1,testserver,test"
    TRUST_PROXY_HEADERS: bool = False

    # LangSmith Observability & LLM Tracing
    LANGSMITH_TRACING: bool = False
    LANGSMITH_ENDPOINT: str = "https://eu.api.smith.langchain.com"
    LANGSMITH_API_KEY: Optional[str] = None
    LANGSMITH_PROJECT: str = "dearbot"
    LANGSMITH_DASHBOARD_URL: Optional[str] = None

    @property
    def resolved_auth_mode(self) -> str:
        """Return the explicitly configured administrative authentication mode."""
        return self.AUTH_MODE

    @property
    def entra_audience(self) -> str:
        return self.ENTRA_AUDIENCE or f"api://{self.ENTRA_CLIENT_ID}"

    @property
    def cors_origins(self) -> list[str]:
        return [value.strip() for value in self.CORS_ORIGINS.split(",") if value.strip()]

    @property
    def allowed_hosts(self) -> list[str]:
        return [value.strip() for value in self.ALLOWED_HOSTS.split(",") if value.strip()]

    def validate_runtime_configuration(self) -> None:
        """Fail closed when production authentication is disabled or incomplete."""
        if self.ENV.lower() != "production":
            return
        if self.resolved_auth_mode == "disabled":
            raise RuntimeError("AUTH_MODE=disabled is not permitted in production")
        if self.resolved_auth_mode == "entra" and not all(
            (self.ENTRA_TENANT_ID, self.ENTRA_CLIENT_ID, self.entra_audience)
        ):
            raise RuntimeError("Entra authentication requires tenant, client, and audience configuration")


settings = Settings()

# Synchronize LangSmith environment variables for the tracer and client
if settings.LANGSMITH_TRACING:
    os.environ["LANGSMITH_TRACING"] = "true"
    if settings.LANGSMITH_ENDPOINT:
        os.environ["LANGSMITH_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
    if settings.LANGSMITH_API_KEY:
        os.environ["LANGSMITH_API_KEY"] = settings.LANGSMITH_API_KEY
    if settings.LANGSMITH_PROJECT:
        os.environ["LANGSMITH_PROJECT"] = settings.LANGSMITH_PROJECT
