import os
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
ON_VERCEL = bool(os.environ.get("VERCEL"))
# Vercel's deployment bundle is read-only; only /tmp can be written at runtime.
PAPERS_DIR = Path("/tmp/mosaiva/papers") if ON_VERCEL else DATA_DIR / "papers"
ALLOWLIST_PATH = Path(__file__).resolve().parent / "data" / "reputable_journals.json"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        extra="ignore",
    )

    mosaiva_database_url: str = Field(
        default="",
        validation_alias=AliasChoices("MOSAIVA_DATABASE_URL", "DATABASE_URL", "POSTGRES_URL"),
    )
    openai_api_key: str = ""
    openai_live_model: str = "gpt-live-1"
    openai_reasoning_model: str = "gpt-5.6-terra"
    mosaiva_research_fixture: str = ""
    mosaiva_mosaic_fixture: bool = False
    mosaiva_seed_hypotheses: bool = True
    mosaiva_seed_interventions: bool = True
    mosaiva_seed_research: bool = True
    mosaiva_coach_plan_fixture: bool = False

    google_client_id: str = ""
    google_client_secret: str = ""
    mosaiva_allowed_emails: str = ""
    mosaiva_session_secret: str = ""
    mosaiva_public_url: str = ""
    mosaiva_auth_disabled: bool = False

    blob_read_write_token: str = ""
    blob_store_id: str = ""
    mosaiva_blob_access: str = "private"

    @property
    def database_url(self) -> str:
        url = self.mosaiva_database_url.strip()
        if not url:
            return f"sqlite:///{DATA_DIR / 'mosaiva.db'}"
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url

    @property
    def allowed_emails(self) -> set[str]:
        return {email.strip().lower() for email in self.mosaiva_allowed_emails.split(",") if email.strip()}

    @property
    def auth_required(self) -> bool:
        """Sign-in is always on for a deployment; locally it turns on once a Google client is set."""
        if ON_VERCEL:
            return True
        if self.mosaiva_auth_disabled:
            return False
        return bool(self.google_client_id)

    @property
    def blob_enabled(self) -> bool:
        return bool(self.blob_read_write_token or self.blob_store_id)


@lru_cache
def get_settings() -> Settings:
    return Settings()
