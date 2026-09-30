from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
PAPERS_DIR = DATA_DIR / "papers"
ALLOWLIST_PATH = Path(__file__).resolve().parent / "data" / "reputable_journals.json"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        extra="ignore",
    )

    mosaiva_database_url: str = ""
    openai_api_key: str = ""
    openai_live_model: str = "gpt-live-1"
    openai_reasoning_model: str = "gpt-5.6-terra"
    mosaiva_research_fixture: str = ""
    mosaiva_mosaic_fixture: bool = False
    mosaiva_seed_hypotheses: bool = True
    mosaiva_seed_interventions: bool = True

    @property
    def database_url(self) -> str:
        if self.mosaiva_database_url:
            return self.mosaiva_database_url
        return f"sqlite:///{DATA_DIR / 'mosaiva.db'}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
